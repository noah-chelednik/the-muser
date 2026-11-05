/**
 * Where finished stem audio goes while a long track is processed.
 *
 *  - MemorySink: full-length Float32 planes in RAM (Node tests, small tracks, fallback).
 *  - OpfsSink:   float32 planes in OPFS files (workers only), so a 10 minute
 *                6-stem job holds only a couple of chunks in RAM instead of
 *                stems x 2 x N floats.
 *
 * Interface: write(name, channel, offset, Float32Array), read(name, channel, start, len) -> Float32Array,
 * names(), dispose(). Layout in OPFS: <stem>.f32 = left plane then right plane.
 */

export class MemorySink {
  constructor(N) { this.kind = 'memory'; this.N = N; this.data = {}; }
  write(name, ch, offset, f32) {
    (this.data[name] ||= [new Float32Array(this.N), new Float32Array(this.N)])[ch].set(f32, offset);
  }
  names() { return Object.keys(this.data); }
  read(name, ch, start, len) { return this.data[name][ch].subarray(start, start + len); }
  async dispose() { this.data = {}; }
}

const DIR = 'roformer-web-stems-v1';

export class OpfsSink {
  static supported() {
    return typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope
      && !!navigator.storage?.getDirectory && typeof FileSystemFileHandle !== 'undefined'
      && typeof FileSystemFileHandle.prototype.createSyncAccessHandle === 'function';
  }

  /** Remove scratch files left behind by a crashed/closed tab. */
  static async sweep() {
    try {
      const root = await navigator.storage.getDirectory();
      await root.removeEntry(DIR, { recursive: true });
    } catch { /* nothing to sweep, or still in use by another tab */ }
  }

  static async create(N) {
    const root = await navigator.storage.getDirectory();
    const dir = await root.getDirectoryHandle(DIR, { create: true });
    const s = new OpfsSink(N, dir);
    s.id = Math.random().toString(36).slice(2, 8);
    return s;
  }

  constructor(N, dir) { this.kind = 'opfs'; this.N = N; this.dir = dir; this.handles = new Map(); this.files = new Map(); this.id = ''; }

  async #handle(name) {
    let h = this.handles.get(name);
    if (!h) {
      const file = `${this.id}_${name}.f32`;
      const fh = await this.dir.getFileHandle(file, { create: true });
      h = await fh.createSyncAccessHandle();
      h.truncate(this.N * 2 * 4);
      this.handles.set(name, h);
      this.files.set(name, file);
    }
    return h;
  }

  async write(name, ch, offset, f32) {
    const h = await this.#handle(name);
    const u8 = new Uint8Array(f32.buffer, f32.byteOffset, f32.byteLength);
    let w = 0;
    while (w < u8.length) {
      const n = h.write(u8.subarray(w), { at: (ch * this.N + offset) * 4 + w });
      if (!n) throw new Error('Browser storage refused a write (out of space?)');
      w += n;
    }
  }

  names() { return [...this.handles.keys()]; }

  read(name, ch, start, len) {
    const h = this.handles.get(name);
    const out = new Float32Array(len);
    h.read(new Uint8Array(out.buffer), { at: (ch * this.N + start) * 4 });
    return out;
  }

  async dispose() {
    for (const h of this.handles.values()) { try { h.flush(); h.close(); } catch { /* ignore */ } }
    this.handles.clear();
    for (const f of this.files.values()) { try { await this.dir.removeEntry(f); } catch { /* ignore */ } }
    this.files.clear();
  }
}

/**
 * Transparent wrapper that lets the UI watch separation as it happens, without
 * keeping the full result in RAM. Every flushed region is reported through
 * `emit` as:
 *   { stem, peaks: Float32Array, peakStart }                 // loudness per 0.1 s block (whole track)
 *   { stem, preview: Float32Array, previewStart, previewRate } // mono half-rate audio, first `previewSeconds` only
 * Both are small (a few KB per chunk / a few MB in total) and are sent for the
 * first stem channel pair only once both channels of a region have been written.
 */
export const PEAK_BLOCK = 4410; // 0.1 s at 44.1 kHz
export class TapSink {
  constructor(inner, emit, { sampleRate = 44100, previewSeconds = 45 } = {}) {
    this.inner = inner; this.emit = emit; this.sr = sampleRate;
    this.blocks = Math.ceil(inner.N / PEAK_BLOCK);
    this.maxPrev = Math.min(Math.ceil(inner.N / 2), Math.floor((sampleRate / 2) * previewSeconds));
    this.state = new Map(); // stem -> { peaks, prev, lastCh0: [start,len] }
  }
  get kind() { return this.inner.kind; }
  get N() { return this.inner.N; }
  get data() { return this.inner.data; }
  names() { return this.inner.names(); }
  read(...a) { return this.inner.read(...a); }
  dispose() { return this.inner.dispose(); }

  async write(name, ch, offset, f32) {
    await this.inner.write(name, ch, offset, f32);
    let st = this.state.get(name);
    if (!st) { st = { peaks: new Float32Array(this.blocks), prev: new Float32Array(this.maxPrev) }; this.state.set(name, st); }
    // peaks (max over both channels)
    for (let i = 0; i < f32.length; i++) {
      const b = ((offset + i) / PEAK_BLOCK) | 0;
      const v = f32[i] < 0 ? -f32[i] : f32[i];
      if (v > st.peaks[b]) st.peaks[b] = v;
    }
    // half-rate mono preview, accumulated as 0.25*x per frame -> avg of L,R and of two neighbours
    for (let i = 0; i < f32.length; i++) {
      const p = (offset + i) >> 1;
      if (p >= this.maxPrev) break;
      if (ch === 0 && ((offset + i) & 1) === 0) st.prev[p] = 0; // fresh pair
      st.prev[p] += 0.25 * f32[i];
    }
    if (ch === 1) {
      const b0 = (offset / PEAK_BLOCK) | 0, b1 = (((offset + f32.length - 1) / PEAK_BLOCK) | 0) + 1;
      const msg = { stem: name, peakStart: b0, peaks: st.peaks.slice(b0, b1) };
      const p0 = offset >> 1;
      const p1 = Math.min(this.maxPrev, ((offset + f32.length - 1) >> 1) + 1);
      if (p0 < this.maxPrev) { msg.preview = st.prev.slice(p0, p1); msg.previewStart = p0; msg.previewRate = this.sr / 2; }
      this.emit(msg);
    }
  }
}
