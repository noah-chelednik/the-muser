/** WAV (RIFF) encoding for planar stereo Float32 audio, whole-buffer or streamed in pieces. */

const bytesPer = (format) => (format === 'pcm16' ? 2 : format === 'pcm24' ? 3 : 4);

/** 44-byte RIFF/WAVE header for `frames` frames of `nCh` channels. */
export function wavHeader(frames, nCh, sampleRate, format = 'pcm16') {
  const bytes = bytesPer(format);
  const dataLen = frames * nCh * bytes;
  const buf = new ArrayBuffer(44);
  const dv = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); dv.setUint32(4, 36 + dataLen, true); str(8, 'WAVE');
  str(12, 'fmt '); dv.setUint32(16, 16, true);
  dv.setUint16(20, format === 'float32' ? 3 : 1, true);
  dv.setUint16(22, nCh, true);
  dv.setUint32(24, sampleRate, true);
  dv.setUint32(28, sampleRate * nCh * bytes, true);
  dv.setUint16(32, nCh * bytes, true);
  dv.setUint16(34, bytes * 8, true);
  str(36, 'data'); dv.setUint32(40, dataLen, true);
  return new Uint8Array(buf);
}

/** Interleave + quantise `channels` (equal-length planar Float32Arrays) to little-endian PCM bytes. */
export function encodeFrames(channels, format = 'pcm16') {
  const nCh = channels.length;
  const n = channels[0].length;
  const bytes = bytesPer(format);
  const out = new Uint8Array(n * nCh * bytes);
  const dv = new DataView(out.buffer);
  let o = 0;
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < nCh; c++) {
      let x = channels[c][i];
      if (format === 'float32') { dv.setFloat32(o, x, true); o += 4; continue; }
      x = x > 1 ? 1 : x < -1 ? -1 : x;
      if (!(x === x)) x = 0; // NaN -> silence
      if (format === 'pcm16') {
        dv.setInt16(o, Math.round(x < 0 ? x * 0x8000 : x * 0x7fff), true); o += 2;
      } else {
        const v = Math.round(x < 0 ? x * 0x800000 : x * 0x7fffff);
        out[o] = v & 255; out[o + 1] = (v >> 8) & 255; out[o + 2] = (v >> 16) & 255; o += 3;
      }
    }
  }
  return out;
}

/**
 * @param {Float32Array[]} channels planar channel data (equal length)
 * @param {number} sampleRate
 * @param {'pcm16'|'pcm24'|'float32'} format
 * @returns {ArrayBuffer}
 */
export function encodeWav(channels, sampleRate, format = 'pcm16') {
  const head = wavHeader(channels[0].length, channels.length, sampleRate, format);
  const body = encodeFrames(channels, format);
  const out = new Uint8Array(head.length + body.length);
  out.set(head, 0); out.set(body, head.length);
  return out.buffer;
}

const PIECE = 1 << 20; // frames per piece (~4-8 MB of PCM)

/** Yield the WAV file for one stem of a sink as a sequence of Uint8Array pieces (header first). */
export function* wavPieces(sink, name, N, sampleRate, format) {
  yield wavHeader(N, 2, sampleRate, format);
  for (let s = 0; s < N; s += PIECE) {
    const len = Math.min(PIECE, N - s);
    yield encodeFrames([sink.read(name, 0, s, len), sink.read(name, 1, s, len)], format);
  }
}

/** Accumulates pieces into a Blob without ever holding the whole file as one ArrayBuffer. */
export class BlobBuilder {
  constructor(type, flushBytes = 48 * 1024 * 1024) { this.type = type; this.parts = []; this.pending = 0; this.flushBytes = flushBytes; this.blob = null; }
  push(u8) {
    this.parts.push(u8); this.pending += u8.length;
    if (this.pending >= this.flushBytes) this.#flush();
  }
  #flush() {
    this.blob = new Blob(this.blob ? [this.blob, ...this.parts] : this.parts, { type: this.type });
    this.parts = []; this.pending = 0;
  }
  finish() { this.#flush(); return this.blob; }
}

export function wavBlob(sink, name, N, sampleRate, format) {
  const b = new BlobBuilder('audio/wav');
  for (const p of wavPieces(sink, name, N, sampleRate, format)) b.push(p);
  return b.finish();
}

