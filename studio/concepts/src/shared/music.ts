import { type Family, type StemId, type Vibe } from './data'

export interface Note { s: number; m: number; l: number } // step 0..15, midi, length in steps
export interface Pattern {
  bpm: number
  family: Family
  keyName: string
  minor: boolean
  root: number
  kick: number[]
  snare: number[]
  hat: number[]
  ohat: number[]
  bass: Note[][] // 4 bars
  chords: number[][] // 4 bars of chord tones (midi)
  lead: Note[][] // 4 bars
  swing: number
  seed: number
}

export const BARS = 16 // length of the track in bars (4 bar pattern x 4)

const z = () => Array(16).fill(0)
const arr = (on: number[], v = 1) => {
  const a = z()
  on.forEach((i) => (a[i] = v))
  return a
}
const FAM: Record<Family, { kick: number[]; snare: number[]; hat: number[]; ohat: number[]; swing: number; bass: [number, number][] }> = {
  four: { kick: arr([0, 4, 8, 12]), snare: arr([4, 12], 0.8), hat: arr([2, 6, 10, 14], 0.6).map((v, i) => v || (i % 2 ? 0.25 : 0)), ohat: arr([2, 6, 10, 14], 0.5), swing: 0, bass: [[2, 2], [6, 2], [10, 2], [14, 2]] },
  boom: { kick: arr([0, 7, 10]), snare: arr([4, 12]), hat: arr([0, 2, 4, 6, 8, 10, 12, 14], 0.55), ohat: z(), swing: 0.16, bass: [[0, 6], [7, 3], [10, 5]] },
  trap: { kick: arr([0, 3, 10]), snare: arr([8], 1), hat: arr([0, 2, 4, 6, 8, 10, 12, 13, 14, 15], 0.5), ohat: arr([6], 0.6), swing: 0, bass: [[0, 6], [3, 3], [10, 5]] },
  dnb: { kick: arr([0, 10]), snare: arr([4, 12]), hat: arr([0, 2, 4, 6, 8, 10, 12, 14], 0.5), ohat: arr([14], 0.4), swing: 0, bass: [[0, 4], [6, 2], [10, 4], [14, 2]] },
  amb: { kick: arr([0], 0.55), snare: z(), hat: arr([4, 12], 0.25), ohat: z(), swing: 0, bass: [[0, 16]] },
  rock: { kick: arr([0, 6, 8, 14], 0.95), snare: arr([4, 12]), hat: arr([0, 2, 4, 6, 8, 10, 12, 14], 0.55), ohat: z(), swing: 0, bass: [[0, 2], [2, 2], [4, 2], [6, 2], [8, 2], [10, 2], [12, 2], [14, 2]] },
  latin: { kick: arr([0, 6, 8, 14]), snare: arr([3, 6, 11, 14], 0.7), hat: arr([0, 2, 4, 6, 8, 10, 12, 14], 0.45), ohat: z(), swing: 0.04, bass: [[0, 3], [6, 2], [8, 3], [14, 2]] },
}
const KEYROOT: Record<string, number> = { C: 48, 'C#': 49, D: 50, Eb: 51, E: 52, F: 53, G: 55, A: 57, Bb: 58 }

