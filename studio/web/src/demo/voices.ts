// Instrument and drum voices for the browser demo synthesizer. Everything here is plain DSP written
// for this project (no samples, no AI). Each voice renders one note or hit into a mono Float32Array.
import { biquadCoef, biquadInPlace } from './dsp'

export const SR = 44100
export const TAU = Math.PI * 2
export const midiHz = (n: number) => 440 * Math.pow(2, (n - 69) / 12)

export type Rng = { random: () => number; int: (lo: number, hi: number) => number; normal: () => number }
export function fnv(str: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) }
  return h >>> 0
}
export function rngFor(seed: number): Rng {
  let a = seed >>> 0
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  return {
    random: next,
    int: (lo, hi) => lo + Math.floor(next() * (hi - lo)),
    normal: () => Math.sqrt(-2 * Math.log(Math.max(next(), 1e-12))) * Math.cos(TAU * next()),
  }
}

// ------------------------------------------------------------------ small filters
export function lp1(x: Float32Array, cutoff: number): Float32Array {
  const a = Math.exp((-TAU * cutoff) / SR), y = new Float32Array(x.length)
  let z = 0
  for (let i = 0; i < x.length; i++) { z = (1 - a) * x[i] + a * z; y[i] = z }
  return y
}
export function hp1(x: Float32Array, cutoff: number): Float32Array {
  const l = lp1(x, cutoff), y = new Float32Array(x.length)
  for (let i = 0; i < x.length; i++) y[i] = x[i] - l[i]
  return y
}
export function bq(x: Float32Array, kind: 'lowpass' | 'highpass' | 'bandpass' | 'peak', f: number, q = 0.7071, g = 0): Float32Array {
  biquadInPlace(x, biquadCoef(kind, SR, f, q, g))
  return x
}
/** Chamberlin state-variable low-pass with a per-sample cutoff (Hz) and resonance Q. */
export function svfLP(x: Float32Array, cutoff: (i: number) => number, q = 1): Float32Array {
  const y = new Float32Array(x.length), q1 = 1 / q
  let lo = 0, bp = 0
  for (let i = 0; i < x.length; i++) {
    const fc = Math.min(Math.max(cutoff(i), 30), 6500), f = 2 * Math.sin((Math.PI * fc) / SR)
    const hi = x[i] - lo - q1 * bp
    bp += f * hi
    lo += f * bp
    y[i] = lo
  }
  return y
}
export const noise = (n: number, r: Rng) => { const o = new Float32Array(n); for (let i = 0; i < n; i++) o[i] = r.random() * 2 - 1; return o }
const fadeEnd = (o: Float32Array, ms = 4) => {
  const k = Math.min(o.length, Math.floor((ms / 1000) * SR))
  for (let i = 0; i < k; i++) o[o.length - 1 - i] *= i / k
  return o
}
const sat = (x: number, d: number) => Math.tanh(x * d) / Math.tanh(d)

// polyBLEP band-limited saw and square
function blepSaw(ph: number, dt: number): number {
  let v = 2 * ph - 1
  if (ph < dt) { const t = ph / dt; v -= t + t - t * t - 1 }
  else if (ph > 1 - dt) { const t = (ph - 1) / dt; v -= t * t + t + t + 1 }
  return v
}
function blepSquare(ph: number, dt: number, pw = 0.5): number {
  let v = ph < pw ? 1 : -1
  const poly = (p: number) => { if (p < dt) { const t = p / dt; return t + t - t * t - 1 } if (p > 1 - dt) { const t = (p - 1) / dt; return t * t + t + t + 1 } return 0 }
  v += poly(ph)
  v -= poly((ph - pw + 1) % 1)
  return v
}

/** Gate envelope: attack, exponential decay to a sustain level, linear release after the gate. */
function env(i: number, gate: number, rel: number, a: number, dec: number, sus: number): number {
  const t = i / SR
  let e = t < a ? t / a : sus + (1 - sus) * Math.exp(-(t - a) * dec)
  if (i >= gate) e *= Math.max(0, 1 - (i - gate) / rel)
  return e
}

