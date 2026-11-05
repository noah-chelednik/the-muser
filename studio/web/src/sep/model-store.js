/**
 * Browser model store.
 *
 *  - Models are downloaded in 16 MB HTTP Range chunks, streamed with progress.
 *    A dropped connection / failed chunk is retried (with back-off) and resumes
 *    from the exact byte it stopped at. A page reload or crash also resumes,
 *    because every received byte is persisted straight into OPFS.
 *  - Persistence is the Origin Private File System (OPFS) - far more reliable
 *    than the Cache API for 100 MB-1 GB files. We ask for persistent storage
 *    (navigator.storage.persist) and check the quota *before* downloading.
 *    Where OPFS isn't available the Cache API is used; if neither works the model
 *    simply isn't kept (it re-downloads next visit) and the UI says so.
 *  - Every file is verified against its pinned SHA-256 after download. A marker
 *    file records that verification passed, so reloads from OPFS are instant.
 *
 * Works in window and (for downloads) dedicated-worker scopes. OPFS writes use
 * FileSystemSyncAccessHandle, which only exists in workers - the worker does the
 * downloading; the window only inspects / clears.
 */
import { MODELS, MODEL_CACHE_NAME, MODEL_OPFS_DIR } from './models.js';

export const CHUNK_BYTES = 16 * 1024 * 1024;

export class StorageError extends Error {
  constructor(msg) { super(msg); this.name = 'StorageError'; }
}

