/** Synthesized drum pads, a polyphonic subtractive synth, and a step sequencer. */
import type { KeyNote, PadParams, SynthParams } from '../types'
import { audio } from './engine'
import { padBank, padOut, playPadSample } from './samples'
import { playNote } from './keys'
export { noteOn, noteOff, midiToHz, allNotesOff } from './keys'

export type PadDef = { name: string; key: string; color: string; play: (t: number, p: PadParams) => void }

function noiseBuffer(ctx: AudioContext, seconds: number) {
  const b = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate)
  const d = b.getChannelData(0)
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1
  return b
}
let _noise: AudioBuffer | null = null
const noise = (ctx: AudioContext) => (_noise ??= noiseBuffer(ctx, 2))

/** Destination for the synthesized hit being built right now (the pad's own FX chain). */
let hitDest: AudioNode | null = null
function out(p: PadParams) {
  const ctx = audio.ensure()
  const g = ctx.createGain()
  g.gain.value = p.volume
  g.connect(hitDest ?? audio.instBus)
  return { ctx, g }
}

const semis = (p: PadParams) => Math.pow(2, p.pitch / 12)

function kick(t: number, p: PadParams, deep = false) {
  const { ctx, g } = out(p)
  const o = ctx.createOscillator()
  const e = ctx.createGain()
  const f0 = (deep ? 55 : 50) * semis(p)
  o.frequency.setValueAtTime(f0 * (deep ? 2.2 : 3.5), t)
  o.frequency.exponentialRampToValueAtTime(f0, t + (deep ? 0.08 : 0.05))
  e.gain.setValueAtTime(1, t)
  e.gain.exponentialRampToValueAtTime(0.001, t + (deep ? 1.2 : 0.45))
  const shaper = ctx.createWaveShaper()
  const curve = new Float32Array(256)
  for (let i = 0; i < 256; i++) {
    const x = (i / 128 - 1) * (1.5 + p.tone * 3)
    curve[i] = Math.tanh(x)
  }
  shaper.curve = curve
  o.connect(shaper).connect(e).connect(g)
  o.start(t)
  o.stop(t + 1.3)
}

function noiseHit(t: number, p: PadParams, opts: { hp: number; bp?: number; decay: number; gain?: number; claps?: number }) {
  const { ctx, g } = out(p)
  const reps = opts.claps ?? 1
  for (let r = 0; r < reps; r++) {
    const tt = t + r * 0.011
    const s = ctx.createBufferSource()
    s.buffer = noise(ctx)
    s.playbackRate.value = semis(p)
    const hp = ctx.createBiquadFilter()
    hp.type = 'highpass'
    hp.frequency.value = opts.hp * (0.6 + p.tone * 0.8)
    const e = ctx.createGain()
    const dec = r === reps - 1 ? opts.decay : 0.012
    e.gain.setValueAtTime(opts.gain ?? 0.6, tt)
    e.gain.exponentialRampToValueAtTime(0.001, tt + dec)
    let node: AudioNode = s.connect(hp)
    if (opts.bp) {
      const bp = ctx.createBiquadFilter()
      bp.type = 'bandpass'
      bp.frequency.value = opts.bp
      bp.Q.value = 1.2
      node = node.connect(bp)
    }
    node.connect(e).connect(g)
    s.start(tt)
    s.stop(tt + dec + 0.05)
  }
}

function tone(t: number, p: PadParams, f: number, type: OscillatorType, decay: number, sweep = 1, gain = 0.5) {
  const { ctx, g } = out(p)
  const o = ctx.createOscillator()
  o.type = type
  const e = ctx.createGain()
  o.frequency.setValueAtTime(f * semis(p) * sweep, t)
  o.frequency.exponentialRampToValueAtTime(f * semis(p), t + 0.04)
  e.gain.setValueAtTime(gain, t)
  e.gain.exponentialRampToValueAtTime(0.001, t + decay)
  const lp = ctx.createBiquadFilter()
  lp.frequency.value = 800 + p.tone * 9000
  o.connect(lp).connect(e).connect(g)
  o.start(t)
  o.stop(t + decay + 0.05)
}

