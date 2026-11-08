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
import { bufferToWav } from './wav'

export { dbToGain }
export const MASTER_ID = '__master__'

type Channel = { id: string; buffer: AudioBuffer; original: AudioBuffer; chain: Chain; source?: AudioBufferSourceNode }
type Listener = () => void
export type Region = { start: number; end: number }
export type OutputState = 'running' | 'suspended' | 'interrupted' | 'closed' | 'none'
/** How sound reaches the speakers: Web Audio, or the HTML media element fallback when Web Audio is held. */
export type OutputPath = 'webaudio' | 'media'

export const isTouchDevice = () => typeof window !== 'undefined' && (('ontouchend' in document) || (navigator.maxTouchPoints ?? 0) > 0 || matchMedia?.('(pointer: coarse)').matches)
const isAppleTouch = () => /iP(hone|ad|od)/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && (navigator.maxTouchPoints ?? 0) > 1)

type AudioSessionNav = Navigator & { audioSession?: { type: string } }

/**
 * How the mix leaves the AudioContext.
 * - 'direct': ctx.destination (desktop and live Android instruments).
 * - 'stream': optional non-Apple diagnostic route. Never selected on Apple touch.
 * Loaded phone tracks use a primed HTMLAudioElement with a file URL or offline WAV bounce.
 * Override with localStorage 'nodaw-audio-route' = 'direct' | 'stream' or ?route=direct|stream.
 */
