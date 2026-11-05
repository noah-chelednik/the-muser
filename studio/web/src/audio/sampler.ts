/**
 * Pure buffer operations for the sampler: crop, fades, normalize, reverse, BPM detection,
 * transient detection and grid snapping. Every function returns a NEW AudioBuffer so edits are undoable.
 */

function make(src: AudioBuffer, length: number): AudioBuffer {
  return new AudioBuffer({ numberOfChannels: src.numberOfChannels, length: Math.max(1, length), sampleRate: src.sampleRate })
}

export function sliceBuffer(buf: AudioBuffer, start: number, end: number): AudioBuffer {
  const sr = buf.sampleRate
  const a = Math.max(0, Math.floor(start * sr))
  const b = Math.min(buf.length, Math.ceil(end * sr))
  const out = make(buf, b - a)
  for (let c = 0; c < buf.numberOfChannels; c++) out.copyToChannel(buf.getChannelData(c).slice(a, Math.max(a + 1, b)), c)
  return out
}

function mapRegion(buf: AudioBuffer, region: { start: number; end: number } | null, fn: (d: Float32Array, a: number, b: number, c: number) => void): AudioBuffer {
  const sr = buf.sampleRate
  const a = region ? Math.max(0, Math.floor(region.start * sr)) : 0
  const b = region ? Math.min(buf.length, Math.ceil(region.end * sr)) : buf.length
  const out = make(buf, buf.length)
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c).slice()
    fn(d, a, b, c)
    out.copyToChannel(d, c)
  }
  return out
}

/** Linear fades inside the region (or the whole buffer). Seconds. */
export function fadeBuffer(buf: AudioBuffer, region: { start: number; end: number } | null, fadeIn: number, fadeOut: number): AudioBuffer {
  const sr = buf.sampleRate
  return mapRegion(buf, region, (d, a, b) => {
    const fi = Math.min(b - a, Math.round(fadeIn * sr))
    const fo = Math.min(b - a, Math.round(fadeOut * sr))
    for (let i = 0; i < fi; i++) d[a + i] *= i / fi
    for (let i = 0; i < fo; i++) d[b - 1 - i] *= i / fo
  })
}

export function peakOf(buf: AudioBuffer, region?: { start: number; end: number } | null): number {
  const sr = buf.sampleRate
  const a = region ? Math.floor(region.start * sr) : 0
  const b = region ? Math.min(buf.length, Math.ceil(region.end * sr)) : buf.length
  let m = 0
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c)
    for (let i = a; i < b; i++) { const v = Math.abs(d[i]); if (v > m) m = v }
  }
  return m
}

export function gainBuffer(buf: AudioBuffer, region: { start: number; end: number } | null, g: number): AudioBuffer {
  return mapRegion(buf, region, (d, a, b) => { for (let i = a; i < b; i++) d[i] *= g })
}

export function normalizeBuffer(buf: AudioBuffer, region: { start: number; end: number } | null, targetDb = -0.3, peak = peakOf(buf, region)): AudioBuffer {
  if (peak < 1e-6) return buf
  return gainBuffer(buf, region, Math.pow(10, targetDb / 20) / peak)
}

export function reverseBuffer(buf: AudioBuffer, region: { start: number; end: number } | null): AudioBuffer {
  return mapRegion(buf, region, (d, a, b) => {
    for (let i = a, j = b - 1; i < j; i++, j--) { const t = d[i]; d[i] = d[j]; d[j] = t }
  })
}

// ---------------------------------------------------------------- analysis

function mono(buf: AudioBuffer): Float32Array {
  const n = buf.length
  const out = new Float32Array(n)
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c)
    for (let i = 0; i < n; i++) out[i] += d[i] / buf.numberOfChannels
  }
  return out
}

/** Onset strength envelope (half-wave rectified, log-compressed energy flux on a high-passed signal). */
export function onsetEnvelope(buf: AudioBuffer, hop = 256): { env: Float32Array; hopSec: number } {
  const x = mono(buf)
  const win = hop * 2
  const frames = Math.max(1, Math.floor((x.length - win) / hop))
  const e = new Float32Array(frames)
  // one-pole high-pass to emphasise attacks (kick/snare/hat energy), then energy per window
  let px = 0, py = 0
  const hp = new Float32Array(x.length)
  for (let i = 0; i < x.length; i++) { const y = 0.97 * (py + x[i] - px); px = x[i]; py = y; hp[i] = y }
  for (let f = 0; f < frames; f++) {
    let s = 0
    const o = f * hop
    for (let i = 0; i < win; i++) s += hp[o + i] * hp[o + i]
    e[f] = Math.log1p(s * 200)
  }
  const env = new Float32Array(frames)
  for (let f = 1; f < frames; f++) env[f] = Math.max(0, e[f] - e[f - 1])
  return { env, hopSec: hop / buf.sampleRate }
}