function chord(t: number, p: PadParams, notes: number[], type: OscillatorType, decay: number) {
  notes.forEach((n) => tone(t, p, 440 * Math.pow(2, (n - 69) / 12), type, decay, 1, 0.16))
}

function snare(t: number, p: PadParams) {
  tone(t, p, 185, 'triangle', 0.12, 1.6, 0.5)
  noiseHit(t, p, { hp: 1500, decay: 0.2, gain: 0.5 })
}

function riser(t: number, p: PadParams) {
  const { ctx, g } = out(p)
  const s = ctx.createBufferSource()
  s.buffer = noise(ctx)
  const bp = ctx.createBiquadFilter()
  bp.type = 'bandpass'
  bp.Q.value = 4
  bp.frequency.setValueAtTime(300, t)
  bp.frequency.exponentialRampToValueAtTime(9000 * (0.5 + p.tone), t + 1.4)
  const e = ctx.createGain()
  e.gain.setValueAtTime(0.001, t)
  e.gain.exponentialRampToValueAtTime(0.5, t + 1.3)
  e.gain.exponentialRampToValueAtTime(0.001, t + 1.5)
  s.connect(bp).connect(e).connect(g)
  s.start(t)
  s.stop(t + 1.6)
}

const BASE_PADS: PadDef[] = [
  { name: 'Kick', key: '1', color: '#ff4d6d', play: (t, p) => kick(t, p) },
  { name: 'Snare', key: '2', color: '#ffb703', play: snare },
  { name: 'Clap', key: '3', color: '#ffd166', play: (t, p) => noiseHit(t, p, { hp: 900, bp: 1500, decay: 0.18, claps: 3, gain: 0.7 }) },
  { name: 'Rim', key: '4', color: '#e9c46a', play: (t, p) => tone(t, p, 1700, 'square', 0.04, 1, 0.25) },
  { name: 'Hat', key: 'q', color: '#4cc9f0', play: (t, p) => noiseHit(t, p, { hp: 7000, decay: 0.05, gain: 0.35 }) },
  { name: 'Open Hat', key: 'w', color: '#48bfe3', play: (t, p) => noiseHit(t, p, { hp: 6500, decay: 0.35, gain: 0.3 }) },
  { name: 'Shaker', key: 'e', color: '#56cfe1', play: (t, p) => noiseHit(t, p, { hp: 5000, bp: 8000, decay: 0.09, gain: 0.3 }) },
  { name: 'Crash', key: 'r', color: '#64dfdf', play: (t, p) => noiseHit(t, p, { hp: 4000, decay: 1.4, gain: 0.3 }) },
  { name: 'Tom Lo', key: 'a', color: '#c77dff', play: (t, p) => tone(t, p, 110, 'sine', 0.4, 1.8, 0.7) },
  { name: 'Tom Hi', key: 's', color: '#b56cff', play: (t, p) => tone(t, p, 180, 'sine', 0.3, 1.8, 0.6) },
  { name: 'Cowbell', key: 'd', color: '#9d4edd', play: (t, p) => { tone(t, p, 540, 'square', 0.25, 1, 0.12); tone(t, p, 800, 'square', 0.25, 1, 0.12) } },
  { name: '808', key: 'f', color: '#7b2cbf', play: (t, p) => kick(t, p, true) },
  { name: 'Stab', key: 'z', color: '#80ffdb', play: (t, p) => chord(t, p, [57, 60, 64, 67], 'sawtooth', 0.35) },
  { name: 'Pluck', key: 'x', color: '#72efdd', play: (t, p) => tone(t, p, 659, 'sawtooth', 0.25, 1, 0.3) },
  { name: 'Zap', key: 'c', color: '#5ee7c9', play: (t, p) => tone(t, p, 220, 'sawtooth', 0.2, 8, 0.3) },
  { name: 'Riser', key: 'v', color: '#3ef0ff', play: riser },
]

