/** Synthesized drum pads, a polyphonic subtractive synth, and a step sequencer. */
import type { PadParams, SynthParams } from '../types'
import { audio } from './engine'
import { playPadSample } from './samples'

export type PadDef = { name: string; key: string; color: string; play: (t: number, p: PadParams) => void }

function noiseBuffer(ctx: AudioContext, seconds: number) {
  const b = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate)
  const d = b.getChannelData(0)
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1
  return b
}
let _noise: AudioBuffer | null = null
const noise = (ctx: AudioContext) => (_noise ??= noiseBuffer(ctx, 2))

function out(p: PadParams) {
  const ctx = audio.ensure()
  const g = ctx.createGain()
  g.gain.value = p.volume
  g.connect(audio.instBus)
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

/** Pads play their own sample when the sampler has put one there, otherwise the synthesized drum. */
export const PADS: PadDef[] = BASE_PADS.map((d, i) => ({ ...d, play: (t, p) => { if (!playPadSample(i, t, p)) d.play(t, p) } }))

// ---------------------------------------------------------------------------
// Polyphonic synth
// ---------------------------------------------------------------------------

type Voice = { osc: OscillatorNode[]; env: GainNode; filter: BiquadFilterNode }
const voices = new Map<number, Voice>()

export const midiToHz = (n: number) => 440 * Math.pow(2, (n - 69) / 12)

export function noteOn(note: number, s: SynthParams, velocity = 0.8) {
  const ctx = audio.ensure()
  noteOff(note, s, true)
  const t = ctx.currentTime
  const filter = ctx.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 120 * Math.pow(2, s.cutoff * 7.5)
  filter.Q.value = 0.5 + s.reso * 18
  const env = ctx.createGain()
  env.gain.setValueAtTime(0, t)
  env.gain.linearRampToValueAtTime(velocity * s.volume * 0.35, t + Math.max(0.003, s.attack))
  const f = midiToHz(note)
  const osc = [-1, 1].map((sign) => {
    const o = ctx.createOscillator()
    o.type = s.wave
    o.frequency.value = f
    o.detune.value = sign * s.detune
    o.connect(filter)
    o.start(t)
    return o
  })
  filter.connect(env).connect(audio.instBus)
  voices.set(note, { osc, env, filter })
}

export function noteOff(note: number, s: SynthParams, immediate = false) {
  const v = voices.get(note)
  if (!v || !audio.ctx) return
  voices.delete(note)
  const t = audio.ctx.currentTime
  const rel = immediate ? 0.01 : Math.max(0.02, s.release)
  v.env.gain.cancelScheduledValues(t)
  v.env.gain.setValueAtTime(v.env.gain.value, t)
  v.env.gain.linearRampToValueAtTime(0, t + rel)
  v.osc.forEach((o) => o.stop(t + rel + 0.05))
}

// ---------------------------------------------------------------------------
// Step sequencer (look-ahead scheduler)
// ---------------------------------------------------------------------------

export class Sequencer {
  private timer: number | null = null
  private nextTime = 0
  step = 0
  onStep: ((s: number) => void) | null = null
  getPattern: () => boolean[][] = () => []
  getBpm: () => number = () => 96
  getPad: () => PadParams = () => ({ volume: 0.8, pitch: 0, tone: 0.5 })

  get running() {
    return this.timer !== null
  }

  start() {
    const ctx = audio.ensure()
    if (this.timer !== null) return
    this.step = 0
    this.nextTime = ctx.currentTime + 0.06
    this.timer = window.setInterval(() => this.tick(), 25)
  }

  stop() {
    if (this.timer !== null) window.clearInterval(this.timer)
    this.timer = null
    this.onStep?.(-1)
  }

  private tick() {
    const ctx = audio.ctx!
    const spb = 60 / this.getBpm() / 4
    while (this.nextTime < ctx.currentTime + 0.12) {
      const pattern = this.getPattern()
      const s = this.step
      pattern.forEach((row, pad) => {
        if (row[s]) PADS[pad].play(this.nextTime, this.getPad())
      })
      const delay = Math.max(0, (this.nextTime - ctx.currentTime) * 1000)
      window.setTimeout(() => this.onStep?.(s), delay)
      this.nextTime += spb
      this.step = (this.step + 1) % 16
    }
  }
}

export const sequencer = new Sequencer()
