// Browser-side DSP for the in-browser demo: biquads, dynamics, reverb, loudness, WAV.
// Everything here is plain TypeScript so it can run (and be tested) outside a browser.

export type Audio = { sr: number; ch: [Float32Array, Float32Array] }

export const db2lin = (db: number) => Math.pow(10, db / 20)
export const lin2db = (x: number) => 20 * Math.log10(Math.max(x, 1e-12))
const clamp = (x: number, a: number, b: number) => Math.min(Math.max(x, a), b)

export function silence(sr: number, n: number): Audio {
  return { sr, ch: [new Float32Array(n), new Float32Array(n)] }
}
export function clone(a: Audio): Audio {
  return { sr: a.sr, ch: [a.ch[0].slice(), a.ch[1].slice()] }
}
export const length = (a: Audio) => a.ch[0].length
export const seconds = (a: Audio) => a.ch[0].length / a.sr

export function sum(list: Audio[]): Audio {
  const n = Math.max(...list.map(length))
  const out = silence(list[0].sr, n)
  for (const a of list) for (let c = 0; c < 2; c++) {
    const o = out.ch[c], s = a.ch[c]
    for (let i = 0; i < s.length; i++) o[i] += s[i]
  }
  return out
}

export function peak(a: Audio): number {
  let p = 0
  for (const ch of a.ch) for (let i = 0; i < ch.length; i++) { const v = Math.abs(ch[i]); if (v > p) p = v }
  return p
}
export function scale(a: Audio, g: number): Audio {
  for (const ch of a.ch) for (let i = 0; i < ch.length; i++) ch[i] *= g
  return a
}
export function pan(a: Audio, p: number): Audio {
  if (Math.abs(p) < 1e-3) return a
  const ang = ((p + 1) * Math.PI) / 4
  const l = Math.cos(ang) * Math.SQRT2, r = Math.sin(ang) * Math.SQRT2
  for (let i = 0; i < a.ch[0].length; i++) { a.ch[0][i] *= l; a.ch[1][i] *= r }
  return a
}

// ---------------------------------------------------------------- biquad (RBJ cookbook)
type Coef = { b0: number; b1: number; b2: number; a1: number; a2: number }
function norm(b0: number, b1: number, b2: number, a0: number, a1: number, a2: number): Coef {
  return { b0: b0 / a0, b1: b1 / a0, b2: b2 / a0, a1: a1 / a0, a2: a2 / a0 }
}
export type BiquadKind = 'lowpass' | 'highpass' | 'peak' | 'lowshelf' | 'highshelf' | 'bandpass'
export function biquadCoef(kind: BiquadKind, sr: number, f: number, q = 0.7071, gainDb = 0): Coef {
  f = clamp(f, 10, sr * 0.49)
  q = Math.max(q, 0.05)
  const w = (2 * Math.PI * f) / sr, cw = Math.cos(w), sw = Math.sin(w)
  const al = sw / (2 * q)
  const A = Math.pow(10, gainDb / 40)
  switch (kind) {
    case 'lowpass': return norm((1 - cw) / 2, 1 - cw, (1 - cw) / 2, 1 + al, -2 * cw, 1 - al)
    case 'highpass': return norm((1 + cw) / 2, -(1 + cw), (1 + cw) / 2, 1 + al, -2 * cw, 1 - al)
    case 'bandpass': return norm(al, 0, -al, 1 + al, -2 * cw, 1 - al)
    case 'peak': return norm(1 + al * A, -2 * cw, 1 - al * A, 1 + al / A, -2 * cw, 1 - al / A)
    case 'lowshelf': {
      const s = 2 * Math.sqrt(A) * al
      return norm(A * ((A + 1) - (A - 1) * cw + s), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - s), (A + 1) + (A - 1) * cw + s, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - s)
    }
    case 'highshelf': {
      const s = 2 * Math.sqrt(A) * al
      return norm(A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s), (A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s)
    }
  }
}
export function biquadInPlace(x: Float32Array, c: Coef): void {
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0
  for (let i = 0; i < x.length; i++) {
    const xi = x[i]
    const y = c.b0 * xi + c.b1 * x1 + c.b2 * x2 - c.a1 * y1 - c.a2 * y2
    x2 = x1; x1 = xi; y2 = y1; y1 = y
    x[i] = y
  }
}
export function biquad(a: Audio, kind: BiquadKind, f: number, q?: number, gainDb?: number): Audio {
  const c = biquadCoef(kind, a.sr, f, q, gainDb)
  for (const ch of a.ch) biquadInPlace(ch, c)
  return a
}

