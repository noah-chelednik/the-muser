/**
 * Client-side guard for user audio. Every upload path (Sampler, pads, Split, Easy, Library) goes through
 * validateAudioFile before anything else touches the bytes.
 *
 *  1. extension allowlist: wav, mp3, flac, ogg, aiff/aif, m4a, webm
 *  2. MIME allowlist (an empty or generic MIME is allowed only because some phones send none;
 *     the magic bytes still have to match)
 *  3. size cap (40 MB) and a minimum size
 *  4. magic bytes sniffed from the first 64 bytes and matched to the extension family
 *  5. decoded ONLY with decodeAudioData (an OfflineAudioContext); anything that fails to decode,
 *     is empty, too long or has too many channels is rejected
 *
 * The file is never executed, inserted as HTML, or written to a web-reachable path. The decoded
 * AudioBuffer lives in memory, and in IndexedDB as raw float planes when a kit is saved.
 */
export const MAX_UPLOAD_BYTES = 40 * 1024 * 1024
export const MAX_UPLOAD_SECONDS = 12 * 60
export const ACCEPT = '.wav,.mp3,.flac,.ogg,.oga,.aif,.aiff,.m4a,.webm,audio/wav,audio/x-wav,audio/mpeg,audio/flac,audio/ogg,audio/aiff,audio/x-aiff,audio/mp4,audio/x-m4a,audio/webm'

export type AudioFamily = 'wav' | 'mp3' | 'flac' | 'ogg' | 'aiff' | 'm4a' | 'webm'

const EXT: Record<string, AudioFamily> = {
  wav: 'wav', wave: 'wav', mp3: 'mp3', flac: 'flac', ogg: 'ogg', oga: 'ogg', opus: 'ogg',
  aif: 'aiff', aiff: 'aiff', aifc: 'aiff', m4a: 'm4a', mp4a: 'm4a', webm: 'webm', weba: 'webm',
}
const MIME_OK = new Set([
  'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/vnd.wave', 'audio/mpeg', 'audio/mp3', 'audio/x-mp3', 'audio/mpeg3',
  'audio/flac', 'audio/x-flac', 'audio/ogg', 'audio/opus', 'application/ogg', 'audio/aiff', 'audio/x-aiff',
  'audio/mp4', 'audio/x-m4a', 'audio/m4a', 'audio/aac', 'audio/webm', 'video/webm',
  // phones and some desktop pickers send no MIME or a generic one; the magic bytes decide then
  '', 'application/octet-stream',
])

export class UploadError extends Error {
  code: 'type' | 'size' | 'bytes' | 'decode' | 'length'
  constructor(code: UploadError['code'], msg: string) { super(msg); this.code = code; this.name = 'UploadError' }
}

