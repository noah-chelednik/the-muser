/** WAV encoding and small buffer helpers shared by the splitter, the FX bounce and the sampler. */

export function encodeWav(channels: Float32Array[], sampleRate: number, bits: 16 | 24 | 32 = 16): Blob {
  const nch = channels.length
  const frames = channels[0]?.length ?? 0
  const bytes = bits / 8
  const dataLen = frames * nch * bytes
  const buf = new ArrayBuffer(44 + dataLen)
  const v = new DataView(buf)
  const w = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)))
  w(0, 'RIFF'); v.setUint32(4, 36 + dataLen, true); w(8, 'WAVE'); w(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, bits === 32 ? 3 : 1, true); v.setUint16(22, nch, true)
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * nch * bytes, true)
  v.setUint16(32, nch * bytes, true); v.setUint16(34, bits, true)
  w(36, 'data'); v.setUint32(40, dataLen, true)
  let o = 44
  for (let i = 0; i < frames; i++) {
    for (let c = 0; c < nch; c++) {
      const x = Math.max(-1, Math.min(1, channels[c][i]))
      if (bits === 16) { v.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7fff, true); o += 2 }
      else if (bits === 24) {
        const n = Math.round(x < 0 ? x * 0x800000 : x * 0x7fffff)
        v.setUint8(o, n & 255); v.setUint8(o + 1, (n >> 8) & 255); v.setUint8(o + 2, (n >> 16) & 255); o += 3
      } else { v.setFloat32(o, x, true); o += 4 }
    }
  }
  return new Blob([buf], { type: 'audio/wav' })
}

export const bufferToWav = (b: AudioBuffer, bits: 16 | 24 | 32 = 16) =>
  encodeWav(Array.from({ length: b.numberOfChannels }, (_, i) => b.getChannelData(i)), b.sampleRate, bits)

export function planesToBuffer(planes: Float32Array[], sampleRate: number): AudioBuffer {
  const b = new AudioBuffer({ numberOfChannels: planes.length, length: planes[0].length, sampleRate })
  planes.forEach((p, i) => b.copyToChannel(p as Float32Array<ArrayBuffer>, i))
  return b
}

export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 30000)
}

export const safeName = (s: string) => s.replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'audio'