// ------------------------------------------------------------------ drums
export type KickP = { f0: number; f1: number; sweep: number; decay: number; drive: number; click: number; len: number }
export function kick(p: KickP): Float32Array {
  const n = Math.floor(p.len * SR), o = new Float32Array(n)
  let ph = 0
  for (let i = 0; i < n; i++) {
    const t = i / SR
    ph += (TAU * (p.f1 + (p.f0 - p.f1) * Math.exp(-t * p.sweep))) / SR
    let s = Math.sin(ph) * Math.exp(-t * p.decay)
    s += p.click * Math.sin(TAU * 3200 * t) * Math.exp(-t * 700)
    o[i] = sat(s, p.drive)
  }
  return fadeEnd(o, 8)
}
export type SnareP = { tone: number; toneDecay: number; toneLevel: number; noiseDecay: number; noiseLevel: number; hp: number; lpf?: number; len: number }
export function snare(p: SnareP, r: Rng): Float32Array {
  const n = Math.floor(p.len * SR)
  let nz = hp1(noise(n, r), p.hp)
  if (p.lpf) nz = lp1(nz, p.lpf)
  const o = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const t = i / SR
    const body = Math.sin(TAU * p.tone * (1 + 0.25 * Math.exp(-t * 55)) * t) * Math.exp(-t * p.toneDecay) * p.toneLevel
    o[i] = body + nz[i] * Math.exp(-t * p.noiseDecay) * p.noiseLevel
  }
  return fadeEnd(o, 6)
}
export function clap(r: Rng, tail = 20, bright = 1300): Float32Array {
  const n = Math.floor(0.3 * SR), o = new Float32Array(n)
  const nz = bq(noise(n, r), 'bandpass', bright, 1.1)
  const hits = [0, 0.009, 0.019, 0.03]
  for (let i = 0; i < n; i++) {
    const t = i / SR
    let a = 0
    for (let k = 0; k < hits.length; k++) {
      const dt = t - hits[k]
      if (dt < 0) continue
      a = Math.max(a, k === hits.length - 1 ? Math.exp(-dt * tail) : Math.exp(-dt * 140))
    }
    o[i] = nz[i] * a * 2.2
  }
  return fadeEnd(o, 6)
}
const METAL = [2, 3, 4.16, 5.43, 6.79, 8.21]
export function hat(r: Rng, open: boolean, tone = 330, hpf = 7000): Float32Array {
  const n = Math.floor((open ? 0.32 : 0.075) * SR), o = new Float32Array(n)
  const dec = open ? 11 : 75
  for (let i = 0; i < n; i++) {
    const t = i / SR
    let s = 0
    for (const m of METAL) s += Math.sign(Math.sin(TAU * tone * m * t))
    o[i] = (s / 6) * 0.5 * Math.exp(-t * dec)
  }
  bq(o, 'highpass', hpf, 0.9)
  const nz = hp1(noise(n, r), 6000)
  for (let i = 0; i < n; i++) o[i] += nz[i] * 0.25 * Math.exp((-i / SR) * dec * 1.2)
  return fadeEnd(o, 3)
}
export function shaker(r: Rng, len = 0.07, f = 6500): Float32Array {
  const n = Math.floor(len * SR), o = bq(noise(n, r), 'bandpass', f, 0.8)
  for (let i = 0; i < n; i++) { const t = i / SR; o[i] *= Math.min(1, t / 0.012) * Math.exp(-t * (3.2 / len)) * 1.4 }
  return fadeEnd(o, 3)
}
export function rim(r: Rng): Float32Array {
  const n = Math.floor(0.06 * SR), o = new Float32Array(n), nz = noise(n, r)
  for (let i = 0; i < n; i++) { const t = i / SR; o[i] = (Math.sin(TAU * 1700 * t) * 0.5 + Math.sin(TAU * 480 * t) * 0.4 + nz[i] * 0.15) * Math.exp(-t * 90) }
  return fadeEnd(o, 3)
}
export function snap(r: Rng): Float32Array {
  const n = Math.floor(0.09 * SR), o = bq(noise(n, r), 'bandpass', 2400, 2.2)
  for (let i = 0; i < n; i++) { const t = i / SR; o[i] *= Math.exp(-t * 55) * (1 + Math.sin(TAU * 1100 * t) * 0.5) * 2 }
  return fadeEnd(o, 3)
}
export function tom(f: number, decay = 9, len = 0.5): Float32Array {
  const n = Math.floor(len * SR), o = new Float32Array(n)
  let ph = 0
  for (let i = 0; i < n; i++) {
    const t = i / SR
    ph += (TAU * f * (1 + 0.5 * Math.exp(-t * 18))) / SR
    o[i] = Math.tanh(1.3 * Math.sin(ph)) * Math.exp(-t * decay)
  }
  return fadeEnd(o, 8)
}
export function conga(f: number): Float32Array {
  const n = Math.floor(0.22 * SR), o = new Float32Array(n)
  for (let i = 0; i < n; i++) { const t = i / SR; o[i] = (Math.sin(TAU * f * (1 + 0.12 * Math.exp(-t * 40)) * t) + 0.3 * Math.sin(TAU * f * 2.3 * t) * Math.exp(-t * 60)) * Math.exp(-t * 22) }
  return fadeEnd(o, 5)
}
export function cowbell(): Float32Array {
  const n = Math.floor(0.28 * SR), o = new Float32Array(n)
  for (let i = 0; i < n; i++) { const t = i / SR; o[i] = (Math.sign(Math.sin(TAU * 562 * t)) + Math.sign(Math.sin(TAU * 845 * t))) * 0.5 * (0.35 * Math.exp(-t * 40) + 0.65 * Math.exp(-t * 11)) }
  bq(o, 'bandpass', 800, 1.4)
  for (let i = 0; i < n; i++) o[i] *= 2.2
  return fadeEnd(o, 5)
}
export function ride(r: Rng, len = 0.7): Float32Array {
  const n = Math.floor(len * SR), o = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const t = i / SR
    let s = 0
    for (const m of METAL) s += Math.sin(TAU * 410 * m * t + m)
    o[i] = (s / 6) * (0.5 * Math.exp(-t * 4.5) + 0.5 * Math.exp(-t * 35))
  }
  bq(o, 'highpass', 4500, 0.7)
  const nz = hp1(noise(n, r), 8000)
  for (let i = 0; i < n; i++) o[i] += nz[i] * 0.15 * Math.exp((-i / SR) * 14)
  return fadeEnd(o, 10)
}
export function crash(r: Rng, len = 1.6): Float32Array {
  const n = Math.floor(len * SR), nz = hp1(noise(n, r), 3500), o = new Float32Array(n)
  for (let i = 0; i < n; i++) { const t = i / SR; o[i] = nz[i] * (0.6 * Math.exp(-t * 2.6) + 0.4 * Math.exp(-t * 14)) }
  return fadeEnd(o, 20)
}
export function brush(r: Rng): Float32Array {
  const n = Math.floor(0.2 * SR), o = lp1(noise(n, r), 5500)
  for (let i = 0; i < n; i++) { const t = i / SR; o[i] *= Math.min(1, t / 0.018) * Math.exp(-t * 11) * 1.6 }
  return fadeEnd(o, 5)
}
export function riser(seconds: number, r: Rng): Float32Array {
  const n = Math.floor(seconds * SR), nz = noise(n, r), o = new Float32Array(n)
  let lo = 0, bp = 0
  for (let i = 0; i < n; i++) {
    const p = i / n, fc = Math.min(500 * Math.pow(12, p), 6000), f = 2 * Math.sin((Math.PI * fc) / SR)
    const hi = nz[i] - lo - 0.5 * bp
    bp += f * hi; lo += f * bp
    o[i] = (bp * 0.8 + Math.sin(TAU * (200 + 1800 * p * p) * (i / SR)) * 0.1) * p * p
  }
  return o
}

