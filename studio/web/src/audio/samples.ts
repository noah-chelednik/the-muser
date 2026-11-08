/**
 * The sample bank behind the 16 pads. A pad with a sample plays it (with its own pitch, rate and gain);
 * an empty pad keeps its synthesized drum. Kits persist in IndexedDB.
 */
import type { PadParams } from '../types'
import { audio } from './engine'
import { buildPadChain, padDestination, type FxSlot } from './padfx'
import { bufferToWav, planesToBuffer, safeName } from './wav'
import { zipFiles } from '../demo/zip'

export type PadSource = { kind: 'library' | 'upload' | 'chop'; id?: string; license?: string; author?: string }
export type PadSample = { name: string; buffer: AudioBuffer; pitch: number; rate: number; gain: number; source?: PadSource }
/** Per-pad settings that apply to the sample or the built-in synth hit alike. */
export type PadSettings = { gain: number; pitch: number; fx: FxSlot[] }
const defaultSettings = (): PadSettings => ({ gain: 1, pitch: 0, fx: [] })

const bank: (PadSample | null)[] = Array.from({ length: 16 }, () => null)
const settings: PadSettings[] = Array.from({ length: 16 }, defaultSettings)
const listeners = new Set<() => void>()
let version = 0
const emit = () => { version++; listeners.forEach((l) => l()); scheduleAutosave() }

export const padBank = {
  get: (i: number) => bank[i],
  all: () => bank,
  version: () => version,
  subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } },
  set(i: number, s: PadSample | null) { bank[i] = s; emit() },
  update(i: number, patch: Partial<PadSample>) { if (bank[i]) { bank[i] = { ...bank[i]!, ...patch }; emit() } },
  clearAll() { bank.fill(null); emit() },
  settings: (i: number) => settings[i],
  setSettings(i: number, patch: Partial<PadSettings>) { settings[i] = { ...settings[i], ...patch }; emit() },
  setFx(i: number, fx: FxSlot[]) { settings[i] = { ...settings[i], fx }; if (audio.ctx) padDestination(i, fx); emit() },
  resetPad(i: number) { bank[i] = null; settings[i] = defaultSettings(); emit() },
}

export const samplePlaybackRate = (s: PadSample, p?: PadParams, extraSemis = 0) => s.rate * Math.pow(2, (s.pitch + (p?.pitch ?? 0) + extraSemis) / 12)

/** Destination node for pad i (its own FX chain, or the instrument bus). */
export const padOut = (i: number) => padDestination(i, settings[i]?.fx)

/**
 * Where pad i's hit goes. Live: the pad's own FX chain. With an explicit destination (playlist track
 * or an offline export) a chain for that destination is built once per FX layout and reused.
 */
const extChains = new WeakMap<AudioNode, Map<number, { sig: string; input: AudioNode }>>()
export function padRoute(i: number, dest?: AudioNode): AudioNode {
  if (!dest) return padOut(i)
  const slots = (settings[i]?.fx ?? []).filter((x) => x.on)
  if (!slots.length) return dest
  let m = extChains.get(dest)
  if (!m) { m = new Map(); extChains.set(dest, m) }
  const sig = JSON.stringify(slots)
  const cur = m.get(i)
  if (cur && cur.sig === sig) return cur.input
  const ch = buildPadChain(dest.context, slots, dest, false)
  m.set(i, { sig, input: ch.input })
  return ch.input
}

/** Fire a pad sample. Returns false when the pad has none. */
export function playPadSample(i: number, when: number, p: PadParams, vel = 1, dest?: AudioNode): boolean {
  const s = bank[i]
  if (!s) return false
  const ctx = (dest?.context ?? audio.ensure()) as BaseAudioContext
  const st = settings[i]
  const src = ctx.createBufferSource()
  src.buffer = s.buffer
  src.playbackRate.value = samplePlaybackRate(s, p, st.pitch)
  const g = ctx.createGain()
  const v = p.volume * s.gain * st.gain * vel
  const t = Math.max(when, ctx.currentTime)
  // short declick at the tail so a one-shot never ends on a step
  const dur = s.buffer.duration / src.playbackRate.value
  g.gain.setValueAtTime(v, t)
  g.gain.setValueAtTime(v, t + Math.max(0, dur - 0.004))
  g.gain.linearRampToValueAtTime(0, t + dur)
  src.connect(g)
  g.connect(padRoute(i, dest))
  src.start(t)
  src.onended = () => { try { g.disconnect() } catch { /* gone */ } }
  return true
}

/** Put a decoded buffer on a pad (the session kit autosaves it). */
export async function loadPadBuffer(i: number, name: string, buffer: AudioBuffer, source?: PadSource) {
  padBank.set(i, { name, buffer, pitch: 0, rate: 1, gain: 1, ...(source ? { source } : {}) })
}

