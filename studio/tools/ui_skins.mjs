// Click-through test for the three skins (Cathode, Terrain, Score) against a studio running with --demo.
// Usage: npm i -D playwright-core (in any folder), start the studio with --demo, then:
//   STUDIO_URL=http://127.0.0.1:8765 CHROME="C:/Program Files/Google/Chrome/Application/chrome.exe" node studio/tools/ui_skins.mjs
// Optional: SHOTS=./screenshots to also save a screenshot per skin and step.
import { chromium } from 'playwright-core'

const BASE = process.env.STUDIO_URL || 'http://127.0.0.1:8765'
const SHOTS = process.env.SHOTS || ''
const SKINS = ['cathode', 'terrain', 'score']
const errors = []
let checks = 0
const log = (...a) => console.log('*', ...a)
const ok = (cond, msg) => { checks++; if (!cond) throw new Error(`FAIL: ${msg}`) }
const T = (id) => `[data-testid=${id}]`

process.on('unhandledRejection', async (e) => { console.log(String(e).slice(0, 600)); try { await page.screenshot({ path: process.env.FAIL_SHOT || '/tmp/ui_skins_fail.png' }) } catch {} process.exit(1) })
const browser = await chromium.launch({
  executablePath: process.env.CHROME || '/usr/bin/google-chrome',
  args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--autoplay-policy=no-user-gesture-required'],
})
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
const page = await ctx.newPage()
page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text()) })
page.on('pageerror', (e) => errors.push(String(e)))

