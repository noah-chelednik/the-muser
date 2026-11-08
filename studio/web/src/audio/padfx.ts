/**
 * Per-pad FX chains. Each pad can carry its own ordered list of processors that only that pad goes
 * through: filter, 3-band EQ, compressor, saturation, bitcrush, delay, reverb, width and pan. The
 * building blocks match the stem / master chain in fx.ts (same IR generator and saturation curve).
 *
 *   pad voice -> [slot 1] -> [slot 2] -> ... -> pad out -> instBus -> master
 *
 * A pad with no slots skips the chain entirely. Structural edits (add, remove, reorder, toggle)
 * rebuild that pad's chain; parameter edits ramp the live nodes. The old chain is kept for a few
 * seconds so delay and reverb tails ring out instead of cutting.
 */
import { audio } from './engine'
import { makeIR, satCurve } from './fx'

export type SlotType = 'filter' | 'eq' | 'comp' | 'sat' | 'crush' | 'delay' | 'reverb' | 'width' | 'pan'
export type FxSlot = { id: string; type: SlotType; on: boolean; p: Record<string, number> }

type ParamDef = { key: string; label: string; min: number; max: number; step?: number; def: number; log?: boolean; fmt: (v: number) => string }
const pct = (v: number) => `${Math.round(v * 100)}%`
const db = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`
const hz = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)} kHz` : `${Math.round(v)} Hz`)

export const SLOT_DEFS: Record<SlotType, { label: string; params: ParamDef[] }> = {
  filter: {
    label: 'Filter',
    params: [
      { key: 'mode', label: 'Type', min: 0, max: 2, step: 1, def: 0, fmt: (v) => ['Low pass', 'High pass', 'Band pass'][Math.round(v)] },
      { key: 'freq', label: 'Freq', min: 40, max: 18000, def: 2400, log: true, fmt: hz },
      { key: 'q', label: 'Reso', min: 0.3, max: 16, def: 1, log: true, fmt: (v) => v.toFixed(1) },
    ],
  },
  eq: {
    label: 'EQ',
    params: [
      { key: 'low', label: 'Low', min: -15, max: 15, def: 0, fmt: db },
      { key: 'mid', label: 'Mid', min: -15, max: 15, def: 0, fmt: db },
      { key: 'high', label: 'High', min: -15, max: 15, def: 0, fmt: db },
    ],
  },
  comp: {
    label: 'Compressor',
    params: [
      { key: 'amount', label: 'Amount', min: 0, max: 1, def: 0.5, fmt: pct },
      { key: 'attack', label: 'Attack', min: 0.001, max: 0.1, def: 0.01, log: true, fmt: (v) => `${(v * 1000).toFixed(v < 0.01 ? 1 : 0)} ms` },
    ],
  },
  sat: {
    label: 'Saturation',
    params: [
      { key: 'drive', label: 'Drive', min: 0, max: 1, def: 0.4, fmt: pct },
      { key: 'mix', label: 'Mix', min: 0, max: 1, def: 1, fmt: pct },
    ],
  },
  crush: {
    label: 'Bitcrush',
    params: [
      { key: 'bits', label: 'Bits', min: 2, max: 16, step: 1, def: 6, fmt: (v) => `${Math.round(v)} bit` },
      { key: 'tone', label: 'Tone', min: 0, max: 1, def: 0.6, fmt: pct },
      { key: 'mix', label: 'Mix', min: 0, max: 1, def: 1, fmt: pct },
    ],
  },
  delay: {
    label: 'Delay',
    params: [
      { key: 'time', label: 'Time', min: 0.03, max: 1.2, def: 0.25, fmt: (v) => `${Math.round(v * 1000)} ms` },
      { key: 'fb', label: 'Feedback', min: 0, max: 0.9, def: 0.35, fmt: pct },
      { key: 'mix', label: 'Mix', min: 0, max: 1, def: 0.3, fmt: pct },
    ],
  },
  reverb: {
    label: 'Reverb',
    params: [
      { key: 'size', label: 'Size', min: 0, max: 1, def: 0.5, fmt: pct },
      { key: 'mix', label: 'Mix', min: 0, max: 1, def: 0.3, fmt: pct },
    ],
  },
  width: {
    label: 'Width',
    params: [{ key: 'width', label: 'Width', min: 0, max: 1, def: 0.6, fmt: pct }],
  },
  pan: {
    label: 'Pan',
    params: [{ key: 'pan', label: 'Pan', min: -1, max: 1, def: 0, fmt: (v) => (Math.abs(v) < 0.02 ? 'C' : `${v < 0 ? 'L' : 'R'}${Math.round(Math.abs(v) * 100)}`) }],
  },
}
export const SLOT_ORDER: SlotType[] = ['filter', 'eq', 'comp', 'sat', 'crush', 'delay', 'reverb', 'width', 'pan']

