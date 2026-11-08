/** Synthesized drum pads, a polyphonic subtractive synth, and a step sequencer. */
import type { Arrangement, BeatPattern, KeyNote, PadParams, SynthParams } from '../types'
import { hitsAt } from './arrange'
import { trackInput } from './arrangeGraph'
import { audio } from './engine'
import { padBank, padRoute, playPadSample } from './samples'
import { playNote } from './keys'
export { noteOn, noteOff, midiToHz, allNotesOff } from './keys'

export type PadDef = { name: string; key: string; color: string; play: (t: number, p: PadParams, dest?: AudioNode) => void }

function noiseBuffer(ctx: BaseAudioContext, seconds: number) {
  const b = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate)
  const d = b.getChannelData(0)
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1
  return b
}
const _noise = new Map<number, AudioBuffer>()
const noise = (ctx: BaseAudioContext) => {
  let buf = _noise.get(ctx.sampleRate)
  if (!buf) {
    buf = noiseBuffer(ctx, 2)
    _noise.set(ctx.sampleRate, buf)
  }
  return buf
}

function out(p: PadParams, dest?: AudioNode) {
  const ctx = (dest?.context ?? audio.ensure()) as BaseAudioContext
  const g = ctx.createGain()
  g.gain.value = p.volume
  g.connect(dest ?? audio.instBus)
  return { ctx, g }
}

const semis = (p: PadParams) => Math.pow(2, p.pitch / 12)