export async function decodeAndLoadPad(i: number, name: string, data: ArrayBuffer) {
  const buffer = await audio.decodeBytes(data.slice(0))
  await loadPadBuffer(i, name.replace(/\.[^.]+$/, ''), buffer)
  return buffer
}

/** Audition outside the sequencer (sampler tab). */
export const auditionPad = (i: number) => playPadSample(i, 0, { volume: 0.9, pitch: 0, tone: 0.5 })

// ---------------------------------------------------------------- kits (IndexedDB)

type KitPad = { index: number; name: string; pitch: number; rate: number; gain: number; sampleRate: number; planes: Float32Array[]; source?: PadSource }
export type Kit = { name: string; created: number; pads: KitPad[]; settings?: PadSettings[] }

/** Autosaved deck (sounds, per-pad level, pitch and FX). Restored on the next visit. */
export const SESSION_KIT = '__session__'

const DB = 'muser-kits-v1'
let dbp: Promise<IDBDatabase> | null = null
export function openDb(): Promise<IDBDatabase> {
  return (dbp ??= new Promise((res, rej) => {
    const r = indexedDB.open(DB, 2)
    r.onupgradeneeded = () => {
      if (!r.result.objectStoreNames.contains('kits')) r.result.createObjectStore('kits', { keyPath: 'name' })
      if (!r.result.objectStoreNames.contains('uploads')) r.result.createObjectStore('uploads', { keyPath: 'id' })
    }
    r.onsuccess = () => res(r.result)
    r.onerror = () => { dbp = null; rej(r.error) }
  }))
}
export const dbTx = async <T,>(store: 'kits' | 'uploads', mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> => {
  const db = await openDb()
  return new Promise((res, rej) => {
    const t = db.transaction(store, mode)
    const rq = fn(t.objectStore(store))
    rq.onsuccess = () => res(rq.result)
    rq.onerror = () => rej(rq.error)
  })
}
const tx = <T,>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>) => dbTx<T>('kits', mode, fn)

const snapshot = (name: string): Kit => {
  const pads: KitPad[] = []
  bank.forEach((s, index) => {
    if (!s) return
    pads.push({ index, name: s.name, pitch: s.pitch, rate: s.rate, gain: s.gain, source: s.source, sampleRate: s.buffer.sampleRate, planes: Array.from({ length: s.buffer.numberOfChannels }, (_, c) => s.buffer.getChannelData(c).slice()) })
  })
  return { name, created: Date.now(), pads, settings: settings.map((x) => ({ ...x, fx: x.fx.map((f) => ({ ...f, p: { ...f.p } })) })) }
}

export async function saveKit(name: string): Promise<number> {
  const k = snapshot(name)
  await tx('readwrite', (s) => s.put(k))
  return k.pads.length
}
export const listKits = async (): Promise<{ name: string; created: number; pads: number }[]> =>
  (await tx<Kit[]>('readonly', (s) => s.getAll() as IDBRequest<Kit[]>)).filter((k) => k.name !== SESSION_KIT).map((k) => ({ name: k.name, created: k.created, pads: k.pads.length })).sort((a, b) => b.created - a.created)

function applyKit(k: Kit) {
  bank.fill(null)
  k.pads.forEach((p) => { bank[p.index] = { name: p.name, pitch: p.pitch, rate: p.rate, gain: p.gain, source: p.source, buffer: planesToBuffer(p.planes, p.sampleRate) } })
  for (let i = 0; i < 16; i++) settings[i] = k.settings?.[i] ? { ...defaultSettings(), ...k.settings[i] } : defaultSettings()
}
export async function loadKit(name: string): Promise<number> {
  const k = await tx<Kit | undefined>('readonly', (s) => s.get(name) as IDBRequest<Kit | undefined>)
  if (!k) throw new Error(`No kit called ${name}`)
  applyKit(k)
  emit()
  return k.pads.length
}
export const deleteKit = (name: string) => tx('readwrite', (s) => s.delete(name))

let restoring = true
let saveTimer = 0
function scheduleAutosave() {
  if (restoring || typeof indexedDB === 'undefined') return
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => { void tx('readwrite', (s) => s.put(snapshot(SESSION_KIT))).catch(() => undefined) }, 700)
}
/** Bring back the last deck. Never creates an AudioContext (AudioBuffers are context independent). */
export async function restoreSession(): Promise<boolean> {
  try {
    if (typeof indexedDB === 'undefined') return false
    const k = await tx<Kit | undefined>('readonly', (s) => s.get(SESSION_KIT) as IDBRequest<Kit | undefined>)
    if (k) { applyKit(k); version++; listeners.forEach((l) => l()) }
    return !!k
  } catch { return false } finally { restoring = false }
}

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
