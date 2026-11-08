/**
 * Browser sound library: the CC0 drum one-shots shipped with the web build (public/library, from the
 * sound-library catalog) plus the user's own validated uploads kept in IndexedDB. No server, no
 * database and no API key needed. Assigning a sound to a pad decodes it once and caches the buffer.
 */
import { audio } from './engine'
import { dbTx, padBank, type PadSample } from './samples'
import { validateAudioFile, type ValidAudio } from './upload'
import { planesToBuffer } from './wav'

export type LibSound = {
  id: string
  title: string
  type: string
  category: string
  genres: string[]
  tags: string[]
  license: string
  author: string
  attribution_text: string
  source_url: string
  file: string
  duration_ms: number
  bytes: number
}
export const LIB_TYPES = ['kick', 'snare', 'clap', 'hat', 'open-hat', 'perc', '808', 'cymbal', 'tom'] as const
export const LIB_BASE = `${import.meta.env.BASE_URL ?? '/'}library/`.replace(/\/\/+/g, '/')
export const soundUrl = (s: LibSound) => LIB_BASE + s.file

let catalog: Promise<LibSound[]> | null = null
export function loadCatalog(): Promise<LibSound[]> {
  return (catalog ??= fetch(`${LIB_BASE}catalog.json`)
    .then((r) => { if (!r.ok) throw new Error('catalog ' + r.status); return r.json() })
    .then((j: { sounds: LibSound[] }) => j.sounds)
    .catch((e) => { catalog = null; throw e }))
}

export function filterSounds(list: LibSound[], f: { type?: string; genre?: string; q?: string }): LibSound[] {
  const q = (f.q ?? '').trim().toLowerCase()
  return list.filter((s) =>
    (!f.type || s.type === f.type) &&
    (!f.genre || s.genres.includes(f.genre)) &&
    (!q || s.title.toLowerCase().includes(q) || s.category.includes(q) || s.tags.some((t) => t.includes(q))))
}

const buffers = new Map<string, Promise<AudioBuffer>>()
export const librarySoundBuffer = (s: LibSound) => {
  if (!buffers.has(s.id)) buffers.set(s.id, audio.decode(soundUrl(s)).catch((e) => { buffers.delete(s.id); throw e }))
  return buffers.get(s.id)!
}

/** Put a library sound on a pad (keeps the pad's level, pitch and FX). */
export async function assignLibrarySound(pad: number, s: LibSound) {
  const buffer = await librarySoundBuffer(s)
  const prev = padBank.get(pad)
  const sample: PadSample = { name: s.title, buffer, pitch: 0, rate: 1, gain: prev?.source?.kind === 'library' ? prev.gain : 1, source: { kind: 'library', id: s.id, license: s.license, author: s.author } }
  padBank.set(pad, sample)
  return sample
}

// ---------------------------------------------------------------- user uploads ("My sounds")

export type UserSound = { id: string; name: string; created: number; sampleRate: number; duration: number; planes: Float32Array[] }
const MAX_USER_SOUNDS = 60
const MAX_USER_SECONDS = 30 // pad and key one-shots; longer audio belongs in the Sampler

export async function listUserSounds(): Promise<UserSound[]> {
  try { return (await dbTx<UserSound[]>('uploads', 'readonly', (s) => s.getAll() as IDBRequest<UserSound[]>)).sort((a, b) => b.created - a.created) } catch { return [] }
}
export const deleteUserSound = (id: string) => dbTx('uploads', 'readwrite', (s) => s.delete(id))
export const userSoundBuffer = (u: UserSound) => planesToBuffer(u.planes, u.sampleRate)

/** Validate, decode and keep an upload for pads and keys. Throws UploadError with a readable message. */
export async function importUserSound(file: File): Promise<{ sound: UserSound; valid: ValidAudio }> {
  const valid = await validateAudioFile(file)
  let b = valid.buffer
  if (b.duration > MAX_USER_SECONDS) {
    // keep the first 30 s; pads are for one-shots and loops
    const n = Math.floor(MAX_USER_SECONDS * b.sampleRate)
    const out = new AudioBuffer({ numberOfChannels: b.numberOfChannels, length: n, sampleRate: b.sampleRate })
    for (let c = 0; c < b.numberOfChannels; c++) out.copyToChannel(b.getChannelData(c).subarray(0, n), c)
    b = out
  }
  const sound: UserSound = {
    id: `u-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    name: valid.name, created: Date.now(), sampleRate: b.sampleRate, duration: b.duration,
    planes: Array.from({ length: Math.min(2, b.numberOfChannels) }, (_, c) => b.getChannelData(c).slice()),
  }
  try {
    await dbTx('uploads', 'readwrite', (s) => s.put(sound))
    const all = await listUserSounds()
    for (const old of all.slice(MAX_USER_SOUNDS)) await deleteUserSound(old.id)
  } catch { /* private mode: keep it in memory only */ }
  return { sound, valid }
}

export function assignUserSound(pad: number, u: UserSound) {
  padBank.set(pad, { name: u.name, buffer: userSoundBuffer(u), pitch: 0, rate: 1, gain: 1, source: { kind: 'upload', id: u.id } })
}
