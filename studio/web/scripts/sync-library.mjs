// Copies the CC0 drum library (studio/library on the sound-library branch) into public/library for the web build.
// Usage: node scripts/sync-library.mjs [path/to/studio/library]
// Writes a slim catalog.json (only the fields the browser needs) plus the FLAC files and ATTRIBUTIONS.md.
import { cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = process.argv[2] || join(root, '..', 'library')
const dst = join(root, 'public', 'library')
if (!existsSync(join(src, 'sounds.json'))) { console.error('sync-library: no sounds.json in', src); process.exit(1) }
const all = JSON.parse(readFileSync(join(src, 'sounds.json'), 'utf8'))
const ALLOWED = new Set(['CC0-1.0', 'CC-BY-4.0', 'CC-BY-3.0'])
const keep = ['id', 'title', 'type', 'category', 'genres', 'tags', 'license', 'author', 'attribution_text', 'source_url', 'file', 'duration_ms', 'bytes']
const sounds = all.sounds.filter((s) => ALLOWED.has(s.license)).map((s) => Object.fromEntries(keep.map((k) => [k, s[k]])))
mkdirSync(dst, { recursive: true })
cpSync(join(src, 'audio'), join(dst, 'audio'), { recursive: true })
cpSync(join(src, 'ATTRIBUTIONS.md'), join(dst, 'ATTRIBUTIONS.md'))
writeFileSync(join(dst, 'catalog.json'), JSON.stringify({ version: all.version, generated: new Date().toISOString().slice(0, 10), count: sounds.length, sounds }))
console.log('sync-library:', sounds.length, 'sounds ->', dst)
