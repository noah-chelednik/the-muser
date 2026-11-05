// Copies the onnxruntime-web runtime (MIT) into public/ort so the browser separator loads it same-origin.
// The wasm is ~27 MB, so it is not committed (public/ort is git-ignored); this runs before dev and build.
import { cpSync, mkdirSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = join(root, 'node_modules', 'onnxruntime-web', 'dist')
const dst = join(root, 'public', 'ort')
const files = ['ort.webgpu.min.mjs', 'ort-wasm-simd-threaded.asyncify.mjs', 'ort-wasm-simd-threaded.asyncify.wasm']
if (!existsSync(src)) { console.warn('copy-ort: onnxruntime-web is not installed, skipping'); process.exit(0) }
mkdirSync(dst, { recursive: true })
for (const f of files) cpSync(join(src, f), join(dst, f))
const lic = join(root, 'node_modules', 'onnxruntime-web', 'LICENSE'); if (existsSync(lic)) cpSync(lic, join(dst, 'LICENSE'))
console.log('copy-ort: copied', files.length, 'files to public/ort')
