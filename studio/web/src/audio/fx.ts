/**
 * One FX chain, built the same way for the live AudioContext and for the
 * OfflineAudioContext bounce, so what you export is what you heard.
 *
 *   in -> HP -> LP -> EQ low / mid / high -> parametric -> compressor
 *      -> saturation (parallel WaveShaper) -> dry + delay + reverb
 *      -> stereo width (mid/side) -> pan -> fader -> mute -> out
 *
 * Every stage is bypassed by neutral parameter values, never by rewiring, so
 * toggling it ramps instead of clicking. Live changes use setTargetAtTime.
 */
import type { StemParams } from '../types'
import { DEFAULT_STEM } from '../types'

export const dbToGain = (db: number) => (db <= -59.9 ? 0 : Math.pow(10, db / 20))

/** Deterministic noise so live and offline renders use the same reverb tail. */
function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const irCache = new WeakMap<BaseAudioContext, Map<number, AudioBuffer>>()
/** Generated stereo impulse response. room 0 = small and dark, 1 = large hall. */
export function makeIR(ctx: BaseAudioContext, room: number): AudioBuffer {
  const q = Math.round(room * 10) / 10
  let m = irCache.get(ctx)
  if (!m) irCache.set(ctx, (m = new Map()))
  const hit = m.get(q)
  if (hit) return hit
  const sr = ctx.sampleRate
  const len = Math.floor(sr * (0.5 + q * 3.3))
  const ir = ctx.createBuffer(2, len, sr)
  for (let c = 0; c < 2; c++) {
    const r = rng(1234 + c * 77 + Math.round(q * 10))
    const d = ir.getChannelData(c)
    let lp = 0
    const damp = 0.25 + (1 - q) * 0.55 // dark rooms roll highs off sooner
    for (let i = 0; i < len; i++) {
      const t = i / len
      const n = r() * 2 - 1
      lp += (n - lp) * (1 - damp * (0.4 + t))
      const early = i < sr * 0.04 ? 1.4 : 1
      d[i] = lp * early * Math.pow(1 - t, 2.2 + (1 - q) * 3)
    }
  }
  m.set(q, ir)
  return ir
}

/** Smooth soft clip; drive is applied before it so the curve never changes. */
export function satCurve(n = 4096): Float32Array<ArrayBuffer> {
  const c = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const x = (i / (n - 1)) * 2 - 1
    c[i] = Math.tanh(x * 2.2) * 0.95 + 0.04 * x * x * Math.sign(x) * 0.5
  }
  return c
}

export type Chain = {
  input: GainNode
  output: GainNode
  analyser: AnalyserNode
  nodes: {
    hp: BiquadFilterNode
    lp: BiquadFilterNode
    eq: BiquadFilterNode[]
    peq: BiquadFilterNode
    comp: DynamicsCompressorNode
    conv: ConvolverNode
    delay: DelayNode
    pan: StereoPannerNode
    fader: GainNode
    mute: GainNode
  }
  /** Push parameters. `live` ramps; offline sets the value at t=0. */
  apply(p: StemParams, opts?: { audible?: boolean; live?: boolean; room?: number }): void
  dispose(): void
}