// ---------------------------------------------------------------- dynamics
export function compress(a: Audio, thr: number, ratio: number, atkMs: number, relMs: number, makeupDb: number): Audio {
  const sr = a.sr, n = length(a)
  const atk = Math.exp(-1 / (Math.max(atkMs, 0.05) * 0.001 * sr)), rel = Math.exp(-1 / (Math.max(relMs, 1) * 0.001 * sr))
  const knee = 4, mk = db2lin(makeupDb)
  let env = 0
  for (let i = 0; i < n; i++) {
    const lvl = lin2db(Math.max(Math.abs(a.ch[0][i]), Math.abs(a.ch[1][i])))
    const over = lvl - thr
    let gr = 0
    if (2 * over < -knee) gr = 0
    else if (2 * Math.abs(over) <= knee) gr = (1 - 1 / ratio) * Math.pow(over + knee / 2, 2) / (2 * knee)
    else gr = (1 - 1 / ratio) * over
    const k = gr > env ? atk : rel
    env = k * env + (1 - k) * gr
    const g = db2lin(-env) * mk
    a.ch[0][i] *= g; a.ch[1][i] *= g
  }
  return a
}
export function gate(a: Audio, thrDb: number, ratio: number, atkMs: number, relMs: number): Audio {
  const sr = a.sr, n = length(a)
  const atk = Math.exp(-1 / (Math.max(atkMs, 0.05) * 0.001 * sr)), rel = Math.exp(-1 / (Math.max(relMs, 1) * 0.001 * sr))
  let g = 1
  for (let i = 0; i < n; i++) {
    const lvl = lin2db(Math.max(Math.abs(a.ch[0][i]), Math.abs(a.ch[1][i])))
    const target = lvl >= thrDb ? 1 : db2lin(-(thrDb - lvl) * (1 - 1 / ratio))
    const k = target > g ? atk : rel
    g = k * g + (1 - k) * target
    a.ch[0][i] *= g; a.ch[1][i] *= g
  }
  return a
}
/** Dynamic high-band cut: a compressor that only acts on the band around `freq`. */
export function deess(a: Audio, freq: number, thr: number, ratio: number): Audio {
  const out = clone(a)
  const band = clone(a)
  biquad(band, 'bandpass', freq, 1.2)
  const sr = a.sr, atk = Math.exp(-1 / (0.001 * sr)), rel = Math.exp(-1 / (0.06 * sr))
  let env = 0
  for (let i = 0; i < length(a); i++) {
    const lvl = lin2db(Math.max(Math.abs(band.ch[0][i]), Math.abs(band.ch[1][i])) * 2)
    const gr = lvl > thr ? (lvl - thr) * (1 - 1 / ratio) : 0
    const k = gr > env ? atk : rel
    env = k * env + (1 - k) * gr
    const cut = db2lin(-env) - 1 // subtract only the band
    out.ch[0][i] += band.ch[0][i] * cut
    out.ch[1][i] += band.ch[1][i] * cut
  }
  return out
}

/** Look-ahead peak limiter. Never exceeds `ceilingDb` by sample value. */
export function limit(a: Audio, ceilingDb: number, releaseMs = 80, lookMs = 3): Audio {
  const n = length(a), c = db2lin(ceilingDb)
  const need = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const p = Math.max(Math.abs(a.ch[0][i]), Math.abs(a.ch[1][i]))
    need[i] = p > c ? c / p : 1
  }
  const look = Math.max(1, Math.round(lookMs * 0.001 * a.sr))
  const up = 1 / look
  const ga = need
  for (let i = n - 2; i >= 0; i--) ga[i] = Math.min(ga[i], ga[i + 1] + up)
  const rel = 1 / (Math.max(releaseMs, 1) * 0.001 * a.sr)
  let g = 1
  for (let i = 0; i < n; i++) {
    g = Math.min(ga[i], g + rel)
    a.ch[0][i] *= g; a.ch[1][i] *= g
  }
  return a
}

