/**
 * Web Audio engine: multi-stem playback with a live per-stem and master FX
 * chain (see fx.ts), region looping, gesture-time unlock for desktop and phone
 * browsers, and an OfflineAudioContext bounce that renders the same graph.
 *
 *   stem chain x N -> stemBus --\
 *   pads / synth   -> instBus --+-> master chain -> master gain -> limiter
 *                                                      -> analyser -> destination
 */
import type { StemParams } from '../types'
import { DEFAULT_STEM } from '../types'
import { buildChain, dbToGain, type Chain } from './fx'

export { dbToGain }
export const MASTER_ID = '__master__'

type Channel = { id: string; buffer: AudioBuffer; original: AudioBuffer; chain: Chain; source?: AudioBufferSourceNode }
type Listener = () => void
export type Region = { start: number; end: number }
export type OutputState = 'running' | 'suspended' | 'interrupted' | 'closed' | 'none'

type AudioSessionNav = Navigator & { audioSession?: { type: string } }
const AC: typeof AudioContext = (window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)

class StudioAudio {
  ctx: AudioContext | null = null
  master!: GainNode
  limiter!: DynamicsCompressorNode
  masterAnalyser!: AnalyserNode
  /** Probe tap on whatever feeds the speakers; the automated audibility check reads it. */
  outAnalyser!: AnalyserNode
  stemBus!: GainNode
  instBus!: GainNode
  masterChain!: Chain
  private channels = new Map<string, Channel>()
  private bufferCache = new Map<string, Promise<AudioBuffer>>()
  private startedAt = 0
  private offset = 0
  private sourcesLive = false
  private pendingPlay = false
  private stopAt = 0
  playing = false
  /** Bumped whenever a channel buffer is swapped (sampler edits) so waveforms can redraw. */
  bufferRev = 0
  loop = true
  region: Region | null = null
  duration = 0
  /** True when playback was requested but the browser has not let the context run yet. */
  blocked = false
  unlocked = false
  private listeners = new Set<Listener>()
  private keepAlive: HTMLAudioElement | null = null
  private lastMixer: Record<string, StemParams> = {}
  private lastMaster = { gain_db: 0, limiter: true }

  get state(): OutputState {
    return this.ctx ? (this.ctx.state as OutputState) : 'none'
  }