/**
 * Store-only ZIP of every stem's WAV. `fflate` is the vendored module namespace
 * ({ Zip, ZipPassThrough }); WAV doesn't compress, so no deflate time is wasted.
 */
export function zipBlob(fflate, sink, names, N, sampleRate, format, base = 'stems') {
  const b = new BlobBuilder('application/zip');
  const zip = new fflate.Zip((err, chunk) => { if (err) throw err; b.push(chunk); });
  const safe = base.replace(/[\\/:*?"<>|]+/g, '_').slice(0, 120) || 'stems';
  for (const name of names) {
    const f = new fflate.ZipPassThrough(`${safe} - ${name}.wav`);
    zip.add(f);
    const it = wavPieces(sink, name, N, sampleRate, format);
    let cur = it.next();
    while (!cur.done) {
      const nxt = it.next();
      f.push(cur.value, nxt.done); // final=true on the last piece
      cur = nxt;
    }
  }
  zip.end();
  return b.finish();
}

/**
 * Tolerant WAV parser used as a decode fallback (RIFF/RF64; PCM 8/16/24/32-bit, float 32/64,
 * WAVE_FORMAT_EXTENSIBLE). Returns planar Float32 channels at the file's own sample rate.
 */
export function parseWav(arrayBuffer) {
  const dv = new DataView(arrayBuffer);
  const tag = (o) => String.fromCharCode(dv.getUint8(o), dv.getUint8(o + 1), dv.getUint8(o + 2), dv.getUint8(o + 3));
  if (arrayBuffer.byteLength < 44 || (tag(0) !== 'RIFF' && tag(0) !== 'RF64') || tag(8) !== 'WAVE') throw new Error('not a WAV file');
  let o = 12, fmt = null, data = null;
  while (o + 8 <= arrayBuffer.byteLength) {
    const id = tag(o);
    let size = dv.getUint32(o + 4, true);
    const body = o + 8;
    if (id === 'fmt ') {
      let format = dv.getUint16(body, true);
      const channels = dv.getUint16(body + 2, true);
      const sampleRate = dv.getUint32(body + 4, true);
      const bits = dv.getUint16(body + 14, true);
      if (format === 0xfffe && size >= 26) format = dv.getUint16(body + 24, true); // extensible: sub-format GUID starts with the real tag
      fmt = { format, channels, sampleRate, bits };
    } else if (id === 'data') {
      if (size === 0xffffffff || body + size > arrayBuffer.byteLength) size = arrayBuffer.byteLength - body; // streamed / truncated / RF64
      data = { body, size };
      break;
    }
    o = body + size + (size & 1);
  }
  if (!fmt || !data) throw new Error('WAV has no fmt/data chunk');
  const { format, channels, sampleRate, bits } = fmt;
  if (!channels || !sampleRate) throw new Error('invalid WAV header');
  const isFloat = format === 3;
  if (!(format === 1 || isFloat)) throw new Error(`unsupported WAV encoding (${format})`);
  if (!(isFloat ? bits === 32 || bits === 64 : [8, 16, 24, 32].includes(bits))) throw new Error(`unsupported WAV bit depth (${bits})`);
  const bps = bits / 8;
  const frames = Math.floor(data.size / (bps * channels));
  const out = Array.from({ length: channels }, () => new Float32Array(frames));
  let p = data.body;
  for (let i = 0; i < frames; i++) {
    for (let c = 0; c < channels; c++, p += bps) {
      let v;
      if (isFloat) v = bits === 32 ? dv.getFloat32(p, true) : dv.getFloat64(p, true);
      else if (bits === 16) v = dv.getInt16(p, true) / 32768;
      else if (bits === 8) v = (dv.getUint8(p) - 128) / 128;
      else if (bits === 24) { let x = dv.getUint8(p) | (dv.getUint8(p + 1) << 8) | (dv.getUint8(p + 2) << 16); if (x & 0x800000) x |= ~0xffffff; v = x / 8388608; }
      else v = dv.getInt32(p, true) / 2147483648;
      out[c][i] = v;
    }
  }
  return { sampleRate, channels: out, frames };
}