// ---------------------------------------------------------------- colour
export function saturate(a: Audio, driveDb: number, mix: number): Audio {
  const d = db2lin(driveDb), comp = 1 / Math.tanh(Math.max(d, 1))
  for (const ch of a.ch) for (let i = 0; i < ch.length; i++) {
    const w = Math.tanh(ch[i] * d) * comp
    ch[i] = ch[i] * (1 - mix) + w * mix
  }
  return a
}
export function bitcrush(a: Audio, bits: number, mix: number): Audio {
  const q = Math.pow(2, Math.round(bits) - 1)
  for (const ch of a.ch) for (let i = 0; i < ch.length; i++) {
    ch[i] = ch[i] * (1 - mix) + (Math.round(ch[i] * q) / q) * mix
  }
  return a
}

// ---------------------------------------------------------------- modulation / space
export function delayFx(a: Audio, ms: number, fb: number, mix: number): Audio {
  const d = Math.max(1, Math.round((ms * 0.001) * a.sr))
  for (const ch of a.ch) {
    const buf = new Float32Array(d)
    let w = 0
    for (let i = 0; i < ch.length; i++) {
      const dry = ch[i], wet = buf[w]
      buf[w] = dry + wet * fb
      w = (w + 1) % d
      ch[i] = dry * (1 - mix * 0.5) + wet * mix
    }
  }
  return a
}
export function chorus(a: Audio, rate: number, depth: number, centreMs: number, fb: number, mix: number): Audio {
  const sr = a.sr, maxD = Math.ceil(sr * 0.06)
  a.ch.forEach((ch, c) => {
    const buf = new Float32Array(maxD)
    let w = 0
    const ph0 = c * 0.5
    for (let i = 0; i < ch.length; i++) {
      const lfo = Math.sin(2 * Math.PI * (rate * i / sr + ph0))
      const d = ((centreMs + depth * centreMs * 0.8 * lfo) * 0.001) * sr
      const rp = (w - d + maxD * 2) % maxD
      const i0 = Math.floor(rp), fr = rp - i0
      const wet = buf[i0 % maxD] * (1 - fr) + buf[(i0 + 1) % maxD] * fr
      buf[w] = ch[i] + wet * fb
      w = (w + 1) % maxD
      ch[i] = ch[i] * (1 - mix) + wet * mix
    }
  })
  return a
}
export function phaser(a: Audio, rate: number, depth: number, centre: number, fb: number, mix: number): Audio {
  const sr = a.sr
  a.ch.forEach((ch, c) => {
    const z = new Float64Array(4)
    let last = 0
    for (let i = 0; i < ch.length; i++) {
      const lfo = Math.sin(2 * Math.PI * (rate * i / sr + c * 0.25))
      const f = clamp(centre * Math.pow(2, depth * 1.5 * lfo), 80, sr * 0.45)
      const t = Math.tan(Math.PI * f / sr), k = (t - 1) / (t + 1)
      let x = ch[i] + last * fb
      for (let s = 0; s < 4; s++) { const y = k * x + z[s]; z[s] = x - k * y; x = y }
      last = x
      ch[i] = ch[i] * (1 - mix * 0.5) + x * mix * 0.5
    }
  })
  return a
}
export function widen(a: Audio, width: number): Audio {
  for (let i = 0; i < length(a); i++) {
    const m = (a.ch[0][i] + a.ch[1][i]) / 2, s = ((a.ch[0][i] - a.ch[1][i]) / 2) * width
    a.ch[0][i] = m + s; a.ch[1][i] = m - s
  }
  return a
}
/** Freeverb-style reverb (8 combs + 4 allpasses per side). */
export function reverb(a: Audio, room: number, damping: number, width: number, mix: number): Audio {
  if (mix <= 0.001) return a
  const k = a.sr / 44100
  const combT = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617]
  const apT = [556, 441, 341, 225]
  const fbk = 0.7 + 0.28 * clamp(room, 0, 1)
  const damp = clamp(damping, 0, 1) * 0.4
  const wets: Float32Array[] = []
  a.ch.forEach((ch, c) => {
    const spread = c * 23
    const combs = combT.map((t) => ({ buf: new Float32Array(Math.round((t + spread) * k)), i: 0, store: 0 }))
    const aps = apT.map((t) => ({ buf: new Float32Array(Math.round((t + spread) * k)), i: 0 }))
    const out = new Float32Array(ch.length)
    for (let n = 0; n < ch.length; n++) {
      const inp = ch[n] * 0.015
      let acc = 0
      for (const cb of combs) {
        const y = cb.buf[cb.i]
        cb.store = y * (1 - damp) + cb.store * damp
        cb.buf[cb.i] = inp + cb.store * fbk
        cb.i = (cb.i + 1) % cb.buf.length
        acc += y
      }
      for (const ap of aps) {
        const bo = ap.buf[ap.i]
        const y = -acc + bo
        ap.buf[ap.i] = acc + bo * 0.5
        ap.i = (ap.i + 1) % ap.buf.length
        acc = y
      }
      out[n] = acc
    }
    wets.push(out)
  })
  const w1 = (1 + width) / 2, w2 = (1 - width) / 2
  for (let n = 0; n < length(a); n++) {
    const l = wets[0][n] * w1 + wets[1][n] * w2, r = wets[1][n] * w1 + wets[0][n] * w2
    a.ch[0][n] = a.ch[0][n] * (1 - mix * 0.5) + l * mix * 1.6
    a.ch[1][n] = a.ch[1][n] * (1 - mix * 0.5) + r * mix * 1.6
  }
  return a
}