export function buildChain(ctx: BaseAudioContext, opts: { meter?: boolean } = {}): Chain {
  const nyq = Math.min(20000, ctx.sampleRate * 0.45)
  const bq = (type: BiquadFilterType, f: number, q = 0.7) => {
    const b = ctx.createBiquadFilter()
    b.type = type
    b.frequency.value = f
    b.Q.value = q
    b.gain.value = 0
    return b
  }
  const g = (v = 1) => {
    const n = ctx.createGain()
    n.gain.value = v
    return n
  }
  const input = ctx.createGain()
  input.channelCount = 2
  input.channelCountMode = 'explicit'
  input.channelInterpretation = 'speakers'
  const hp = bq('highpass', 20, 0.707)
  const lp = bq('lowpass', nyq, 0.707)
  const eq = [bq('peaking', 100, 0.7), bq('peaking', 1000, 1.0), bq('peaking', 8000, 0.7)]
  const peq = bq('peaking', 2500, 1.2)
  const comp = ctx.createDynamicsCompressor()
  comp.threshold.value = 0
  comp.ratio.value = 1
  comp.knee.value = 4
  comp.attack.value = 0.01
  comp.release.value = 0.2

  // saturation, parallel
  const satDry = g(1)
  const drive = g(1)
  const shaper = ctx.createWaveShaper()
  shaper.curve = satCurve()
  shaper.oversample = '4x'
  const satWet = g(0)
  const mix1 = g(1)

  // time effects
  const dryOut = g(1)
  const dSend = g(0)
  const delay = ctx.createDelay(2)
  delay.delayTime.value = 0.375
  const fb = g(0.35)
  const dTone = bq('lowpass', 5200, 0.5)
  const dWet = g(1)
  const rSend = g(0)
  const conv = ctx.createConvolver()
  conv.buffer = makeIR(ctx, 0.5)
  const rWet = g(1)
  const sum = g(1)

  // mid / side width
  const split = ctx.createChannelSplitter(2)
  const merge = ctx.createChannelMerger(2)
  const mL = g(0.5), mR = g(0.5), sL = g(0.5), sR = g(-0.5)
  const M = g(1), S = g(1), Sinv = g(-1)

  const pan = ctx.createStereoPanner()
  const fader = g(1)
  const mute = g(1)
  const output = g(1)
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 512

  input.connect(hp); hp.connect(lp); lp.connect(eq[0]); eq[0].connect(eq[1]); eq[1].connect(eq[2]); eq[2].connect(peq); peq.connect(comp)
  comp.connect(satDry); comp.connect(drive); drive.connect(shaper); shaper.connect(satWet)
  satDry.connect(mix1); satWet.connect(mix1)
  mix1.connect(dryOut); dryOut.connect(sum)
  mix1.connect(dSend); dSend.connect(delay); delay.connect(dTone); dTone.connect(fb); fb.connect(delay); dTone.connect(dWet); dWet.connect(sum)
  mix1.connect(rSend); rSend.connect(conv); conv.connect(rWet); rWet.connect(sum)
  sum.connect(split)
  split.connect(mL, 0); split.connect(mR, 1); split.connect(sL, 0); split.connect(sR, 1)
  mL.connect(M); mR.connect(M); sL.connect(S); sR.connect(S); S.connect(Sinv)
  M.connect(merge, 0, 0); S.connect(merge, 0, 0)
  M.connect(merge, 0, 1); Sinv.connect(merge, 0, 1)
  merge.connect(pan); pan.connect(fader); fader.connect(mute)
  if (opts.meter) { mute.connect(analyser); analyser.connect(output) } else mute.connect(output)

  let room = 0.5
  const apply: Chain['apply'] = (raw, o = {}) => {
    const live = o.live !== false
    const t = ctx.currentTime
    const set = (param: AudioParam, v: number, tc = 0.015) => {
      if (!Number.isFinite(v)) return
      if (live) param.setTargetAtTime(v, t, tc)
      else param.setValueAtTime(v, 0)
    }
    const p = { ...DEFAULT_STEM, ...raw }
    const off = (b: boolean) => p.bypass || b
    // EQ
    const e = off(p.byp_eq)
    set(eq[0].gain, e ? 0 : p.eq_low_db)
    set(eq[1].gain, e ? 0 : p.eq_mid_db)
    set(eq[2].gain, e ? 0 : p.eq_high_db)
    set(peq.gain, e ? 0 : p.peq_gain)
    set(peq.frequency, p.peq_freq, 0.02)
    set(peq.Q, p.peq_q, 0.02)
    // compressor
    const c = off(p.byp_comp) || p.comp <= 0.01
    set(comp.threshold, c ? 0 : -6 - 30 * p.comp)
    set(comp.ratio, c ? 1 : 1.5 + 6.5 * p.comp)
    // saturation
    const sOn = !off(p.byp_sat) && p.sat > 0.005
    const s = sOn ? p.sat : 0
    set(drive.gain, 1 + s * 9)
    set(satWet.gain, s * 0.9 / (1 + s * 2.5))
    set(satDry.gain, 1 - s * 0.85)
    // delay
    const dOn = !off(p.byp_delay) && p.delay_mix > 0.005
    set(delay.delayTime, Math.min(1.9, Math.max(0.02, p.delay_time)), 0.05)
    set(fb.gain, Math.min(0.92, Math.max(0, p.delay_fb)))
    set(dSend.gain, dOn ? p.delay_mix : 0)
    // reverb
    const rOn = !off(p.byp_verb) && p.reverb > 0.005
    const wetR = rOn ? p.reverb : 0
    set(dryOut.gain, 1 - wetR * 0.3)
    set(rSend.gain, wetR * 0.9)
    const wantRoom = o.room ?? p.room
    if (Math.abs(room - wantRoom) > 0.05) {
      room = wantRoom
      conv.buffer = makeIR(ctx, wantRoom)
    }
    // filter sweep
    const f = off(p.byp_filter) ? 0 : Math.max(-1, Math.min(1, p.filter))
    const lpHz = f < -0.01 ? nyq * Math.pow(140 / nyq, -f) : nyq
    const hpHz = f > 0.01 ? 20 * Math.pow(9000 / 20, f) : 20
    set(lp.frequency, lpHz, 0.03)
    set(hp.frequency, hpHz, 0.03)
    const q = Math.abs(f) > 0.01 ? Math.max(0.3, p.filter_q) : 0.707
    set(lp.Q, q, 0.03)
    set(hp.Q, q, 0.03)
    // width (side gain)
    const w = off(p.byp_width) ? 1 : Math.max(0, Math.min(2, p.width))
    set(S.gain, w)
    // level
    set(pan.pan, p.pan)
    set(fader.gain, dbToGain(p.gain_db))
    set(mute.gain, o.audible === false ? 0 : 1)
  }

  const dispose = () => {
    ;[input, hp, lp, ...eq, peq, comp, satDry, drive, shaper, satWet, mix1, dryOut, dSend, delay, fb, dTone, dWet, rSend, conv, rWet, sum, split, merge, mL, mR, sL, sR, M, S, Sinv, pan, fader, mute, analyser, output].forEach((n) => {
      try { n.disconnect() } catch { /* already gone */ }
    })
  }

  return { input, output, analyser, nodes: { hp, lp, eq, peq, comp, conv, delay, pan, fader, mute }, apply, dispose }
}
