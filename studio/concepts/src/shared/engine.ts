import { BARS, type Pattern, buildPattern } from './music'
import { NEUTRAL, STEMS, VIBES, type Macros, type StemId, type Vibe } from './data'

export const NB = 128 // spectral bands
export interface StemParams { vol: number; pan: number; mute: boolean; solo: boolean; low: number; mid: number; high: number; comp: number; verb: number; room: number }
export const defaultStem = (): StemParams => ({ vol: 0, pan: 0, mute: false, solo: false, low: 0, mid: 0, high: 0, comp: 0, verb: 0, room: 0 })

export interface Frame {
  t: number
  beat: number
  gstep: number
  bar: number
  step: number
  pos: number
  spec: Float32Array
  wave: Float32Array
  level: number
  env: Record<'kick' | 'snare' | 'hat' | 'bass' | 'keys' | 'voice', number>
  stem: Record<StemId, number>
  stemWave: Record<StemId, Float32Array>
  live: boolean
}

const mk = () => ({ kick: 0, snare: 0, hat: 0, bass: 0, keys: 0, voice: 0 })
const m2f = (m: number) => 440 * Math.pow(2, (m - 69) / 12)
const bandFreq = (i: number) => 30 * Math.pow(16000 / 30, i / NB)
const gauss = (x: number, c: number, w: number) => Math.exp(-((x - c) * (x - c)) / (2 * w * w))
const bandOf = (f: number) => (Math.log(f / 30) / Math.log(16000 / 30)) * NB

class Engine {
  vibe: Vibe | null = null
  pattern: Pattern = buildPattern(VIBES[13])
  macros: Macros = { ...NEUTRAL }
  stems: Record<StemId, StemParams> = { drums: defaultStem(), bass: defaultStem(), keys: defaultStem(), voice: defaultStem() }
  playing = false
  beat = 0
  excite = 0
  masterGain = 1
  // audio
  ctx: AudioContext | null = null
  live = false
  private bus: Record<StemId, { input: GainNode; lo: BiquadFilterNode; mid: BiquadFilterNode; hi: BiquadFilterNode; comp: DynamicsCompressorNode; pan: StereoPannerNode; vol: GainNode; an: AnalyserNode; send: GainNode; echo: GainNode; tone: BiquadFilterNode }> | null = null
  private master: { an: AnalyserNode; tilt: BiquadFilterNode; wet: GainNode; fb: GainNode } | null = null
  private noiseBuf: AudioBuffer | null = null
  private timer: number | undefined
  private nextStep = 0
  private stepIdx = 0
  private f: Frame = {
    t: 0, beat: 0, gstep: 0, bar: 0, step: 0, pos: 0, spec: new Float32Array(NB), wave: new Float32Array(512), level: 0, env: mk(),
    stem: { drums: 0, bass: 0, keys: 0, voice: 0 },
    stemWave: { drums: new Float32Array(128), bass: new Float32Array(128), keys: new Float32Array(128), voice: new Float32Array(128) }, live: false,
  }
  private lastNow = 0
  private lastFrameT = -1
  private fbuf = new Uint8Array(1024)
  private tbuf = new Float32Array(512)
  private listeners = new Set<() => void>()

  get bpm() { return this.pattern.bpm * (0.9 + (this.macros.energy / 100) * 0.22) }
  get totalBeats() { return BARS * 4 }
  get duration() { return (this.totalBeats * 60) / this.bpm }
  get time() { return ((this.beat % this.totalBeats) * 60) / this.bpm }

  on(fn: () => void) { this.listeners.add(fn); return () => this.listeners.delete(fn) }
  private emit() { this.listeners.forEach((l) => l()) }

  setVibe(v: Vibe | null) {
    this.vibe = v
    this.pattern = buildPattern(v ?? VIBES[13])
  }
  setMacros(m: Macros) {
    this.macros = { ...m }
    this.applyMacros()
  }
  setStem(id: StemId, patch: Partial<StemParams>) {
    this.stems[id] = { ...this.stems[id], ...patch }
    this.applyStems()
  }
  seek(pos: number) { this.beat = Math.max(0, Math.min(0.9999, pos)) * this.totalBeats }

