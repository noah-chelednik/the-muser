// Minimal store-only ZIP writer so stems can be downloaded as one file in the browser demo.
const table = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0 }
  return t
})()
const crc32 = (b: Uint8Array) => { let c = 0xffffffff; for (let i = 0; i < b.length; i++) c = table[(c ^ b[i]) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0 }

export async function zipFiles(files: { name: string; blob: Blob }[]): Promise<Blob> {
  const parts: BlobPart[] = [], central: number[][] = []
  let offset = 0
  const enc = new TextEncoder()
  for (const f of files) {
    const data = new Uint8Array(await f.blob.arrayBuffer()), name = enc.encode(f.name), crc = crc32(data)
    const h = new DataView(new ArrayBuffer(30))
    h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint32(14, crc, true)
    h.setUint32(18, data.length, true); h.setUint32(22, data.length, true); h.setUint16(26, name.length, true)
    parts.push(h.buffer, name, data)
    central.push([crc, data.length, offset, name.length])
    offset += 30 + name.length + data.length
  }
  const cdStart = offset
  files.forEach((f, i) => {
    const [crc, size, off, nl] = central[i]
    const h = new DataView(new ArrayBuffer(46))
    h.setUint32(0, 0x02014b50, true); h.setUint16(4, 20, true); h.setUint16(6, 20, true); h.setUint32(16, crc, true)
    h.setUint32(20, size, true); h.setUint32(24, size, true); h.setUint16(28, nl, true); h.setUint32(42, off, true)
    parts.push(h.buffer, enc.encode(f.name))
    offset += 46 + nl
  })
  const e = new DataView(new ArrayBuffer(22))
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, files.length, true); e.setUint16(10, files.length, true)
  e.setUint32(12, offset - cdStart, true); e.setUint32(16, cdStart, true)
  parts.push(e.buffer)
  return new Blob(parts, { type: 'application/zip' })
}
