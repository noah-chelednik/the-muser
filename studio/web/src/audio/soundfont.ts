/**
 * Lightweight SoundFont / SFZ player for the on-screen keyboard.
 * SF2: reads the smpl PCM chunk and shdr sample headers (no preset modulators).
 * SFZ: loads neighboring sample= files through the scanned library.
 * SF3 (compressed) is rejected with a clear error.
 */
import { audio } from './engine'

export type FontKind = 'sf2' | 'sfz'

type Region = {
  name: string
  lo: number
  hi: number
  originalPitch: number
  pitchCorrection: number
  buffer: AudioBuffer
  loopStart: number
  loopEnd: number
}

export type LoadedFont = { name: string; kind: FontKind; regions: Region[] }

let current: LoadedFont | null = null
const voices = new Map<number, Array<{ src: AudioBufferSourceNode; gain: GainNode }>>()

export const hasFont = () => !!current && current.regions.length > 0
export const fontName = () => current?.name ?? ''
export const loadedFont = () => current

export function unloadFont() {
  allNotesOff()
  current = null
}

function libraryUrl(path: string) {
  return `/api/library/file?path=${encodeURIComponent(path)}`
}

export async function loadFromLibrary(path: string) {
  const name = path.split(/[\\/]/).pop() || path
  const lower = name.toLowerCase()
  if (lower.endsWith('.sf3')) throw new Error('SF3 (compressed) soundfonts are not supported yet. Use an .sf2 or .sfz.')
  const res = await fetch(libraryUrl(path))
  if (!res.ok) throw new Error(res.status === 403 ? 'That file is not in the scanned library.' : `Could not load ${name}`)
  const data = await res.arrayBuffer()
  const dir = path.replace(/[\\/][^\\/]+$/, '')
  if (lower.endsWith('.sfz')) current = await parseSfz(new TextDecoder().decode(data), name, dir)
  else current = parseSf2(data, name)
  return current
}

export async function loadFile(file: File) {
  const lower = file.name.toLowerCase()
  if (lower.endsWith('.sf3')) throw new Error('SF3 (compressed) soundfonts are not supported yet. Use an .sf2 or .sfz.')
  if (lower.endsWith('.sfz')) {
    throw new Error('Drop an .sf2, or load an .sfz from the scanned library so its sample folder can be found.')
  }
  current = parseSf2(await file.arrayBuffer(), file.name)
  return current
}

export function noteOn(midi: number, dest: AudioNode, when?: number, velocity = 0.85) {
  if (!current) return false
  const matches = current.regions.filter((r) => midi >= r.lo && midi <= r.hi)
  if (!matches.length) return false
  matches.sort((a, b) => Math.abs(a.originalPitch - midi) - Math.abs(b.originalPitch - midi))
  const region = matches[0]
  const ctx = dest.context as AudioContext
  const t = when ?? ctx.currentTime
  const src = ctx.createBufferSource()
  src.buffer = region.buffer
  src.playbackRate.value = Math.pow(2, (midi - region.originalPitch + region.pitchCorrection / 100) / 12)
  if (region.loopStart >= 0 && region.loopEnd > region.loopStart) {
    src.loop = true
    src.loopStart = region.loopStart
    src.loopEnd = region.loopEnd
  }
  const gain = ctx.createGain()
  gain.gain.setValueAtTime(Math.max(0.04, Math.min(1, velocity)), t)
  src.connect(gain)
  gain.connect(dest)
  src.start(t)
  const list = voices.get(midi) ?? []
  list.push({ src, gain })
  voices.set(midi, list)
  return true
}

export function noteOff(midi: number, when?: number) {
  const list = voices.get(midi)
  if (!list) return
  voices.delete(midi)
  for (const voice of list) {
    const t = when ?? voice.gain.context.currentTime
    try {
      voice.gain.gain.cancelScheduledValues(t)
      voice.gain.gain.setValueAtTime(Math.max(0.001, voice.gain.gain.value), t)
      voice.gain.gain.exponentialRampToValueAtTime(0.001, t + 0.08)
      voice.src.stop(t + 0.1)
    } catch { /* already stopped */ }
  }
}

export function allNotesOff() {
  for (const midi of [...voices.keys()]) noteOff(midi)
}

function ascii(bytes: Uint8Array, off: number, n: number) {
  return String.fromCharCode(...bytes.subarray(off, off + n))
}