// ---------------------------------------------------------------- loudness (ITU-R BS.1770-4)
function kWeight(x: Float32Array, sr: number): Float32Array {
  const y = x.slice()
  // stage 1: high shelf (+4 dB at ~1.68 kHz), stage 2: high pass at ~38 Hz
  const f0 = 1681.974450955533, G = 3.999843853973347, Q = 0.7071752369554196
  const K = Math.tan(Math.PI * f0 / sr), Vh = Math.pow(10, G / 20), Vb = Math.pow(Vh, 0.4996667741545416)
  const a0 = 1 + K / Q + K * K
  biquadInPlace(y, { b0: (Vh + Vb * K / Q + K * K) / a0, b1: 2 * (K * K - Vh) / a0, b2: (Vh - Vb * K / Q + K * K) / a0, a1: 2 * (K * K - 1) / a0, a2: (1 - K / Q + K * K) / a0 })
  const f1 = 38.13547087602444, Q1 = 0.5003270373238773
  const K1 = Math.tan(Math.PI * f1 / sr), d = 1 + K1 / Q1 + K1 * K1
  biquadInPlace(y, { b0: 1 / d, b1: -2 / d, b2: 1 / d, a1: 2 * (K1 * K1 - 1) / d, a2: (1 - K1 / Q1 + K1 * K1) / d })
  return y
}
export function lufs(a: Audio): number {
  const w = a.ch.map((c) => kWeight(c, a.sr))
  const block = Math.round(0.4 * a.sr), hop = Math.round(0.1 * a.sr)
  const n = length(a)
  const energies: number[] = []
  for (let s = 0; s + block <= n || (s === 0 && n > 0); s += hop) {
    const e = Math.min(s + block, n)
    let acc = 0
    for (const ch of w) { let z = 0; for (let i = s; i < e; i++) z += ch[i] * ch[i]; acc += z / (e - s) }
    energies.push(acc)
    if (e >= n) break
  }
  const lk = (z: number) => -0.691 + 10 * Math.log10(Math.max(z, 1e-12))
  const abs = energies.filter((z) => lk(z) > -70)
  if (!abs.length) return -Infinity
  const rel = lk(abs.reduce((p, c) => p + c, 0) / abs.length) - 10
  const kept = abs.filter((z) => lk(z) > rel)
  if (!kept.length) return -Infinity
  return lk(kept.reduce((p, c) => p + c, 0) / kept.length)
}
/** 4x oversampled (Catmull-Rom) peak in dBFS, an estimate of true peak. */
export function truePeakDb(a: Audio): number {
  let p = 0
  for (const ch of a.ch) {
    for (let i = 1; i < ch.length - 2; i++) {
      const y0 = ch[i - 1], y1 = ch[i], y2 = ch[i + 1], y3 = ch[i + 2]
      p = Math.max(p, Math.abs(y1))
      for (let t = 0.25; t < 1; t += 0.25) {
        const v = 0.5 * (2 * y1 + (-y0 + y2) * t + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t * t + (-y0 + 3 * y1 - 3 * y2 + y3) * t * t * t)
        if (Math.abs(v) > p) p = Math.abs(v)
      }
    }
  }
  return lin2db(p)
}
export function rmsDb(a: Audio): number {
  let z = 0
  for (const ch of a.ch) for (let i = 0; i < ch.length; i++) z += ch[i] * ch[i]
  return lin2db(Math.sqrt(z / (2 * length(a))))
}
export function analyze(a: Audio) {
  const l = lufs(a)
  return {
    lufs: Number.isFinite(l) ? +l.toFixed(2) : null,
    true_peak_db: +truePeakDb(a).toFixed(2),
    peak_db: +lin2db(peak(a)).toFixed(2),
    rms_db: +rmsDb(a).toFixed(2),
    duration_s: +seconds(a).toFixed(2),
    sample_rate: a.sr,
    channels: 2,
  }
}
/** Gain to a target loudness, then a limiter, iterated so the reported number is measured. */
export function masterTo(a: Audio, targetLufs: number, ceilingDb: number, releaseMs = 80): Audio {
  const cur = lufs(a)
  if (Number.isFinite(cur)) scale(a, db2lin(clamp(targetLufs - cur, -30, 30)))
  const ceil = ceilingDb - 0.6
  for (let k = 0; k < 4; k++) {
    limit(a, ceil, releaseMs)
    const l = lufs(a)
    if (!Number.isFinite(l) || Math.abs(l - targetLufs) < 0.15) break
    scale(a, db2lin(clamp(targetLufs - l, -6, 6)))
  }
  limit(a, ceil, releaseMs)
  return a
}

