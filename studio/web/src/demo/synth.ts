// Genre-aware procedural synthesizer for the browser demo. Drums, bass, chords and lead are written by
// rule (see genres.ts) and rendered by plain DSP (see voices.ts). This is NOT AI generation and the UI says so.
import { type Audio, biquad, scale, peak, sum, saturate, bitcrush, delayFx, chorus, widen, reverb, compress } from './dsp'
import * as V from './voices'
import { SR, midiHz, rngFor, fnv, lp1, type Rng } from './voices'
import { KICKS, SNARES, MODES, PROFILES, matchProfile, profileFor, DEFAULT_PROFILE, PROFILE_BY_ID, type Profile, type Mode, type ChordVoice, type ChordLayer, type Lane } from './genres'

export { SR }
const NOTE_INDEX: Record<string, number> = { C: 0, 'C#': 1, DB: 1, D: 2, 'D#': 3, EB: 3, E: 4, F: 5, 'F#': 6, GB: 6, G: 7, 'G#': 8, AB: 8, A: 9, 'A#': 10, BB: 10, B: 11 }
const MINORISH: Mode[] = ['minor', 'dorian', 'phrygian']

export type Spec = {
  prompt: string; bpm: number; keyRoot: number; minor: boolean; mode: Mode; genre: string; swing: number
  progression: number[]; brightness: number; bars: number; seed: number; profile: Profile
}
export const keyName = (s: Spec) => `${['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'][s.keyRoot]} ${s.minor ? 'minor' : 'major'}`
export { PROFILES }