export const fmtBytes = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(2)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(0)} MB` : `${Math.max(0, Math.round(n / 1e3))} KB`);

const inWorker = typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope;

export async function sha256Hex(bytes) {
  const d = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

const sleep = (ms, signal) => new Promise((res, rej) => {
  const t = setTimeout(res, ms);
  signal?.addEventListener('abort', () => { clearTimeout(t); rej(new DOMException('Aborted', 'AbortError')); }, { once: true });
});

// ---------------------------------------------------------------- OPFS ----

async function opfsDir(create = true) {
  try {
    if (!navigator.storage?.getDirectory) return null;
    const root = await navigator.storage.getDirectory();
    return await root.getDirectoryHandle(MODEL_OPFS_DIR, { create });
  } catch { return null; }
}

const fileKey = (model, file) => `${model.id}__${(file.sha256 || 'nosha').slice(0, 12)}__${file.name}`;

async function getHandle(dir, name, create) {
  try { return await dir.getFileHandle(name, { create }); } catch (e) { if (e?.name === 'NotFoundError' || e?.name === 'TypeMismatchError') return null; throw e; }
}
async function sizeOf(dir, name) {
  const h = await getHandle(dir, name, false);
  return h ? (await h.getFile()).size : -1;
}
async function removeIf(dir, name) {
  try { await dir.removeEntry(name); } catch (e) { if (e?.name !== 'NotFoundError') throw e; }
}

async function writeMarker(dir, name, text) {
  const fh = await dir.getFileHandle(name, { create: true });
  const data = new TextEncoder().encode(text);
  if (typeof fh.createSyncAccessHandle === 'function' && inWorker) {
    const h = await fh.createSyncAccessHandle();
    try { h.truncate(0); h.write(data, { at: 0 }); h.flush(); } finally { h.close(); }
  } else {
    const w = await fh.createWritable(); await w.write(data); await w.close();
  }
}

/** Sequential writer on top of a FileSystemSyncAccessHandle (workers only). */
async function openPartWriter(dir, name, startAt) {
  const fh = await dir.getFileHandle(name, { create: true });
  if (typeof fh.createSyncAccessHandle !== 'function' || !inWorker) return null;
  const h = await fh.createSyncAccessHandle();
  h.truncate(startAt);
  let pos = startAt;
  return {
    write(u8) {
      let w = 0;
      while (w < u8.length) {
        const n = h.write(u8.subarray(w), { at: pos + w });
        if (!n) throw new StorageError('The browser refused to write to its file storage');
        w += n;
      }
      pos += u8.length;
    },
    flush() { h.flush(); },
    close() { try { h.flush(); } catch { /* ignore */ } try { h.close(); } catch { /* ignore */ } },
  };
}

// --------------------------------------------------------- public status ----

/** { usage, quota, persisted } - any field may be null when the browser can't say. */
export async function storageInfo() {
  const out = { usage: null, quota: null, persisted: null, opfs: !!navigator.storage?.getDirectory };
  try { const e = await navigator.storage.estimate(); out.usage = e.usage ?? null; out.quota = e.quota ?? null; } catch { /* ignore */ }
  try { out.persisted = await navigator.storage.persisted(); } catch { /* ignore */ }
  return out;
}

export async function requestPersistence() {
  try {
    if (await navigator.storage.persisted()) return true;
    return await navigator.storage.persist();
  } catch { return false; }
}

async function openCache() {
  if (typeof caches === 'undefined') return null;
  try { return await caches.open(MODEL_CACHE_NAME); } catch { return null; }
}

async function opfsComplete(dir, key, file) {
  if ((await sizeOf(dir, key + '.ok')) < 0) return false;
  return (await sizeOf(dir, key + '.part')) === file.bytes;
}

/** Is every file of this model fully downloaded and verified in the browser's storage? */
export async function isModelCached(model) {
  const dir = await opfsDir(false);
  let allOpfs = !!dir;
  if (dir) for (const f of model.files) if (!(await opfsComplete(dir, fileKey(model, f), f))) { allOpfs = false; break; }
  if (allOpfs) return true;
  const cache = await openCache();
  if (!cache) return false;
  for (const f of model.files) if (!(await cache.match(f.url))) return false;
  return true;
}

/** Bytes of an unfinished (resumable) download for this model, 0 if none. */
export async function partialModelBytes(model) {
  const dir = await opfsDir(false);
  if (!dir) return 0;
  let n = 0;
  for (const f of model.files) {
    const key = fileKey(model, f);
    if ((await sizeOf(dir, key + '.ok')) >= 0) continue;
    const s = await sizeOf(dir, key + '.part');
    if (s > 0 && s < f.bytes) n += s;
  }
  return n;
}

export async function cachedModelIds() {
  const ids = [];
  for (const m of Object.values(MODELS)) if (await isModelCached(m)) ids.push(m.id);
  return ids;
}

/** Delete downloaded models (one id, or all) incl. unfinished downloads. Returns names that could not be removed. */
export async function clearModelCache(modelId) {
  const failed = [];
  const models = modelId ? [MODELS[modelId]] : Object.values(MODELS);
  const dir = await opfsDir(false);
  if (dir) {
    for (const m of models) for (const f of m.files) {
      const key = fileKey(m, f);
      for (const n of [key + '.ok', key + '.part']) {
        try { await removeIf(dir, n); } catch { failed.push(n); }
      }
    }
    if (!modelId) { // also sweep stale entries from older revisions
      try { for await (const name of dir.keys()) { try { await dir.removeEntry(name); } catch { failed.push(name); } } } catch { /* ignore */ }
    }
  }
  if (typeof caches !== 'undefined') {
    try {
      if (!modelId) await caches.delete(MODEL_CACHE_NAME);
      else { const c = await openCache(); for (const f of MODELS[modelId].files) await c?.delete(f.url); }
    } catch { /* ignore */ }
  }
  return failed;
}

// ------------------------------------------------------------- download ----

/**
 * Fetch bytes [state.pos, bytes) in Range chunks into `buf`, calling
 * `persist(u8)` for each piece. Resumes after failures from state.pos.
 */
async function downloadInto(file, buf, state, { persist, onBytes, signal, retries, chunkBytes }) {
  let failures = 0;
  while (state.pos < file.bytes) {
    const start = state.pos;
    const end = Math.min(start + chunkBytes, file.bytes) - 1;
    try {
      const res = await fetch(file.url, { mode: 'cors', credentials: 'omit', signal, headers: { Range: `bytes=${start}-${end}` } });
      if (res.status !== 206 && res.status !== 200) throw new Error(`HTTP ${res.status}`);
      // A server that ignores Range sends the whole file (200): skip what we already have.
      let skip = res.status === 200 ? start : 0;
      const reader = res.body.getReader();
      const want = end - start + 1;
      let got = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        let v = value;
        if (skip > 0) {
          if (v.length <= skip) { skip -= v.length; continue; }
          v = v.subarray(skip); skip = 0;
        }
        if (got + v.length > want) {
          if (res.status === 200) { try { await reader.cancel(); } catch { /* ignore */ } v = v.subarray(0, want - got); } else throw new Error('server sent more than requested');
        }
        buf.set(v, state.pos);
        persist?.(v);
        state.pos += v.length;
        got += v.length;
        failures = 0;
        onBytes(v.length);
        if (got >= want) { if (res.status === 200) { try { await reader.cancel(); } catch { /* ignore */ } } break; }
      }
      if (got !== want) throw new Error(`short read (${got}/${want} bytes)`);
    } catch (e) {
      if (e?.name === 'AbortError' || signal?.aborted) throw e;
      if (e instanceof StorageError) throw e;
      failures++;
      if (failures > retries) throw new Error(`Download of ${file.name} failed after ${retries + 1} attempts at ${fmtBytes(state.pos)}/${fmtBytes(file.bytes)}: ${e?.message || e}. Your progress is saved - press the button again to resume.`);
      await sleep(Math.min(8000, 1000 * 2 ** (failures - 1)), signal);
    }
  }
}

/**
 * Returns { [file.name]: Uint8Array } for the model, downloading what is missing.
 * onProgress({ loaded, total, fromCache, file, resumedFrom?, verifying?, notice? })
 */
export async function getModelFiles(model, onProgress, { signal, retries = 4, chunkBytes = CHUNK_BYTES } = {}) {
  const dir = await opfsDir(true);
  const cache = await openCache();
  const total = model.files.reduce((s, f) => s + f.bytes, 0);
  let loaded = 0;
  let allFromCache = true;
  let persistChecked = false;
  const out = {};

  for (const file of model.files) {
    const key = fileKey(model, file);
    let bytes = null;

    // 1) OPFS (verified earlier -> marker present)
    if (dir && await opfsComplete(dir, key, file)) {
      try {
        const f = await (await dir.getFileHandle(key + '.part')).getFile();
        bytes = new Uint8Array(await f.arrayBuffer());
      } catch (e) { onProgress?.({ loaded, total, notice: `Could not read the saved model (${e?.message || e}); downloading again.` }); }
      if (bytes && bytes.length !== file.bytes) bytes = null;
    }
    // 2) legacy / fallback: Cache API
    if (!bytes && cache) {
      const hit = await cache.match(file.url);
      if (hit) {
        const buf = new Uint8Array(await hit.arrayBuffer());
        if (buf.length === file.bytes) bytes = buf; else await cache.delete(file.url);
      }
    }
    if (bytes) {
      loaded += file.bytes;
      onProgress?.({ loaded, total, fromCache: allFromCache, file: file.name });
      out[file.name] = bytes;
      continue;
    }

    // 3) download (resuming a partial OPFS file if there is one)
    allFromCache = false;
    let resume = 0;
    if (dir) {
      const s = await sizeOf(dir, key + '.part');
      const hasMarker = (await sizeOf(dir, key + '.ok')) >= 0;
      if (hasMarker || s > file.bytes || s < 0) { await removeIf(dir, key + '.ok'); await removeIf(dir, key + '.part').catch(() => {}); }
      else resume = s;
      if (resume === file.bytes) { /* complete but unverified: verified below */ }
    }

    // storage budget & persistence
    let canPersist = !!dir;
    const est = await storageInfo();
    if (!persistChecked) { persistChecked = true; if (dir) requestPersistence(); }
    const need = file.bytes - resume;
    if (est.quota != null && est.usage != null && canPersist && est.quota - est.usage < need * 1.02) {
      canPersist = false;
      onProgress?.({ loaded, total, notice: `Not enough free browser storage to keep ${file.name} (needs ${fmtBytes(need)}, ${fmtBytes(Math.max(0, est.quota - est.usage))} free). It will download for this session only and re-download next time. Free some space or use the "Clear downloaded models" button, then retry.`, storageShort: true });
      resume = 0; // can't trust the partial either; keep memory-only
    }

    let buf;
    try { buf = new Uint8Array(file.bytes); } catch {
      throw new StorageError(`Not enough memory to load ${file.name} (${fmtBytes(file.bytes)}). Close other tabs or choose the smaller Mini model.`);
    }
    let writer = null;
    if (canPersist) {
      try {
        if (resume > 0) {
          const f = await (await dir.getFileHandle(key + '.part')).getFile();
          buf.set(new Uint8Array(await f.slice(0, resume).arrayBuffer()), 0);
          onProgress?.({ loaded: loaded + resume, total, fromCache: false, file: file.name, resumedFrom: resume });
        }
        writer = await openPartWriter(dir, key + '.part', resume);
        if (!writer) { canPersist = false; resume = 0; }
      } catch (e) {
        onProgress?.({ loaded, total, notice: `Browser storage is unavailable (${e?.message || e}); downloading for this session only.` });
        canPersist = false; resume = 0; writer = null;
      }
    }

    const state = { pos: resume };
    const base = loaded;
    let quotaHit = false;
    const persist = writer ? (u8) => {
      if (!writer || quotaHit) return;
      try { writer.write(u8); } catch (e) {
        quotaHit = true;
        try { writer.close(); } catch { /* ignore */ }
        writer = null;
        onProgress?.({ loaded: base + state.pos, total, notice: `The browser ran out of storage while saving ${file.name} (${e?.name || 'error'}). Continuing without saving; it will re-download next time.`, storageShort: true });
      }
    } : null;

    try {
      await downloadInto(file, buf, state, {
        persist, signal, retries, chunkBytes,
        onBytes: () => onProgress?.({ loaded: base + state.pos, total, fromCache: false, file: file.name }),
      });
    } finally {
      writer?.close();
    }
    loaded = base + file.bytes;

    if (file.sha256) {
      onProgress?.({ loaded, total, fromCache: false, file: file.name, verifying: true });
      const hex = await sha256Hex(buf);
      if (hex !== file.sha256) {
        if (dir) { await removeIf(dir, key + '.part').catch(() => {}); await removeIf(dir, key + '.ok').catch(() => {}); }
        throw new Error(`Integrity check failed for ${file.name} (SHA-256 mismatch). The partial download was discarded - please retry.`);
      }
    }
    if (dir && canPersist && !quotaHit) {
      try { await writeMarker(dir, key + '.ok', file.sha256 || 'ok'); } catch (e) { console.warn('[roformer-web] could not write verification marker', e); }
    } else if (cache && !dir) {
      try {
        await cache.put(file.url, new Response(buf, { headers: { 'content-type': 'application/octet-stream', 'content-length': String(buf.length) } }));
      } catch (e) { console.warn('[roformer-web] could not cache model file (storage quota?):', e); }
    }
    out[file.name] = buf;
  }
  return out;
}