// ---------------------------------------------------------------- WAV + decode
export function encodeWav(a: Audio): Blob {
  const n = length(a), bytes = new ArrayBuffer(44 + n * 4), v = new DataView(bytes)
  const s = (o: number, t: string) => { for (let i = 0; i < t.length; i++) v.setUint8(o + i, t.charCodeAt(i)) }
  s(0, 'RIFF'); v.setUint32(4, 36 + n * 4, true); s(8, 'WAVE'); s(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 2, true)
  v.setUint32(24, a.sr, true); v.setUint32(28, a.sr * 4, true); v.setUint16(32, 4, true); v.setUint16(34, 16, true)
  s(36, 'data'); v.setUint32(40, n * 4, true)
  let o = 44
  for (let i = 0; i < n; i++) for (let c = 0; c < 2; c++) {
    const x = clamp(a.ch[c][i], -1, 1)
    v.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7fff, true); o += 2
  }
  return new Blob([bytes], { type: 'audio/wav' })
}
export function resample(a: Audio, sr: number): Audio {
  if (a.sr === sr) return a
  const n = Math.round(length(a) * sr / a.sr), out = silence(sr, n)
  for (let c = 0; c < 2; c++) for (let i = 0; i < n; i++) {
    const p = i * a.sr / sr, i0 = Math.floor(p), f = p - i0
    const x0 = a.ch[c][i0] ?? 0, x1 = a.ch[c][i0 + 1] ?? x0
    out.ch[c][i] = x0 + (x1 - x0) * f
  }
  return out
}