/**
 * Pads play their own sample when one is loaded (library, upload or chop), otherwise the synthesized
 * drum. Either way the hit goes through the pad's level, pitch and FX chain. `vel` is 0..1.
 */
export type LivePad = Omit<PadDef, 'play'> & { play: (t: number, p: PadParams, vel?: number) => void }
export const PADS: LivePad[] = BASE_PADS.map((d, i): LivePad => ({
  name: d.name, key: d.key, color: d.color,
  play: (t: number, p: PadParams, vel: number = 1) => {
    if (playPadSample(i, t, p, vel)) return
    const st = padBank.settings(i)
    hitDest = padOut(i)
    try { d.play(t, { ...p, volume: p.volume * st.gain * vel, pitch: p.pitch + st.pitch }) } finally { hitDest = null }
  },
}))
export const BASE_PAD_NAMES = BASE_PADS.map((d) => d.name)

// ---------------------------------------------------------------------------
// Step sequencer (look-ahead scheduler)
// ---------------------------------------------------------------------------

export class Sequencer {
  private timer: number | null = null
  private nextTime = 0
  /** Recent (step, time) pairs so a live hit can be placed on the step the listener heard. */
  private sched: { step: number; time: number }[] = []
  step = 0
  onStep: ((s: number) => void) | null = null
  getPattern: () => boolean[][] = () => []
  getBpm: () => number = () => 96
  getPad: () => PadParams = () => ({ volume: 0.8, pitch: 0, tone: 0.5 })
  getKeyNotes: () => KeyNote[] = () => []
  getSynth: (() => SynthParams) | null = null
  /** Quarter-note click while recording. */
  metronome = false

  get running() {
    return this.timer !== null
  }

  get stepSeconds() {
    return 60 / this.getBpm() / 4
  }

  start() {
    const ctx = audio.ensure()
    if (this.timer !== null) return
    this.step = 0
    this.sched = []
    this.nextTime = ctx.currentTime + 0.06
    this.timer = window.setInterval(() => this.tick(), 25)
    this.tick()
  }

  stop() {
    if (this.timer !== null) window.clearInterval(this.timer)
    this.timer = null
    this.sched = []
    this.onStep?.(-1)
  }

  /** The 16th step nearest to audio time `t` (what a live hit at `t` should be written to). */
  stepAt(t: number): number {
    const past = this.sched.filter((x) => x.time <= t + 1e-4)
    const last = past.length ? past[past.length - 1] : this.sched[0]
    if (!last) return 0
    const frac = (t - last.time) / this.stepSeconds
    return ((last.step + Math.round(frac)) % 16 + 16) % 16
  }

  private click(t: number, accent: boolean) {
    const ctx = audio.ctx!
    const o = ctx.createOscillator()
    const g = ctx.createGain()
    o.frequency.value = accent ? 1760 : 1320
    g.gain.setValueAtTime(0.0001, t)
    g.gain.exponentialRampToValueAtTime(accent ? 0.18 : 0.1, t + 0.002)
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.05)
    o.connect(g).connect(audio.instBus)
    o.start(t)
    o.stop(t + 0.06)
  }

  private tick() {
    const ctx = audio.ctx
    if (!ctx) return
    const spb = this.stepSeconds
    while (this.nextTime < ctx.currentTime + 0.12) {
      const pattern = this.getPattern()
      const s = this.step
      const t = this.nextTime
      pattern.forEach((row, pad) => {
        if (row[s]) PADS[pad].play(t, this.getPad())
      })
      const synth = this.getSynth?.()
      if (synth) this.getKeyNotes().forEach((n) => { if (n.step === s) playNote(n.note, synth, n.vel, t, n.len * spb * 0.95) })
      if (this.metronome && s % 4 === 0) this.click(t, s === 0)
      this.sched.push({ step: s, time: t })
      if (this.sched.length > 32) this.sched.shift()
      const delay = Math.max(0, (t - ctx.currentTime) * 1000)
      window.setTimeout(() => this.onStep?.(s), delay)
      this.nextTime += spb
      this.step = (this.step + 1) % 16
    }
  }
}

export const sequencer = new Sequencer()
