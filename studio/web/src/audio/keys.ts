/**
 * Keys instrument: a preset-driven polyphonic synth. Every preset is built from Web Audio
 * oscillators, FM, noise and filters at play time, so nothing has to download and nothing carries a
 * third-party sample licence. Presets can also play any pad sound or library one-shot chromatically.
 *
 * The SynthParams knobs (wave, cutoff, reso, attack, release, detune, level) stay live on top of the
 * chosen preset: picking a preset writes its starting values into those knobs.
 */
import type { SynthParams } from '../types'
import { audio } from './engine'
import { padBank } from './samples'

type Osc = { type?: OscillatorType | 'main'; semi?: number; det?: number; gain?: number }
export type KeyPreset = {
  id: string
  name: string
  cat: 'Keys' | 'Bass' | 'Lead' | 'Pad' | 'Pluck' | 'Bell' | 'Organ' | 'Strings' | 'Brass' | 'FX' | 'Sampler'
  base: Partial<SynthParams>
  osc?: Osc[]
  fm?: { ratio: number; index: number; decay: number; sustain?: number }
  noise?: number
  filter?: { type?: BiquadFilterType; env?: number; decay?: number }
  amp?: { d?: number; s?: number }
  vib?: { rate: number; depth: number }
  mono?: boolean
  sample?: 'pad' | 'library'
}