function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function buildPattern(v: Vibe): Pattern {
  const f = FAM[v.family]
  const root = KEYROOT[v.key] ?? 57
  const prog = v.minor ? [0, 8, 3, 10] : [0, 7, 9, 5]
  const qual = v.minor ? ['m', 'M', 'M', 'M'] : ['M', 'M', 'm', 'M']
  const seed = (v.index + 1) * 2654435761
  const r = rng(seed)
  const scale = v.minor ? [0, 2, 3, 5, 7, 8, 10] : [0, 2, 4, 5, 7, 9, 11]
  const jazzy = v.id === 'jazz-lounge' || v.id === 'lo-fi-chill' || v.id === 'r-b-slow-jam' || v.id === 'gospel-soul'
  const chords = prog.map((p, i) => {
    const base = root + 12 + p
    const third = qual[i] === 'm' ? 3 : 4
    const tones = [base, base + third, base + 7]
    if (jazzy) tones.push(base + (qual[i] === 'm' ? 10 : 11), base + 14)
    return tones
  })
  const bass: Note[][] = prog.map((p, bar) =>
    f.bass.map(([s, l], j) => ({ s, m: root - 12 + p + (v.family === 'rock' && j % 2 ? 7 * 0 : 0) + (j === 2 && bar % 2 ? 12 : 0), l })),
  )
  const lead: Note[][] = prog.map((p, bar) => {
    const notes: Note[] = []
    const slots = v.family === 'amb' ? [0, 8] : [0, 3, 6, 8, 11, 14]
    let deg = bar * 2
    slots.forEach((s, i) => {
      if (r() < 0.25 && i > 0) return
      deg = Math.max(0, Math.min(13, deg + Math.floor(r() * 5) - 2))
      const oct = Math.floor(deg / 7)
      notes.push({ s, m: root + 24 + p * 0 + scale[deg % 7] + oct * 12, l: i === slots.length - 1 ? 3 : v.family === 'amb' ? 8 : 2 + Math.floor(r() * 2) })
    })
    return notes
  })
  return {
    bpm: v.bpm, family: v.family, keyName: v.key + (v.minor ? ' minor' : ' major'), minor: v.minor, root,
    kick: [...f.kick], snare: [...f.snare], hat: [...f.hat], ohat: [...f.ohat], bass, chords, lead, swing: f.swing, seed,
  }
}

/** Mock overview peaks for a stem lane (0..1), deterministic. Shaped by the real pattern so it reads like the audio. */
export function stemPeaks(stem: StemId, p: Pattern, n = 320): Float32Array {
  const out = new Float32Array(n)
  const r = rng(p.seed + stem.length * 977)
  const stepsTotal = BARS * 16
  for (let i = 0; i < n; i++) {
    const pos = (i / n) * stepsTotal
    const bar = Math.floor(pos / 16)
    const step = Math.floor(pos % 16)
    const frac = pos - Math.floor(pos)
    // song arc: intro, build, drop, outro
    const arc = bar < 2 ? 0.45 : bar < 4 ? 0.7 : bar < 12 ? 1 : bar < 14 ? 0.8 : 0.5
    const gap = stem === 'voice' ? ((bar % 4) === 3 || bar < 2 ? 0 : 1) : stem === 'drums' && bar < 1 ? 0.3 : 1
    let a = 0
    if (stem === 'drums') {
      const k = p.kick[step] ?? 0, s = p.snare[step] ?? 0, h = p.hat[step] ?? 0
      const env = Math.exp(-frac * 3.2)
      a = Math.max(k * 0.95, s * 0.8, h * 0.4) * (0.35 + 0.65 * env)
    } else if (stem === 'bass') {
      const nts = p.bass[bar % 4]
      const hit = nts.find((nn) => step >= nn.s && step < nn.s + nn.l)
      a = hit ? 0.55 + 0.2 * Math.exp(-(pos - (bar * 16 + hit.s)) * 0.5) : 0.04
    } else if (stem === 'keys') {
      a = 0.32 + 0.18 * Math.exp(-((pos % 16) / 6)) + (step % 4 === 0 ? 0.08 : 0)
    } else {
      const nts = p.lead[bar % 4]
      const hit = nts.find((nn) => step >= nn.s && step < nn.s + nn.l)
      a = hit ? 0.5 + 0.2 * Math.sin(pos * 0.9) : 0.03
    }
    out[i] = Math.max(0.015, Math.min(1, a * arc * gap * (0.88 + r() * 0.24)))
  }
  return out
}

export const midiName = (m: number) => ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'][m % 12] + (Math.floor(m / 12) - 1)
