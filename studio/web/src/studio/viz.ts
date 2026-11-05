import { useEffect, useRef } from 'react'
import { audio } from '../audio/engine'

/**
 * Live visual feed for every skin. One place turns the real audio graph into a
 * normalized frame (spectrum, waveform, level, playhead). Skins only draw.
 *
 * Sources, in order: the multi-stem engine master analyser, then any <audio>
 * element that was tapped (library previews, A/B), then a calm idle signal so
 * the stage never looks dead.
 */
export const NB = 128

export interface Frame {
  t: number
  beat: number
  pos: number
  spec: Float32Array
  wave: Float32Array
  level: number
  live: boolean
}

/** Mutable knobs the studio writes and the visuals read every frame. */
export const viz = {
  bpm: 92,
  energy: 50,
  /** 0 when idle, 0..1 while a job runs (indeterminate ramp). */
  making: 0,
  /** Decaying kick from pointer events and actions. */
  pulse: 0,
  hit(a = 0.5) {
    this.pulse = Math.min(1.5, this.pulse + a)
  },
  /** Elements that are playing through a tap analyser. */
  duration: 0,
}

const taps = new Map<HTMLAudioElement, { an: AnalyserNode; ctx: AudioContext }>()

/**
 * Route an <audio> element through an analyser so previews drive the visuals.
 * It shares the engine's single AudioContext (phones allow only a few contexts,
 * and a second one can end up suspended or silent).
 */
export function tapAudioElement(el: HTMLAudioElement) {
  if (taps.has(el)) return
  try {
    const ctx = audio.ensure()
    const src = ctx.createMediaElementSource(el)
    const an = ctx.createAnalyser()
    an.fftSize = 1024
    src.connect(an)
    an.connect(ctx.destination)
    taps.set(el, { an, ctx })
  } catch {
    /* already tapped or blocked: playback still works untapped */
  }
}

const bins = new Float32Array(512)
const wavBuf = new Float32Array(1024)
const spec = new Float32Array(NB)
const wave = new Float32Array(512)
let bandMap: { sr: number; lo: Int32Array; hi: Int32Array } | null = null

function mapBands(sr: number) {
  if (bandMap && bandMap.sr === sr) return bandMap
  const lo = new Int32Array(NB)
  const hi = new Int32Array(NB)
  const hz = (i: number) => 30 * Math.pow(16000 / 30, i / NB)
  const per = sr / 1024
  for (let i = 0; i < NB; i++) {
    lo[i] = Math.max(1, Math.floor(hz(i) / per))
    hi[i] = Math.max(lo[i] + 1, Math.min(511, Math.ceil(hz(i + 1) / per)))
  }
  bandMap = { sr, lo, hi }
  return bandMap
}

function fromAnalyser(an: AnalyserNode, sr: number) {
  an.getFloatFrequencyData(bins)
  const m = mapBands(sr)
  for (let i = 0; i < NB; i++) {
    let v = -140
    for (let b = m.lo[i]; b < m.hi[i]; b++) v = Math.max(v, bins[b])
    // -95 dB floor to -22 dB ceiling, with a gentle tilt so highs are visible
    const n = Math.max(0, Math.min(1, (v + 95) / 73 + (i / NB) * 0.12))
    spec[i] = Math.max(n, spec[i] * 0.86)
  }
  an.getFloatTimeDomainData(wavBuf)
  let peak = 0
  for (let i = 0; i < 512; i++) {
    const a = wavBuf[i * 2] ?? 0
    wave[i] = a
    peak = Math.max(peak, Math.abs(a))
  }
  return Math.min(1, peak * 1.3)
}

function idle(t: number) {
  for (let i = 0; i < NB; i++) {
    const x = i / NB
    const target = 0.1 + 0.08 * Math.sin(t * 0.7 + x * 9) * (1 - x) + 0.05 * Math.sin(t * 1.9 + x * 23) + 0.03 * (1 - x)
    spec[i] += (target - spec[i]) * 0.08
  }
  for (let i = 0; i < 512; i++) {
    const x = i / 512
    wave[i] = Math.sin(x * 6.28 * 3 + t * 1.3) * 0.08 + Math.sin(x * 6.28 * 7 - t * 0.9) * 0.04
  }
  return 0.06
}

let lastNow = -1
let cached: Frame = { t: 0, beat: 0, pos: 0, spec, wave, level: 0, live: false }

export function getFrame(now: number): Frame {
  if (now === lastNow) return cached
  lastNow = now
  const t = now / 1000
  let live = false
  let level = 0
  let pos = 0
  let beat = (t * viz.bpm) / 60
  let measured = false
  if (audio.ctx && audio.masterAnalyser) {
    level = fromAnalyser(audio.masterAnalyser, audio.ctx.sampleRate)
    measured = audio.playing || level > 0.02
  }
  if (measured) {
    live = true
    pos = audio.duration ? audio.currentTime() / audio.duration : 0
    beat = (audio.currentTime() * viz.bpm) / 60
  } else {
    let tapped: { an: AnalyserNode; ctx: AudioContext; el: HTMLAudioElement } | null = null
    taps.forEach((v, el) => {
      if (!el.paused && !tapped) tapped = { ...v, el }
    })
    if (tapped) {
      const tp = tapped as { an: AnalyserNode; ctx: AudioContext; el: HTMLAudioElement }
      level = fromAnalyser(tp.an, tp.ctx.sampleRate)
      live = true
      pos = tp.el.duration ? tp.el.currentTime / tp.el.duration : 0
      beat = (tp.el.currentTime * viz.bpm) / 60
    } else {
      level = idle(t)
      pos = audio.duration ? audio.currentTime() / audio.duration : 0
      beat = (audio.currentTime() * viz.bpm) / 60
    }
  }
  cached = { t, beat, pos, spec, wave, level, live }
  return cached
}

/** Run a per-frame callback with the live frame. */
export function useFrame(cb: (f: Frame, now: number, dt: number) => void, deps: unknown[] = []) {
  const ref = useRef(cb)
  ref.current = cb
  useEffect(() => {
    let raf = 0
    let last = performance.now()
    const loop = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      ref.current(getFrame(now), now, dt)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

/** Level 0..1 for one stem lane. */
const stemBuf = new Float32Array(512)
export function stemLevel(id: string): number {
  const an = audio.analyser(id)
  if (!an || !audio.playing) return 0
  an.getFloatTimeDomainData(stemBuf as Float32Array<ArrayBuffer>)
  let p = 0
  for (let i = 0; i < stemBuf.length; i++) p = Math.max(p, Math.abs(stemBuf[i]))
  return Math.min(1, p * 1.2)
}

export function prefersReducedMotion() {
  return typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Tiny Web Animations helper. No-ops under prefers-reduced-motion. */
export function animateIn(el: Element | Element[] | NodeListOf<Element>, from: Keyframe, to: Keyframe, o: { duration?: number; stagger?: number; easing?: string } = {}) {
  if (prefersReducedMotion()) return
  const list = el instanceof Element ? [el] : Array.from(el)
  list.forEach((n, i) => {
    n.animate([from, to], { duration: o.duration ?? 500, delay: i * (o.stagger ?? 0), easing: o.easing ?? 'cubic-bezier(.16,1,.3,1)', fill: 'backwards' })
  })
}

export function webgl2Available(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!c.getContext('webgl2')
  } catch {
    return false
  }
}