let uid = 0
export function newSlot(type: SlotType): FxSlot {
  const p: Record<string, number> = {}
  SLOT_DEFS[type].params.forEach((d) => { p[d.key] = d.def })
  return { id: `${type}-${Date.now().toString(36)}-${uid++}`, type, on: true, p }
}

type Node = { input: AudioNode; output: AudioNode; set: (p: Record<string, number>, live: boolean) => void; nodes: AudioNode[] }

function crushCurve(bits: number): Float32Array<ArrayBuffer> {
  const n = 4096
  const steps = Math.pow(2, Math.max(1, Math.round(bits)) - 1)
  const c = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const x = (i / (n - 1)) * 2 - 1
    c[i] = Math.round(x * steps) / steps
  }
  return c
}

/** Build one processor. Works for AudioContext and OfflineAudioContext. */
export function buildSlot(ctx: BaseAudioContext, slot: FxSlot): Node {
  const g = (v = 1) => { const n = ctx.createGain(); n.gain.value = v; return n }
  const t0 = () => ctx.currentTime
  const setp = (param: AudioParam, v: number, live: boolean) => {
    if (!Number.isFinite(v)) return
    if (live) param.setTargetAtTime(v, t0(), 0.015)
    else param.setValueAtTime(v, 0)
  }
  const wetDry = () => {
    const input = g(), output = g(), dry = g(1), wet = g(0)
    input.connect(dry); dry.connect(output); wet.connect(output)
    return { input, output, dry, wet }
  }
  switch (slot.type) {
    case 'filter': {
      const f = ctx.createBiquadFilter()
      let mode = -1
      return {
        input: f, output: f, nodes: [f],
        set: (p, live) => {
          const m = Math.round(p.mode)
          if (m !== mode) { mode = m; f.type = (['lowpass', 'highpass', 'bandpass'] as BiquadFilterType[])[m] ?? 'lowpass' }
          setp(f.frequency, Math.min(p.freq, ctx.sampleRate * 0.45), live)
          setp(f.Q, p.q, live)
        },
      }
    }
    case 'eq': {
      const lo = ctx.createBiquadFilter(); lo.type = 'lowshelf'; lo.frequency.value = 120
      const mid = ctx.createBiquadFilter(); mid.type = 'peaking'; mid.frequency.value = 1200; mid.Q.value = 0.9
      const hi = ctx.createBiquadFilter(); hi.type = 'highshelf'; hi.frequency.value = 7000
      lo.connect(mid); mid.connect(hi)
      return { input: lo, output: hi, nodes: [lo, mid, hi], set: (p, live) => { setp(lo.gain, p.low, live); setp(mid.gain, p.mid, live); setp(hi.gain, p.high, live) } }
    }
    case 'comp': {
      const c = ctx.createDynamicsCompressor()
      c.knee.value = 6; c.release.value = 0.15
      const makeup = g(1)
      c.connect(makeup)
      return {
        input: c, output: makeup, nodes: [c, makeup],
        set: (p, live) => {
          setp(c.threshold, -4 - 34 * p.amount, live)
          setp(c.ratio, 1.5 + 10 * p.amount, live)
          setp(c.attack, p.attack, live)
          setp(makeup.gain, 1 + p.amount * 1.2, live)
        },
      }
    }
    case 'sat': {
      const w = wetDry()
      const drive = g(1)
      const sh = ctx.createWaveShaper(); sh.curve = satCurve(); sh.oversample = '4x'
      const trim = g(1)
      w.input.connect(drive); drive.connect(sh); sh.connect(trim); trim.connect(w.wet)
      return {
        input: w.input, output: w.output, nodes: [w.input, w.output, w.dry, w.wet, drive, sh, trim],
        set: (p, live) => {
          setp(drive.gain, 1 + p.drive * 14, live)
          setp(trim.gain, 1 / (1 + p.drive * 2.2), live)
          setp(w.wet.gain, p.mix, live)
          setp(w.dry.gain, 1 - p.mix, live)
        },
      }
    }
    case 'crush': {
      const w = wetDry()
      const sh = ctx.createWaveShaper()
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'
      w.input.connect(sh); sh.connect(lp); lp.connect(w.wet)
      let bits = -1
      return {
        input: w.input, output: w.output, nodes: [w.input, w.output, w.dry, w.wet, sh, lp],
        set: (p, live) => {
          const b = Math.round(p.bits)
          if (b !== bits) { bits = b; sh.curve = crushCurve(b) }
          setp(lp.frequency, 1500 * Math.pow(12, p.tone), live)
          setp(w.wet.gain, p.mix, live)
          setp(w.dry.gain, 1 - p.mix, live)
        },
      }
    }
    case 'delay': {
      const w = wetDry()
      const d = ctx.createDelay(2)
      const fb = g(0.35)
      const tone = ctx.createBiquadFilter(); tone.type = 'lowpass'; tone.frequency.value = 6000
      w.input.connect(d); d.connect(tone); tone.connect(fb); fb.connect(d); tone.connect(w.wet)
      return {
        input: w.input, output: w.output, nodes: [w.input, w.output, w.dry, w.wet, d, fb, tone],
        set: (p, live) => {
          setp(d.delayTime, p.time, live)
          setp(fb.gain, Math.min(0.9, p.fb), live)
          setp(w.wet.gain, p.mix, live)
          setp(w.dry.gain, 1, live)
        },
      }
    }
    case 'reverb': {
      const w = wetDry()
      const conv = ctx.createConvolver()
      let size = -1
      w.input.connect(conv); conv.connect(w.wet)
      return {
        input: w.input, output: w.output, nodes: [w.input, w.output, w.dry, w.wet, conv],
        set: (p, live) => {
          const q = Math.round(p.size * 10) / 10
          if (q !== size) { size = q; conv.buffer = makeIR(ctx, q) }
          setp(w.wet.gain, p.mix * 0.9, live)
          setp(w.dry.gain, 1 - p.mix * 0.35, live)
        },
      }
    }
    case 'width': {
      // Haas-style widener for mono one-shots: a short delay on the right side.
      const input = g()
      input.channelCount = 2; input.channelCountMode = 'explicit'
      const split = ctx.createChannelSplitter(2)
      const merge = ctx.createChannelMerger(2)
      const d = ctx.createDelay(0.05)
      input.connect(split)
      split.connect(merge, 0, 0)
      split.connect(d, 1); d.connect(merge, 0, 1)
      return { input, output: merge, nodes: [input, split, merge, d], set: (p, live) => setp(d.delayTime, p.width * 0.022, live) }
    }
    case 'pan': {
      const pn = ctx.createStereoPanner()
      return { input: pn, output: pn, nodes: [pn], set: (p, live) => setp(pn.pan, p.pan, live) }
    }
  }
}

