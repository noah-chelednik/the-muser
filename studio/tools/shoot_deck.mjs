// Quick visual: open Advanced + Deck dock on a phone in each skin, screenshot, report overflow.
import { pathToFileURL } from 'node:url'
const PW = process.env.PW || '/tmp/pw/node_modules/playwright-core/index.js'
const { chromium, devices } = (await import(pathToFileURL(PW).href)).default
const BASE = process.env.BASE || 'http://127.0.0.1:5198'
const OUT = process.env.OUT || '/tmp/shots'
const DEV = process.env.DEV || 'iPhone 14'
const DOCK = process.env.DOCK || 'deck'
import fs from 'node:fs'; fs.mkdirSync(OUT, { recursive: true })
const b = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
for (const skin of (process.env.SKINS || 'cathode,terrain,score').split(',')) {
  const ctx = await b.newContext({ ...devices[DEV] })
  await ctx.addInitScript((s) => localStorage.setItem('muser.skin', s), skin)
  const p = await ctx.newPage()
  p.on('pageerror', (e) => console.log('pageerror', String(e).slice(0, 200)))
  await p.goto(`${BASE}/?demo=1`, { waitUntil: 'networkidle' })
  await p.locator('[data-testid=prompt]').first().waitFor({ timeout: 60000 })
  if (process.env.GATE) { const g = p.locator('[data-testid=sound-gate]'); if (await g.count()) { await p.screenshot({ path: `${OUT}/${skin}-gate.png` }); await g.tap() } }
  await p.locator('[data-testid=mode-advanced]:visible').first().tap(); await p.waitForTimeout(600)
  const t = p.locator(`[data-dock-tab=${DOCK}]:visible`).first(); await t.scrollIntoViewIfNeeded(); await t.tap(); await p.waitForTimeout(800)
  const deck = p.locator('.deck, [data-testid=sample-library]').first()
  if (await deck.count()) await deck.scrollIntoViewIfNeeded()
  await p.screenshot({ path: `${OUT}/${skin}-${DOCK}.png` })
  if (process.env.FULL) await p.screenshot({ path: `${OUT}/${skin}-${DOCK}-full.png`, fullPage: true })
  const o = await p.evaluate(() => {
    const iw = innerWidth; const bad = []
    document.querySelectorAll('.deck *, .cc *, .ca *, .cb *').forEach((el) => { const r = el.getBoundingClientRect(); if (r.width && (r.right > iw + 1 || r.left < -1) && getComputedStyle(el).position !== 'fixed') bad.push((el.className || el.tagName).toString().slice(0, 40) + ':' + Math.round(r.right)) })
    return { sw: document.documentElement.scrollWidth, iw, bad: bad.slice(0, 12) }
  })
  console.log(skin, JSON.stringify(o))
  await ctx.close()
}
await b.close()
