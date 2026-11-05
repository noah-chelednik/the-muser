/** Turns real decoded audio into notation events. This is a transcription of what is playing, not a canned pattern:
 *  onsets come from the step-wise energy of the stem, noteheads for pitched stems from autocorrelation pitch tracking,
 *  and drum hits from a low / mid / high band split. */
export type Clef = 'perc' | 'bass' | 'treble'
export type Ev = { bar: number; s: number; l: number; midis: number[]; kind?: 'k' | 'sn' | 'h' | 'oh' }

export const clefFor = (role: string): Clef => (role === 'drums' || role === 'perc' ? 'perc' : role === 'bass' ? 'bass' : 'treble')

const NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
export const midiName = (m: number) => NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1)

const snap = (n: number) => (n >= 12 ? 16 : n >= 6 ? 8 : n >= 3 ? 4 : n >= 2 ? 2 : 1)

function pitchAt(d: Float32Array, sr: number, start: number, lo: number, hi: number): number | null {
  const k = Math.max(1, Math.round(sr / 11025))
  const rate = sr / k
  const n = 1024
  const win = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    let a = 0
    for (let j = 0; j < k; j++) a += d[start + i * k + j] ?? 0
    win[i] = a / k
  }
  const minLag = Math.max(2, Math.floor(rate / hi))
  const maxLag = Math.min(n / 2, Math.ceil(rate / lo))
  let e0 = 0
  for (let i = 0; i < n; i++) e0 += win[i] * win[i]
  if (e0 < 1e-6) return null
  const nsdf = new Float32Array(maxLag + 1)
  let best = 0
  for (let lag = minLag; lag <= maxLag; lag++) {
    let c = 0
    let e = 0
    for (let i = 0; i < n - lag; i++) {
      c += win[i] * win[i + lag]
      e += win[i + lag] * win[i + lag]
    }
    const v = (2 * c) / (e0 + e + 1e-9)
    nsdf[lag] = v
    if (v > best) best = v
  }
  if (best < 0.45) return null
  for (let lag = minLag + 1; lag < maxLag; lag++) {
    if (nsdf[lag] > best * 0.88 && nsdf[lag] >= nsdf[lag - 1] && nsdf[lag] >= nsdf[lag + 1]) {
      const f = rate / lag
      return Math.round(69 + 12 * Math.log2(f / 440))
    }
  }
  return null
}

function bands(d: Float32Array, sr: number, start: number) {
  const n = Math.min(1024, d.length - start)
  const aL = 1 - Math.exp((-2 * Math.PI * 160) / sr)
  const aH = 1 - Math.exp((-2 * Math.PI * 3500) / sr)
  let l = 0
  let h = 0
  let eL = 0
  let eH = 0
  let eT = 0
  for (let i = 0; i < n; i++) {
    const x = d[start + i]
    l += aL * (x - l)
    h += aH * (x - h)
    eL += l * l
    eH += (x - h) * (x - h)
    eT += x * x
  }
  return eT > 0 ? { low: eL / eT, high: eH / eT } : { low: 0, high: 0 }
}

/** Four bars starting at `bar0` (0-based). */
export function transcribe(buf: AudioBuffer | null, bpm: number, clef: Clef, bar0: number): Ev[] {
  if (!buf || !bpm) return []
  const d = buf.getChannelData(0)
  const sr = buf.sampleRate
  const stepSamples = Math.round(((60 / bpm) / 4) * sr)
  const base = bar0 * 16 * stepSamples
  const N = 64
  const rms = new Float32Array(N)
  let mx = 0
  for (let s = 0; s < N; s++) {
    const a = base + s * stepSamples
    if (a >= d.length) break
    let e = 0
    let c = 0
    for (let i = a; i < Math.min(d.length, a + stepSamples); i += 7) {
      e += d[i] * d[i]
      c++
    }
    rms[s] = c ? Math.sqrt(e / c) : 0
    mx = Math.max(mx, rms[s])
  }
  if (mx < 0.004) return []
  const onsets: number[] = []
  for (let s = 0; s < N; s++) {
    const prev = s ? rms[s - 1] : 0
    if (rms[s] > mx * 0.12 && rms[s] > prev * 1.4 + mx * 0.03) onsets.push(s)
  }
  if (clef !== 'perc') {
    for (let b = 0; b < 4; b++) if (rms[b * 16] > mx * 0.12 && !onsets.some((s) => s >= b * 16 && s < b * 16 + 16)) onsets.push(b * 16)
    onsets.sort((a, b) => a - b)
  }
  const out: Ev[] = []
  onsets.forEach((s, i) => {
    const next = onsets[i + 1] ?? N
    let end = s + 1
    while (end < next && end < s + 16 && rms[end] > rms[s] * 0.4) end++
    const l = snap(end - s)
    const bar = Math.floor(s / 16)
    const st = s % 16
    const at = base + s * stepSamples
    if (clef === 'perc') {
      const { low, high } = bands(d, sr, at)
      if (high > 0.3) out.push({ bar, s: st, l: l >= 2 ? 2 : 1, midis: [], kind: l >= 2 ? 'oh' : 'h' })
      else if (low > 0.35 && high < 0.03) out.push({ bar, s: st, l: 1, midis: [], kind: 'k' })
      else out.push({ bar, s: st, l: 1, midis: [], kind: 'sn' })
    } else {
      const start = at + Math.round(0.02 * sr)
      if (start + 1024 * Math.max(1, Math.round(sr / 11025)) >= d.length) return
      const m = pitchAt(d, sr, start, clef === 'bass' ? 32 : 110, clef === 'bass' ? 300 : 1000)
      if (m == null) return
      let p = m
      if (clef === 'bass') while (p > 55) p -= 12
      else {
        while (p > 88) p -= 12
        while (p < 55) p += 12
      }
      out.push({ bar, s: st, l, midis: [p] })
    }
  })
  return out
}
