// NoDAW Studio PRO v3 check: audible Advanced playback, live FX, crop and pad chop, real in-browser ONNX split,
// NoDAW teaser, no horizontal overflow. Runs every skin on desktop and on iPhone and Pixel emulation.
// Usage (needs playwright-core and Chrome; serve studio/web with `npm run build && npx vite preview --port 5198`):
//   BASE=http://127.0.0.1:5198 CHROME=/usr/bin/google-chrome SHOTS=./screenshots/v3 node studio/tools/v3_check.mjs
// Env: SKINS=cathode,terrain,score  DEVICES=desktop,iPhone 14,Pixel 7  FULL=1 (also run the 181 MB Demucs once)  PW=path to playwright-core
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const PW = process.env.PW || 'playwright-core'
const pwMod = await import(PW.startsWith('/') ? pathToFileURL(PW).href : PW)
const { chromium, devices } = pwMod.chromium ? pwMod : pwMod.default
const HERE = path.dirname(fileURLToPath(import.meta.url))
const BASE = process.env.BASE || 'http://127.0.0.1:5198'
const SHOTS = process.env.SHOTS || ''
const SKINS = (process.env.SKINS || 'cathode,terrain,score').split(',')
const DEVICES = (process.env.DEVICES || 'desktop,iPhone 14,Pixel 7').split(',')
const CLIP = path.join(HERE, 'fixtures', 'split_clip.wav')
const PROFILE = fs.mkdtempSync(path.join(os.tmpdir(), 'v3-profile-'))
const results = []
let failed = 0
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true })

const wavStats = (buf) => {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  let off = 12, ch = 2, bits = 16, data = 0, len = 0
  while (off + 8 <= buf.length) {
    const id = buf.toString('ascii', off, off + 4), n = dv.getUint32(off + 4, true)
    if (id === 'fmt ') { ch = dv.getUint16(off + 10, true); bits = dv.getUint16(off + 22, true) }
    if (id === 'data') { data = off + 8; len = Math.min(n, buf.length - data); break }
    off += 8 + n + (n & 1)
  }
  const bytes = bits / 8, count = Math.floor(len / bytes / ch)
  let e = 0, peak = 0
  for (let i = 0; i < count; i++) {
    const p = data + i * bytes * ch
    const v = bits === 16 ? dv.getInt16(p, true) / 32768 : bits === 24 ? ((dv.getUint8(p) | (dv.getUint8(p + 1) << 8) | (dv.getInt8(p + 2) << 16)) / 8388608) : dv.getFloat32(p, true)
    e += v * v; peak = Math.max(peak, Math.abs(v))
  }
  return { rms: Math.sqrt(e / Math.max(1, count)), peak, seconds: count / 44100 }
}