function kick(t: number, p: PadParams, deep = false, dest?: AudioNode) {
  const { ctx, g } = out(p, dest)
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

function noiseHit(t: number, p: PadParams, opts: { hp: number; bp?: number; decay: number; gain?: number; claps?: number }, dest?: AudioNode) {
  const { ctx, g } = out(p, dest)
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

function tone(t: number, p: PadParams, f: number, type: OscillatorType, decay: number, sweep = 1, gain = 0.5, dest?: AudioNode) {
  const { ctx, g } = out(p, dest)
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

function chord(t: number, p: PadParams, notes: number[], type: OscillatorType, decay: number, dest?: AudioNode) {
  notes.forEach((n) => tone(t, p, 440 * Math.pow(2, (n - 69) / 12), type, decay, 1, 0.16, dest))
}

function snare(t: number, p: PadParams, dest?: AudioNode) {
  tone(t, p, 185, 'triangle', 0.12, 1.6, 0.5, dest)
  noiseHit(t, p, { hp: 1500, decay: 0.2, gain: 0.5 }, dest)
}

function riser(t: number, p: PadParams, dest?: AudioNode) {
  const { ctx, g } = out(p, dest)
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
  { name: 'Kick', key: '1', color: '#ff4d6d', play: (t, p, dest) => kick(t, p, false, dest) },
  { name: 'Snare', key: '2', color: '#ffb703', play: (t, p, dest) => snare(t, p, dest) },
  { name: 'Clap', key: '3', color: '#ffd166', play: (t, p, dest) => noiseHit(t, p, { hp: 900, bp: 1500, decay: 0.18, claps: 3, gain: 0.7 }, dest) },
  { name: 'Rim', key: '4', color: '#e9c46a', play: (t, p, dest) => tone(t, p, 1700, 'square', 0.04, 1, 0.25, dest) },
  { name: 'Hat', key: 'q', color: '#4cc9f0', play: (t, p, dest) => noiseHit(t, p, { hp: 7000, decay: 0.05, gain: 0.35 }, dest) },
  { name: 'Open Hat', key: 'w', color: '#48bfe3', play: (t, p, dest) => noiseHit(t, p, { hp: 6500, decay: 0.35, gain: 0.3 }, dest) },
  { name: 'Shaker', key: 'e', color: '#56cfe1', play: (t, p, dest) => noiseHit(t, p, { hp: 5000, bp: 8000, decay: 0.09, gain: 0.3 }, dest) },
  { name: 'Crash', key: 'r', color: '#64dfdf', play: (t, p, dest) => noiseHit(t, p, { hp: 4000, decay: 1.4, gain: 0.3 }, dest) },
  { name: 'Tom Lo', key: 'a', color: '#c77dff', play: (t, p, dest) => tone(t, p, 110, 'sine', 0.4, 1.8, 0.7, dest) },
  { name: 'Tom Hi', key: 's', color: '#b56cff', play: (t, p, dest) => tone(t, p, 180, 'sine', 0.3, 1.8, 0.6, dest) },
  { name: 'Cowbell', key: 'd', color: '#9d4edd', play: (t, p, dest) => { tone(t, p, 540, 'square', 0.25, 1, 0.12, dest); tone(t, p, 800, 'square', 0.25, 1, 0.12, dest) } },
  { name: '808', key: 'f', color: '#7b2cbf', play: (t, p, dest) => kick(t, p, true, dest) },
  { name: 'Stab', key: 'z', color: '#80ffdb', play: (t, p, dest) => chord(t, p, [57, 60, 64, 67], 'sawtooth', 0.35, dest) },
  { name: 'Pluck', key: 'x', color: '#72efdd', play: (t, p, dest) => tone(t, p, 659, 'sawtooth', 0.25, 1, 0.3, dest) },
  { name: 'Zap', key: 'c', color: '#5ee7c9', play: (t, p, dest) => tone(t, p, 220, 'sawtooth', 0.2, 8, 0.3, dest) },
  { name: 'Riser', key: 'v', color: '#3ef0ff', play: (t, p, dest) => riser(t, p, dest) },
]

/**
 * Pads play their own sample when one is loaded (library, upload or chop), otherwise the synthesized
 * drum. Either way the hit goes through the pad's level, pitch and FX chain. `dest` is a playlist
 * track or an offline export input; `vel` is 0..1.
 */
export type LivePad = Omit<PadDef, 'play'> & { play: (t: number, p: PadParams, dest?: AudioNode, vel?: number) => void }
export const PADS: LivePad[] = BASE_PADS.map((d, i): LivePad => ({
  name: d.name, key: d.key, color: d.color,
  play: (t: number, p: PadParams, dest?: AudioNode, vel: number = 1) => {
    if (playPadSample(i, t, p, vel, dest)) return
    const st = padBank.settings(i)
    d.play(t, { ...p, volume: p.volume * st.gain * vel, pitch: p.pitch + st.pitch }, padRoute(i, dest))
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
  mode: 'pattern' | 'arrange' = 'pattern'
  getArrangement: () => { arrangement: Arrangement; patterns: BeatPattern[] } | null = () => null
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
      const s = this.step
      const t = this.nextTime
      if (this.mode === 'arrange') {
        const data = this.getArrangement()
        if (data) {
          const bars = Math.max(1, data.arrangement.bars)
          const bar = Math.floor(s / 16) % bars
          const st = s % 16
          for (const hit of hitsAt(data.arrangement, data.patterns, bar, st)) {
            PADS[hit.pad]?.play(t, this.getPad(), trackInput(hit.track))
          }
          this.sched.push({ step: st, time: t })
          if (this.sched.length > 32) this.sched.shift()
          const delay = Math.max(0, (t - ctx.currentTime) * 1000)
          window.setTimeout(() => this.onStep?.(s), delay)
          this.nextTime += spb
          this.step = (s + 1) % (bars * 16)
          continue
        }
      }
      const pattern = this.getPattern()
      if (this.step >= 16) this.step %= 16
      const ps = this.step
      pattern.forEach((row, pad) => {
        if (row[ps]) PADS[pad].play(t, this.getPad())
      })
      const synth = this.getSynth?.()
      if (synth) this.getKeyNotes().forEach((n) => { if (n.step === ps) playNote(n.note, synth, n.vel, t, n.len * spb * 0.95) })
      if (this.metronome && ps % 4 === 0) this.click(t, ps === 0)
      this.sched.push({ step: ps, time: t })
      if (this.sched.length > 32) this.sched.shift()
      const delay = Math.max(0, (t - ctx.currentTime) * 1000)
      window.setTimeout(() => this.onStep?.(ps), delay)
      this.nextTime += spb
      this.step = (ps + 1) % 16
    }
  }
}

export const sequencer = new Sequencer()