  /* ---------- audio graph ---------- */
  private ensure() {
    if (this.ctx) return true
    const AC = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    if (!AC) return false
    const ctx = new AC()
    this.ctx = ctx
    const out = ctx.createGain()
    out.gain.value = 0.8
    const lim = ctx.createDynamicsCompressor()
    lim.threshold.value = -8; lim.ratio.value = 6; lim.attack.value = 0.004; lim.release.value = 0.2
    const tilt = ctx.createBiquadFilter(); tilt.type = 'highshelf'; tilt.frequency.value = 4500
    const an = ctx.createAnalyser(); an.fftSize = 2048; an.smoothingTimeConstant = 0.55
    tilt.connect(lim); lim.connect(out); out.connect(an); an.connect(ctx.destination)
    // space: convolution reverb + echo
    const conv = ctx.createConvolver()
    const len = ctx.sampleRate * 2.6
    const ir = ctx.createBuffer(2, len, ctx.sampleRate)
    for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3.2) }
    conv.buffer = ir
    const wet = ctx.createGain(); wet.gain.value = 0.3
    const rsend = ctx.createGain(); rsend.gain.value = 1
    rsend.connect(conv); conv.connect(wet); wet.connect(tilt)
    const dl = ctx.createDelay(1.5); dl.delayTime.value = 0.375
    const fb = ctx.createGain(); fb.gain.value = 0.3
    const esend = ctx.createGain(); esend.gain.value = 1
    esend.connect(dl); dl.connect(fb); fb.connect(dl); dl.connect(wet)
    this.master = { an, tilt, wet, fb }
    const nb = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate)
    const nd = nb.getChannelData(0); for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1
    this.noiseBuf = nb
    const bus = {} as NonNullable<Engine['bus']>
    for (const s of STEMS) {
      const input = ctx.createGain()
      const lo = ctx.createBiquadFilter(); lo.type = 'lowshelf'; lo.frequency.value = 160
      const mid = ctx.createBiquadFilter(); mid.type = 'peaking'; mid.frequency.value = 1400; mid.Q.value = 0.8
      const hi = ctx.createBiquadFilter(); hi.type = 'highshelf'; hi.frequency.value = 6000
      const tone = ctx.createBiquadFilter(); tone.type = 'lowpass'; tone.frequency.value = 18000
      const comp = ctx.createDynamicsCompressor()
      const pan = ctx.createStereoPanner()
      const vol = ctx.createGain()
      const stAn = ctx.createAnalyser(); stAn.fftSize = 256
      const send = ctx.createGain(); send.gain.value = 0.2
      const echo = ctx.createGain(); echo.gain.value = 0
      input.connect(lo); lo.connect(mid); mid.connect(hi); hi.connect(tone); tone.connect(comp); comp.connect(pan); pan.connect(vol); vol.connect(stAn)
      vol.connect(tilt); vol.connect(send); send.connect(rsend); vol.connect(echo); echo.connect(esend)
      bus[s.id] = { input, lo, mid, hi, comp, pan, vol, an: stAn, send, echo, tone }
    }
    this.bus = bus
    this.applyMacros(); this.applyStems()
    return true
  }
  private applyMacros() {
    if (!this.ctx || !this.master) return
    const t = this.ctx.currentTime, m = this.macros
    this.master.tilt.gain.setTargetAtTime((m.brightness - 50) * 0.16, t, 0.05)
    this.master.wet.gain.setTargetAtTime(0.05 + (m.space / 100) * 0.7, t, 0.08)
    this.master.fb.gain.setTargetAtTime(0.15 + (m.space / 100) * 0.45, t, 0.08)
    this.applyStems()
  }
  private applyStems() {
    if (!this.ctx || !this.bus) return
    const t = this.ctx.currentTime, m = this.macros
    const anySolo = STEMS.some((s) => this.stems[s.id].solo)
    for (const s of STEMS) {
      const p = this.stems[s.id], b = this.bus[s.id]
      const audible = !p.mute && (!anySolo || p.solo)
      let g = Math.pow(10, p.vol / 20)
      if (s.id === 'voice') g *= 0.2 + (m.vocals / 100) * 1.3
      if (s.id === 'bass') g *= 0.4 + (m.bass / 100) * 1.1
      if (s.id === 'drums') g *= 0.6 + (m.energy / 100) * 0.7
      b.vol.gain.setTargetAtTime(audible ? g : 0, t, 0.03)
      b.pan.pan.setTargetAtTime(p.pan, t, 0.03)
      b.lo.gain.setTargetAtTime(p.low + (s.id === 'bass' ? (m.bass - 50) * 0.12 : 0), t, 0.03)
      b.mid.gain.setTargetAtTime(p.mid, t, 0.03)
      b.hi.gain.setTargetAtTime(p.high, t, 0.03)
      b.tone.frequency.setTargetAtTime(s.id === 'drums' || s.id === 'voice' ? 18000 : 1800 * Math.pow(10, (m.brightness / 100) * 1.1), t, 0.05)
      b.comp.threshold.setTargetAtTime(-4 - (p.comp / 100) * 30, t, 0.03)
      b.comp.ratio.setTargetAtTime(1.5 + (p.comp / 100) * 8, t, 0.03)
      b.send.gain.setTargetAtTime(0.12 + (p.verb / 100) * 0.7, t, 0.03)
      b.echo.gain.setTargetAtTime((p.room / 100) * 0.5, t, 0.03)
    }
  }

  /* ---------- scheduler ---------- */
  async play() {
    this.playing = true
    if (this.ensure() && this.ctx) {
      try { await this.ctx.resume() } catch { /* ignore */ }
      this.live = this.ctx.state === 'running'
      if (this.live) {
        this.stepIdx = Math.floor(this.beat * 4)
        this.nextStep = this.ctx.currentTime + 0.06
        window.clearInterval(this.timer)
        this.timer = window.setInterval(() => this.tick(), 25)
      }
    }
    this.emit()
  }
  pause() {
    this.playing = false
    window.clearInterval(this.timer)
    this.emit()
  }
  toggle() { return this.playing ? this.pause() : this.play() }

  private tick() {
    const ctx = this.ctx
    if (!ctx || !this.playing) return
    while (this.nextStep < ctx.currentTime + 0.14) {
      this.schedule(this.stepIdx, this.nextStep)
      const sd = 60 / this.bpm / 4
      this.nextStep += sd
      this.stepIdx++
    }
  }
  private schedule(gs: number, t: number) {
    const p = this.pattern, st = gs % 16, bar = Math.floor(gs / 16) % 4
    const sd = 60 / this.bpm / 4
    const sw = st % 2 ? p.swing * sd : 0
    t += sw
    const dens = this.macros.energy / 100
    if (p.kick[st]) this.kick(t, p.kick[st])
    if (p.snare[st]) this.snare(t, p.snare[st])
    if (p.hat[st] && (p.hat[st] >= 0.4 || dens > 0.45)) this.hat(t, p.hat[st] * (0.6 + dens * 0.6), false)
    if (p.ohat[st]) this.hat(t, p.ohat[st], true)
    for (const n of p.bass[bar]) if (n.s === st) this.bassNote(t, n.m, n.l * sd)
    if (st === 0) for (const m of p.chords[bar]) this.keyNote(t, m, sd * 15.5)
    for (const n of p.lead[bar]) if (n.s === st) this.voiceNote(t, n.m, n.l * sd)
  }
  private env(g: GainNode, t: number, a: number, peak: number, d: number, sus = 0) {
    g.gain.setValueAtTime(0.0001, t)
    g.gain.linearRampToValueAtTime(peak, t + a)
    g.gain.exponentialRampToValueAtTime(Math.max(sus, 0.0001), t + a + d)
  }
  private kick(t: number, v: number) {
    const c = this.ctx!, o = c.createOscillator(), g = c.createGain()
    o.frequency.setValueAtTime(155, t); o.frequency.exponentialRampToValueAtTime(42, t + 0.14)
    this.env(g, t, 0.002, 0.95 * v, 0.34)
    o.connect(g); g.connect(this.bus!.drums.input); o.start(t); o.stop(t + 0.4)
  }
  private noise(t: number, dur: number, type: BiquadFilterType, f: number, q: number, peak: number, decay: number, dest: AudioNode) {
    const c = this.ctx!, s = c.createBufferSource(), fl = c.createBiquadFilter(), g = c.createGain()
    s.buffer = this.noiseBuf; fl.type = type; fl.frequency.value = f; fl.Q.value = q
    this.env(g, t, 0.001, peak, decay)
    s.connect(fl); fl.connect(g); g.connect(dest); s.start(t, Math.random() * 0.5); s.stop(t + dur)
  }
  private snare(t: number, v: number) {
    this.noise(t, 0.3, 'bandpass', 1900, 0.7, 0.55 * v, 0.2, this.bus!.drums.input)
    const c = this.ctx!, o = c.createOscillator(), g = c.createGain()
    o.type = 'triangle'; o.frequency.setValueAtTime(210, t); o.frequency.exponentialRampToValueAtTime(130, t + 0.08)
    this.env(g, t, 0.002, 0.35 * v, 0.12); o.connect(g); g.connect(this.bus!.drums.input); o.start(t); o.stop(t + 0.2)
  }
  private hat(t: number, v: number, open: boolean) {
    this.noise(t, open ? 0.35 : 0.1, 'highpass', 7200, 0.5, 0.22 * v, open ? 0.24 : 0.045, this.bus!.drums.input)
  }
  private bassNote(t: number, m: number, dur: number) {
    const c = this.ctx!, f = m2f(m)
    const o = c.createOscillator(), o2 = c.createOscillator(), g = c.createGain(), lp = c.createBiquadFilter()
    o.type = 'sawtooth'; o2.type = 'sine'; o.frequency.value = f; o2.frequency.value = f
    lp.type = 'lowpass'; lp.frequency.setValueAtTime(900, t); lp.frequency.exponentialRampToValueAtTime(220, t + dur)
    this.env(g, t, 0.01, 0.42, Math.max(0.12, dur), 0.0001)
    o.connect(lp); o2.connect(g); lp.connect(g); g.connect(this.bus!.bass.input)
    o.start(t); o2.start(t); o.stop(t + dur + 0.1); o2.stop(t + dur + 0.1)
  }
  private keyNote(t: number, m: number, dur: number) {
    const c = this.ctx!, f = m2f(m), g = c.createGain()
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.085, t + 0.04); g.gain.exponentialRampToValueAtTime(0.0001, t + dur)
    for (const d of [-6, 5]) {
      const o = c.createOscillator(); o.type = 'triangle'; o.frequency.value = f; o.detune.value = d
      o.connect(g); o.start(t); o.stop(t + dur + 0.1)
    }
    g.connect(this.bus!.keys.input)
  }
  private voiceNote(t: number, m: number, dur: number) {
    const c = this.ctx!, f = m2f(m)
    const o = c.createOscillator(), lfo = c.createOscillator(), lg = c.createGain(), g = c.createGain()
    o.type = 'sawtooth'; o.frequency.value = f; lfo.frequency.value = 5.2; lg.gain.value = f * 0.012
    lfo.connect(lg); lg.connect(o.frequency)
    const f1 = c.createBiquadFilter(), f2 = c.createBiquadFilter()
    f1.type = f2.type = 'bandpass'; f1.Q.value = f2.Q.value = 6
    f1.frequency.setValueAtTime(650, t); f1.frequency.linearRampToValueAtTime(420, t + dur)
    f2.frequency.setValueAtTime(1100, t); f2.frequency.linearRampToValueAtTime(800, t + dur)
    g.gain.setValueAtTime(0.0001, t); g.gain.linearRampToValueAtTime(0.5, t + 0.05); g.gain.setValueAtTime(0.5, t + Math.max(0.06, dur - 0.08)); g.gain.linearRampToValueAtTime(0.0001, t + dur + 0.05)
    o.connect(f1); o.connect(f2); f1.connect(g); f2.connect(g); g.connect(this.bus!.voice.input)
    o.start(t); lfo.start(t); o.stop(t + dur + 0.1); lfo.stop(t + dur + 0.1)
  }

  /* ---------- analysis frame (real analyser when live, otherwise a faithful synthetic model) ---------- */
  frame(now: number): Frame {
    if (now === this.lastFrameT) return this.f
    this.lastFrameT = now
    const dt = this.lastNow ? Math.min(0.1, (now - this.lastNow) / 1000) : 0
    this.lastNow = now
    const f = this.f
    f.t = now / 1000
    if (this.playing) this.beat += (dt * this.bpm) / 60
    f.beat = this.beat
    f.gstep = this.beat * 4
    f.bar = Math.floor(f.gstep / 16) % BARS
    f.step = f.gstep % 16
    f.pos = (this.beat % this.totalBeats) / this.totalBeats
    this.envelopes(f)
    f.live = this.live && this.playing
    const prev = f.spec
    const sp = this.synthSpec(f)
    const space = this.macros.space / 100
    const rel = 0.82 + space * 0.1
    if (f.live && this.master) {
      const an = this.master.an
      an.getByteFrequencyData(this.fbuf)
      const nyq = (this.ctx!.sampleRate / 2) / 1024
      for (let i = 0; i < NB; i++) {
        const lo = Math.floor(bandFreq(i) / nyq), hi = Math.max(lo + 1, Math.floor(bandFreq(i + 1) / nyq))
        let m = 0
        for (let k = lo; k < hi && k < 1024; k++) m = Math.max(m, this.fbuf[k])
        const tilt = 1 + (i / NB) * 0.55
        sp[i] = Math.min(1, Math.pow(m / 255, 1.35) * tilt * 1.1)
      }
      an.getFloatTimeDomainData(this.tbuf)
      f.wave.set(this.tbuf)
      let rms = 0; for (let i = 0; i < 512; i++) rms += this.tbuf[i] * this.tbuf[i]
      f.level = Math.min(1, Math.sqrt(rms / 512) * 3.2)
      for (const s of STEMS) {
        const a = this.bus![s.id].an; a.getFloatTimeDomainData(this.tbuf)
        const w = f.stemWave[s.id]; let r = 0
        for (let i = 0; i < 128; i++) { w[i] = this.tbuf[i * 2]; r += w[i] * w[i] }
        f.stem[s.id] = Math.min(1, Math.sqrt(r / 128) * 4)
      }
    } else {
      this.synthWave(f)
    }
    for (let i = 0; i < NB; i++) prev[i] = Math.max(sp[i], prev[i] * rel)
    return f
  }
  private tmp = new Float32Array(NB)
  private hitEnv(a: number[], gs: number, decay: number) {
    const base = Math.floor(gs), fr = gs - base
    let m = 0
    for (let k = 0; k < 4; k++) { const v = a[(((base - k) % 16) + 16) % 16] ?? 0; if (v) m = Math.max(m, v * Math.exp(-(k + fr) * decay)) }
    return m
  }
  private envelopes(f: Frame) {
    const p = this.pattern, gs = f.gstep, st = Math.floor(gs % 16), bar = Math.floor(gs / 16) % 4
    const on = this.playing ? 1 : 0
    const e = f.env
    const m = this.macros
    const sa = (id: StemId) => { const s = this.stems[id]; const anySolo = STEMS.some((x) => this.stems[x.id].solo); return !s.mute && (!anySolo || s.solo) ? Math.pow(10, s.vol / 20) : 0 }
    e.kick = on * this.hitEnv(p.kick, gs, 1.5) * sa('drums') * (0.6 + m.energy / 160)
    e.snare = on * this.hitEnv(p.snare, gs, 1.1) * sa('drums')
    e.hat = on * Math.max(this.hitEnv(p.hat, gs, 2.6) * (m.energy > 45 ? 1 : 0.4), this.hitEnv(p.ohat, gs, 0.7)) * sa('drums')
    const bn = p.bass[bar].find((n) => st >= n.s && st < n.s + n.l)
    e.bass = on * (bn ? 0.55 + 0.45 * Math.exp(-(st - bn.s + (gs % 1)) * 0.35) : 0.08) * sa('bass') * (0.4 + m.bass / 90)
    e.keys = on * (0.45 + 0.4 * Math.exp(-(st + (gs % 1)) * 0.22)) * sa('keys')
    const ln = p.lead[bar].find((n) => st >= n.s && st < n.s + n.l)
    e.voice = on * (ln ? 0.7 : 0.06) * sa('voice') * (0.25 + m.vocals / 80)
    if (!f.live) {
      f.stem.drums = Math.min(1, Math.max(e.kick, e.snare * 0.9, e.hat * 0.5))
      f.stem.bass = Math.min(1, e.bass * 0.9)
      f.stem.keys = Math.min(1, e.keys * 0.7)
      f.stem.voice = Math.min(1, e.voice * 0.9)
    }
  }
  private synthSpec(f: Frame) {
    const sp = this.tmp, e = f.env, m = this.macros, t = f.t
    const bright = 0.45 + m.brightness / 100
    const idle = this.playing ? 0 : 1
    const ex = this.excite
    const keysF = this.pattern.chords[f.bar % 4].map((n) => bandOf(m2f(n)))
    const leadN = this.pattern.lead[f.bar % 4].find((n) => f.step >= n.s && f.step < n.s + n.l)
    for (let i = 0; i < NB; i++) {
      const x = i
      let v = 0.035 + 0.02 * Math.sin(i * 0.31 + t * 1.3)
      v += e.kick * 0.95 * gauss(x, NB * 0.1, NB * 0.045)
      v += e.snare * (0.5 * gauss(x, NB * 0.3, NB * 0.1) + 0.4 * gauss(x, NB * 0.62, NB * 0.16))
      v += e.hat * 0.55 * bright * gauss(x, NB * 0.86, NB * 0.1) * (0.7 + 0.3 * Math.sin(i * 1.7 + t * 40))
      v += e.bass * 0.8 * (gauss(x, NB * 0.12, NB * 0.03) + 0.4 * gauss(x, NB * 0.2, NB * 0.03))
      let kc = 0
      for (const kf of keysF) for (let h = 1; h <= 5; h++) kc += gauss(x, kf + NB * 0.145 * Math.log2(h) * 1.0, NB * 0.012) / h
      v += e.keys * 0.38 * kc * (0.7 + 0.3 * bright)
      if (leadN) { const lf = bandOf(m2f(leadN.m)); v += e.voice * 0.6 * (gauss(x, lf, NB * 0.014) + 0.5 * gauss(x, lf + NB * 0.145, NB * 0.014) + 0.4 * gauss(x, NB * 0.5, NB * 0.05)) }
      // idle: the muse hums
      if (idle) v += 0.2 * (0.5 + 0.5 * Math.sin(t * 0.5 + i * 0.07)) * gauss(x, NB * (0.3 + 0.18 * Math.sin(t * 0.23)), NB * 0.16) + 0.12 * gauss(x, NB * (0.62 + 0.2 * Math.sin(t * 0.17 + 2)), NB * 0.1) * (0.5 + 0.5 * Math.sin(t * 0.9))
      if (ex > 0) v += ex * (0.25 + 0.5 * Math.abs(Math.sin(i * 12.9898 + Math.floor(t * 24) * 78.233))) * (0.4 + 0.6 * gauss(x, NB * 0.5, NB * 0.35))
      sp[i] = Math.min(1, v)
    }
    return sp
  }
  private synthWave(f: Frame) {
    const e = f.env, w = f.wave, t = f.t
    const lead = this.pattern.lead[f.bar % 4].find((n) => f.step >= n.s && f.step < n.s + n.l)
    const lf = lead ? m2f(lead.m) : 220
    const bnote = this.pattern.bass[f.bar % 4].find((n) => f.step >= n.s && f.step < n.s + n.l)
    const bf = bnote ? m2f(bnote.m) : 55
    let rms = 0
    for (let i = 0; i < 512; i++) {
      const x = i / 512
      const ph = x * 6.2832
      let v = e.bass * 0.5 * Math.sin(ph * (bf / 55) * 1.5 + t) + e.voice * 0.4 * Math.sin(ph * (lf / 110) * 2) * (1 + 0.3 * Math.sin(ph * 5))
      v += e.keys * 0.22 * Math.sin(ph * 9 + t * 2) * Math.sin(ph * 2)
      v += e.kick * 0.7 * Math.sin(ph * 1.5) * (1 - x) + e.snare * 0.35 * (Math.sin(i * 12.9898 + t * 99) * 0.9) + e.hat * 0.15 * Math.sin(i * 4.1 + t * 300)
      if (!this.playing) v = 0.12 * Math.sin(ph * 3 + t) * Math.sin(ph * 1.3 - t * 0.6) + 0.06 * Math.sin(ph * 11 + t * 1.7)
      v += this.excite * 0.5 * Math.sin(i * 7.77 + Math.floor(t * 30) * 3.3)
      w[i] = Math.max(-1, Math.min(1, v))
      rms += w[i] * w[i]
    }
    f.level = Math.min(1, Math.sqrt(rms / 512) * 2.2)
    for (const s of STEMS) {
      const a = f.stemWave[s.id], amp = f.stem[s.id]
      const fr = s.id === 'drums' ? 40 : s.id === 'bass' ? bf / 12 : s.id === 'keys' ? 9 : lf / 40
      for (let i = 0; i < 128; i++) a[i] = amp * Math.sin(i * 0.1 * fr + t * (2 + fr * 0.2)) * (s.id === 'drums' ? 0.6 + 0.4 * Math.sin(i * 7.31 + t * 77) : 1) * 0.8
    }
  }
}

export const engine = new Engine()
export { m2f }