type Live = { input: GainNode; output: GainNode; slots: { slot: FxSlot; node: Node }[]; sig: string }

/** Builds a whole chain into `dest`. Returns the entry node. Used live and in offline bounces. */
export function buildPadChain(ctx: BaseAudioContext, slots: FxSlot[], dest: AudioNode, live: boolean): { input: GainNode; output: GainNode; slots: { slot: FxSlot; node: Node }[] } {
  const input = ctx.createGain()
  const output = ctx.createGain()
  let prev: AudioNode = input
  const built = slots.filter((s) => s.on).map((slot) => {
    const node = buildSlot(ctx, slot)
    node.set(slot.p, live)
    prev.connect(node.input)
    prev = node.output
    return { slot, node }
  })
  prev.connect(output)
  output.connect(dest)
  return { input, output, slots: built }
}

const chains = new Map<number, Live>()
const sigOf = (slots: FxSlot[]) => slots.filter((s) => s.on).map((s) => s.id).join('|')

function retire(c: Live) {
  // let tails ring, then free the nodes
  window.setTimeout(() => {
    try { c.output.disconnect() } catch { /* gone */ }
    c.slots.forEach((s) => s.node.nodes.forEach((n) => { try { n.disconnect() } catch { /* gone */ } }))
    try { c.input.disconnect() } catch { /* gone */ }
  }, 4000)
}

/** Where pad `i` should send its voice right now. */
export function padDestination(i: number, slots: FxSlot[] | undefined): AudioNode {
  const ctx = audio.ensure()
  const on = (slots ?? []).filter((s) => s.on)
  const cur = chains.get(i)
  if (!on.length) {
    if (cur) { chains.delete(i); retire(cur) }
    return audio.instBus
  }
  const sig = sigOf(slots!)
  if (cur && cur.sig === sig && cur.output.context === ctx) {
    // same structure: push parameters
    cur.slots.forEach(({ slot, node }) => {
      const now = slots!.find((s) => s.id === slot.id)
      if (now && now.p !== slot.p) { node.set(now.p, true); slot.p = now.p }
    })
    return cur.input
  }
  if (cur) retire(cur)
  const built = buildPadChain(ctx, slots!, audio.instBus, true)
  const next: Live = { ...built, sig, slots: built.slots.map((x) => ({ slot: { ...x.slot }, node: x.node })) }
  chains.set(i, next)
  return next.input
}

/** Push parameter changes immediately (knob drags) without waiting for the next hit. */
export function refreshPadChain(i: number, slots: FxSlot[]) {
  if (!audio.ctx) return
  padDestination(i, slots)
}