function parseSf2(data: ArrayBuffer, name: string): LoadedFont {
  const bytes = new Uint8Array(data)
  const view = new DataView(data)
  if (ascii(bytes, 0, 4) !== 'RIFF' || ascii(bytes, 8, 4) !== 'sfbk') {
    throw new Error('Not a SoundFont 2 (.sf2) file')
  }
  let smpl: DataView | null = null
  let shdr: Uint8Array | null = null
  let pos = 12
  while (pos + 8 <= data.byteLength) {
    const id = ascii(bytes, pos, 4)
    const size = view.getUint32(pos + 4, true)
    const start = pos + 8
    if (id === 'LIST') {
      const listType = ascii(bytes, start, 4)
      let inner = start + 4
      const end = start + size
      while (inner + 8 <= end && inner + 8 <= data.byteLength) {
        const cid = ascii(bytes, inner, 4)
        const csize = view.getUint32(inner + 4, true)
        const cstart = inner + 8
        if (listType === 'sdta' && cid === 'smpl') smpl = new DataView(data, cstart, Math.min(csize, data.byteLength - cstart))
        if (listType === 'pdta' && cid === 'shdr') shdr = bytes.subarray(cstart, Math.min(cstart + csize, bytes.length))
        inner += 8 + csize + (csize % 2)
      }
    }
    pos += 8 + size + (size % 2)
  }
  if (!smpl || !shdr) throw new Error('SoundFont is missing sample data')
  const ctx = audio.ensure()
  const regions: Region[] = []
  const rec = 46
  const count = Math.floor(shdr.length / rec)
  for (let i = 0; i < count; i++) {
    const off = i * rec
    const sname = new TextDecoder('latin1').decode(shdr.subarray(off, off + 20)).replace(/\0.*$/s, '').trim()
    if (!sname || sname === 'EOS') continue
    const dv = new DataView(shdr.buffer, shdr.byteOffset + off, rec)
    const startFrame = dv.getUint32(20, true)
    const endFrame = dv.getUint32(24, true)
    const loopStart = dv.getUint32(28, true)
    const loopEnd = dv.getUint32(32, true)
    const sr = dv.getUint32(36, true) || 44100
    const originalPitch = dv.getUint8(40) || 60
    const pitchCorrection = dv.getInt8(41)
    const sampleType = dv.getUint16(44, true)
    if (sampleType & 0x8000) continue
    const frames = endFrame - startFrame
    if (frames < 16) continue
    const buffer = ctx.createBuffer(1, frames, sr)
    const ch = buffer.getChannelData(0)
    const byteOff = startFrame * 2
    for (let f = 0; f < frames; f++) {
      const o = byteOff + f * 2
      if (o + 1 >= smpl.byteLength) break
      ch[f] = smpl.getInt16(o, true) / 32768
    }
    const looping = loopEnd > loopStart && loopStart >= startFrame
    regions.push({
      name: sname,
      lo: 0,
      hi: 127,
      originalPitch,
      pitchCorrection,
      buffer,
      loopStart: looping ? (loopStart - startFrame) / sr : -1,
      loopEnd: looping ? (loopEnd - startFrame) / sr : -1,
    })
  }
  if (!regions.length) throw new Error('SoundFont has no playable samples')
  return { name, kind: 'sf2', regions }
}

type Opcodes = Record<string, string>

function parseOpcodeLine(line: string, into: Opcodes) {
  const re = /([a-zA-Z0-9_]+)\s*=\s*(\S+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(line))) into[m[1].toLowerCase()] = m[2]
}

function joinLib(base: string, rel: string) {
  const cleaned = rel.replace(/\\/g, '/')
  if (/^[a-zA-Z]:/.test(cleaned) || cleaned.startsWith('/')) return cleaned
  const parts = `${base.replace(/\\/g, '/').replace(/\/$/, '')}/${cleaned}`.split('/')
  const out: string[] = []
  for (const part of parts) {
    if (part === '..') out.pop()
    else if (part !== '.') out.push(part)
  }
  return out.join('/')
}

async function parseSfz(text: string, name: string, basePath: string): Promise<LoadedFont> {
  const global: Opcodes = {}
  let group: Opcodes = {}
  let currentOp: Opcodes | null = null
  let section = 'global'
  const regionsOp: Opcodes[] = []
  const flush = () => {
    if (section === 'region' && currentOp) regionsOp.push({ ...global, ...group, ...currentOp })
  }
  for (const raw of text.replace(/\r/g, '').split('\n')) {
    const line = raw.replace(/\/\/.*$/, '').trim()
    if (!line) continue
    for (const part of line.split(/(<(?:region|group|global|control)>)/i)) {
      const header = part.match(/^<(region|group|global|control)>$/i)
      if (header) {
        flush()
        const tag = header[1].toLowerCase()
        if (tag === 'group') { group = {}; currentOp = group; section = 'group' }
        else if (tag === 'global') { currentOp = global; section = 'global' }
        else if (tag === 'region') { currentOp = {}; section = 'region' }
        else { currentOp = null; section = tag }
        continue
      }
      if (currentOp) parseOpcodeLine(part, currentOp)
    }
  }
  flush()
  const ctx = audio.ensure()
  const regions: Region[] = []
  for (const op of regionsOp) {
    if (!op.sample) continue
    const samplePath = joinLib(basePath, op.sample)
    const res = await fetch(libraryUrl(samplePath))
    if (!res.ok) continue
    const buffer = await ctx.decodeAudioData((await res.arrayBuffer()).slice(0))
    const keycenter = Number(op.pitch_keycenter ?? op.key ?? 60)
    const lokey = Number(op.lokey ?? 0)
    const hikey = Number(op.hikey ?? 127)
    const sr = buffer.sampleRate
    const loopMode = (op.loop_mode || '').toLowerCase()
    const looping = loopMode.includes('loop') && !loopMode.includes('no')
    const loopStart = looping ? Number(op.loop_start ?? 0) / sr : -1
    const loopEnd = looping ? Number(op.loop_end ?? buffer.length) / sr : -1
    regions.push({
      name: op.sample,
      lo: Number.isFinite(lokey) ? lokey : 0,
      hi: Number.isFinite(hikey) ? hikey : 127,
      originalPitch: Number.isFinite(keycenter) ? keycenter : 60,
      pitchCorrection: 0,
      buffer,
      loopStart,
      loopEnd,
    })
  }
  if (!regions.length) {
    throw new Error('None of this SFZ’s samples are in the library. Scan the folder that holds them, then try again.')
  }
  return { name, kind: 'sfz', regions }
}