  ensure(): AudioContext {
    if (!this.ctx) {
      // iOS: use the "playback" audio category so the ringer switch does not mute Web Audio.
      try {
        const s = (navigator as AudioSessionNav).audioSession
        if (s) s.type = 'playback'
      } catch { /* not supported */ }
      const ctx = new AC({ latencyHint: 'interactive' })
      this.ctx = ctx
      this.master = ctx.createGain()
      this.limiter = ctx.createDynamicsCompressor()
      this.limiter.threshold.value = -1
      this.limiter.knee.value = 0
      this.limiter.ratio.value = 20
      this.limiter.attack.value = 0.002
      this.limiter.release.value = 0.1
      this.masterAnalyser = ctx.createAnalyser()
      this.masterAnalyser.fftSize = 1024
      this.outAnalyser = ctx.createAnalyser()
      this.outAnalyser.fftSize = 2048
      this.stemBus = ctx.createGain()
      this.instBus = ctx.createGain()
      this.masterChain = buildChain(ctx)
      this.stemBus.connect(this.masterChain.input)
      this.instBus.connect(this.masterChain.input)
      this.masterChain.output.connect(this.master)
      this.master.connect(this.limiter)
      this.limiter.connect(this.masterAnalyser)
      this.masterAnalyser.connect(ctx.destination)
      this.masterAnalyser.connect(this.outAnalyser)
      ctx.onstatechange = () => {
        this.onState()
      }
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') void this.resume()
      })
      this.applyMaster(this.lastMixer[MASTER_ID] ?? DEFAULT_STEM, this.lastMaster.gain_db, this.lastMaster.limiter)
    }
    if (this.ctx.state !== 'running') void this.resume()
    return this.ctx
  }

  private onState() {
    if (this.ctx?.state === 'running') {
      this.blocked = false
      if (this.playing && !this.sourcesLive) this.startSources()
    }
    this.emit()
  }

  /** Resume the context. Safari reports 'interrupted' after calls or lock; both need resume(). */
  async resume(): Promise<boolean> {
    const ctx = this.ctx
    if (!ctx) return false
    try {
      if (ctx.state !== 'running') await Promise.race([ctx.resume(), new Promise((r) => setTimeout(r, 1500))])
    } catch { /* needs a gesture */ }
    const ok = (ctx.state as string) === 'running'
    this.blocked = !ok && (this.playing || this.pendingPlay)
    this.emit()
    return ok
  }

  /**
   * Call from a real user gesture (pointerdown, touchend, click, keydown).
   * Resumes the context, plays a silent buffer, and starts a silent media element
   * so iOS treats the page as media playback (the ringer switch no longer mutes it).
   */
  unlock() {
    const ctx = this.ensure()
    try {
      const b = ctx.createBuffer(1, 1, 22050)
      const s = ctx.createBufferSource()
      s.buffer = b
      s.connect(ctx.destination)
      s.start(0)
    } catch { /* ignore */ }
    void ctx.resume().then(() => {
      this.unlocked = ctx.state === 'running'
      this.blocked = false
      this.emit()
    }).catch(() => undefined)
    if (!this.keepAlive && /iP(hone|ad|od)|Macintosh/.test(navigator.userAgent) && 'ontouchend' in document) {
      try {
        const a = document.createElement('audio')
        a.setAttribute('playsinline', '')
        a.setAttribute('x-webkit-airplay', 'deny')
        a.loop = true
        a.volume = 0.0001
        a.src = silentWavUrl()
        this.keepAlive = a
        void a.play().catch(() => { this.keepAlive = null })
      } catch { /* ignore */ }
    }
  }

  subscribe(fn: Listener) {
    this.listeners.add(fn)
    return () => {
      this.listeners.delete(fn)
    }
  }
  private emit() {
    this.listeners.forEach((l) => l())
  }

  async decodeBytes(ab: ArrayBuffer): Promise<AudioBuffer> {
    return this.ensure().decodeAudioData(ab)
  }

  async decode(url: string): Promise<AudioBuffer> {
    const ctx = this.ensure()
    if (!this.bufferCache.has(url)) {
      this.bufferCache.set(
        url,
        fetch(url)
          .then((r) => {
            if (!r.ok) throw new Error(`Failed to load ${url}`)
            return r.arrayBuffer()
          })
          .then((ab) => ctx.decodeAudioData(ab)),
      )
    }
    return this.bufferCache.get(url)!
  }

  /** Replace the loaded channel set. */
  async load(list: { id: string; url: string }[], opts: { keepPosition?: boolean } = {}): Promise<void> {
    const ctx = this.ensure()
    const wasPlaying = this.playing
    const keep = opts.keepPosition ? this.currentTime() : 0
    this.stop()
    this.disposeChannels()
    const buffers = await Promise.all(list.map((s) => this.decode(s.url)))
    this.setChannels(list.map((s, i) => ({ id: s.id, buffer: buffers[i] })), keep)
    void ctx
    if (wasPlaying || this.pendingPlay) this.play()
    this.emit()
  }

  /** Install already-decoded buffers (used by the stem separator and tests). */
  loadBuffers(list: { id: string; buffer: AudioBuffer }[], keep = 0) {
    this.ensure()
    this.stop()
    this.disposeChannels()
    this.setChannels(list, keep)
    if (this.pendingPlay) this.play()
    this.emit()
  }

  private disposeChannels() {
    this.channels.forEach((c) => c.chain.dispose())
    this.channels.clear()
  }

  private setChannels(list: { id: string; buffer: AudioBuffer }[], keep: number) {
    const ctx = this.ensure()
    list.forEach((s) => {
      const chain = buildChain(ctx, { meter: true })
      chain.output.connect(this.stemBus)
      this.channels.set(s.id, { id: s.id, buffer: s.buffer, original: s.buffer, chain })
      chain.apply(this.lastMixer[s.id] ?? DEFAULT_STEM, { audible: true })
    })
    this.duration = Math.max(0, ...list.map((b) => b.buffer.duration))
    this.offset = Math.min(keep, Math.max(0, this.duration - 0.05))
    if (this.region && this.region.end > this.duration) this.region = null
  }

  /** Swap one channel's audio (crop, normalize, reverse...) without touching its chain. */
  setBuffer(id: string, buffer: AudioBuffer | null) {
    const c = this.channels.get(id)
    if (!c) return
    const next = buffer ?? c.original
    if (c.buffer === next) return
    const was = this.playing
    const t = this.currentTime()
    if (was) this.killSources()
    c.buffer = next
    this.bufferRev++
    this.duration = Math.max(0, ...[...this.channels.values()].map((x) => x.buffer.duration))
    this.offset = Math.min(t, this.duration)
    if (was) { this.playing = false; this.play() }
    this.emit()
  }

  buffer(id: string) {
    return this.channels.get(id)?.buffer
  }
  original(id: string) {
    return this.channels.get(id)?.original
  }
  ids() {
    return [...this.channels.keys()]
  }
  analyser(id: string) {
    return this.channels.get(id)?.chain.analyser
  }

  applyParams(id: string, p: StemParams, anySolo: boolean) {
    this.lastMixer[id] = p
    const c = this.channels.get(id)
    if (!c || !this.ctx) return
    c.chain.apply(p, { audible: !p.mute && (!anySolo || p.solo) })
  }

  applyMaster(p: StemParams, gainDb: number, limiter = true) {
    this.lastMixer[MASTER_ID] = p
    this.lastMaster = { gain_db: gainDb, limiter }
    if (!this.ctx) return
    const t = this.ctx.currentTime
    this.masterChain.apply({ ...p, pan: 0, mute: false, solo: false, gain_db: 0 })
    this.master.gain.setTargetAtTime(dbToGain(gainDb), t, 0.02)
    this.limiter.threshold.setTargetAtTime(limiter ? -1 : 0, t, 0.02)
    this.limiter.ratio.setTargetAtTime(limiter ? 20 : 1, t, 0.02)
  }

  setMasterGain(db: number) {
    this.applyMaster(this.lastMixer[MASTER_ID] ?? DEFAULT_STEM, db, this.lastMaster.limiter)
  }

  /** RMS of what is about to reach the speakers (post limiter). Used by the audibility test. */
  outputRms(): number {
    if (!this.ctx) return 0
    const buf = new Float32Array(this.outAnalyser.fftSize)
    this.outAnalyser.getFloatTimeDomainData(buf)
    let s = 0
    for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i]
    return Math.sqrt(s / buf.length)
  }

  currentTime(): number {
    if (!this.ctx || !this.playing || !this.sourcesLive) return this.offset
    const t = Math.max(0, this.ctx.currentTime - this.startedAt)
    const r = this.region
    if (this.loop && r && r.end > r.start) return t < r.end ? t : r.start + ((t - r.start) % (r.end - r.start))
    if (this.loop && this.duration > 0) return t % this.duration
    return Math.min(t, this.stopAt || this.duration)
  }

  play() {
    const ctx = this.ensure()
    if (this.playing) return
    if (!this.channels.size) {
      // tapped before the audio finished loading: start as soon as it is ready
      this.pendingPlay = true
      this.emit()
      return
    }
    this.pendingPlay = false
    this.playing = true
    if (ctx.state === 'running') this.startSources()
    else {
      this.blocked = true
      void this.resume().then((ok) => {
        if (ok && this.playing && !this.sourcesLive) this.startSources()
      })
    }
    this.emit()
  }

  private startSources() {
    const ctx = this.ctx!
    if (!this.playing || this.sourcesLive) return
    const r = this.region
    let off = this.offset >= this.duration - 0.01 ? 0 : Math.max(0, this.offset)
    if (r && (off < r.start || off >= r.end)) off = r.start
    const when = ctx.currentTime + 0.03
    const regionLoop = !!(this.loop && r)
    this.stopAt = r && !this.loop ? r.end : 0
    this.channels.forEach((c) => {
      const dur = c.buffer.duration
      if (off >= dur && !this.loop) return
      const src = ctx.createBufferSource()
      src.buffer = c.buffer
      src.loop = this.loop
      if (regionLoop) {
        src.loopStart = r!.start
        src.loopEnd = Math.min(r!.end, dur)
      } else if (this.loop) {
        src.loopStart = 0
        src.loopEnd = dur
      }
      src.connect(c.chain.input)
      const o = this.loop && !regionLoop ? off % dur : off
      if (this.stopAt) src.start(when, o, Math.max(0.01, this.stopAt - o))
      else src.start(when, o)
      c.source = src
    })
    this.startedAt = when - off
    this.sourcesLive = true
    this.blocked = false
    if (!this.loop) {
      const first = [...this.channels.values()].find((c) => c.source)
      const longest = [...this.channels.values()].sort((a, b) => b.buffer.duration - a.buffer.duration)[0]?.source ?? first?.source
      if (longest) {
        longest.onended = () => {
          if (this.playing) {
            this.playing = false
            this.sourcesLive = false
            this.offset = r ? r.start : 0
            this.emit()
          }
        }
      }
    }
  }

  pause() {
    this.pendingPlay = false
    if (!this.playing) return
    this.offset = this.currentTime()
    this.killSources()
    this.playing = false
    this.blocked = false
    this.emit()
  }

  stop() {
    this.pendingPlay = false
    this.killSources()
    this.playing = false
    this.offset = this.region ? this.region.start : 0
    this.emit()
  }

  seek(t: number) {
    const was = this.playing
    this.killSources()
    this.playing = false
    this.offset = Math.max(0, Math.min(t, this.duration))
    if (was) this.play()
    else this.emit()
  }

  setLoop(on: boolean) {
    const t = this.currentTime()
    this.loop = on
    if (this.playing) {
      this.killSources()
      this.playing = false
      this.offset = Math.max(0, t)
      this.play()
    }
    this.emit()
  }

  /** Select a region (seconds). While looping, playback cycles inside it. */
  setRegion(r: Region | null) {
    const was = this.playing
    const t = this.currentTime()
    this.region = r && r.end - r.start > 0.01 ? { start: Math.max(0, r.start), end: Math.min(this.duration, r.end) } : null
    if (was) {
      this.killSources()
      this.playing = false
      this.offset = Math.max(0, t)
      this.play()
    }
    this.emit()
  }

  private killSources() {
    this.sourcesLive = false
    this.channels.forEach((c) => {
      if (c.source) {
        c.source.onended = null
        try {
          c.source.stop()
        } catch {
          /* already stopped */
        }
        c.source.disconnect()
        c.source = undefined
      }
    })
  }

  /**
   * Bounce what you hear: the same chains, built in an OfflineAudioContext.
   * `range` limits it to a region; `tail` seconds are kept for reverb and delay decay.
   */
  async bounce(opts: {
    mixer: Record<string, StemParams>
    masterGainDb: number
    limiter?: boolean
    range?: Region | null
    tail?: number
    only?: string[]
    sampleRate?: number
  }): Promise<AudioBuffer> {
    const live = this.ctx
    const sr = opts.sampleRate ?? live?.sampleRate ?? 44100
    const r = opts.range ?? { start: 0, end: this.duration }
    const body = Math.max(0.05, r.end - r.start)
    const tail = opts.tail ?? 1.5
    const len = Math.ceil((body + tail) * sr)
    const off = new OfflineAudioContext(2, len, sr)
    const ids = (opts.only ?? [...this.channels.keys()]).filter((i) => this.channels.has(i))
    const anySolo = ids.some((i) => opts.mixer[i]?.solo)
    const bus = off.createGain()
    const master = buildChain(off)
    const gain = off.createGain()
    const lim = off.createDynamicsCompressor()
    lim.knee.value = 0
    lim.attack.value = 0.002
    lim.release.value = 0.1
    const useLim = opts.limiter !== false
    lim.threshold.value = useLim ? -1 : 0
    lim.ratio.value = useLim ? 20 : 1
    gain.gain.value = dbToGain(opts.masterGainDb)
    bus.connect(master.input)
    master.output.connect(gain)
    gain.connect(lim)
    lim.connect(off.destination)
    const mp = { ...DEFAULT_STEM, ...(opts.mixer[MASTER_ID] ?? {}), pan: 0, mute: false, solo: false, gain_db: 0 }
    master.apply(mp, { live: false })
    for (const id of ids) {
      const c = this.channels.get(id)!
      const p = { ...DEFAULT_STEM, ...(opts.mixer[id] ?? {}) }
      const chain = buildChain(off)
      chain.apply(p, { live: false, audible: !p.mute && (!anySolo || p.solo) })
      chain.output.connect(bus)
      const src = off.createBufferSource()
      src.buffer = c.buffer
      src.connect(chain.input)
      if (r.start < c.buffer.duration) src.start(0, r.start, Math.min(body, c.buffer.duration - r.start))
    }
    return off.startRendering()
  }
}

let silentUrl = ''
function silentWavUrl(): string {
  if (silentUrl) return silentUrl
  const n = 4410
  const buf = new ArrayBuffer(44 + n * 2)
  const v = new DataView(buf)
  const w = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)))
  w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE'); w(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, 44100, true); v.setUint32(28, 88200, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true)
  w(36, 'data'); v.setUint32(40, n * 2, true)
  for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, i % 2 ? 1 : -1, true)
  silentUrl = URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }))
  return silentUrl
}

export const audio = new StudioAudio()

/** Install the gesture listeners that unlock audio on the first real tap, click or key. */
export function installAudioUnlock() {
  const evs = ['pointerdown', 'touchend', 'click', 'keydown'] as const
  const handler = () => {
    audio.unlock()
    if (audio.state === 'running') evs.forEach((e) => window.removeEventListener(e, handler, true))
  }
  evs.forEach((e) => window.addEventListener(e, handler, { capture: true, passive: true }))
}

/** RMS level 0..1 from an analyser. */
export function level(an: AnalyserNode, buf: Float32Array<ArrayBuffer>): number {
  an.getFloatTimeDomainData(buf)
  let peak = 0
  for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i]))
  return peak
}