/** Tempo and first-beat offset by autocorrelation of the onset envelope. Folded into 70..170 BPM. */
export function detectBpm(buf: AudioBuffer): { bpm: number; offset: number; confidence: number } {
  const { env, hopSec } = onsetEnvelope(buf)
  const n = env.length
  if (n < 64) return { bpm: 120, offset: 0, confidence: 0 }
  let mean = 0
  for (let i = 0; i < n; i++) mean += env[i]
  mean /= n
  const z = Float32Array.from(env, (v) => v - mean)
  let best = { bpm: 120, score: -Infinity }
  const scores: [number, number][] = []
  for (let bpm = 60; bpm <= 200; bpm += 0.5) {
    const lag = 60 / bpm / hopSec
    let s = 0
    // comb: lag, 2*lag and 4*lag reinforce a true pulse
    for (const [m, w] of [[1, 1], [2, 0.6], [4, 0.35]] as const) {
      const L = lag * m
      const li = Math.floor(L)
      const fr = L - li
      let acc = 0
      let cnt = 0
      for (let i = 0; i + li + 1 < n; i++) { acc += z[i] * (z[i + li] * (1 - fr) + z[i + li + 1] * fr); cnt++ }
      s += (w * acc) / Math.max(1, cnt)
    }
    scores.push([bpm, s])
    if (s > best.score) best = { bpm, score: s }
  }
  let bpm = best.bpm
  while (bpm < 70) bpm *= 2
  while (bpm > 170) bpm /= 2
  // refine to 0.1 around the pick
  let refine = { bpm, score: -Infinity }
  for (let b = bpm - 1; b <= bpm + 1; b += 0.1) {
    const lag = 60 / b / hopSec
    const li = Math.floor(lag), fr = lag - li
    let acc = 0
    for (let i = 0; i + li + 1 < n; i++) acc += z[i] * (z[i + li] * (1 - fr) + z[i + li + 1] * fr)
    if (acc > refine.score) refine = { bpm: b, score: acc }
  }
  bpm = Math.round(refine.bpm * 10) / 10
  // phase: the offset in [0, beat) whose comb sums the most onset energy
  const beat = 60 / bpm
  const steps = 48
  let bestOff = 0, bestSum = -1
  for (let k = 0; k < steps; k++) {
    const off = (k / steps) * beat
    let s = 0
    for (let t = off; t < n * hopSec; t += beat) s += env[Math.min(n - 1, Math.round(t / hopSec))]
    if (s > bestSum) { bestSum = s; bestOff = off }
  }
  const sorted = scores.map((x) => x[1]).sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)]
  const confidence = Math.max(0, Math.min(1, (best.score - median) / (Math.abs(best.score) + 1e-9)))
  return { bpm, offset: bestOff, confidence }
}

/** Transient times in seconds (peak picking with an adaptive threshold), snapped back to the start of the attack. */
export function detectTransients(buf: AudioBuffer, sensitivity = 0.5, minGap = 0.06): number[] {
  const { env, hopSec } = onsetEnvelope(buf, 128)
  const n = env.length
  const out: number[] = []
  const w = Math.round(0.15 / hopSec)
  const k = 1.2 + (1 - sensitivity) * 3
  const d = mono(buf)
  let last = -1e9
  for (let i = 1; i < n - 1; i++) {
    if (env[i] < env[i - 1] || env[i] < env[i + 1]) continue
    let sum = 0, cnt = 0
    for (let j = Math.max(0, i - w); j < Math.min(n, i + w); j++) { sum += env[j]; cnt++ }
    const thr = (sum / cnt) * k + 0.05
    if (env[i] < thr) continue
    let t = i * hopSec
    if (t - last < minGap) continue
    // walk back to the quietest point just before the attack, then to a zero crossing
    let idx = Math.max(0, Math.round((t - 0.012) * buf.sampleRate))
    const stop = Math.max(0, idx - Math.round(0.02 * buf.sampleRate))
    while (idx > stop && Math.abs(d[idx]) > 0.003) idx--
    t = idx / buf.sampleRate
    out.push(t)
    last = t
  }
  return out
}

export function snapTime(t: number, bpm: number, offset: number, division: number): number {
  const step = 60 / bpm / division
  return offset + Math.round((t - offset) / step) * step
}

export function equalSlices(start: number, end: number, n: number): number[] {
  return Array.from({ length: n }, (_, i) => start + ((end - start) * i) / n)
}