/** Display name: no path, no extension, no control or markup characters, at most 60 chars. */
export function sanitizeName(raw: string): string {
  const base = (raw.split(/[\\/]/).pop() ?? '').replace(/\.[A-Za-z0-9]{1,5}$/, '')
  const clean = base
    .normalize('NFKC')
    .replace(/[\u0000-\u001f\u007f<>"'`&;{}$|\\]/g, '')
    .replace(/[^\p{L}\p{N} ._()#+-]/gu, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^[.\s-]+|[.\s]+$/g, '')
    .trim()
    .slice(0, 60)
  return clean || 'Upload'
}

export function extFamily(name: string): AudioFamily | null {
  const m = /\.([A-Za-z0-9]{1,5})$/.exec(name.trim())
  return m ? EXT[m[1].toLowerCase()] ?? null : null
}

const ascii = (b: Uint8Array, o: number, n: number) => String.fromCharCode(...b.subarray(o, o + n))

/** Identify the container from its first bytes. Returns null for anything that is not audio we accept. */
export function sniffAudio(b: Uint8Array): AudioFamily | null {
  if (b.length < 12) return null
  if (ascii(b, 0, 4) === 'RIFF' && ascii(b, 8, 4) === 'WAVE') return 'wav'
  if (ascii(b, 0, 4) === 'RF64' && ascii(b, 8, 4) === 'WAVE') return 'wav'
  if (ascii(b, 0, 4) === 'FORM' && /^AIF[FC]$/.test(ascii(b, 8, 4))) return 'aiff'
  if (ascii(b, 0, 4) === 'fLaC') return 'flac'
  if (ascii(b, 0, 4) === 'OggS') return 'ogg'
  if (b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3) return 'webm'
  if (ascii(b, 4, 4) === 'ftyp') {
    const brand = ascii(b, 8, 4)
    if (/^(M4A |M4B |mp42|mp41|isom|iso2|dash|3gp\d|MSNV|f4a )$/.test(brand)) return 'm4a'
    return null
  }
  if (ascii(b, 0, 3) === 'ID3') {
    // ID3v2 header; the real stream follows the tag (mp3, or rarely flac)
    const size = ((b[6] & 0x7f) << 21) | ((b[7] & 0x7f) << 14) | ((b[8] & 0x7f) << 7) | (b[9] & 0x7f)
    const o = 10 + size
    if (b.length >= o + 4 && ascii(b, o, 4) === 'fLaC') return 'flac'
    return 'mp3'
  }
  // MPEG audio frame sync: 11 set bits, a valid layer and bitrate index
  if (b[0] === 0xff && (b[1] & 0xe0) === 0xe0 && (b[1] & 0x06) !== 0 && (b[2] & 0xf0) !== 0xf0) return 'mp3'
  // ADTS AAC (some phones label it .m4a)
  if (b[0] === 0xff && (b[1] & 0xf6) === 0xf0) return 'm4a'
  return null
}

const compatible = (ext: AudioFamily, sniff: AudioFamily) => ext === sniff

/** Cheap checks that need no bytes. Throws UploadError. */
export function checkMeta(name: string, type: string, size: number): AudioFamily {
  const fam = extFamily(name)
  if (!fam) throw new UploadError('type', 'Only WAV, MP3, FLAC, OGG, AIFF, M4A or WebM audio files can be uploaded.')
  if (!MIME_OK.has((type || '').toLowerCase())) throw new UploadError('type', `This file says it is ${type}, not audio.`)
  if (size > MAX_UPLOAD_BYTES) throw new UploadError('size', `That file is ${(size / 1048576).toFixed(1)} MB. The limit is ${MAX_UPLOAD_BYTES / 1048576} MB.`)
  if (size < 44) throw new UploadError('bytes', 'That file is empty or too small to be audio.')
  return fam
}

export type ValidAudio = { name: string; family: AudioFamily; bytes: ArrayBuffer; buffer: AudioBuffer; size: number }

let decoder: OfflineAudioContext | null = null
const getDecoder = () => (decoder ??= new OfflineAudioContext(2, 1, 44100))

/** Full check plus decode. The returned bytes are a copy that is safe to hand to a server upload. */
export async function validateAudioFile(file: File | Blob & { name?: string }, opts: { maxSeconds?: number } = {}): Promise<ValidAudio> {
  const name = (file as File).name ?? 'upload.wav'
  const fam = checkMeta(name, file.type, file.size)
  const bytes = await file.arrayBuffer()
  const sniff = sniffAudio(new Uint8Array(bytes, 0, Math.min(bytes.byteLength, 4096)))
  if (!sniff) throw new UploadError('bytes', 'The file contents are not a recognised audio format.')
  if (!compatible(fam, sniff)) throw new UploadError('bytes', `The file is named .${name.split('.').pop()} but its contents are ${sniff.toUpperCase()}.`)
  let buffer: AudioBuffer
  try {
    buffer = await getDecoder().decodeAudioData(bytes.slice(0))
  } catch {
    throw new UploadError('decode', `This browser could not decode ${sanitizeName(name)}. Try WAV or MP3; some phones cannot read OGG or WebM.`)
  }
  const maxS = opts.maxSeconds ?? MAX_UPLOAD_SECONDS
  if (!buffer || buffer.length < 2 || !Number.isFinite(buffer.duration)) throw new UploadError('decode', 'The file decoded to no audio.')
  if (buffer.duration > maxS) throw new UploadError('length', `That is ${Math.round(buffer.duration / 60)} minutes long. The limit is ${Math.round(maxS / 60)} minutes.`)
  if (buffer.numberOfChannels > 8) throw new UploadError('decode', 'Too many channels.')
  return { name: sanitizeName(name), family: fam, bytes, buffer, size: file.size }
}

/** A File rebuilt from validated bytes with a sanitized name, for code paths that still want a File. */
export const toSafeFile = (v: ValidAudio) => {
  const ext = v.family === 'aiff' ? 'aiff' : v.family
  return new File([v.bytes], `${v.name.replace(/[^\w.-]+/g, '_').slice(0, 60) || 'upload'}.${ext}`, { type: MIME_BY_FAMILY[v.family] })
}
const MIME_BY_FAMILY: Record<AudioFamily, string> = {
  wav: 'audio/wav', mp3: 'audio/mpeg', flac: 'audio/flac', ogg: 'audio/ogg', aiff: 'audio/aiff', m4a: 'audio/mp4', webm: 'audio/webm',
}
