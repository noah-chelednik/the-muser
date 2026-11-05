/**
 * The sample bank behind the 16 pads. A pad with a sample plays it (with its own pitch, rate and gain);
 * an empty pad keeps its synthesized drum. Kits persist in IndexedDB.
 */
import type { PadParams } from '../types'
import { audio } from './engine'
import { bufferToWav, planesToBuffer, safeName } from './wav'
import { zipFiles } from '../demo/zip'

export type PadSample = { name: string; buffer: AudioBuffer; pitch: number; rate: number; gain: number }

const bank: (PadSample | null)[] = Array.from({ length: 16 }, () => null)
const listeners = new Set<() => void>()
let version = 0
const emit = () => { version++; listeners.forEach((l) => l()) }

export const padBank = {
  get: (i: number) => bank[i],
  all: () => bank,
  version: () => version,
  subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } },
  set(i: number, s: PadSample | null) { bank[i] = s; emit() },
  update(i: number, patch: Partial<PadSample>) { if (bank[i]) { bank[i] = { ...bank[i]!, ...patch }; emit() } },
  clearAll() { bank.fill(null); emit() },
}

export const samplePlaybackRate = (s: PadSample, p?: PadParams) => s.rate * Math.pow(2, (s.pitch + (p?.pitch ?? 0)) / 12)

/** Fire a pad sample. Returns false when the pad has none. */
export function playPadSample(i: number, when: number, p: PadParams): boolean {
  const s = bank[i]
  if (!s) return false
  const ctx = audio.ensure()
  const src = ctx.createBufferSource()
  src.buffer = s.buffer
  src.playbackRate.value = samplePlaybackRate(s, p)
  const g = ctx.createGain()
  const v = p.volume * s.gain
  const t = Math.max(when, ctx.currentTime)
  // short declick at the tail so a one-shot never ends on a step
  const dur = s.buffer.duration / src.playbackRate.value
  g.gain.setValueAtTime(v, t)
  g.gain.setValueAtTime(v, t + Math.max(0, dur - 0.004))
  g.gain.linearRampToValueAtTime(0, t + dur)
  src.connect(g)
  g.connect(audio.instBus)
  src.start(t)
  src.onended = () => { try { g.disconnect() } catch { /* gone */ } }
  return true
}

/** Audition outside the sequencer (sampler tab). */
export const auditionPad = (i: number) => playPadSample(i, 0, { volume: 0.9, pitch: 0, tone: 0.5 })

// ---------------------------------------------------------------- kits (IndexedDB)

type KitPad = { index: number; name: string; pitch: number; rate: number; gain: number; sampleRate: number; planes: Float32Array[] }
export type Kit = { name: string; created: number; pads: KitPad[] }

const DB = 'muser-kits-v1'
function open(): Promise<IDBDatabase> {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB, 1)
    r.onupgradeneeded = () => r.result.createObjectStore('kits', { keyPath: 'name' })
    r.onsuccess = () => res(r.result)
    r.onerror = () => rej(r.error)
  })
}
const tx = async <T,>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> => {
  const db = await open()
  return new Promise((res, rej) => {
    const t = db.transaction('kits', mode)
    const rq = fn(t.objectStore('kits'))
    rq.onsuccess = () => res(rq.result)
    rq.onerror = () => rej(rq.error)
  })
}

export async function saveKit(name: string): Promise<number> {
  const pads: KitPad[] = []
  bank.forEach((s, index) => {
    if (!s) return
    pads.push({ index, name: s.name, pitch: s.pitch, rate: s.rate, gain: s.gain, sampleRate: s.buffer.sampleRate, planes: Array.from({ length: s.buffer.numberOfChannels }, (_, c) => s.buffer.getChannelData(c).slice()) })
  })
  await tx('readwrite', (s) => s.put({ name, created: Date.now(), pads } satisfies Kit))
  return pads.length
}
export const listKits = async (): Promise<{ name: string; created: number; pads: number }[]> =>
  (await tx<Kit[]>('readonly', (s) => s.getAll() as IDBRequest<Kit[]>)).map((k) => ({ name: k.name, created: k.created, pads: k.pads.length })).sort((a, b) => b.created - a.created)
export async function loadKit(name: string): Promise<number> {
  const k = await tx<Kit | undefined>('readonly', (s) => s.get(name) as IDBRequest<Kit | undefined>)
  if (!k) throw new Error(`No kit called ${name}`)
  audio.ensure()
  bank.fill(null)
  k.pads.forEach((p) => { bank[p.index] = { name: p.name, pitch: p.pitch, rate: p.rate, gain: p.gain, buffer: planesToBuffer(p.planes, p.sampleRate) } })
  emit()
  return k.pads.length
}
export const deleteKit = (name: string) => tx('readwrite', (s) => s.delete(name))

export async function kitZip(name: string): Promise<Blob> {
  const files: { name: string; blob: Blob }[] = []
  const meta: unknown[] = []
  bank.forEach((s, i) => {
    if (!s) return
    const file = `pad${String(i + 1).padStart(2, '0')}_${safeName(s.name)}.wav`
    files.push({ name: file, blob: bufferToWav(s.buffer, 24) })
    meta.push({ pad: i + 1, file, name: s.name, pitch_semitones: s.pitch, rate: s.rate, gain: s.gain })
  })
  files.push({ name: 'kit.json', blob: new Blob([JSON.stringify({ kit: name, pads: meta }, null, 2)], { type: 'application/json' }) })
  return zipFiles(files)
}