// ------------------------------------------------------------------ pitched voices
/** gate = note-on length in samples. Every voice adds its own release tail. */
export type Voice = (f: number, gate: number, vel: number, r: Rng) => Float32Array
const tail = (s: number) => Math.floor(s * SR)

export const rhodes: Voice = (f, gate, vel, r) => {
  const rel = tail(0.3), n = gate + rel, o = new Float32Array(n)
  const idx = 0.7 + 1.7 * vel, trem = r.random() * TAU
  for (let i = 0; i < n; i++) {
    const t = i / SR
    const car = Math.sin(TAU * f * t + idx * Math.exp(-t * 4) * Math.sin(TAU * f * t))
    const tine = 0.22 * vel * Math.sin(TAU * f * 14 * t + 0.4) * Math.exp(-t * 26)
    const bark = 0.12 * Math.sin(TAU * f * 2 * t) * Math.exp(-t * 2.2)
    o[i] = (car + tine + bark) * env(i, gate, rel, 0.003, 1.6, 0.35) * (0.6 + 0.4 * vel) * (1 + 0.06 * Math.sin(TAU * 5 * t + trem))
  }
  return o
}
export const piano: Voice = (f, gate, vel, r) => {
  const rel = tail(0.35), n = gate + rel, o = new Float32Array(n)
  const parts = Math.max(3, Math.min(10, Math.floor(7000 / f))), B = 0.00012
  const ph = Array.from({ length: parts }, () => r.random() * 0.3)
  for (let i = 0; i < n; i++) {
    const t = i / SR
    let s = 0
    for (let h = 1; h <= parts; h++) {
      const ff = f * h * Math.sqrt(1 + B * h * h)
      s += (Math.sin(TAU * ff * t + ph[h - 1]) / Math.pow(h, 0.9 + (1 - vel) * 0.8)) * Math.exp(-t * (1.1 + h * 0.55 + f / 700))
    }
    const hammer = (r.random() * 2 - 1) * Math.exp(-t * 280) * 0.18 * vel
    o[i] = (s * 0.8 + hammer) * env(i, gate, rel, 0.002, 0.0001, 1)
  }
  return o
}
export const organ: Voice = (f, gate, vel, r) => {
  const rel = tail(0.08), n = gate + rel, o = new Float32Array(n)
  const bars: [number, number][] = [[0.5, 0.8], [1, 1], [1.5, 0.6], [2, 0.7], [3, 0.35], [4, 0.3]]
  const ph = r.random() * TAU
  for (let i = 0; i < n; i++) {
    const t = i / SR
    const vib = 1 + 0.0035 * Math.sin(TAU * 6.4 * t + ph)
    let s = 0
    for (const [m, a] of bars) s += a * Math.sin(TAU * f * m * t * vib)
    const click = (r.random() * 2 - 1) * Math.exp(-t * 200) * 0.15
    o[i] = (s / 4 * (1 + 0.14 * Math.sin(TAU * 6.4 * t)) + click) * env(i, gate, rel, 0.012, 0.0001, 1) * (0.7 + 0.3 * vel)
  }
  return o
}
const DET = [-24, -14, -5, 0, 6, 15, 25]
export const supersaw: Voice = (f, gate, vel, r) => {
  const rel = tail(0.22), n = gate + rel, o = new Float32Array(n)
  const ph = DET.map(() => r.random()), dt = DET.map((c) => (f * Math.pow(2, c / 1200)) / SR)
  for (let i = 0; i < n; i++) {
    let s = 0
    for (let k = 0; k < DET.length; k++) { ph[k] += dt[k]; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], dt[k]) * (k === 3 ? 1.1 : 0.8) }
    o[i] = (s / 5) * env(i, gate, rel, 0.008, 3, 0.8) * (0.6 + 0.4 * vel)
  }
  return lp1(o, Math.min(9000, 2500 + f * 8))
}
export const pad: Voice = (f, gate, vel, r) => {
  const rel = tail(0.7), n = gate + rel, o = new Float32Array(n)
  const dets = [-9, -3, 4, 10], ph = dets.map(() => r.random()), dt = dets.map((c) => (f * Math.pow(2, c / 1200)) / SR)
  const lf = r.random() * TAU
  for (let i = 0; i < n; i++) {
    let s = 0
    for (let k = 0; k < dets.length; k++) { ph[k] += dt[k]; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], dt[k]) }
    o[i] = (s / 3) * env(i, gate, rel, 0.45, 0.4, 0.8) * (0.7 + 0.3 * vel) * (1 + 0.08 * Math.sin(TAU * 0.3 * (i / SR) + lf))
  }
  return lp1(lp1(o, 1700 + f), 2600)
}
export const strings: Voice = (f, gate, vel, r) => {
  const rel = tail(0.55), n = gate + rel, o = new Float32Array(n)
  const dets = [-11, -4, 3, 9], ph = dets.map(() => r.random()), lf = r.random() * TAU
  for (let i = 0; i < n; i++) {
    const t = i / SR, vib = 1 + 0.0042 * Math.sin(TAU * 5.3 * t + lf) * Math.min(1, t / 0.5)
    let s = 0
    for (let k = 0; k < dets.length; k++) { const d = (f * vib * Math.pow(2, dets[k] / 1200)) / SR; ph[k] += d; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], d) }
    o[i] = (s / 3) * env(i, gate, rel, 0.22, 0.3, 0.85) * (0.6 + 0.4 * vel)
  }
  return lp1(lp1(o, 3200 + f * 2), 5500)
}
export const brass: Voice = (f, gate, vel, r) => {
  const rel = tail(0.25), n = gate + rel, o = new Float32Array(n), dets = [-5, 5], ph = [r.random(), r.random()]
  const raw = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    let s = 0
    for (let k = 0; k < 2; k++) { const d = (f * Math.pow(2, dets[k] / 1200)) / SR; ph[k] += d; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], d) }
    raw[i] = s / 2
  }
  const sw = svfLP(raw, (i) => 350 + 3600 * Math.min(1, i / (0.18 * SR)) * (0.6 + 0.4 * vel), 1.2)
  for (let i = 0; i < n; i++) o[i] = sw[i] * env(i, gate, rel, 0.05, 1, 0.9)
  return o
}
const VOWELS: Record<string, [number, number, number][]> = {
  a: [[800, 8, 1], [1150, 10, 0.5], [2900, 14, 0.15]],
  o: [[450, 7, 1], [800, 9, 0.45], [2830, 14, 0.1]],
}
export const choir: Voice = (f, gate, vel, r) => {
  const rel = tail(0.5), n = gate + rel, raw = new Float32Array(n), dets = [-14, -6, 5, 13], ph = dets.map(() => r.random())
  for (let i = 0; i < n; i++) {
    const t = i / SR, vib = 1 + 0.005 * Math.sin(TAU * 5.6 * t) * Math.min(1, t / 0.4)
    let s = 0
    for (let k = 0; k < dets.length; k++) { const d = (f * vib * Math.pow(2, dets[k] / 1200)) / SR; ph[k] += d; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], d) }
    raw[i] = s / 3
  }
  const out = new Float32Array(n)
  for (const [fc, q, amp] of VOWELS[vel > 0.7 ? 'a' : 'o']) {
    const b = bq(raw.slice(), 'bandpass', fc, q)
    for (let i = 0; i < n; i++) out[i] += b[i] * amp * 3.2
  }
  for (let i = 0; i < n; i++) out[i] *= env(i, gate, rel, 0.12, 0.5, 0.85)
  return out
}
export const harmonium: Voice = (f, gate, vel, r) => {
  const rel = tail(0.12), n = gate + rel, o = new Float32Array(n), ph = [r.random(), r.random()]
  for (let i = 0; i < n; i++) {
    const t = i / SR
    let s = 0
    for (let k = 0; k < 2; k++) { const d = (f * (k ? 1.004 : 0.996)) / SR; ph[k] += d; if (ph[k] >= 1) ph[k] -= 1; s += blepSquare(ph[k], d, 0.35) }
    o[i] = (s / 2) * env(i, gate, rel, 0.03, 0.2, 0.9) * (1 + 0.05 * Math.sin(TAU * 5.2 * t)) * (0.6 + 0.4 * vel)
  }
  return lp1(lp1(o, 2200), 3200)
}
/** Karplus-Strong string. brightness 0..1, decay near 1 sustains longer. */
export function ks(f: number, n: number, vel: number, r: Rng, decay = 0.997, brightness = 0.6): Float32Array {
  const L = Math.max(2, Math.round(SR / f)), b = new Float32Array(L), o = new Float32Array(n)
  const seed = lp1(noise(L, r), 1500 + 9000 * brightness * (0.5 + 0.5 * vel))
  for (let i = 0; i < L; i++) b[i] = seed[i] * 2.2
  let idx = 0
  for (let i = 0; i < n; i++) {
    const cur = b[idx], nxt = b[(idx + 1) % L]
    const y = 0.5 * (cur + nxt) * decay
    b[idx] = y
    idx = (idx + 1) % L
    o[i] = cur
  }

  return o
}
export const pluckGuitar: Voice = (f, gate, vel, r) => {
  const rel = tail(0.12), n = gate + rel, o = ks(f, n, vel, r, 0.9965, 0.7)
  for (let i = 0; i < n; i++) o[i] *= env(i, gate, rel, 0.001, 0.0001, 1) * (0.6 + 0.5 * vel)
  return bq(lp1(o, 5200), 'peak', 220, 1, 3)
}
export const distGuitar = (palm: boolean): Voice => (f, gate, vel, r) => {
  const rel = tail(palm ? 0.04 : 0.15), n = gate + rel, raw = new Float32Array(n)
  const ph = [r.random(), r.random()]
  for (let i = 0; i < n; i++) {
    let s = 0
    for (let k = 0; k < 2; k++) { const d = (f * (k ? 1.003 : 0.997)) / SR; ph[k] += d; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], d) }
    raw[i] = s / 2
  }
  const o = new Float32Array(n)
  for (let i = 0; i < n; i++) o[i] = Math.tanh(raw[i] * (palm ? 7 : 5) * (0.7 + 0.3 * vel)) * env(i, gate, rel, 0.002, palm ? 30 : 2.2, palm ? 0.02 : 0.55)
  return bq(bq(lp1(o, 4200), 'peak', 800, 0.8, 4), 'highpass', 70, 0.7)
}
export const bell: Voice = (f, gate, vel) => {
  const rel = tail(0.4), n = gate + rel, o = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const t = i / SR
    const s = Math.sin(TAU * f * t + 2.2 * vel * Math.exp(-t * 3.5) * Math.sin(TAU * f * 3.5 * t)) + 0.3 * Math.sin(TAU * f * 5.43 * t) * Math.exp(-t * 6)
    o[i] = s * env(i, gate, rel, 0.002, 2.2, 0.0) * (0.5 + 0.5 * vel)
  }
  return o
}
export const pluckSynth: Voice = (f, gate, vel, r) => {
  const rel = tail(0.12), n = gate + rel, raw = new Float32Array(n), ph = [r.random(), r.random()]
  for (let i = 0; i < n; i++) {
    let s = 0
    for (let k = 0; k < 2; k++) { const d = (f * (k ? 1.004 : 0.996)) / SR; ph[k] += d; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], d) }
    raw[i] = s / 2
  }
  const y = svfLP(raw, (i) => 400 + (2800 + f * 3) * Math.exp(-(i / SR) * 14) * (0.5 + 0.5 * vel), 1.4)
  for (let i = 0; i < n; i++) y[i] *= env(i, gate, rel, 0.002, 6, 0.15)
  return y
}
export const squareLead: Voice = (f, gate, vel, r) => {
  const rel = tail(0.2), n = gate + rel, o = new Float32Array(n), lf = r.random() * TAU
  let ph = 0, ph2 = r.random()
  for (let i = 0; i < n; i++) {
    const t = i / SR, vib = 1 + 0.006 * Math.sin(TAU * 5.6 * t + lf) * Math.min(1, t / 0.25)
    const d = (f * vib) / SR
    ph += d; if (ph >= 1) ph -= 1
    ph2 += d * 1.006; if (ph2 >= 1) ph2 -= 1
    o[i] = (blepSquare(ph, d, 0.42) * 0.6 + blepSaw(ph2, d) * 0.4) * env(i, gate, rel, 0.01, 1.5, 0.8) * (0.6 + 0.4 * vel)
  }
  return lp1(o, 4200)
}
export const stab: Voice = (f, gate, vel, r) => {
  const rel = tail(0.08), n = gate + rel, raw = new Float32Array(n), ph = [r.random(), r.random(), r.random()]
  for (let i = 0; i < n; i++) {
    let s = 0
    for (let k = 0; k < 3; k++) { const d = (f * Math.pow(2, (k - 1) * 0.1 / 12)) / SR; ph[k] += d; if (ph[k] >= 1) ph[k] -= 1; s += blepSaw(ph[k], d) }
    raw[i] = s / 3
  }
  const y = svfLP(raw, (i) => 250 + 3200 * Math.exp(-(i / SR) * 11), 2.2)
  for (let i = 0; i < n; i++) y[i] *= env(i, gate, rel, 0.002, 7, 0.1) * (0.6 + 0.4 * vel)
  return y
}