const S = (o: Partial<SynthParams>) => o
export const KEY_PRESETS: KeyPreset[] = [
  // Keys
  { id: 'epiano', name: 'E-Piano', cat: 'Keys', base: S({ wave: 'sine', cutoff: 0.72, reso: 0.05, attack: 0.003, release: 0.6, detune: 4 }), osc: [{ type: 'main' }], fm: { ratio: 14, index: 1.6, decay: 0.35 }, amp: { d: 1.6, s: 0.25 } },
  { id: 'rhodes', name: 'Tine Keys', cat: 'Keys', base: S({ wave: 'sine', cutoff: 0.65, reso: 0.05, attack: 0.004, release: 0.8, detune: 3 }), osc: [{ type: 'main' }, { type: 'sine', semi: 12, gain: 0.15 }], fm: { ratio: 1, index: 2.2, decay: 0.5, sustain: 0.2 }, amp: { d: 2.2, s: 0.3 } },
  { id: 'wurli', name: 'Reed Keys', cat: 'Keys', base: S({ wave: 'triangle', cutoff: 0.62, reso: 0.1, attack: 0.004, release: 0.35, detune: 5 }), osc: [{ type: 'main' }], fm: { ratio: 2, index: 1.4, decay: 0.25 }, amp: { d: 1.1, s: 0.35 } },
  { id: 'piano', name: 'Soft Piano', cat: 'Keys', base: S({ wave: 'triangle', cutoff: 0.7, reso: 0.02, attack: 0.002, release: 0.7, detune: 2 }), osc: [{ type: 'main' }, { type: 'sine', semi: 12, gain: 0.3 }, { type: 'sine', semi: 19, gain: 0.08 }], filter: { env: 2.5, decay: 0.5 }, amp: { d: 2.4, s: 0.12 } },
  { id: 'clav', name: 'Clav', cat: 'Keys', base: S({ wave: 'square', cutoff: 0.6, reso: 0.4, attack: 0.002, release: 0.12, detune: 0 }), osc: [{ type: 'main', gain: 0.6 }], filter: { type: 'bandpass', env: 3, decay: 0.12 }, amp: { d: 0.4, s: 0.2 } },
  { id: 'lofi-keys', name: 'Lo-fi Keys', cat: 'Keys', base: S({ wave: 'triangle', cutoff: 0.48, reso: 0.1, attack: 0.008, release: 0.5, detune: 14 }), osc: [{ type: 'main' }, { type: 'sine', semi: 12, gain: 0.2 }], vib: { rate: 0.6, depth: 9 }, amp: { d: 1.4, s: 0.35 } },
  // Organ
  { id: 'organ', name: 'Drawbar Organ', cat: 'Organ', base: S({ wave: 'sine', cutoff: 0.9, reso: 0, attack: 0.006, release: 0.08, detune: 2 }), osc: [{ type: 'sine', semi: -12, gain: 0.6 }, { type: 'main' }, { type: 'sine', semi: 7, gain: 0.4 }, { type: 'sine', semi: 12, gain: 0.5 }, { type: 'sine', semi: 24, gain: 0.25 }], vib: { rate: 6.2, depth: 6 }, amp: { s: 1 } },
  { id: 'gospel-organ', name: 'Gospel Organ', cat: 'Organ', base: S({ wave: 'sine', cutoff: 0.95, reso: 0, attack: 0.004, release: 0.12, detune: 3 }), osc: [{ type: 'sine', semi: -12, gain: 0.7 }, { type: 'main' }, { type: 'sine', semi: 12, gain: 0.6 }, { type: 'sine', semi: 19, gain: 0.3 }, { type: 'sine', semi: 24, gain: 0.35 }, { type: 'square', semi: 36, gain: 0.04 }], vib: { rate: 6.8, depth: 10 }, amp: { s: 1 } },
  { id: 'reed-organ', name: 'Reed Organ', cat: 'Organ', base: S({ wave: 'sawtooth', cutoff: 0.4, reso: 0.05, attack: 0.05, release: 0.2, detune: 4 }), osc: [{ type: 'main' }, { type: 'square', semi: 12, gain: 0.25 }], amp: { s: 1 } },
  // Bass
  { id: 'sub', name: 'Sub Bass', cat: 'Bass', base: S({ wave: 'sine', cutoff: 0.45, reso: 0, attack: 0.004, release: 0.18, detune: 0, octave: -2 }), osc: [{ type: 'main' }, { type: 'triangle', semi: 12, gain: 0.08 }], amp: { s: 1 }, mono: true },
  { id: '808-bass', name: '808 Bass', cat: 'Bass', base: S({ wave: 'sine', cutoff: 0.5, reso: 0, attack: 0.002, release: 0.9, detune: 0, octave: -2 }), osc: [{ type: 'main' }], fm: { ratio: 1, index: 0.8, decay: 0.08 }, amp: { d: 2.5, s: 0.0 }, mono: true },
  { id: 'reese', name: 'Reese', cat: 'Bass', base: S({ wave: 'sawtooth', cutoff: 0.38, reso: 0.2, attack: 0.01, release: 0.2, detune: 22, octave: -1 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }, { type: 'sawtooth', semi: -12, gain: 0.4 }], amp: { s: 1 }, mono: true },
  { id: 'acid', name: 'Acid', cat: 'Bass', base: S({ wave: 'sawtooth', cutoff: 0.28, reso: 0.75, attack: 0.003, release: 0.12, detune: 0, octave: -1 }), osc: [{ type: 'main' }], filter: { env: 7, decay: 0.22 }, amp: { d: 0.5, s: 0.6 }, mono: true },
  { id: 'pluck-bass', name: 'Pluck Bass', cat: 'Bass', base: S({ wave: 'square', cutoff: 0.3, reso: 0.3, attack: 0.002, release: 0.1, detune: 6, octave: -1 }), osc: [{ type: 'main' }, { type: 'sine', semi: -12, gain: 0.6 }], filter: { env: 5, decay: 0.15 }, amp: { d: 0.5, s: 0.15 } },
  { id: 'funk-bass', name: 'Funk Bass', cat: 'Bass', base: S({ wave: 'sawtooth', cutoff: 0.33, reso: 0.35, attack: 0.002, release: 0.08, detune: 0, octave: -1 }), osc: [{ type: 'main' }], filter: { type: 'lowpass', env: 4, decay: 0.09 }, amp: { d: 0.35, s: 0.4 }, mono: true },
  { id: 'wobble', name: 'Wobble', cat: 'Bass', base: S({ wave: 'sawtooth', cutoff: 0.3, reso: 0.55, attack: 0.01, release: 0.15, detune: 12, octave: -1 }), osc: [{ type: 'main' }, { type: 'square', semi: -12, gain: 0.5 }], vib: { rate: 0.1, depth: 0 }, filter: { env: 3, decay: 0.4 }, amp: { s: 1 }, mono: true },
  // Lead
  { id: 'saw-lead', name: 'Saw Lead', cat: 'Lead', base: S({ wave: 'sawtooth', cutoff: 0.68, reso: 0.18, attack: 0.008, release: 0.25, detune: 10 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }], vib: { rate: 5.5, depth: 5 }, amp: { s: 0.9 } },
  { id: 'square-lead', name: 'Square Lead', cat: 'Lead', base: S({ wave: 'square', cutoff: 0.62, reso: 0.12, attack: 0.006, release: 0.2, detune: 6 }), osc: [{ type: 'main' }, { type: 'square', semi: 12, gain: 0.2 }], amp: { s: 0.9 } },
  { id: 'supersaw', name: 'Supersaw', cat: 'Lead', base: S({ wave: 'sawtooth', cutoff: 0.78, reso: 0.08, attack: 0.01, release: 0.45, detune: 18 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: -0.5 }, { type: 'main' }, { type: 'main', det: 0.5 }, { type: 'main', det: 1 }, { type: 'sawtooth', semi: 12, gain: 0.25 }], amp: { s: 0.85 } },
  { id: 'chip', name: 'Chiptune', cat: 'Lead', base: S({ wave: 'square', cutoff: 1, reso: 0, attack: 0.002, release: 0.06, detune: 0 }), osc: [{ type: 'main' }], vib: { rate: 7, depth: 12 }, amp: { s: 0.8 } },
  { id: 'whistle', name: 'Whistle', cat: 'Lead', base: S({ wave: 'sine', cutoff: 0.9, reso: 0, attack: 0.05, release: 0.2, detune: 0, octave: 1 }), osc: [{ type: 'main' }], noise: 0.02, vib: { rate: 5, depth: 14 }, amp: { s: 1 } },
  { id: 'trap-lead', name: 'Bell Lead', cat: 'Lead', base: S({ wave: 'triangle', cutoff: 0.8, reso: 0.05, attack: 0.003, release: 0.5, detune: 8 }), osc: [{ type: 'main' }, { type: 'sine', semi: 24, gain: 0.15 }], fm: { ratio: 3.5, index: 2, decay: 0.3 }, amp: { d: 1.2, s: 0.35 } },
  { id: 'sync-lead', name: 'Hard Lead', cat: 'Lead', base: S({ wave: 'sawtooth', cutoff: 0.74, reso: 0.3, attack: 0.004, release: 0.18, detune: 7 }), osc: [{ type: 'main' }, { type: 'square', semi: 7, gain: 0.3 }], filter: { env: 2, decay: 0.3 }, amp: { s: 0.85 } },
  // Pad
  { id: 'warm-pad', name: 'Warm Pad', cat: 'Pad', base: S({ wave: 'sawtooth', cutoff: 0.42, reso: 0.1, attack: 0.6, release: 1.8, detune: 16 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }, { type: 'triangle', semi: -12, gain: 0.4 }], vib: { rate: 0.3, depth: 6 }, amp: { s: 1 } },
  { id: 'glass-pad', name: 'Glass Pad', cat: 'Pad', base: S({ wave: 'triangle', cutoff: 0.75, reso: 0.15, attack: 0.9, release: 2.4, detune: 9 }), osc: [{ type: 'main' }, { type: 'sine', semi: 12, gain: 0.4 }, { type: 'sine', semi: 19, gain: 0.15 }], fm: { ratio: 4, index: 0.6, decay: 2, sustain: 0.4 }, amp: { s: 1 } },
  { id: 'dark-pad', name: 'Dark Pad', cat: 'Pad', base: S({ wave: 'sawtooth', cutoff: 0.25, reso: 0.25, attack: 1.2, release: 2.8, detune: 20 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }, { type: 'square', semi: -12, gain: 0.3 }], vib: { rate: 0.2, depth: 8 }, amp: { s: 1 } },
  { id: 'choir', name: 'Choir Aah', cat: 'Pad', base: S({ wave: 'sawtooth', cutoff: 0.4, reso: 0.5, attack: 0.35, release: 1.2, detune: 12 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }], noise: 0.03, filter: { type: 'bandpass' }, vib: { rate: 5, depth: 7 }, amp: { s: 1 } },
  { id: 'air-pad', name: 'Air Pad', cat: 'Pad', base: S({ wave: 'sine', cutoff: 0.85, reso: 0.05, attack: 1.4, release: 3, detune: 6 }), osc: [{ type: 'main' }, { type: 'sine', semi: 7, gain: 0.35 }, { type: 'sine', semi: 12, gain: 0.3 }], noise: 0.05, amp: { s: 1 } },
  { id: 'synthwave-pad', name: 'Synthwave Pad', cat: 'Pad', base: S({ wave: 'sawtooth', cutoff: 0.55, reso: 0.2, attack: 0.25, release: 1.6, detune: 24 }), osc: [{ type: 'main', det: -1 }, { type: 'main' }, { type: 'main', det: 1 }], vib: { rate: 4.5, depth: 4 }, amp: { s: 0.9 } },
  // Pluck
  { id: 'pluck', name: 'Pluck', cat: 'Pluck', base: S({ wave: 'sawtooth', cutoff: 0.32, reso: 0.3, attack: 0.002, release: 0.25, detune: 8 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }], filter: { env: 6, decay: 0.16 }, amp: { d: 0.5, s: 0 } },
  { id: 'kalimba', name: 'Kalimba', cat: 'Pluck', base: S({ wave: 'sine', cutoff: 0.8, reso: 0, attack: 0.002, release: 0.4, detune: 0, octave: 1 }), osc: [{ type: 'main' }], fm: { ratio: 5.4, index: 1.1, decay: 0.06 }, amp: { d: 0.9, s: 0 } },
  { id: 'harp', name: 'Harp', cat: 'Pluck', base: S({ wave: 'triangle', cutoff: 0.6, reso: 0.05, attack: 0.002, release: 0.9, detune: 3 }), osc: [{ type: 'main' }, { type: 'sine', semi: 12, gain: 0.25 }], filter: { env: 3, decay: 0.3 }, amp: { d: 1.8, s: 0 } },
  { id: 'guitar', name: 'Nylon Pluck', cat: 'Pluck', base: S({ wave: 'sawtooth', cutoff: 0.3, reso: 0.15, attack: 0.002, release: 0.4, detune: 4 }), osc: [{ type: 'main' }, { type: 'triangle', semi: 12, gain: 0.3 }], filter: { env: 4, decay: 0.25 }, amp: { d: 1.2, s: 0 } },
  { id: 'marimba', name: 'Marimba', cat: 'Pluck', base: S({ wave: 'sine', cutoff: 0.7, reso: 0, attack: 0.002, release: 0.25, detune: 0 }), osc: [{ type: 'main' }, { type: 'sine', semi: 24, gain: 0.12 }], fm: { ratio: 4, index: 1.5, decay: 0.03 }, amp: { d: 0.55, s: 0 } },
  { id: 'steel-drum', name: 'Steel Drum', cat: 'Pluck', base: S({ wave: 'sine', cutoff: 0.75, reso: 0, attack: 0.002, release: 0.4, detune: 0 }), osc: [{ type: 'main' }, { type: 'sine', semi: 16, gain: 0.2 }], fm: { ratio: 1.5, index: 1.8, decay: 0.15 }, amp: { d: 0.9, s: 0 } },
  // Bell
  { id: 'bell', name: 'Bell', cat: 'Bell', base: S({ wave: 'sine', cutoff: 0.9, reso: 0, attack: 0.002, release: 1.4, detune: 0, octave: 1 }), osc: [{ type: 'main' }], fm: { ratio: 3.5, index: 3, decay: 1.2, sustain: 0.1 }, amp: { d: 3, s: 0 } },
  { id: 'music-box', name: 'Music Box', cat: 'Bell', base: S({ wave: 'sine', cutoff: 0.95, reso: 0, attack: 0.001, release: 0.6, detune: 0, octave: 1 }), osc: [{ type: 'main' }, { type: 'sine', semi: 24, gain: 0.3 }], fm: { ratio: 7, index: 0.8, decay: 0.2 }, amp: { d: 1.4, s: 0 } },
  { id: 'vibes', name: 'Vibraphone', cat: 'Bell', base: S({ wave: 'sine', cutoff: 0.85, reso: 0, attack: 0.002, release: 1.2, detune: 0 }), osc: [{ type: 'main' }, { type: 'sine', semi: 24, gain: 0.1 }], fm: { ratio: 4, index: 0.9, decay: 0.4 }, vib: { rate: 5.5, depth: 0 }, amp: { d: 2.6, s: 0 } },
  { id: 'celesta', name: 'Celesta', cat: 'Bell', base: S({ wave: 'triangle', cutoff: 0.95, reso: 0, attack: 0.001, release: 0.8, detune: 0, octave: 1 }), osc: [{ type: 'main' }], fm: { ratio: 2, index: 1.2, decay: 0.3 }, amp: { d: 1.6, s: 0 } },
  // Strings and brass
  { id: 'strings', name: 'String Section', cat: 'Strings', base: S({ wave: 'sawtooth', cutoff: 0.5, reso: 0.05, attack: 0.25, release: 0.8, detune: 14 }), osc: [{ type: 'main', det: -1 }, { type: 'main' }, { type: 'main', det: 1 }], vib: { rate: 5.2, depth: 6 }, amp: { s: 1 } },
  { id: 'pizz', name: 'Pizzicato', cat: 'Strings', base: S({ wave: 'sawtooth', cutoff: 0.35, reso: 0.1, attack: 0.002, release: 0.2, detune: 6 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }], filter: { env: 3, decay: 0.08 }, amp: { d: 0.3, s: 0 } },
  { id: 'cello', name: 'Low Strings', cat: 'Strings', base: S({ wave: 'sawtooth', cutoff: 0.4, reso: 0.1, attack: 0.18, release: 0.6, detune: 9, octave: -1 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }], vib: { rate: 5, depth: 8 }, amp: { s: 1 } },
  { id: 'brass', name: 'Brass Stab', cat: 'Brass', base: S({ wave: 'sawtooth', cutoff: 0.36, reso: 0.15, attack: 0.03, release: 0.25, detune: 8 }), osc: [{ type: 'main', det: -1 }, { type: 'main', det: 1 }], filter: { env: 3, decay: 0.25 }, amp: { d: 0.8, s: 0.7 } },
  { id: 'horn', name: 'Soft Horn', cat: 'Brass', base: S({ wave: 'sawtooth', cutoff: 0.3, reso: 0.05, attack: 0.09, release: 0.35, detune: 5 }), osc: [{ type: 'main' }, { type: 'triangle', semi: -12, gain: 0.3 }], filter: { env: 1.5, decay: 0.5 }, vib: { rate: 4.8, depth: 4 }, amp: { s: 1 } },
  { id: 'flute', name: 'Flute', cat: 'Brass', base: S({ wave: 'sine', cutoff: 0.7, reso: 0, attack: 0.07, release: 0.2, detune: 0, octave: 1 }), osc: [{ type: 'main' }, { type: 'triangle', semi: 12, gain: 0.08 }], noise: 0.04, vib: { rate: 5, depth: 8 }, amp: { s: 1 } },
  // FX
  { id: 'laser', name: 'Laser', cat: 'FX', base: S({ wave: 'sawtooth', cutoff: 0.9, reso: 0.4, attack: 0.002, release: 0.2, detune: 0 }), osc: [{ type: 'main' }], fm: { ratio: 0.5, index: 8, decay: 0.2 }, amp: { d: 0.4, s: 0 } },
  { id: 'noise-sweep', name: 'Noise Sweep', cat: 'FX', base: S({ wave: 'sine', cutoff: 0.3, reso: 0.7, attack: 0.3, release: 1, detune: 0 }), osc: [{ type: 'main', gain: 0.2 }], noise: 0.6, filter: { type: 'bandpass', env: 6, decay: 1.2 }, amp: { s: 1 } },
  { id: 'vinyl-tone', name: 'Dusty Sine', cat: 'FX', base: S({ wave: 'sine', cutoff: 0.5, reso: 0, attack: 0.02, release: 0.6, detune: 25 }), osc: [{ type: 'main' }], noise: 0.06, vib: { rate: 0.4, depth: 18 }, amp: { s: 0.8 } },
  // Sampler: chromatic playback of a pad's sound
  { id: 'pad-sampler', name: 'Selected Pad', cat: 'Sampler', base: S({ cutoff: 1, reso: 0, attack: 0.002, release: 0.3 }), sample: 'pad' },
  { id: 'lib-sampler', name: 'Library Sound', cat: 'Sampler', base: S({ cutoff: 1, reso: 0, attack: 0.002, release: 0.3 }), sample: 'library' },
]
export const KEY_CATS = [...new Set(KEY_PRESETS.map((p) => p.cat))]
export const presetById = (id?: string) => KEY_PRESETS.find((p) => p.id === id)