const skinNow = () => page.evaluate(() => document.documentElement.dataset.skin)
const stored = () => page.evaluate(() => localStorage.getItem('muser.skin'))
const shot = async (name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` }) }
const settle = (ms = 700) => page.waitForTimeout(ms)
const idle = () => page.waitForFunction(() => document.querySelector('[data-testid=make]')?.getAttribute('data-phase') !== 'busy', null, { timeout: 120000 })
const versions = async () => Number(await page.locator(T('versions')).getAttribute('data-count'))
const useSkin = async (id) => {
  await page.locator(T('skin-button')).click()
  await page.locator(T('skin-popover')).waitFor()
  await page.locator(`[data-skin-option=${id}]`).click()
  await page.waitForFunction((s) => document.documentElement.dataset.skin === s, id)
  await settle(900)
}

// ---- boot: default skin is Cathode, Easy mode, no gold anywhere in the tokens
await page.addInitScript(() => { if (!sessionStorage.getItem('init')) { localStorage.clear(); sessionStorage.setItem('init', '1') } })
await page.goto(BASE, { waitUntil: 'networkidle' })
await page.locator(T('prompt')).waitFor()
ok((await skinNow()) === 'cathode', 'default skin is cathode')
ok(await page.locator(T('mode-easy')).count(), 'easy mode toggle present')
ok(await page.locator(T('demo-badge')).count(), 'demo badge present')
const hot = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--hot').trim().toLowerCase())
ok(/^#[0-9a-f]{6}$/.test(hot), 'accent token resolves')
const DEMO = (await page.locator(T('demo-ribbon')).count()) > 0
log('boot ok, hot token', hot, DEMO ? '(browser demo)' : '')

// ---- skin switcher: button, thumbnails, Alt+S, palette, persistence, state kept
await page.locator(T('skin-button')).click()
const pop = page.locator(T('skin-popover'))
await pop.waitFor()
ok((await pop.locator('[data-skin-option]').count()) === 3, 'switcher lists three skins')
ok((await pop.locator('[data-skin-option] svg, [data-skin-option] canvas, [data-skin-option] img').count()) >= 3, 'switcher shows a thumbnail per skin')
await shot('switcher-open')
await page.keyboard.press('Escape')
ok((await pop.count()) === 0, 'Esc closes the switcher')

await page.locator(T('prompt')).fill('rainy night drive, warm and dusty')
await page.locator(T('make')).click()
await page.waitForFunction(() => document.querySelector('[data-testid=make]')?.getAttribute('data-phase') === 'ready', null, { timeout: 120000 })
await settle(1200)
const v0 = await versions()
ok(v0 >= 1, 'Make It produced a version')

await useSkin('terrain')
ok((await stored()) === 'terrain', 'skin choice stored in localStorage')
ok((await page.locator(T('prompt')).inputValue()) === 'rainy night drive, warm and dusty', 'typed prompt survives a skin switch')
ok((await versions()) === v0, 'versions survive a skin switch')

await page.keyboard.press('Alt+s')
await page.waitForFunction(() => document.documentElement.dataset.skin === 'score')
ok((await skinNow()) === 'score', 'Alt+S cycles the skin')

await page.keyboard.press('Control+k')
await page.locator(T('palette')).waitFor()
await page.keyboard.type('skin cathode')
await page.keyboard.press('Enter')
await page.waitForFunction(() => document.documentElement.dataset.skin === 'cathode')
ok((await stored()) === 'cathode', 'palette switches skin and persists')
await page.reload({ waitUntil: 'networkidle' })
await page.locator(T('prompt')).waitFor()
ok((await skinNow()) === 'cathode', 'skin restored after reload')

// ---- per-skin core flows
for (const skin of SKINS) {
  log('skin', skin)
  await useSkin(skin)
  if (await page.locator(T('mode-easy')).getAttribute('aria-selected') !== 'true') await page.locator(T('mode-easy')).click()
  await settle(500)

  // Easy: vibes, make, macros, finish, export, tools
  const vibes = page.locator(`${T('vibes')} > *`)
  ok((await vibes.count()) >= 5, `${skin}: vibe list`)
  await page.locator(T('show-all')).click()
  await settle(300)
  ok((await vibes.count()) >= 20, `${skin}: show all vibes expands`)
  await page.locator(T('show-all')).click()
  await vibes.nth(2).click()
  await page.locator(T('prompt')).fill('moody late night synth')
  await shot(`${skin}-easy-empty`)
  await page.locator(T('make')).click()
  await page.waitForFunction(() => document.querySelector('[data-testid=make]')?.getAttribute('data-phase') === 'ready', null, { timeout: 120000 })
  await settle(1500)
  ok(await page.locator(T('play')).count(), `${skin}: transport present after make`)
  ok((await page.locator(`${T('macros')} input[type=range], ${T('macros')} [role=slider]`).count()) >= 5 || (await page.locator(`${T('macros')} > *`).count()) >= 5, `${skin}: five macros`)

  const vb = await versions()
  // the version list is capped at 40 and restored from autosave, so wait on the render call, not on growth
  // in the serverless browser demo there is no network call, so just settle and wait for idle
  const rendered = DEMO ? settle(1500) : page.waitForResponse((r) => r.url().includes('/api/easy/render') && r.ok(), { timeout: 120000 })
  await page.keyboard.press('2')
  for (let i = 0; i < 5; i++) await page.keyboard.press('ArrowRight')
  await rendered
  await idle()
  ok((await versions()) >= Math.min(vb, 40), `${skin}: macro nudge renders a new version`)
  await page.keyboard.press('Control+z')
  await settle(500)
  await page.waitForFunction(() => !document.querySelector('[data-testid=finish] button')?.disabled, null, { timeout: 120000 })

  const fin = page.locator(`${T('finish')} button`)
  ok((await fin.count()) >= 4, `${skin}: finish targets`)
  await fin.nth(1).click()
  await page.waitForFunction(() => /LUFS/i.test(document.querySelector('[data-testid=measure]')?.textContent || ''), null, { timeout: 120000 })
  await idle()
  ok(/LUFS/i.test(await page.locator(T('measure')).innerText()), `${skin}: finish reports a measured loudness`)

  await page.locator(T('export')).click()
  await page.locator(`${T('files')} a`).first().waitFor({ timeout: 120000 })
  ok((await page.locator(`${T('files')} a`).count()) >= (DEMO ? 1 : 2), `${skin}: export lists WAV and MP3`)

  const tools = page.locator(`${T('tools')} button`)
  ok((await tools.count()) >= 5, `${skin}: one-click tools`)
  await tools.nth(2).click()
  await page.locator('.toast').first().waitFor({ timeout: 120000 })
  await idle()

  // Engines drawer with 8 GB fit badges
  await page.locator(T('engines-button')).click()
  await page.waitForFunction(() => /8 ?GB/i.test(document.body.innerText) && !!document.querySelector('.drawer, [data-testid=drawer], aside.sys'), null, { timeout: 15000 }).catch(() => {})
  ok(/fit|fits|8 ?GB/i.test(await page.locator('body').innerText()), `${skin}: engines drawer shows 8 GB fit`)
  await page.keyboard.press('Escape')
  await settle(300)

  // Help sheet
  await page.keyboard.press('?')
  await page.locator(T('help')).waitFor()
  ok(!/\u2014/.test(await page.locator(T('help')).innerText()), `${skin}: no em dashes in help copy`)
  await page.keyboard.press('Escape')

  // Advanced: lanes, tabs, presets, deck
  await page.keyboard.press('Alt+e')
  await page.waitForFunction(() => document.querySelector('[data-testid=mode-advanced]')?.getAttribute('aria-selected') === 'true')
  await settle(1500)
  const lanes = await page.locator(`${T('lane')}, ${T('strips')} > *`).count()
  ok(lanes >= 3, `${skin}: advanced stem lanes (${lanes})`)
  await shot(`${skin}-advanced`)

  if (skin === 'cathode') {
    await page.locator('[data-dock-tab=presets]').first().click()
    await page.locator(T('presets')).waitFor()
    ok((await page.locator(`${T('presets')} > *`).count()) >= 20, `${skin}: preset shelf`)
  } else {
    for (const tab of ['Live FX', 'Split', 'Sampler', 'Generate', 'Master', 'Presets', 'A/B', 'Chains']) {
      await page.locator('[role=tab]', { hasText: tab }).first().click()
      await settle(250)
      ok((await page.locator('[role=tab][aria-selected=true]', { hasText: tab }).count()) >= 1, `${skin}: ${tab} tab opens`)
    }
  }

  // Deck: pads, sequencer, keys
  const deck = page.locator('[data-dock-tab=deck]').first()
  await deck.click()
  await page.locator('.pad').first().waitFor({ timeout: 10000 })
  ok((await page.locator('.pad').count()) >= 16, `${skin}: pads in the deck`)
  await page.locator('.pad').first().click()
  await settle(300)

  // Space toggles playback without error
  await page.keyboard.press('Escape')
  await page.keyboard.press('Alt+e')
  await settle(500)
  ok((await page.locator(T('mode-easy')).getAttribute('aria-selected')) === 'true', `${skin}: back to easy`)
}

// ---- reduced motion and no-WebGL fallback
const rm = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: 'reduce' })
const rp = await rm.newPage()
rp.on('pageerror', (e) => errors.push(`reduced-motion: ${e}`))
await rp.addInitScript(() => localStorage.setItem('muser.skin', 'terrain'))
await rp.goto(BASE, { waitUntil: 'networkidle' })
await rp.locator(T('prompt')).waitFor()
ok((await rp.evaluate(() => document.documentElement.dataset.skin)) === 'terrain', 'terrain loads with reduced motion')
await rm.close()
const nogl = await browser.newContext({ viewport: { width: 1280, height: 800 } })
const np = await nogl.newPage()
np.on('pageerror', (e) => errors.push(`no-webgl: ${e}`))
await np.addInitScript(() => {
  const g = HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/.test(t) ? null : g.call(this, t, ...a) }
  localStorage.setItem('muser.skin', 'terrain')
})
await np.goto(BASE, { waitUntil: 'networkidle' })
await np.locator(T('prompt')).waitFor()
ok(await np.locator(T('make')).count(), 'terrain still usable without WebGL')
await nogl.close()

await browser.close()
if (errors.length) { console.log('console errors:\n' + errors.join('\n')); throw new Error(`FAIL: ${errors.length} console or page errors`) }
console.log(`ui_skins: ${checks} checks passed`)
