import { MODELS, MODEL_ORDER, formatBytes } from './models.js'
import { isModelCached, clearModelCache, storageInfo } from './model-store.js'

export { MODELS, MODEL_ORDER, formatBytes, isModelCached, clearModelCache, storageInfo }

export type ModelDef = {
  id: string
  label: string
  short: string
  description: string
  stems: string[]
  sampleRate: number
  sizeBytes: number
  minMemoryGB?: number
  ramHint: string
  speedHint: string
  warning: string | null
  license: { spdx: string; name: string; url: string; note?: string; caveat?: string }
}

export type SepCaps = {
  webgpu: boolean
  gpuReason: string | null
  isolated: boolean
  cores: number
  memoryGB: number | null
  mobile: boolean
  ios: boolean
  lowMemory: boolean
  /** Longest clip we let this device separate in one go. */
  maxSeconds: number
  recommended: string
}

export async function detectSepCaps(): Promise<SepCaps> {
  const ua = navigator.userAgent
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
  const mobile = ios || /Android/i.test(ua) || (matchMedia?.('(pointer: coarse)').matches && Math.min(screen.width, screen.height) < 820)
  const memoryGB = (navigator as unknown as { deviceMemory?: number }).deviceMemory ?? null
  const lowMemory = ios || (memoryGB !== null && memoryGB <= 4) || (mobile && memoryGB === null)
  let webgpu = false
  let gpuReason: string | null = null
  const nav = navigator as unknown as { gpu?: { requestAdapter: (o?: unknown) => Promise<{ features: Set<string> } | null> } }
  if (!nav.gpu) gpuReason = 'This browser has no WebGPU, so the separator runs on the CPU (WASM). Chrome or Edge on a desktop with a GPU is much faster.'
  else {
    try {
      const adapter = await nav.gpu.requestAdapter()
      if (!adapter) gpuReason = 'No GPU adapter is available, so the separator runs on the CPU (WASM).'
      else if (!adapter.features.has('shader-f16')) gpuReason = 'This GPU lacks 16-bit shaders, which the models need for WebGPU, so the separator runs on the CPU (WASM).'
      else webgpu = true
    } catch (e) {
      gpuReason = `WebGPU failed to start (${(e as Error).message}), so the separator runs on the CPU (WASM).`
    }
  }
  return {
    webgpu,
    gpuReason,
    isolated: typeof crossOriginIsolated !== 'undefined' && crossOriginIsolated,
    cores: navigator.hardwareConcurrency || 2,
    memoryGB,
    mobile,
    ios,
    lowMemory,
    maxSeconds: lowMemory ? 45 : webgpu ? 600 : 240,
    recommended: lowMemory ? 'mini' : 'htdemucs',
  }
}

export type SepProgress = {
  phase: 'download' | 'init' | 'ready' | 'fallback' | 'separate'
  loaded?: number
  total?: number
  fromCache?: boolean
  done?: number
  etaMs?: number
  elapsedMs?: number
  backend?: string
  notice?: string
  verifying?: boolean
}

export type SepResult = {
  stems: Record<string, [Float32Array, Float32Array]>
  backend: string
  ms: number
  sampleRate: number
  frames: number
  threads: string
}

export class BrowserSeparator {
  private worker: Worker | null = null
  private listener: ((m: Record<string, unknown>) => void) | null = null
  private threads = 'single'

  private ensure() {
    if (this.worker) return this.worker
    const w = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' })
    w.onmessage = (ev) => this.listener?.(ev.data)
    w.onerror = (ev) => this.listener?.({ type: 'error', message: ev.message || 'The separator worker crashed' })
    this.worker = w
    return w
  }

  private call<T>(msg: Record<string, unknown>, until: string, onProgress?: (p: SepProgress) => void, transfer: Transferable[] = []) {
    const w = this.ensure()
    return new Promise<T>((resolve, reject) => {
      this.listener = (m) => {
        if (m.type === 'progress') return onProgress?.(m as unknown as SepProgress)
        if (m.type === 'error') {
          this.listener = null
          return reject(Object.assign(new Error(String(m.message)), { cancelled: !!m.cancelled }))
        }
        if (m.type === until) {
          this.listener = null
          resolve(m as unknown as T)
        }
      }
      w.postMessage(msg, transfer)
    })
  }

  async load(modelId: string, device: 'auto' | 'wasm' | 'webgpu', onProgress?: (p: SepProgress) => void) {
    const r = await this.call<{ backend: string; gpuError: string | null; threads: string }>({ type: 'load', modelId, device }, 'loaded', onProgress)
    this.threads = r.threads
    return r
  }

  async separate(left: Float32Array, right: Float32Array, onProgress?: (p: SepProgress) => void): Promise<SepResult> {
    const r = await this.call<SepResult>({ type: 'separate', left, right }, 'done', onProgress, [left.buffer, right.buffer])
    return { ...r, threads: this.threads }
  }

  cancel() {
    this.worker?.postMessage({ type: 'cancel' })
  }

  release() {
    this.worker?.postMessage({ type: 'release' })
  }

  terminate() {
    this.worker?.terminate()
    this.worker = null
    this.listener = null
  }
}

/** Planar 44.1 kHz stereo copy of a decoded AudioBuffer (resampled when needed). */
export async function toStereo44k(buf: AudioBuffer, from = 0, to = buf.duration): Promise<{ left: Float32Array; right: Float32Array }> {
  const SR = 44100
  const frames = Math.max(1, Math.round((to - from) * SR))
  const off = new OfflineAudioContext(2, frames, SR)
  const src = off.createBufferSource()
  src.buffer = buf
  src.connect(off.destination)
  src.start(0, from, to - from)
  const out = await off.startRendering()
  return { left: out.getChannelData(0).slice(), right: out.getChannelData(Math.min(1, out.numberOfChannels - 1)).slice() }
}
