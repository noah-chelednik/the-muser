// Usage: node scripts/shoot.mjs [base-url] [only]   e.g. node scripts/shoot.mjs http://127.0.0.1:5199 a
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const base = process.argv[2] || 'http://127.0.0.1:5173'
const only = process.argv[3]; const onlyShot = process.argv[4]
const out = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../screenshots/concepts')
fs.mkdirSync(out, { recursive: true })
const chrome = ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find((p) => fs.existsSync(p))

const SHOTS = [
  ['easy', { w: 1440, h: 900, hash: 'easy', s: 'made,fin', settle: 3200 }],
  ['advanced', { w: 1440, h: 900, hash: 'advanced', s: 'made,split', settle: 3600 }],
  ['engines', { w: 1440, h: 900, hash: 'advanced', s: 'made,split,eng', settle: 3000 }],
  ['mobile-advanced', { w: 390, h: 844, hash: 'advanced', s: 'made,split', settle: 3200, mobile: true }],
  ['mobile', { w: 390, h: 844, hash: 'easy', s: 'made,fin', settle: 3200, mobile: true }],
]
const browser = await puppeteer.launch({
  executablePath: chrome, headless: 'new',
  args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required', '--enable-webgl'],
})
for (const c of ['a', 'b', 'c']) {
  if (only && only !== c) continue
  for (const [name, o] of SHOTS) {
    if (onlyShot && onlyShot !== name) continue
    const page = await browser.newPage()
    await page.setViewport({ width: o.w, height: o.h, deviceScaleFactor: o.mobile ? 2 : 1, isMobile: !!o.mobile, hasTouch: !!o.mobile })
    page.on('pageerror', (e) => console.log(`[${c}-${name}] pageerror`, e.message))
    page.on('console', (m) => { if (m.type() === 'error') console.log(`[${c}-${name}] console`, m.text()) })
    await page.goto(`${base}/?s=${o.s}#/${c}/${o.hash}`, { waitUntil: 'networkidle0' })
    await page.evaluate(() => document.fonts.ready)
    await new Promise((r) => setTimeout(r, o.settle))
    const file = path.join(out, `${c.toUpperCase()}-${name}.png`)
    await page.screenshot({ path: file })
    console.log('wrote', file)
    await page.close()
  }
}
await browser.close()