// ------------------------------------------------------------------ bass voices
export type BassKind = 'sub808' | 'sub' | 'saw' | 'reese' | 'wobble' | 'walk' | 'pluck' | 'electric' | 'logdrum' | 'drone'
export type BassCtx = { glideFrom?: number; glideTau?: number; lfoHz?: number; drive?: number; decay?: number }
export function bassNote(kind: BassKind, f: number, gate: number, vel: number, r: Rng, c: BassCtx = {}): Float32Array {
  const rel = tail(kind === 'sub808' ? 0.12 : 0.06), n = gate + rel
  const g0 = c.glideFrom ?? f, tau = c.glideTau ?? 0.06
  let ph = 0, ph2 = r.random(), ph3 = r.random()
  const raw = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const t = i / SR
    const ff = f + (g0 - f) * Math.exp(-t / tau)
    const d = ff / SR
    ph += TAU * d
    switch (kind) {
      case 'sub808': {
        const s = Math.sin(ph + 0.5 * Math.sin(ph) * Math.exp(-t * 20))
        const click = Math.sin(TAU * 120 * t) * Math.exp(-t * 110) * 0.35
        raw[i] = sat(s * (1 + 0.25 * Math.exp(-t * 7)), c.drive ?? 1.6) + click
        break
      }
      case 'sub': raw[i] = Math.sin(ph) + 0.18 * Math.sin(2 * ph) + 0.05 * Math.sin(3 * ph); break
      case 'drone': raw[i] = Math.sin(ph) + 0.35 * Math.sin(2 * ph + 0.3) + 0.15 * Math.sin(3 * ph); break
      case 'logdrum': raw[i] = Math.sin(ph * (1 + 0.45 * Math.exp(-t * 28))) + 0.25 * Math.sin(2 * ph) * Math.exp(-t * 12); break
      case 'walk': raw[i] = Math.sin(ph) + 0.5 * Math.sin(2 * ph) * Math.exp(-t * 3) + 0.25 * Math.sin(3 * ph) * Math.exp(-t * 6) + (r.random() * 2 - 1) * 0.06 * Math.exp(-t * 90); break
      default: {
        ph2 += d * 1.006; if (ph2 >= 1) ph2 -= 1
        ph3 += d * 0.994; if (ph3 >= 1) ph3 -= 1
        const s = kind === 'reese' || kind === 'wobble' ? blepSaw(ph2, d) + blepSaw(ph3, d) : blepSaw(ph2, d)
        raw[i] = s * 0.55 + Math.sin(ph) * (kind === 'reese' || kind === 'wobble' ? 0.8 : 0.6)
      }
    }
  }
  let y: Float32Array = raw
  if (kind === 'saw' || kind === 'pluck' || kind === 'electric') {
    const top = kind === 'pluck' ? 1800 : kind === 'electric' ? 1400 : 2600
    y = svfLP(raw, (i) => 160 + top * Math.exp(-(i / SR) * 9) * (0.5 + 0.5 * vel), 1.5)
  } else if (kind === 'reese') y = svfLP(raw, () => 750, 1.3)
  else if (kind === 'wobble') {
    const lfo = c.lfoHz ?? 3
    y = svfLP(raw, (i) => 130 + 2300 * (0.5 + 0.5 * Math.sin(TAU * lfo * (i / SR) - Math.PI / 2)), 3.2)
    for (let i = 0; i < n; i++) y[i] = Math.tanh(y[i] * 2.6)
  }
  const dec = c.decay ?? (kind === 'sub808' ? 0.9 : kind === 'pluck' ? 5 : kind === 'walk' ? 2.2 : kind === 'logdrum' ? 7 : kind === 'electric' ? 2 : 0.2)
  const sus = kind === 'sub808' || kind === 'logdrum' ? 0 : kind === 'pluck' ? 0.15 : kind === 'walk' ? 0.1 : 0.8
  for (let i = 0; i < n; i++) y[i] *= env(i, gate, rel, 0.003, dec, sus) * (0.7 + 0.3 * vel)
  if (kind === 'electric' && (c.drive ?? 0) > 0) for (let i = 0; i < n; i++) y[i] = Math.tanh(y[i] * (c.drive ?? 1))
  return y
}

export function vinyl(n: number, r: Rng, level = 0.012): Float32Array {
  const o = lp1(noise(n, r), 5000)
  for (let i = 0; i < n; i++) o[i] *= level * 0.6
  const pops = Math.floor((n / SR) * 5)
  for (let k = 0; k < pops; k++) {
    const at = r.int(0, n - 60), a = (0.25 + 0.6 * r.random()) * level * 6
    for (let j = 0; j < 40; j++) o[at + j] += (r.random() * 2 - 1) * a * Math.exp(-j / 6)
  }
  return o
}