export function parsePrompt(prompt: string, bpm?: number | null, key?: string | null, durationS?: number | null, genreId?: string | null): Spec {
  const text = prompt.toLowerCase()
  const p = profileFor(genreId) ?? matchProfile(text) ?? PROFILE_BY_ID[DEFAULT_PROFILE]
  const seed = fnv(prompt + '|' + p.id)
  const s: Spec = {
    prompt, bpm: p.bpm, keyRoot: p.root, minor: MINORISH.includes(p.mode), mode: p.mode, genre: p.id, swing: p.swing,
    progression: [...p.progs[seed % p.progs.length]], brightness: 0.5, bars: 8, seed, profile: p,
  }
  const m = text.match(/(\d{2,3})\s*bpm/)
  if (m) s.bpm = parseInt(m[1])
  if (bpm) s.bpm = Math.round(bpm)
  s.bpm = Math.max(50, Math.min(190, s.bpm))
  const km = key ? key.match(/^\s*([A-Ga-g])([#b]?)\s*(major|minor|maj|min|m)?/) : prompt.match(/\bin\s+([A-G])([#b]?)\s*(major|minor|maj|min|m)?\b/)
  let q = ''
  if (km) {
    const root = (km[1] + km[2]).toUpperCase()
    if (root in NOTE_INDEX) s.keyRoot = NOTE_INDEX[root]
    q = (km[3] || '').toLowerCase()
  } else if (['happy', 'bright', 'uplifting', 'sunny'].some((w) => text.includes(w))) q = 'major'
  if ((q === 'major' || q === 'maj') && s.minor) { s.mode = 'major'; s.minor = false }
  else if ((q === 'minor' || q === 'min' || q === 'm') && !s.minor) { s.mode = 'minor'; s.minor = true }
  if (text.includes('dark') || text.includes('sad')) s.brightness = 0.35
  if (['bright', 'airy', 'shimmer'].some((w) => text.includes(w))) s.brightness = 0.7
  const target = durationS || 16
  const barS = (4 * 60) / s.bpm
  const minBars = p.structure === 'groove' ? 4 : 8
  s.bars = Math.round(Math.max(minBars, Math.min(32, Math.round(target / barS / 4) * 4 || 4)))
  return s
}

export type NoteEvent = { stem: string; pitch: number; start: number; dur: number; vel: number }

// ------------------------------------------------------------------ arrangement
type BarPlan = {
  kick: boolean; back: boolean; hat: boolean; perc: boolean; fill: boolean; crash: boolean; roll: number; riser: number
  bass: number; chords: number; lead: number; vel: number; cut: boolean; filter: number; layers: number; name: string
}
const plan0 = (): BarPlan => ({ kick: true, back: true, hat: true, perc: true, fill: false, crash: false, roll: 0, riser: 0, bass: 1, chords: 1, lead: 1, vel: 1, cut: false, filter: 1, layers: 9, name: 'main' })

export function makePlan(p: Profile, N: number, barS: number): BarPlan[] {
  const out: BarPlan[] = []
  const nLayers = p.chords.length
  for (let b = 0; b < N; b++) {
    const q = plan0()
    const last = b === N - 1
    switch (p.structure) {
      case 'edm': {
        const intro = Math.max(2, Math.round(N * 0.25)), build = Math.max(1, Math.round(N * 0.125)), outro = Math.max(1, Math.round(N * 0.125))
        const dropStart = intro + build, dropEnd = N - outro
        if (b < intro) {
          Object.assign(q, { name: 'intro', back: false, perc: b >= intro / 2, bass: 0, lead: 0, layers: 1, filter: 0.15 + 0.35 * (b / intro), vel: 0.85 })
        } else if (b < dropStart) {
          const k = b - intro
          Object.assign(q, { name: 'build', kick: false, back: false, roll: build === 1 ? 2 : k === build - 1 ? 3 : 1, bass: 0, lead: 0, layers: 1, filter: 0.5 + 0.5 * ((k + 1) / build), vel: 0.8 + 0.2 * ((k + 1) / build), riser: k === 0 ? build * barS : 0 })
        } else if (b < dropEnd) {
          Object.assign(q, { name: 'drop', crash: b === dropStart, fill: (b - dropStart) % 4 === 3 && b !== dropEnd - 1 })
        } else {
          Object.assign(q, { name: 'outro', perc: false, lead: 0, bass: 0.7, vel: 0.85, layers: 1, filter: 0.7, cut: last })
        }
        break
      }
      case 'groove': {
        if (N >= 8 && b === 0) Object.assign(q, { name: 'intro', kick: false, back: false, perc: false, bass: 0, lead: 0, filter: 0.6, vel: 0.8 })
        else if (last) Object.assign(q, { name: 'outro', cut: true, lead: 0, vel: 0.9 })
        else if (b < N / 2) Object.assign(q, { name: 'verse', lead: 0.5, fill: b % 4 === 3 })
        else Object.assign(q, { name: 'hook', lead: 1, fill: b % 4 === 3 })
        break
      }
      case 'band': {
        const intro = N >= 12 ? 2 : 1
        const lay = Math.max(1, nLayers - 1)
        if (b < intro) Object.assign(q, { name: 'intro', kick: false, back: false, bass: 0, lead: 0, layers: 1, vel: 0.8, fill: b === intro - 1 })
        else if (last) Object.assign(q, { name: 'outro', cut: true, crash: true, lead: 0, vel: 1 })
        else if (b < N / 2) Object.assign(q, { name: 'verse', lead: 0.5, layers: lay, vel: 0.92, fill: b % 4 === 3 })
        else Object.assign(q, { name: 'chorus', lead: 1, vel: 1.05, crash: b === Math.floor(N / 2) || (b - Math.floor(N / 2)) % 4 === 0, fill: b % 4 === 3 })
        break
      }
      case 'ambient': {
        Object.assign(q, { name: 'drift', kick: false, back: false, hat: false, bass: b >= 1 ? 1 : 0, lead: b >= N / 4 ? 1 : 0, layers: b >= N / 2 ? 9 : 1, filter: 0.4 + 0.6 * (b / Math.max(1, N - 1)), vel: 0.8 + 0.2 * (b / N) })
        break
      }
      case 'cinematic': {
        const third = Math.floor(N / 3), two = Math.floor((2 * N) / 3)
        if (b < third) Object.assign(q, { name: 'rise', kick: false, back: false, hat: false, perc: false, layers: 1, lead: b >= 2 ? 0.5 : 0, vel: 0.7, filter: 0.5 })
        else if (b < two) Object.assign(q, { name: 'march', back: false, hat: false, layers: 1, lead: 1, vel: 0.85, fill: b === two - 1 })
        else Object.assign(q, { name: 'climax', crash: b === two, lead: 1, vel: 1.05, layers: 9, cut: last, fill: false })
        break
      }
    }
    out.push(q)
  }
  return out
}

// ------------------------------------------------------------------ helpers
const VEL: Record<string, number> = { x: 0.85, X: 1, o: 0.55, g: 0.3 }
const GM: Record<string, number> = { kick: 36, snare: 38, clap: 39, snap: 39, rim: 37, hat: 42, ohat: 46, shaker: 70, conga: 63, cowbell: 56, tom: 45, ride: 51, brush: 38 }
const VOICES: Record<ChordVoice, V.Voice> = {
  rhodes: V.rhodes, piano: V.piano, organ: V.organ, supersaw: V.supersaw, pad: V.pad, strings: V.strings, brass: V.brass,
  choir: V.choir, harmonium: V.harmonium, guitar: V.pluckGuitar, distPalm: V.distGuitar(true), dist: V.distGuitar(false),
  bell: V.bell, pluck: V.pluckSynth, stab: V.stab, square: V.squareLead,
}
const mod12 = (n: number) => ((n % 12) + 12) % 12

const SHOT_GAIN: Record<string, number> = { hat: 2, ohat: 1.8, ride: 2.6, cowbell: 0.45, shaker: 1.3 }
function makeShot(name: string, r: Rng): Float32Array {
  const y = rawShot(name, r), g = SHOT_GAIN[name.split(':')[0]]
  if (g) for (let i = 0; i < y.length; i++) y[i] *= g
  return y
}
function rawShot(name: string, r: Rng): Float32Array {
  const [base, arg] = name.split(':')
  switch (base) {
    case 'kick': return V.kick(KICKS[arg] ?? KICKS.boom)
    case 'snare': return V.snare(SNARES[arg] ?? SNARES.boom, r)
    case 'clap': return V.clap(r)
    case 'snap': return V.snap(r)
    case 'rim': return V.rim(r)
    case 'hat': return arg === 'trap' ? V.hat(r, false, 420, 8200) : V.hat(r, false)
    case 'ohat': return V.hat(r, true)
    case 'shaker': return V.shaker(r)
    case 'conga': return V.conga(arg === 'lo' ? 190 : 290)
    case 'cowbell': return V.cowbell()
    case 'tom': return V.tom(({ lo: 72, mid: 108, hi: 150 } as Record<string, number>)[arg] ?? 100)
    case 'ride': return V.ride(r)
    case 'brush': return V.brush(r)
    default: return V.rim(r)
  }
}
function add(dst: Float32Array, src: Float32Array, start: number, g: number): void {
  const s0 = Math.max(0, Math.round(start))
  const n = Math.min(src.length, dst.length - s0)
  for (let i = 0; i < n; i++) dst[s0 + i] += src[i] * g
}

type Stem = { mono: Float32Array; notes: NoteEvent[]; kicks: number[] }

class Timing {
  private spec: Spec
  stepDur: number
  private r: Rng
  constructor(spec: Spec, stepDur: number, r: Rng) { this.spec = spec; this.stepDur = stepDur; this.r = r }
  at(bar: number, step: number, humanMs = 0): number {
    const p = this.spec.profile, grid = p.swingGrid ?? 16
    let st = step
    if (grid === 16 && step % 2 === 1) st += this.spec.swing
    else if (grid === 8 && step % 4 === 2) st += this.spec.swing * 2
    return (bar * 16 + st) * this.stepDur + ((this.r.random() - 0.5) * 2 * humanMs) / 1000
  }
}

// ------------------------------------------------------------------ drums
function renderDrums(s: Spec, plans: BarPlan[], total: number, r: Rng, tm: Timing): Stem {
  const p = s.profile, buf = new Float32Array(total), notes: NoteEvent[] = [], kicks: number[] = []
  const human = p.human ?? 4, stepDur = tm.stepDur, barS = stepDur * 16
  const cache = new Map<string, Float32Array[]>(), hits = new Map<string, number>()
  const shot = (name: string): Float32Array => {
    let v = cache.get(name)
    if (!v) { const n = /^(hat|ohat|shaker|rim|snare|clap|snap|brush)/.test(name) ? 3 : 1; v = Array.from({ length: n }, () => makeShot(name, r)); cache.set(name, v) }
    const k = hits.get(name) ?? 0; hits.set(name, k + 1)
    return v[k % v.length]
  }
  const gmFor = (name: string) => { const [b, a] = name.split(':'); return b === 'tom' ? ({ lo: 45, mid: 47, hi: 50 } as Record<string, number>)[a] ?? 47 : b === 'conga' ? (a === 'lo' ? 64 : 63) : GM[b] ?? 38 }
  const hit = (name: string, t: number, vel: number) => {
    const sig = shot(name)
    add(buf, sig, t * SR, vel)
    notes.push({ stem: 'drums', pitch: gmFor(name), start: Math.max(0, t), dur: 0.1, vel: Math.max(1, Math.min(127, Math.round(vel * 105))) })
    if (name.startsWith('kick')) kicks.push(Math.max(0, t))
  }
  const snareLane = p.drums.lanes.find((l) => l.role === 'back' && l.voice.startsWith('snare')) ?? p.drums.lanes.find((l) => l.role === 'back')
  const fillVoice = p.drums.fill === 'tom' ? null : (snareLane?.voice ?? 'snare:boom')
  const allowed = (l: Lane, q: BarPlan) => (l.role === 'kick' ? q.kick : l.role === 'back' ? q.back : l.role === 'hat' ? q.hat : q.perc)
  for (let b = 0; b < plans.length; b++) {
    const q = plans[b]
    const bt = b * barS
    for (const l of p.drums.lanes) {
      if (!allowed(l, q)) continue
      const n = l.pat.length
      const idx = b % 4 === 3 && n > 1 ? n - 1 : b % Math.max(1, n > 1 ? n - 1 : 1)
      const pat = l.pat[idx]
      for (let st = 0; st < 16; st++) {
        const ch = pat[st]
        const v0 = VEL[ch]
        if (!v0) continue
        if (q.cut && st >= 8) continue
        if (q.fill && st >= 12 && l.role !== 'kick' && l.role !== 'hat') continue
        const vel = Math.min(1.2, v0 * (l.gain ?? 1) * q.vel * (0.92 + r.random() * 0.16))
        const t = tm.at(b, st, l.role === 'kick' ? human * 0.5 : human)
        const roll = l.rolls && l.rolls.at.includes(st) && r.random() < l.rolls.prob ? l.rolls : null
        if (roll) {
          const span = (roll.steps ?? 1) * stepDur
          for (let k = 0; k < roll.sub; k++) hit(l.voice, t + (k * span) / roll.sub, vel * (0.55 + 0.45 * ((k + 1) / roll.sub)))
        } else hit(l.voice, t, vel)
      }
    }
    // fills and builds
    if (q.fill && p.drums.fill !== 'none') {
      if (p.drums.fill === 'tom') {
        const seq = ['tom:hi', 'tom:hi', 'tom:mid', 'tom:mid', 'tom:lo', 'tom:lo']
        for (let k = 0; k < 6; k++) hit(seq[k], bt + (12 + k * (4 / 6)) * stepDur, 0.7 + 0.05 * k)
      } else {
        for (let k = 0; k < 8; k++) hit(fillVoice!, bt + (12 + k * 0.5) * stepDur, 0.45 + 0.07 * k)
      }
    }
    if (q.roll) {
      const v = fillVoice ?? 'snare:boom'
      const sub = q.roll === 1 ? 2 : q.roll === 2 ? 4 : 4
      for (let k = 0; k < 16 * (sub / 4) * (q.roll === 1 ? 2 : 1); k++) {
        const stepPos = (k * 4) / sub
        if (q.roll === 3 && stepPos < 8) { if (k % 2) continue }
        const frac = stepPos / 16
        const finalHalf = q.roll === 3 && stepPos >= 12
        if (finalHalf) hit(v, bt + stepPos * stepDur, 0.5 + 0.5 * frac)
        else hit(v, bt + stepPos * stepDur, 0.35 + 0.5 * frac)
      }
    }
    if (q.crash) {
      add(buf, V.crash(r), bt * SR, 0.7)
      notes.push({ stem: 'drums', pitch: 49, start: bt, dur: 0.8, vel: 100 })
    }
    if (q.riser > 0) add(buf, V.riser(q.riser, r), bt * SR, 0.55)
  }
  return { mono: buf, notes, kicks }
}

// ------------------------------------------------------------------ harmony
function chordPcs(s: Spec, deg: number, ext: number): number[] {
  const sc = MODES[s.mode], out: number[] = []
  for (let k = 0; k < ext; k++) { const d = deg + 2 * k; out.push(mod12(s.keyRoot + sc[d % 7] + 12 * Math.floor(d / 7))) }
  return out
}
const nearest = (pc: number, around: number) => { let n = around - mod12(around - pc); if (around - n > 6) n += 12; return n }
function voiceLead(prev: number[], pcs: number[], center: number): number[] {
  let tones: number[]
  if (!prev.length) {
    tones = []
    let cur = center - 7
    for (const pc of pcs) { let n = cur + mod12(pc - cur); if (tones.length && n <= tones[tones.length - 1]) n += 12; tones.push(n); cur = n }
  } else {
    const free = [...pcs]
    tones = []
    for (const pv of [...prev].sort((a, b) => a - b)) {
      if (!free.length) break
      let bi = 0, bd = 99
      free.forEach((pc, i) => { const d = Math.abs(nearest(pc, pv) - pv); if (d < bd) { bd = d; bi = i } })
      tones.push(nearest(free[bi], pv)); free.splice(bi, 1)
    }
    for (const pc of free) tones.push(nearest(pc, center))
  }
  return tones.map((n) => { while (n > center + 14) n -= 12; while (n < center - 10) n += 12; return n }).sort((a, b) => a - b)
}
function holdSteps(pat: string, st: number, hold: number): number {
  let nx = 16
  for (let k = st + 1; k < 16; k++) if (pat[k] !== '.') { nx = k; break }
  return Math.max(1, Math.min(nx - st, hold))
}
function patFor(pats: string[], b: number): string { const n = pats.length; return pats[b % 4 === 3 && n > 1 ? n - 1 : b % Math.max(1, n > 1 ? n - 1 : 1)] }

function renderBass(s: Spec, plans: BarPlan[], total: number, r: Rng, tm: Timing): Stem {
  const p = s.profile, bs = p.bass, buf = new Float32Array(total), notes: NoteEvent[] = []
  if (!bs) return { mono: buf, notes, kicks: [] }
  const stepDur = tm.stepDur, human = (p.human ?? 4) * 0.4
  let prevF = 0, prevEnd = -9
  for (let b = 0; b < plans.length; b++) {
    const q = plans[b]
    if (!q.bass) continue
    const deg = s.progression[b % s.progression.length]
    const pcs = chordPcs(s, deg, 4)
    let rootM = bs.lo + mod12(pcs[0] - bs.lo)
    const pat = patFor(bs.pat, b)
    const nextDeg = s.progression[(b + 1) % s.progression.length]
    const nextRoot = bs.lo + mod12(chordPcs(s, nextDeg, 3)[0] - bs.lo)
    for (let st = 0; st < 16; st++) {
      const ch = pat[st]
      if (ch === '.' || (q.cut && st >= 8)) continue
      let pitch = rootM
      if (bs.walk) {
        const beat = st / 4
        pitch = beat === 0 ? rootM : beat === 1 ? bs.lo + mod12(pcs[r.random() < 0.5 ? 1 : 2] - bs.lo) : beat === 2 ? bs.lo + mod12(pcs[2] - bs.lo) : nextRoot + (r.random() < 0.5 ? -1 : 1)
      } else if (ch === '5') pitch = rootM + 7
      else if (ch === 'o') pitch = rootM + 12
      else if (ch === 'b') pitch = rootM + 10
      else if (ch === '3') pitch = bs.lo + mod12(pcs[1] - bs.lo)
      const gateSteps = holdSteps(pat, st, bs.hold ?? 4)
      const t = tm.at(b, st, human)
      const f = midiHz(pitch), gate = Math.round(gateSteps * stepDur * SR * 0.96)
      const slide = bs.glide && prevF && prevF !== f && t - prevEnd < stepDur * 1.5 && Math.abs(Math.log2(f / prevF)) <= 1
      const vel = Math.min(1.1, (ch === 'x' || ch === 'X' ? 0.9 : 0.8) * q.bass * q.vel * (0.93 + r.random() * 0.14))
      const sig = V.bassNote(bs.kind, f, gate, vel, r, { glideFrom: slide ? prevF : undefined, glideTau: bs.glide, lfoHz: bs.lfo ? bs.lfo * (s.bpm / 140) : undefined, drive: bs.drive, decay: bs.decay })
      add(buf, sig, t * SR, 1)
      notes.push({ stem: 'bass', pitch, start: Math.max(0, t), dur: gateSteps * stepDur, vel: Math.round(vel * 100) })
      prevF = f; prevEnd = t + gateSteps * stepDur
    }
    void rootM
  }
  return { mono: buf, notes, kicks: [] }
}

function renderChords(s: Spec, plans: BarPlan[], total: number, r: Rng, tm: Timing): Stem {
  const p = s.profile, buf = new Float32Array(total), notes: NoteEvent[] = []
  const stepDur = tm.stepDur, human = (p.human ?? 4) * 0.6
  p.chords.forEach((L: ChordLayer, li) => {
    const voice = VOICES[L.voice], gainL = L.gain ?? 1
    let prev: number[] = [], hitN = 0
    for (let b = 0; b < plans.length; b++) {
      const q = plans[b]
      if (!q.chords || li >= q.layers) continue
      const deg = s.progression[b % s.progression.length]
      const pcs = chordPcs(s, deg, L.ext ?? 4)
      let tones: number[]
      if (L.style === 'power') {
        const root = L.center - 6 + mod12(pcs[0] - (L.center - 6))
        tones = [root, root + 7, root + 12]
      } else { tones = voiceLead(prev, pcs, L.center); prev = tones }
      const pat = patFor(L.pat, b)
      for (let st = 0; st < 16; st++) {
        const ch = pat[st]
        if (ch === '.' || (q.cut && st >= 12 && L.style !== 'block')) continue
        const gateSteps = holdSteps(pat, st, L.hold ?? 4)
        const gate = Math.round(gateSteps * stepDur * SR * (L.style === 'block' && gateSteps >= 8 ? 1.02 : 0.95))
        const t0 = tm.at(b, st, human)
        const vel0 = Math.min(1.1, (VEL[ch] ?? 0.8) * q.vel * q.chords * gainL * (0.92 + r.random() * 0.16))
        const emit = (pitch: number, off: number, vel: number, gate_: number) => {
          let sig = voice(midiHz(pitch), gate_, vel, r)
          if (q.filter < 1 && (L.voice === 'pad' || L.voice === 'supersaw' || L.voice === 'strings' || L.voice === 'stab')) sig = lp1(sig, 380 + q.filter * q.filter * 9000)
          add(buf, sig, (t0 + off) * SR, 1)
          notes.push({ stem: 'chords', pitch, start: Math.max(0, t0 + off), dur: gate_ / SR, vel: Math.round(Math.min(1, vel) * 100) })
        }
        if (L.style === 'arp') {
          const n = tones.length, k = hitN++ % (2 * n - 2 || 1)
          const pick = k < n ? k : 2 * n - 2 - k
          emit(tones[pick] + (L.octave ?? 0) * 12, 0, vel0 * 0.9, gate)
        } else if (L.style === 'strum') {
          const down = ch !== 'o', ms = (L.strumMs ?? 14) / 1000
          const order = down ? tones : [...tones].reverse()
          order.forEach((tn, i) => emit(tn, i * ms, vel0 * (down ? 1 : 0.7), gate))
        } else {
          const ms = (L.strumMs ?? 0) / 1000
          tones.forEach((tn, i) => emit(tn, i * ms + (r.random() - 0.5) * 0.004, vel0 / Math.sqrt(Math.max(1, tones.length / 3)) * (i === 0 ? 1 : 0.92), gate))
        }
      }
    }
  })
  return { mono: buf, notes, kicks: [] }
}

function renderLead(s: Spec, plans: BarPlan[], total: number, r: Rng, tm: Timing): Stem {
  const p = s.profile, L = p.lead, buf = new Float32Array(total), notes: NoteEvent[] = []
  if (!L) return { mono: buf, notes, kicks: [] }
  const voice = VOICES[L.voice], sc = MODES[s.mode], stepDur = tm.stepDur, human = (p.human ?? 4) * 0.8
  const pool = L.pent ? (MINORISH.includes(s.mode) ? [0, 2, 3, 4, 6] : [0, 1, 2, 4, 5]) : [0, 1, 2, 3, 4, 5, 6]
  const tonic = L.base - 12 + mod12(s.keyRoot - (L.base - 12))
  const toMidi_ = (pi: number) => tonic + sc[pool[pi % pool.length]] + 12 * Math.floor(pi / pool.length)
  const lastIdx = pool.length * 2 - 1
  // build one four bar phrase: A A' A B, repeated for the whole piece so the hook is memorable
  type Bar = { pat: string; idx: number[] }
  const mk = (pat: string, start: number): Bar => {
    let pi = start
    const idx: number[] = []
    for (let i = 0; i < pat.length; i++) if (pat[i] !== '.') {
      pi = Math.max(0, Math.min(lastIdx, pi + [-2, -1, 0, 1, 1, 2][r.int(0, 6)]))
      idx.push(pi)
    }
    return { pat, idx }
  }
  const rh = L.rhythms
  const a = mk(rh[r.int(0, rh.length)], pool.length + r.int(0, 3))
  const a2: Bar = { pat: a.pat, idx: a.idx.map((x, i) => (i >= a.idx.length - 2 ? Math.max(0, Math.min(lastIdx, x + (r.random() < 0.5 ? 1 : -1))) : x)) }
  const bb = mk(rh[r.int(0, rh.length)], a.idx[a.idx.length - 1] ?? pool.length)
  bb.idx = bb.idx.map((x, i) => (i === bb.idx.length - 1 ? pool.length : x))
  const phrase = [a, a2, a, bb]
  const on = plans.map((q, b) => (q.lead >= 1 ? true : q.lead > 0 ? b % 2 === 0 : false) && (b % 4 === 0 ? true : r.random() < (L.prob ?? 1)))
  for (let b = 0; b < plans.length; b++) {
    const q = plans[b]
    if (!on[b]) continue
    const bar = phrase[b % 4]
    const pcs = chordPcs(s, s.progression[b % s.progression.length], 4)
    const att: number[] = []
    for (let st = 0; st < 16; st++) if (bar.pat[st] !== '.') att.push(st)
    att.forEach((st, k) => {
      if (q.cut && st >= 8) return
      let pitch = toMidi_(bar.idx[k])
      if (st % 4 === 0 && !pcs.includes(mod12(pitch))) {
        let best = pitch, bd = 99
        for (const pc of pcs) { const c = nearest(pc, pitch); for (const cand of [c, c + 12]) { const d = Math.abs(cand - pitch); if (d < bd) { bd = d; best = cand } } }
        if (bd <= 3) pitch = best
      }
      if (b % 4 === 3 && k === att.length - 1) pitch = nearest(pcs[0], pitch)
      const nextSt = k + 1 < att.length ? att[k + 1] : 16
      const steps = Math.max(1, Math.min(nextSt - st, L.len ?? 2))
      const gate = Math.round(steps * stepDur * SR * 0.95)
      const t = tm.at(b, st, human)
      const vel = Math.min(1.05, (bar.pat[st] === 'X' ? 1 : 0.85) * q.vel * (L.gain ?? 1) * (0.9 + r.random() * 0.2))
      add(buf, voice(midiHz(pitch), gate, vel, r), t * SR, 1)
      notes.push({ stem: 'lead', pitch, start: Math.max(0, t), dur: steps * stepDur, vel: Math.round(Math.min(1, vel) * 100) })
    })
  }
  return { mono: buf, notes, kicks: [] }
}

// ------------------------------------------------------------------ mix
function stereo(mono: Float32Array, width: number, pan: number): Audio {
  const a: Audio = { sr: SR, ch: [mono.slice(), mono.slice()] }
  if (width > 0) {
    // short Haas offset gives a wider image without touching mono compatibility much
    const d = Math.round(0.011 * SR)
    for (let i = a.ch[1].length - 1; i >= 0; i--) a.ch[1][i] = (i >= d ? mono[i - d] : 0) * width + mono[i] * (1 - width)
  }
  if (pan) { const l = Math.cos(((pan + 1) * Math.PI) / 4), rr = Math.sin(((pan + 1) * Math.PI) / 4); for (let i = 0; i < a.ch[0].length; i++) { a.ch[0][i] *= l * Math.SQRT2; a.ch[1][i] *= rr * Math.SQRT2 } }
  return a
}
function rms(x: Float32Array): number { let s = 0; for (let i = 0; i < x.length; i++) s += x[i] * x[i]; return Math.sqrt(s / Math.max(1, x.length)) }
function duck(a: Audio, kicks: number[], depth: number, rel = 0.16): void {
  if (!depth || !kicks.length) return
  const n = a.ch[0].length, g = new Float32Array(n).fill(1), len = Math.round(rel * 4 * SR)
  for (const k of kicks) {
    const i0 = Math.round(k * SR)
    for (let j = 0; j < len && i0 + j < n; j++) { const v = 1 - depth * Math.exp(-j / (rel * SR)) * Math.min(1, j / (0.004 * SR)) ; if (v < g[i0 + j]) g[i0 + j] = v }
  }
  for (const ch of a.ch) for (let i = 0; i < n; i++) ch[i] *= g[i]
}
const softclip = (a: Audio, lim = 0.95) => { for (const ch of a.ch) for (let i = 0; i < ch.length; i++) { const x = ch[i]; if (Math.abs(x) > 0.7) ch[i] = Math.sign(x) * (0.7 + (lim - 0.7) * Math.tanh((Math.abs(x) - 0.7) / (lim - 0.7))) } }

export const STEM_NAMES = ['drums', 'bass', 'chords', 'lead'] as const
export type Rendered = { mix: Audio; stems: Record<string, Audio>; notes: NoteEvent[]; spec: Spec }
const tick = () => new Promise<void>((r) => setTimeout(r, 0))
const TARGET_RMS = { drums: 0.105, bass: 0.12, chords: 0.105, lead: 0.095 }

export async function renderSpec(s: Spec, progress?: (p: number, msg: string) => void): Promise<Rendered> {
  const p = s.profile, r = rngFor(s.seed), barS = (4 * 60) / s.bpm, stepDur = barS / 16
  const total = Math.floor((s.bars * barS + 1.6) * SR)
  const plans = makePlan(p, s.bars, barS), tm = new Timing(s, stepDur, r)
  const mx = p.mix
  const raw: Record<string, Stem> = {}
  const order: [string, () => Stem][] = [
    ['drums', () => renderDrums(s, plans, total, r, tm)],
    ['bass', () => renderBass(s, plans, total, r, tm)],
    ['chords', () => renderChords(s, plans, total, r, tm)],
    ['lead', () => renderLead(s, plans, total, r, tm)],
  ]
  let i = 0
  for (const [name, fn] of order) {
    progress?.(0.1 + 0.2 * i++, `Synthesizing ${name} (demo synth)`)
    await tick()
    raw[name] = fn()
  }
  progress?.(0.75, 'Mixing (demo synth)')
  await tick()
  const kicks = raw.drums.kicks
  const stems: Record<string, Audio> = {}
  const lvl = (name: keyof typeof TARGET_RMS, a: Audio) => { const g = (TARGET_RMS[name] * mx.gains[name]) / (rms(a.ch[0]) || 1); scale(a, Math.min(g, 20)) }
  // drums
  { const a = stereo(raw.drums.mono, 0, 0)
    if (mx.drumsLp) biquad(a, 'lowpass', mx.drumsLp)
    if (mx.drumsSat) saturate(a, mx.drumsSat, 0.6)
    if (mx.crush) bitcrush(a, mx.crush, 0.3)
    compress(a, -16, 2.2, 8, 110, 1.5)
    lvl('drums', a); softclip(a); stems.drums = a }
  // bass
  { const a = stereo(raw.bass.mono, 0, 0)
    biquad(a, 'highpass', 26)
    if (mx.bassSat) saturate(a, mx.bassSat, 0.5)
    duck(a, kicks, (mx.pump ?? 0) * 0.9, 0.12)
    lvl('bass', a); softclip(a); stems.bass = a }
  // chords
  { const a = stereo(raw.chords.mono, 0.8, 0)
    const lpHz = (mx.chordsLp ?? 9000) * (0.6 + 0.8 * s.brightness)
    biquad(a, 'lowpass', lpHz)
    biquad(a, 'highpass', 90)
    if (mx.chordsChorus) chorus(a, 0.35, 0.5, 14, 0.1, mx.chordsChorus)
    if (mx.crush) bitcrush(a, mx.crush + 2, 0.25)
    duck(a, kicks, mx.pump ?? 0)
    if (mx.chordsRev) reverb(a, 0.6, 0.55, 1, mx.chordsRev)
    if (mx.vinyl) { const n = V.vinyl(total, r, mx.vinyl); for (let k = 0; k < total; k++) { a.ch[0][k] += n[k]; a.ch[1][k] += n[total - 1 - k] } }
    if (mx.width) widen(a, mx.width)
    lvl('chords', a); softclip(a); stems.chords = a }
  // lead
  { const a = stereo(raw.lead.mono, 0.3, 0.15)
    biquad(a, 'highpass', 180)
    if (mx.leadSat) saturate(a, mx.leadSat, 0.5)
    duck(a, kicks, (mx.pump ?? 0) * 0.7)
    if (mx.leadDelay) delayFx(a, (mx.leadDelay[0] * 60000) / s.bpm, mx.leadDelay[1], mx.leadDelay[2])
    if (mx.leadRev) reverb(a, 0.55, 0.5, 1, mx.leadRev)
    lvl('lead', a); softclip(a); stems.lead = a }
  const mix = sum(Object.values(stems))
  const g = 0.89 / (peak(mix) || 1)
  for (const a of [...Object.values(stems), mix]) scale(a, g)
  progress?.(0.95, 'Done (demo synth)')
  return { mix, stems, notes: [...raw.drums.notes, ...raw.bass.notes, ...raw.chords.notes, ...raw.lead.notes], spec: s }
}

/** Standard MIDI file (format 1, one track per stem). */
export function toMidi(notes: NoteEvent[], bpm: number): Uint8Array {
  const ppq = 480, tps = (ppq * bpm) / 60
  const vlq = (v: number) => { const o = [v & 0x7f]; while ((v >>= 7)) o.unshift((v & 0x7f) | 0x80); return o }
  const be = (v: number, n: number) => Array.from({ length: n }, (_, i) => (v >> (8 * (n - 1 - i))) & 0xff)
  const tracks: number[][] = []
  const mpq = Math.round(60000000 / bpm)
  tracks.push([0, 0xff, 0x51, 3, ...be(mpq, 3), 0, 0xff, 0x2f, 0])
  for (const stem of STEM_NAMES) {
    const ch = stem === 'drums' ? 9 : STEM_NAMES.indexOf(stem)
    const ev: [number, number[]][] = []
    for (const n of notes.filter((x) => x.stem === stem)) {
      ev.push([Math.round(n.start * tps), [0x90 | ch, n.pitch & 0x7f, n.vel & 0x7f]])
      ev.push([Math.round((n.start + n.dur) * tps), [0x80 | ch, n.pitch & 0x7f, 0]])
    }
    ev.sort((a, b) => a[0] - b[0])
    const name = Array.from(stem).map((c) => c.charCodeAt(0))
    const t: number[] = [0, 0xff, 0x03, name.length, ...name]
    let last = 0
    for (const [tick_, bytes] of ev) { t.push(...vlq(tick_ - last), ...bytes); last = tick_ }
    t.push(0, 0xff, 0x2f, 0)
    tracks.push(t)
  }
  const out: number[] = [0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 1, ...be(tracks.length, 2), ...be(ppq, 2)]
  for (const t of tracks) out.push(0x4d, 0x54, 0x72, 0x6b, ...be(t.length, 4), ...t)
  return new Uint8Array(out)
}

/** Four-band crossover used for uploaded audio. A crossover, not source separation. */
export function bandSplit(a: Audio): Record<string, Audio> {
  const mk = (kind: 'lowpass' | 'highpass' | 'bandpass', f: number, q?: number) => {
    const c: Audio = { sr: a.sr, ch: [a.ch[0].slice(), a.ch[1].slice()] }
    biquad(c, kind, f, q ?? 0.7071); biquad(c, kind, f, q ?? 0.7071)
    return c
  }
  return {
    'low (sub/bass)': mk('lowpass', 160),
    'low-mid (body)': mk('bandpass', 440, 0.5),
    'high-mid (presence)': mk('bandpass', 2700, 0.6),
    'air (highs)': mk('highpass', 6000),
  }
}