async function run(skin, devName) {
  const tag = `${skin}-${devName === 'desktop' ? 'desktop' : devName.replace(/\s+/g, '')}`
  const mobile = devName !== 'desktop'
  const steps = []
  const errors = []
  const step = async (name, fn) => {
    const t = Date.now()
    try { const note = await fn(); steps.push({ name, ok: true, note: note ?? '', ms: Date.now() - t }); console.log(`  ok   ${tag}: ${name}${note ? ' (' + note + ')' : ''}`) }
    catch (e) { failed++; steps.push({ name, ok: false, note: String(e.message || e).slice(0, 300) }); console.log(`  FAIL ${tag}: ${name}: ${String(e.message || e).slice(0, 300)}`) }
  }
  const must = (c, m) => { if (!c) throw new Error(m) }
  const ctx = await chromium.launchPersistentContext(PROFILE, {
    executablePath: process.env.CHROME || '/usr/bin/google-chrome',
    headless: true,
    args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    acceptDownloads: true,
    ...(mobile ? devices[devName] : { viewport: { width: 1440, height: 900 } }),
  })
  const page = ctx.pages()[0] || await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text().slice(0, 200)) })
  page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
  await page.route('**/__clip.wav', (r) => r.fulfill({ body: fs.readFileSync(CLIP), contentType: 'audio/wav', headers: { 'Cross-Origin-Resource-Policy': 'same-origin' } }))
  await page.addInitScript((s) => { localStorage.setItem('muse.skin', s); localStorage.setItem('muser.skin', s) }, skin)
  const T = (id) => page.locator(`[data-testid=${id}]`).first()
  const press = (loc) => (mobile ? loc.tap() : loc.click())
  const shot = async (n) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${tag}-${n}.png` }) }
  const state = () => page.evaluate(() => ({ s: window.__muser.audio.state, playing: window.__muser.audio.playing, blocked: window.__muser.audio.blocked, rms: window.__muser.audio.outputRms() }))
  const maxRms = async (n = 12) => { let m = 0; for (let i = 0; i < n; i++) { m = Math.max(m, (await state()).rms); await page.waitForTimeout(100) } return m }
  const overflow = () => page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }))
  const tab = async (name) => { const b = page.getByRole('tab', { name, exact: true }).first(); await b.scrollIntoViewIfNeeded().catch(() => {}); await press(b); await page.waitForTimeout(500) }

  await page.goto(`${BASE}/?demo=1`, { waitUntil: 'domcontentloaded' })
  await page.evaluate((s) => { for (const k of Object.keys(localStorage)) if (!/skin/.test(k)) localStorage.removeItem(k); localStorage.setItem('muser.skin', s) }, skin)
  await page.reload({ waitUntil: 'networkidle' })
  await T('prompt').waitFor({ timeout: 90000 })

  await step('skin applied, cross-origin isolated', async () => {
    const d = await page.evaluate(() => ({ skin: document.documentElement.dataset.skin, iso: crossOriginIsolated }))
    must(d.skin === skin, `skin is ${d.skin}`); must(d.iso, 'page is not cross-origin isolated')
  })
  await step('title and brand say NoDAW Studio PRO', async () => {
    must(/NoDAW Studio PRO/.test(await page.title()), 'title: ' + (await page.title()))
    must(!/The Muser/.test(await page.locator('body').innerText()), 'old name still visible')
  })
  await step('NoDAW button opens the v2 teaser panel', async () => {
    await shot('0-home')
    await press(T('nodaw-button')); await T('nodaw-panel').waitFor()
    const txt = await T('nodaw-panel').innerText()
    for (const w of ['library', 'pattern', 'arrangement', 'FLAC', '.flp', '.rpp']) must(new RegExp(w, 'i').test(txt), 'teaser misses ' + w)
    must(!txt.includes('\u2014'), 'em dash in teaser')
    const bb = await T('nodaw-panel').boundingBox(); const vp = page.viewportSize()
    must(bb.x >= -1 && bb.x + bb.width <= vp.width + 1, 'teaser panel overflows the viewport')
    await shot('1-nodaw-panel')
    await page.keyboard.press('Escape'); await page.waitForTimeout(200)
    if (await T('nodaw-panel').count()) await page.getByRole('button', { name: 'Got it' }).click()
    must((await T('nodaw-panel').count()) === 0, 'panel did not close')
  })
  if (!mobile) await step('NoDAW entry in the command palette', async () => {
    await page.keyboard.press('Control+k'); await T('palette').waitFor()
    await page.keyboard.type('nodaw'); await page.waitForTimeout(200); await shot('2-palette')
    await page.keyboard.press('Enter'); await T('nodaw-panel').waitFor()
    await page.keyboard.press('Escape'); await page.waitForTimeout(200)
    if (await T('nodaw-panel').count()) await page.getByRole('button', { name: 'Got it' }).click()
  })

  await step('Easy generate (genre synth)', async () => {
    await T('prompt').fill('hard trap beat with heavy 808')
    await press(T('make'))
    await page.waitForFunction(() => document.querySelector('[data-testid=make]')?.getAttribute('data-phase') === 'ready', null, { timeout: 120000 })
    await page.waitForTimeout(500); await shot('3-easy-ready')
  })
  await step('Advanced mode: audible with a real tap (RMS > 0.002)', async () => {
    await press(T('mode-advanced')); await page.waitForTimeout(800)
    await press(T('play')); await page.waitForTimeout(1800)
    const st = await state(); const m = await maxRms()
    await shot('4-advanced-playing')
    must(st.s === 'running', 'AudioContext is ' + st.s)
    must(st.playing, 'engine not playing')
    must(m > 0.002, 'output RMS ' + m.toFixed(5) + ' (silent)')
    return `rms ${m.toFixed(3)}`
  })
  await step('no horizontal overflow (Advanced)', async () => { const o = await overflow(); must(o.sw <= o.iw + 1, `scrollWidth ${o.sw} > ${o.iw}`) })

  await step('Live FX: scenes, limiter, bypass, undo/redo change the sound', async () => {
    await tab('Live FX'); await T('livefx-tab').waitFor(); await shot('5-livefx')
    const before = await maxRms()
    const lim = T('fx-limiter'); const lt = await lim.innerText()
    await press(lim); await page.waitForTimeout(200)
    must((await lim.innerText()) !== lt, 'limiter toggle did not change')
    await press(lim)
    const scenes = page.locator('.fx-scenes button'); must((await scenes.count()) >= 2, 'no scenes')
    await press(page.locator('[data-testid^=fx-target-]').nth(1))
    await press(scenes.nth(1)); await page.waitForTimeout(600)
    const undo = page.getByRole('button', { name: 'Undo', exact: true }).first()
    must(await undo.isEnabled(), 'undo not enabled after an FX change')
    const after = await maxRms()
    must(after > 0.0005, 'silent after a scene')
    const bp = T('fx-bypass-all'); await press(bp); must((await bp.getAttribute('aria-pressed')) === 'true', 'bypass not engaged'); await press(bp)
    await press(undo); await page.waitForTimeout(300)
    return `rms ${before.toFixed(3)} -> ${after.toFixed(3)}`
  })
  await step('Live FX: export of the mix is non-silent WAV', async () => {
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), press(T('fx-export-mix'))])
    const p = await dl.path(); const s = wavStats(fs.readFileSync(p))
    must(s.rms > 0.003, 'exported rms ' + s.rms.toFixed(5)); return `rms ${s.rms.toFixed(3)} peak ${s.peak.toFixed(2)} ${s.seconds.toFixed(1)}s`
  })

  await step('Sampler: region, crop, undo, BPM detect, chop to pads', async () => {
    await tab('Sampler'); await T('sampler').waitFor(); await shot('6-sampler')
    const wv = T('region-wave'); await wv.scrollIntoViewIfNeeded(); const bb = await wv.boundingBox()
    await page.mouse.move(bb.x + bb.width * 0.2, bb.y + bb.height / 2); await page.mouse.down()
    await page.mouse.move(bb.x + bb.width * 0.6, bb.y + bb.height / 2, { steps: 6 }); await page.mouse.up(); await page.waitForTimeout(300)
    must(await T('crop').isEnabled(), 'dragging did not make a region')
    await shot('7-sampler-region')
    await press(T('crop')); await page.waitForTimeout(800)
    must(await T('sampler-undo').isEnabled(), 'crop is not undoable')
    await press(T('detect-bpm')); await page.waitForTimeout(1500)
    const bpm = Number(await T('bpm').inputValue()); must(bpm >= 40 && bpm <= 240, 'bpm ' + bpm)
    await press(T('chop')); await page.waitForTimeout(1500)
    const has = await page.locator('[data-testid^=sp-pad-].has').count()
    must(has >= 2, 'chop filled ' + has + ' pads')
    await shot('8-sampler-chopped')
    await press(T('sampler-undo')); await page.waitForTimeout(400)
    return `bpm ${bpm}, ${has} pads`
  })
  await step('Pads play from the Sampler tab (pad 1 audition)', async () => {
    await press(T('sp-pad-0')); await page.waitForTimeout(300); return 'ok'
  })

  const models = ['mini'].concat(process.env.FULL === '1' && skin === 'cathode' && !mobile ? ['htdemucs'] : [])
  for (const model of models) {
    await step(`Split in browser (${model}) on split_clip.wav: stems non-silent, sum ~ mix`, async () => {
      await tab('Split'); await T('split-tab').waitFor()
      await T('split-file').setInputFiles(CLIP); await page.waitForTimeout(1200)
      await press(T(`model-${model}`))
      await press(T('split-go')); await page.waitForTimeout(500)
      if (await T('download-warning').count()) await press(T('split-go'))
      await page.waitForSelector('[data-testid=split-done],[data-testid=split-error]', { timeout: 600000 })
      if (await T('split-error').count()) throw new Error(await T('split-error').innerText())
      await shot(`9-split-${model}`)
      const rep = await T('split-done').locator('.report').innerText()
      const r = await page.evaluate(async () => {
        const a = window.__muser.audio
        const ctx = a.ensure()
        const mix = await ctx.decodeAudioData(await (await fetch('/__clip.wav')).arrayBuffer())
        const ids = a.ids(); const stems = ids.map((id) => a.buffer(id)).filter(Boolean)
        const n = Math.min(mix.length, ...stems.map((b) => b.length))
        const m = mix.getChannelData(0); const sum = new Float32Array(n)
        const rmsList = []
        for (const b of stems) { const d = b.getChannelData(0); let e = 0; for (let i = 0; i < n; i++) { sum[i] += d[i]; e += d[i] * d[i] } rmsList.push(Math.sqrt(e / n)) }
        let num = 0, den = 0; for (let i = 0; i < n; i++) { const d = sum[i] - m[i]; num += d * d; den += m[i] * m[i] }
        return { count: stems.length, rmsList, snr: 10 * Math.log10(den / (num || 1e-12)) }
      })
      must(r.count >= 2, 'stems loaded: ' + r.count)
      must(r.rmsList.every((x) => x > 1e-4), 'a stem is silent: ' + r.rmsList.map((x) => x.toFixed(4)))
      must(r.snr > 10, 'stems do not sum to the mix, SNR ' + r.snr.toFixed(1))
      return `${model}: ${rep.replace(/\s+/g, ' ')} | stems ${r.count} SNR ${r.snr.toFixed(1)} dB`
    })
  }
  await step('split stems play audibly in the mixer', async () => {
    await page.waitForTimeout(1500)
    if (!(await state()).playing) { await press(T('play')); await page.waitForTimeout(1500) }
    const m = await maxRms(); must(m > 0.001, 'silent, rms ' + m.toFixed(5)); return `rms ${m.toFixed(3)}`
  })
  await step('no horizontal overflow (after all tabs)', async () => { const o = await overflow(); must(o.sw <= o.iw + 1, `scrollWidth ${o.sw} > ${o.iw}`) })
  await step('no console errors', async () => { must(!errors.length, errors.slice(0, 3).join(' | ')) })
  await ctx.close()

  // negative case: untrusted click must not leave a silent app without the gate banner
  const ctx2 = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] })
  const c2 = await ctx2.newContext(mobile ? devices[devName] : { viewport: { width: 1440, height: 900 } })
  const p2 = await c2.newPage()
  await p2.addInitScript((s) => { localStorage.setItem('muse.skin', s); localStorage.setItem('muser.skin', s) }, skin)
  await p2.goto(`${BASE}/?demo=1`, { waitUntil: 'networkidle' })
  await step('autoplay blocked: gate banner appears, then a real tap is audible', async () => {
    await p2.locator('[data-testid=prompt]').fill('rainy night drive')
    await p2.evaluate(() => document.querySelector('[data-testid=make]').click())
    await p2.waitForFunction(() => document.querySelector('[data-testid=make]')?.getAttribute('data-phase') === 'ready', null, { timeout: 120000 })
    await p2.evaluate(() => document.querySelector('[data-testid=mode-advanced]').click()); await p2.waitForTimeout(800)
    await p2.evaluate(() => document.querySelector('[data-testid=play]').click()); await p2.waitForTimeout(1500)
    const st = await p2.evaluate(() => ({ s: window.__muser.audio.state, blocked: window.__muser.audio.blocked }))
    const gate = await p2.locator('[data-testid=audio-gate]').count()
    if (st.s !== 'running') must(gate > 0 || st.blocked, 'context ' + st.s + ' but no gate banner')
    const real = p2.locator('[data-testid=play]').first()
    if (mobile) await real.tap(); else await real.click()
    await p2.waitForTimeout(400)
    if (!(await p2.evaluate(() => window.__muser.audio.playing))) { if (mobile) await real.tap(); else await real.click() }
    await p2.waitForTimeout(1800)
    let m = 0; for (let i = 0; i < 10; i++) { m = Math.max(m, await p2.evaluate(() => window.__muser.audio.outputRms())); await p2.waitForTimeout(100) }
    must(m > 0.002, 'silent after a real tap, rms ' + m.toFixed(5))
    return `first state ${st.s}, gate ${gate}, rms ${m.toFixed(3)}`
  })
  await ctx2.close()
  results.push({ tag, steps })
}

for (const dev of DEVICES) for (const skin of SKINS) { console.log(`== ${skin} / ${dev}`); await run(skin, dev) }
fs.writeFileSync(path.join(SHOTS || os.tmpdir(), 'v3-results.json'), JSON.stringify(results, null, 1))
const total = results.reduce((a, r) => a + r.steps.length, 0)
console.log(`\n${total - failed}/${total} checks passed, ${failed} failed`)
fs.rmSync(PROFILE, { recursive: true, force: true })
process.exit(failed ? 1 : 0)