/** Which pad / library buffer the Sampler presets play. Set from the Deck. */
export const keySampler: { pad: number; library: AudioBuffer | null; libraryName: string } = { pad: 0, library: null, libraryName: '' }

type Voice = { stop: (t: number, release: number) => void; env: GainNode }
const held = new Map<number, Voice>()
let keysOut: GainNode | null = null
const out = () => {
  const ctx = audio.ensure()
  if (!keysOut || keysOut.context !== ctx) { keysOut = ctx.createGain(); keysOut.connect(audio.instBus) }
  return keysOut
}
let noiseBuf: AudioBuffer | null = null
const noise = (ctx: BaseAudioContext) => {
  if (!noiseBuf || noiseBuf.sampleRate !== ctx.sampleRate) {
    noiseBuf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate)
    const d = noiseBuf.getChannelData(0)
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1
  }
  return noiseBuf
}
export const midiToHz = (n: number) => 440 * Math.pow(2, (n - 69) / 12)

/** Build and start one voice at `t`. Returns a handle to release it. */
function voice(note: number, s: SynthParams, vel: number, t: number): Voice | null {
  const ctx = audio.ensure()
  const pr = presetById(s.preset) ?? null
  const f = midiToHz(note)
  const env = ctx.createGain()
  const peak = vel * s.volume * 0.32
  const a = Math.max(0.002, s.attack)
  const d = pr?.amp?.d ?? 0.4
  const sus = pr?.amp?.s ?? 1
  env.gain.setValueAtTime(0, t)
  env.gain.linearRampToValueAtTime(peak, t + a)
  if (sus < 1) env.gain.setTargetAtTime(Math.max(0.0001, peak * sus), t + a, d / 3)
  env.connect(out())

  // sampler presets: chromatic playback of a buffer, C4 = original pitch
  if (pr?.sample) {
    const buf = pr.sample === 'pad' ? padBank.get(keySampler.pad)?.buffer : keySampler.library
    if (!buf) return null
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.playbackRate.value = Math.pow(2, (note - 60) / 12)
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 120 * Math.pow(2, s.cutoff * 7.5); lp.Q.value = 0.5 + s.reso * 12
    src.connect(lp).connect(env)
    src.start(t)
    return {
      env,
      stop: (t2, rel) => {
        env.gain.cancelScheduledValues(t2); env.gain.setValueAtTime(env.gain.value, t2); env.gain.linearRampToValueAtTime(0, t2 + rel)
        try { src.stop(t2 + rel + 0.05) } catch { /* ended */ }
      },
    }
  }

  const filter = ctx.createBiquadFilter()
  filter.type = pr?.filter?.type ?? 'lowpass'
  const cut = 120 * Math.pow(2, s.cutoff * 7.5)
  filter.Q.value = filter.type === 'bandpass' ? 1 + s.reso * 10 : 0.5 + s.reso * 18
  const fenv = pr?.filter?.env ?? 0
  if (fenv > 0) {
    filter.frequency.setValueAtTime(Math.min(18000, cut * (1 + fenv)), t)
    filter.frequency.setTargetAtTime(cut, t + 0.003, (pr?.filter?.decay ?? 0.2) / 3)
  } else filter.frequency.setValueAtTime(cut, t)
  filter.connect(env)

  const oscs: OscillatorNode[] = []
  const others: AudioScheduledSourceNode[] = []
  const list = pr?.osc ?? [{ type: 'main' as const, det: -1 }, { type: 'main' as const, det: 1 }]
  const total = list.reduce((x, o) => x + (o.gain ?? 1), 0)
  let fmGain: GainNode | null = null
  if (pr?.fm) {
    const mod = ctx.createOscillator()
    mod.frequency.value = f * pr.fm.ratio
    fmGain = ctx.createGain()
    const idx = f * pr.fm.index * (0.6 + vel * 0.6)
    fmGain.gain.setValueAtTime(idx, t)
    fmGain.gain.setTargetAtTime(idx * (pr.fm.sustain ?? 0), t + 0.002, pr.fm.decay / 3)
    mod.connect(fmGain)
    mod.start(t)
    others.push(mod)
  }
  let vib: GainNode | null = null
  if (pr?.vib && pr.vib.depth > 0) {
    const lfo = ctx.createOscillator()
    lfo.frequency.value = pr.vib.rate
    vib = ctx.createGain()
    vib.gain.value = pr.vib.depth
    lfo.connect(vib)
    lfo.start(t)
    others.push(lfo)
  }
  for (const o of list) {
    const osc = ctx.createOscillator()
    osc.type = o.type === 'main' || !o.type ? s.wave : o.type
    osc.frequency.value = f * Math.pow(2, (o.semi ?? 0) / 12)
    osc.detune.value = (o.det ?? 0) * s.detune
    if (fmGain) fmGain.connect(osc.frequency)
    if (vib) vib.connect(osc.detune)
    const g = ctx.createGain()
    g.gain.value = (o.gain ?? 1) / Math.max(1, total * 0.7)
    osc.connect(g).connect(filter)
    osc.start(t)
    oscs.push(osc)
  }
  if (pr?.noise) {
    const n = ctx.createBufferSource()
    n.buffer = noise(ctx)
    n.loop = true
    const g = ctx.createGain(); g.gain.value = pr.noise
    n.connect(g).connect(filter)
    n.start(t)
    others.push(n)
  }
  return {
    env,
    stop: (t2, rel) => {
      env.gain.cancelScheduledValues(t2)
      env.gain.setValueAtTime(env.gain.value, t2)
      env.gain.linearRampToValueAtTime(0, t2 + rel)
      ;[...oscs, ...others].forEach((o) => { try { o.stop(t2 + rel + 0.05) } catch { /* stopped */ } })
      window.setTimeout(() => { try { env.disconnect() } catch { /* gone */ } }, (t2 - ctx.currentTime + rel + 0.2) * 1000)
    },
  }
}

export function noteOn(note: number, s: SynthParams, velocity = 0.8) {
  const ctx = audio.ensure()
  noteOff(note, s, true)
  const pr = presetById(s.preset)
  if (pr?.mono) held.forEach((v, n) => { v.stop(ctx.currentTime, 0.02); held.delete(n) })
  const v = voice(note, s, velocity, ctx.currentTime)
  if (v) held.set(note, v)
}

export function noteOff(note: number, s: SynthParams, immediate = false) {
  const v = held.get(note)
  if (!v || !audio.ctx) return
  held.delete(note)
  v.stop(audio.ctx.currentTime, immediate ? 0.01 : Math.max(0.02, s.release))
}

/** Scheduled note for the sequencer: start at `t`, release after `dur` seconds. */
export function playNote(note: number, s: SynthParams, velocity: number, t: number, dur: number) {
  const v = voice(note, s, velocity, t)
  if (v) v.stop(t + Math.max(0.02, dur), Math.max(0.02, s.release))
}

export const allNotesOff = () => { if (!audio.ctx) return; held.forEach((v) => v.stop(audio.ctx!.currentTime, 0.02)); held.clear() }