export type OutRoute = 'direct' | 'stream'
function preferredRoute(): OutRoute {
  // A resolved MediaStream play() is not evidence of audible output on Safari.
  if (isAppleTouch()) return 'direct'
  try {
    const q = new URLSearchParams(location.search).get('route')
    if (q === 'direct' || q === 'stream') { localStorage.setItem('nodaw-audio-route', q); return q }
    const v = localStorage.getItem('nodaw-audio-route')
    if (v === 'direct' || v === 'stream') return v
  } catch { /* storage blocked */ }
  return 'direct'
}
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
  /** Gain into ctx.destination: 1 on the direct route, 0 while the stream element carries the sound. */
  private directGain: GainNode | null = null
  private streamDest: MediaStreamAudioDestinationNode | null = null
  /** The <audio> element that plays the mix on the 'stream' route (exposed for the automated checks). */
  streamEl: HTMLAudioElement | null = null
  /** Route that is live right now ('stream' only once its element is actually playing). */
  route: OutRoute = 'direct'
  readonly wantRoute: OutRoute = typeof window !== 'undefined' ? preferredRoute() : 'direct'
  /** Gesture-primed HTMLAudioElement: primary loaded-track output on touch devices. */
  private fallbackEl: HTMLAudioElement | null = null
  private fallbackUrl = ''
  path: OutputPath = 'webaudio'
  /** True once any real user gesture reached unlock(). */
  gestured = false
  /** Result of the last audible check (test tone through the analyser). */
  lastVerify: { rms: number; state: OutputState; at: number; path: OutputPath } | null = null
  /** Channels loaded before the first gesture: decoded offline and installed when the context exists. */
  private deferred: { list: { id: string; buffer: AudioBuffer }[]; keep: number } | null = null
  private decoder: OfflineAudioContext | null = null
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
      this.directGain = ctx.createGain()
      this.masterAnalyser.connect(this.directGain)
      this.directGain.connect(ctx.destination)
      this.masterAnalyser.connect(this.outAnalyser)
      ctx.onstatechange = () => {
        this.onState()
      }
      const wake = () => {
        if (document.visibilityState !== 'visible') return
        void this.resume()
        if (this.streamEl?.paused && this.gestured) void this.streamEl.play().catch(() => undefined)
      }
      document.addEventListener('visibilitychange', wake)
      window.addEventListener('pageshow', wake)
      window.addEventListener('focus', wake)
      this.applyMaster(this.lastMixer[MASTER_ID] ?? DEFAULT_STEM, this.lastMaster.gain_db, this.lastMaster.limiter)
      if (this.deferred) {
        const d = this.deferred
        this.deferred = null
        this.setChannels(d.list, d.keep)
      }
    }
    if (this.ctx.state !== 'running') void this.resume()
    return this.ctx
  }

  private onState() {
    const st = this.ctx?.state as string | undefined
    if (st === 'running') {
      this.blocked = false
      if (this.playing && !this.sourcesLive && this.path === 'webaudio') this.startSources()
    } else if ((st === 'interrupted' || st === 'suspended') && document.visibilityState === 'visible') {
      // iOS: a call, Siri or another app took the audio session. Try to take it back; a tap may be needed.
      window.setTimeout(() => { void this.resume() }, 250)
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
   * Call synchronously from a real user gesture (click, touchend, pointerup, keydown, and at the top of
   * every play, pad, key and record handler). Creates the AudioContext inside the gesture if it does not
   * exist yet, resumes it, plays a silent buffer, and starts a silent media element so iOS treats the
   * page as media playback (the ringer switch no longer mutes it). Cheap to call repeatedly.
   */
  unlock() {
    this.gestured = true
    const ctx = this.ensure()
    if (ctx.state !== 'running') {
      try {
        const b = ctx.createBuffer(1, 1, 22050)
        const s = ctx.createBufferSource()
        s.buffer = b
        s.connect(ctx.destination)
        s.start(0)
      } catch { /* ignore */ }
      void ctx.resume().then(() => {
        this.unlocked = ctx.state === 'running'
        if (this.unlocked) this.blocked = false
        this.emit()
      }).catch(() => undefined)
    } else this.unlocked = true
    if (isAppleTouch()) {
      try { const s = (navigator as AudioSessionNav).audioSession; if (s && s.type !== 'playback') s.type = 'playback' } catch { /* not supported */ }
      if (!this.keepAlive) {
        try {
          const a = document.createElement('audio')
          a.setAttribute('playsinline', '')
          a.setAttribute('webkit-playsinline', '')
          a.setAttribute('x-webkit-airplay', 'deny')
          a.preload = 'auto'
          a.loop = true
          a.src = silentWavUrl()
          this.keepAlive = a
          void a.play().catch(() => { this.keepAlive = null })
        } catch { /* ignore */ }
      } else if (this.keepAlive.paused) void this.keepAlive.play().catch(() => undefined)
    }
    if (this.wantRoute === 'stream' && !isAppleTouch()) this.startStreamRoute(ctx)
    // Prime the fallback media element inside this gesture so a later play() of a bounce is allowed.
    if (!this.fallbackEl && isTouchDevice()) {
      try {
        const f = document.createElement('audio')
        f.setAttribute('playsinline', '')
        f.setAttribute('webkit-playsinline', '')
        f.preload = 'auto'
        f.loop = true
        f.muted = false
        f.volume = 1
        f.src = silentWavUrl()
        this.fallbackEl = f
        // Keep THIS element playing through async generation; don't discard its media permission.
        void f.play().catch(() => { this.blocked = true; this.emit() })
        f.onended = () => {
          if (f.src === chimeUrl) {
            // The first-run sound check must not leave the primed element ended
            // while the user spends seconds choosing/generating their first beat.
            f.loop = true
            f.src = silentWavUrl()
            this.path = 'webaudio'
            void f.play().catch(() => undefined)
          } else if (this.path === 'media' && !f.loop) {
            this.playing = false
            this.offset = 0
          }
          this.emit()
        }
      } catch { /* ignore */ }
    } else if (this.fallbackEl?.paused && this.fallbackEl.src === silentUrl && this.path !== 'media') {
      void this.fallbackEl.play().catch(() => undefined)
    }
  }

  /**
   * 'stream' route: send the mix to a MediaStream and play it with an <audio> element started inside
   * this gesture. ctx.destination is only muted once the element is really playing; if it pauses
   * (another app, a call, Safari pausing media) the direct path comes back until the next tap restarts it.
   */
  private startStreamRoute(ctx: AudioContext) {
    if (typeof ctx.createMediaStreamDestination !== 'function') return
    try {
      if (!this.streamDest) {
        this.streamDest = ctx.createMediaStreamDestination()
        this.masterAnalyser.connect(this.streamDest)
        const el = document.createElement('audio')
        el.setAttribute('playsinline', '')
        el.setAttribute('webkit-playsinline', '')
        el.setAttribute('x-webkit-airplay', 'deny')
        el.autoplay = false
        el.srcObject = this.streamDest.stream
        el.addEventListener('playing', () => this.setRoute('stream'))
        el.addEventListener('pause', () => this.setRoute('direct'))
        el.addEventListener('ended', () => this.setRoute('direct'))
        el.addEventListener('error', () => this.setRoute('direct'))
        el.style.display = 'none'
        document.body.appendChild(el)
        this.streamEl = el
      }
      const el = this.streamEl!
      if (el.paused) void el.play().then(() => this.setRoute('stream')).catch(() => this.setRoute('direct'))
    } catch {
      this.setRoute('direct')
    }
  }

  private setRoute(r: OutRoute) {
    if (r === 'stream' && (isAppleTouch() || !this.streamEl || this.streamEl.paused)) r = 'direct'
    this.route = r
    const g = this.directGain
    if (g && this.ctx) {
      const t = this.ctx.currentTime
      g.gain.cancelScheduledValues(t)
      g.gain.setTargetAtTime(r === 'stream' ? 0 : 1, t, 0.01)
    }
    this.emit()
  }

  /**
   * Audible check: plays a short two-note chime through the master bus and measures the analyser.
   * If Web Audio is still held after the tap, the chime plays through the primed media element instead.
   * Must be called from a gesture handler (it calls unlock first).
   */
  async verify(): Promise<{ rms: number; state: OutputState; path: OutputPath }> {
    this.unlock()
    const ctx = this.ctx!
    if (ctx.state !== 'running') await this.resume()
    let rms = 0
    if ((ctx.state as string) === 'running' && !isTouchDevice()) {
      // a fresh context can take a few hundred ms before its clock moves (device start-up)
      const c0 = ctx.currentTime
      for (let i = 0; i < 40 && ctx.currentTime === c0; i++) await new Promise((r) => setTimeout(r, 20))
      const t = ctx.currentTime + 0.03
      ;[[659.25, 0], [987.77, 0.11]].forEach(([f, dt]) => {
        const o = ctx.createOscillator()
        const g = ctx.createGain()
        o.type = 'triangle'
        o.frequency.value = f
        g.gain.setValueAtTime(0, t + dt)
        g.gain.linearRampToValueAtTime(0.22, t + dt + 0.01)
        g.gain.exponentialRampToValueAtTime(0.001, t + dt + 0.22)
        o.connect(g).connect(this.instBus)
        o.start(t + dt)
        o.stop(t + dt + 0.25)
      })
      for (let i = 0; i < 50; i++) {
        await new Promise((r) => setTimeout(r, 20))
        rms = Math.max(rms, this.outputRms())
        if (rms > 0.01 && ctx.currentTime > t + 0.15) break
      }
      this.path = 'webaudio'
    } else if (this.fallbackEl) {
      // Web Audio refused to start: prove the media path instead.
      const el = this.fallbackEl
      el.loop = false
      el.src = chimeWavUrl()
      try { await el.play(); rms = el.paused ? 0 : 0.1 } catch { rms = 0 }
      this.path = rms > 0 ? 'media' : 'webaudio'
    }
    this.lastVerify = { rms, state: this.state, at: Date.now(), path: this.path }
    this.emit()
    return this.lastVerify
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

  /** Decoder that does not create the live AudioContext (phones only allow that inside a gesture). */
  decoderCtx(): BaseAudioContext {
    if (this.ctx) return this.ctx
    if (!this.decoder) this.decoder = new OfflineAudioContext(2, 1, 44100)
    return this.decoder
  }

  async decodeBytes(ab: ArrayBuffer): Promise<AudioBuffer> {
    return this.decoderCtx().decodeAudioData(ab)
  }

  async decode(url: string): Promise<AudioBuffer> {
    const ctx = this.decoderCtx()
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
  private loadSeq = 0
  private trackMediaUrl = ''
  async load(list: { id: string; url: string }[], opts: { keepPosition?: boolean; mediaUrl?: string } = {}): Promise<void> {
    const seq = ++this.loadSeq
    const wasPlaying = this.playing || this.pendingPlay
    const keep = opts.keepPosition ? this.currentTime() : 0
    this.stop()
    this.disposeChannels()
    const buffers = await Promise.all(list.map((s) => this.decode(s.url)))
    if (seq !== this.loadSeq) return
    this.trackMediaUrl = opts.mediaUrl ?? ''
    this.install(list.map((s, i) => ({ id: s.id, buffer: buffers[i] })), keep)
    if (wasPlaying || this.pendingPlay) this.play()
    this.emit()
  }

  /** Install channels now, or keep them until the first gesture creates the AudioContext. */
  private install(list: { id: string; buffer: AudioBuffer }[], keep: number) {
    if (!this.ctx && !this.gestured) {
      this.deferred = { list, keep }
      this.duration = Math.max(0, ...list.map((b) => b.buffer.duration))
      this.bufferRev++
      return
    }
    this.setChannels(list, keep)
  }

  /** Install already-decoded buffers (used by the stem separator and tests). */
  loadBuffers(list: { id: string; buffer: AudioBuffer }[], keep = 0) {
    this.loadSeq++
    this.trackMediaUrl = ''
    this.stop()
    this.disposeChannels()
    this.install(list, keep)
    if (this.pendingPlay) this.play()
    this.emit()
  }

  private disposeChannels() {
    this.channels.forEach((c) => c.chain.dispose())
    this.channels.clear()
    this.deferred = null
  }

  private setChannels(list: { id: string; buffer: AudioBuffer }[], keep: number) {
    this.bufferRev++
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
    this.trackMediaUrl = ''
    this.bufferRev++
    this.duration = Math.max(0, ...[...this.channels.values()].map((x) => x.buffer.duration))
    this.offset = Math.min(t, this.duration)
    if (was) { this.playing = false; this.play() }
    this.emit()
  }

  buffer(id: string) {
    return this.channels.get(id)?.buffer ?? this.deferred?.list.find((c) => c.id === id)?.buffer
  }
  original(id: string) {
    return this.channels.get(id)?.original
  }
  ids() {
    return this.deferred ? this.deferred.list.map((c) => c.id) : [...this.channels.keys()]
  }
  analyser(id: string) {
    return this.channels.get(id)?.chain.analyser
  }

  applyParams(id: string, p: StemParams, anySolo: boolean) {
    const changed = JSON.stringify(this.lastMixer[id]) !== JSON.stringify(p)
    this.lastMixer[id] = p
    if (changed) this.refreshMedia()
    const c = this.channels.get(id)
    if (!c || !this.ctx) return
    c.chain.apply(p, { audible: !p.mute && (!anySolo || p.solo) })
  }

  applyMaster(p: StemParams, gainDb: number, limiter = true) {
    const changed = JSON.stringify([this.lastMixer[MASTER_ID], this.lastMaster]) !== JSON.stringify([p, { gain_db: gainDb, limiter }])
    this.lastMixer[MASTER_ID] = p
    this.lastMaster = { gain_db: gainDb, limiter }
    if (changed) this.refreshMedia()
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
    if (this.path === 'media') return this.playing && this.fallbackEl && !this.blocked ? this.fallbackEl.currentTime + (this.region?.start ?? 0) : this.offset
    if (!this.ctx || !this.playing || !this.sourcesLive) return this.offset
    const t = Math.max(0, this.ctx.currentTime - this.startedAt)
    const r = this.region
    if (this.loop && r && r.end > r.start) return t < r.end ? t : r.start + ((t - r.start) % (r.end - r.start))
    if (this.loop && this.duration > 0) return t % this.duration
    return Math.min(t, this.stopAt || this.duration)
  }

  play() {
    if (this.gestured || (navigator as Navigator & { userActivation?: { isActive: boolean } }).userActivation?.isActive) this.unlock()
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
    if (isTouchDevice() && this.fallbackEl) {
      // Phones use normal file media playback even when a RUNNING context is inaudible.
      this.path = 'media'
      this.blocked = true
      void this.playViaMedia()
    } else if (ctx.state === 'running') {
      this.path = 'webaudio'
      this.startSources()
    } else {
      this.blocked = true
      void this.resume().then((ok) => {
        if (ok && this.playing && !this.sourcesLive) { this.path = 'webaudio'; this.startSources() }
        else if (!ok && this.playing && this.fallbackEl) void this.playViaMedia()
      })
    }
    this.emit()
  }

  /**
   * Phone primary output: a full mix URL while untouched, otherwise the identical offline FX graph
   * bounced to WAV. Never depends on a running-but-inaudible iOS destination or a MediaStream.
   */
  private mediaRefresh: ReturnType<typeof setTimeout> | undefined
  private refreshMedia() {
    if (this.path !== 'media' || !this.playing) return
    clearTimeout(this.mediaRefresh)
    this.mediaRefresh = setTimeout(() => {
      if (this.path !== 'media' || !this.playing) return
      this.offset = this.currentTime()
      void this.playViaMedia()
    }, 180)
  }
  private mediaSeq = 0
  private fallbackKey = ''
  private async playViaMedia() {
    const el = this.fallbackEl
    if (!el || !this.channels.size) return
    const seq = ++this.mediaSeq
    let usedTrackUrl = false
    try {
      const r = this.region
      const key = JSON.stringify([
        Array.from(this.channels, ([id, c]) => [id, c.buffer.length]),
        this.bufferRev, this.lastMixer, this.lastMaster, r,
      ])
      // The track URL is its full mixdown. Only use it while the mix is untouched.
      const neutral = [...this.channels.keys(), MASTER_ID].every((id) => {
        const p = this.lastMixer[id] ?? DEFAULT_STEM
        return Object.keys(DEFAULT_STEM).every((k) => p[k as keyof StemParams] === DEFAULT_STEM[k as keyof StemParams])
      }) && this.lastMaster.gain_db === 0 && !r
      let url = neutral ? this.trackMediaUrl : ''
      usedTrackUrl = !!url
      if (!url && (key !== this.fallbackKey || !this.fallbackUrl)) {
        const buf = await this.bounce({ mixer: this.lastMixer, masterGainDb: this.lastMaster.gain_db, limiter: this.lastMaster.limiter, range: r, tail: 0, sampleRate: 44100 })
        if (!this.playing || seq !== this.mediaSeq) return
        if (this.fallbackUrl) URL.revokeObjectURL(this.fallbackUrl)
        this.fallbackUrl = URL.createObjectURL(bufferToWav(buf, 16))
        this.fallbackKey = key
      }
      url ||= this.fallbackUrl
      if (!this.playing || seq !== this.mediaSeq) return
      this.path = 'media'
      el.muted = false
      el.volume = 1
      el.loop = this.loop
      if (el.getAttribute('src') !== url) el.src = url
      const start = r?.start ?? 0
      const end = r?.end ?? this.duration
      const off = this.offset < start || this.offset >= end - 0.01 ? start : this.offset
      const seek = () => {
        if (seq !== this.mediaSeq) return
        try { el.currentTime = Math.max(0, off - start) } catch { /* seek again on metadata */ }
      }
      // Safari can reject seeks until metadata arrives after a src replacement.
      if (el.readyState >= 1) seek()
      else el.addEventListener('loadedmetadata', seek, { once: true })
      await el.play()
      if (seq !== this.mediaSeq) return
      this.path = 'media'
      this.blocked = false
    } catch (error) {
      if (seq === this.mediaSeq && this.playing && usedTrackUrl && (error as Error).name !== 'NotAllowedError') {
        // Missing/unsupported server mix: render decoded channels instead, on the same element.
        this.trackMediaUrl = ''
        await this.playViaMedia()
        return
      }
      if (seq === this.mediaSeq) {
        this.blocked = true
        this.playing = false // allow the next Play tap to retry permission/network failures
      }
    }
    this.emit()
  }

  private stopMedia() {
    this.mediaSeq++
    clearTimeout(this.mediaRefresh)
    if (this.path !== 'media') return
    try { this.fallbackEl?.pause() } catch { /* ignore */ }
    this.path = 'webaudio'
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
    this.stopMedia()
    this.killSources()
    this.playing = false
    this.blocked = false
    this.emit()
  }

  stop() {
    this.pendingPlay = false
    this.stopMedia()
    this.killSources()
    this.playing = false
    this.offset = this.region ? this.region.start : 0
    this.emit()
  }

  seek(t: number) {
    const was = this.playing
    this.stopMedia()
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
      this.stopMedia()
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
      this.stopMedia()
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

let chimeUrl = ''
/** Short audible two-note chime for the media-element path of the sound check. */
function chimeWavUrl(): string {
  if (chimeUrl) return chimeUrl
  const sr = 44100, n = Math.floor(sr * 0.4)
  const d = new Float32Array(n)
  for (let i = 0; i < n; i++) {
    const t = i / sr
    const f = t < 0.11 ? 659.25 : 987.77
    const t0 = t < 0.11 ? t : t - 0.11
    d[i] = 0.25 * Math.sin(2 * Math.PI * f * t) * Math.min(1, t0 * 100) * Math.exp(-t0 * 14)
  }
  const b = new AudioBuffer({ length: n, sampleRate: sr, numberOfChannels: 1 })
  b.copyToChannel(d, 0)
  chimeUrl = URL.createObjectURL(bufferToWav(b, 16))
  return chimeUrl
}

export const audio = new StudioAudio()

/** Install the gesture listeners that unlock audio on the first real tap, click or key. */
export function installAudioUnlock() {
  // touchend, pointerup, click and keydown are activation-triggering; a touch pointerdown is not,
  // so it only helps on desktop. Listeners stay installed: iOS can suspend the context again later.
  const evs = ['pointerdown', 'pointerup', 'touchend', 'click', 'keydown'] as const
  const handler = (e: Event) => {
    if (e.type === 'pointerdown' && (e as PointerEvent).pointerType !== 'mouse') return
    if (audio.state === 'running' && audio.unlocked && !isAppleTouch()) return
    audio.unlock()
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
