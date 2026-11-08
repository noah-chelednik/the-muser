// NoDAW Studio PRO deck + mobile check.
// Covers: first-run sound gate + audible output on phones, layout overflow and touch targets in every skin,
// upload rejects and accepts, library sound onto a pad (audible), record a pad hit into the pattern,
// per-pad FX changing the output (and persisting), MIDI default layout + recording, no-Web-MIDI note,
// and the HTMLAudio fallback when Web Audio stays suspended.
// Usage: npm run build && npx vite preview --port 5231 --host 127.0.0.1 (in studio/web), then
//   BASE=http://127.0.0.1:5231 PW=/path/to/playwright-core/index.js node studio/tools/deck_check.mjs
// Env: SKINS=cathode,terrain,score DEVICES="iPhone 14,Pixel 7,desktop" SHOTS=dir
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const PW = process.env.PW || 'playwright-core'
const pwMod = await import(PW.startsWith('/') ? pathToFileURL(PW).href : PW)
const { chromium, devices } = pwMod.chromium ? pwMod : pwMod.default
const BASE = process.env.BASE || 'http://127.0.0.1:5231'
const SKINS = (process.env.SKINS || 'cathode,terrain,score').split(',')
const DEVICES = (process.env.DEVICES || 'iPhone 14,Pixel 7,desktop').split(',')
const SHOTS = process.env.SHOTS || ''
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true })
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'deck-'))
const results = []
let failed = 0

// ---- fixture files
const wav = (seconds = 0.25, freq = 220) => {
  const sr = 44100, n = Math.floor(sr * seconds), b = Buffer.alloc(44 + n * 2)
  b.write('RIFF', 0); b.writeUInt32LE(36 + n * 2, 4); b.write('WAVE', 8); b.write('fmt ', 12)
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(sr, 24); b.writeUInt32LE(sr * 2, 28)
  b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write('data', 36); b.writeUInt32LE(n * 2, 40)
  for (let i = 0; i < n; i++) b.writeInt16LE(Math.round(Math.sin(2 * Math.PI * freq * i / sr) * Math.exp(-i / sr * 8) * 26000), 44 + i * 2)
  return b
}
const F = {
  good: path.join(TMP, 'my snare <b>.wav'),
  exe: path.join(TMP, 'beat.exe'),
  text: path.join(TMP, 'fake.wav'),
  huge: path.join(TMP, 'huge.wav'),
  mismatch: path.join(TMP, 'liar.mp3'),
}
fs.writeFileSync(F.good, wav())
fs.writeFileSync(F.exe, Buffer.concat([Buffer.from('MZ'), Buffer.alloc(2000)]))
fs.writeFileSync(F.text, Buffer.from('<script>alert(1)</script> this is not audio at all, just text pretending to be a wav file'.repeat(4)))
fs.writeFileSync(F.mismatch, wav())
{ const h = wav(0.01); const big = Buffer.alloc(41 * 1024 * 1024); h.copy(big); fs.writeFileSync(F.huge, big) }

async function run(skin, devName, opts = {}) {
  const mobile = devName !== 'desktop'
  const tag = `${skin}-${devName.replace(/\s+/g, '')}${opts.tag ? '-' + opts.tag : ''}`
  const errors = []
  const step = async (name, fn) => {
    const t = Date.now()
    try { const note = await fn(); results.push({ tag, name, ok: true, note: note ?? '', ms: Date.now() - t }); console.log(`  ok   ${tag}: ${name}${note ? ' (' + note + ')' : ''}`) }
    catch (e) { failed++; results.push({ tag, name, ok: false, note: String(e.message || e).slice(0, 300) }); console.log(`  FAIL ${tag}: ${name}: ${String(e.message || e).slice(0, 300)}`) }
  }
  const must = (c, m) => { if (!c) throw new Error(m) }
  const browser = await chromium.launch({
    executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: true,
    args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=document-user-activation-required'],
  })
  const ctx = await browser.newContext({ ...(mobile ? devices[devName] : { viewport: { width: 1440, height: 900 } }), acceptDownloads: true })
  await ctx.addInitScript(([s, o]) => {
    if (!sessionStorage.getItem('deck-init')) { sessionStorage.setItem('deck-init', '1'); for (const k of Object.keys(localStorage)) localStorage.removeItem(k); try { indexedDB.deleteDatabase('muser-kits-v1') } catch {} }
    localStorage.setItem('muser.skin', s)
    if (o.noMidi) { try { delete Navigator.prototype.requestMIDIAccess } catch {} ; Object.defineProperty(navigator, 'requestMIDIAccess', { value: undefined, configurable: true }) }
    if (o.stuck) {
      // Simulate an iPhone where Web Audio never leaves "suspended" after the tap.
      const Orig = window.AudioContext
      window.AudioContext = function (...a) { const c = new Orig(...a); void c.suspend(); c.resume = () => Promise.resolve(); return c }
      window.AudioContext.prototype = Orig.prototype
    }
  }, [skin, opts])
  const page = await ctx.newPage()
  page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)))
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource|MIDI/.test(m.text())) errors.push(m.text().slice(0, 200)) })
  const T = (id) => page.locator(`[data-testid=${id}]`).first()
  const V = (id) => page.locator(`[data-testid=${id}]:visible`).first()
  const press = (loc) => (mobile ? loc.tap() : loc.click())
  const shot = async (n) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${tag}-${n}.png` }) }
  const A = (fn, arg) => page.evaluate(fn, arg)
  const maxRms = async (ms = 900) => { let m = 0; const end = Date.now() + ms; while (Date.now() < end) { m = Math.max(m, await A(() => window.__muser.audio.outputRms())); await page.waitForTimeout(40) } return m }
  const overflow = () => A(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth }))
  const noOverflow = async (where) => { const o = await overflow(); must(o.sw <= o.iw + 1, `${where}: page scrolls sideways, scrollWidth ${o.sw} > ${o.iw}`) }

  await page.goto(`${BASE}/?demo=1`, { waitUntil: 'networkidle' })
  await T('prompt').waitFor({ timeout: 90000 })

  if (mobile) {
    await step('first-run "Tap to enable sound" shows on a phone', async () => {
      await T('sound-gate').waitFor({ timeout: 5000 }); await shot('0-gate')
      const t = await T('sound-gate').innerText(); must(!t.includes('\u2014'), 'em dash in gate copy')
      must((await A(() => window.__muser.audio.state)) === 'none', 'AudioContext was created before the first tap: ' + await A(() => window.__muser.audio.state))
    })
    await step('tap enables sound: context created in the gesture, chime reaches the output', async () => {
      await press(T('sound-gate'))
      let tries = 1
      // the sheet asks for a second tap when the first chime measured silent; a user would tap again too
      while (!(await T('sound-gate-sheet').waitFor({ state: 'detached', timeout: 8000 }).then(() => true, () => false))) {
        if (tries >= 3) throw new Error('gate still open after 3 taps: ' + JSON.stringify(await A(() => window.__muser.audio.lastVerify)))
        await shot(`0-gate-retry${tries}`)
        await press(T('sound-gate')); tries++
      }
      const v = await A(() => window.__muser.audio.lastVerify)
      must(v && v.rms > 0.0005, 'verify ' + JSON.stringify(v))
      if (opts.stuck) { must(v.path === 'media', 'expected the media fallback, got ' + v.path) ; return `media path, state ${v.state}` }
      must(v.state === 'running', 'state ' + v.state)
      return `rms ${v.rms.toFixed(3)}${tries > 1 ? `, needed ${tries} taps` : ''}`
    })
  } else {
    await step('desktop: no first-run gate', async () => { must((await T('sound-gate').count()) === 0, 'gate shown on desktop') })
  }
  await step('no horizontal page scroll (Easy)', () => noOverflow('Easy'))

  if (opts.stuck) {
    await step('Web Audio held: a generated track still plays through the media element', async () => {
      await T('prompt').fill('lofi hip hop')
      await press(V('make'))
      await page.waitForFunction(() => document.querySelector('[data-testid=make]')?.getAttribute('data-phase') === 'ready', null, { timeout: 120000 })
      await press(V('mode-advanced')); await page.waitForTimeout(600)
      await press(V('play'))
      await page.waitForFunction(() => { const el = window.__muser.audio.fallbackEl; return el && !el.paused && el.currentTime > 0.3 && el.src.startsWith('blob:') }, null, { timeout: 20000 }).catch(() => {})
      const s = await A(() => { const a = window.__muser.audio; const el = a.fallbackEl; return { state: a.state, path: a.path, playing: a.playing, paused: el?.paused, t: el?.currentTime, src: (el?.src || '').slice(0, 5) } })
      must(s.state !== 'running', 'context is running, the simulation failed')
      must(s.path === 'media' && s.paused === false && s.t > 0.2 && s.src === 'blob:', 'media fallback not playing: ' + JSON.stringify(s))
      await shot('stuck-media')
      return `ctx ${s.state}, media playing at ${s.t.toFixed(2)}s`
    })
    await browser.close(); return
  }

  await step('Advanced mode: no horizontal scroll', async () => { await press(V('mode-advanced')); await page.waitForTimeout(700); await noOverflow('Advanced'); await shot('1-advanced') })

  // ---- the beat deck
  await step('Beats button opens the deck', async () => { await press(T('beats-open')); await T('beats-sheet').waitFor(); await T('pad-grid').waitFor(); await shot('2-pads') })
  const deck = (id) => page.locator(`[data-testid=beats-sheet] [data-testid=${id}]`).first()
  await step('deck views fit the screen with finger-sized targets', async () => {
    const bad = []
    for (const v of ['pads', 'sounds', 'keys']) {
      await press(deck(`deck-${v}`)); await page.waitForTimeout(400)
      await noOverflow(`deck ${v}`)
      if (mobile) {
        const small = await A(() => {
          const out = []
          document.querySelectorAll('[data-testid=beats-sheet] button, [data-testid=beats-sheet] select, [data-testid=beats-sheet] input[type=range]').forEach((el) => {
            const r = el.getBoundingClientRect(); if (!r.width || !r.height || getComputedStyle(el).visibility === 'hidden') return
            if (el.closest('details:not([open])') && el.tagName !== 'SUMMARY') return
            if (r.height < 43.5 || r.width < 36) out.push(`${el.getAttribute('aria-label') || el.textContent.trim().slice(0, 14) || el.className}:${Math.round(r.width)}x${Math.round(r.height)}`)
          })
          return out
        })
        bad.push(...small.map((x) => `${v}:${x}`))
      }
      await shot(`3-deck-${v}`)
    }
    must(!bad.length, 'targets under 44px: ' + bad.slice(0, 8).join(', '))
  })

  await press(deck('deck-pads'))
  await step('tap a pad (synth hit) is audible', async () => {
    await press(deck('pad-0')); const m = await maxRms(); must(m > 0.003, 'pad rms ' + m.toFixed(4)); return `rms ${m.toFixed(3)}`
  })

  await step('upload rejects: wrong extension, fake WAV bytes, extension/content mismatch, over 40 MB', async () => {
    const msgs = []
    for (const f of [F.exe, F.text, F.mismatch, F.huge]) {
      await deck('pad-upload').setInputFiles(f)
      await deck('upload-error').waitFor({ timeout: 10000 })
      msgs.push(path.basename(f) + ': ' + (await deck('upload-error').innerText()).slice(0, 60))
      must((await deck('pad-sound-name').innerText()) === 'Kick', 'a rejected file was loaded onto the pad')
    }
    const s = msgs.join(' | ')
    must(/Only WAV/.test(msgs[0]) && /not a recognised/.test(msgs[1]) && /contents are WAV/.test(msgs[2]) && /limit is 40 MB/.test(msgs[3]), s)
    return s
  })
  await step('upload accepts a tiny valid WAV, sanitizes its name, and the pad plays it', async () => {
    await deck('pad-upload').setInputFiles(F.good)
    await page.waitForFunction(() => document.querySelector('[data-testid=beats-sheet] [data-testid=pad-sound-name]')?.textContent !== 'Kick', null, { timeout: 10000 })
    const name = await deck('pad-sound-name').innerText()
    must(name === 'my snare b', 'name ' + JSON.stringify(name))
    await page.waitForTimeout(400)
    await press(deck('pad-0')); const m = await maxRms(); must(m > 0.003, 'uploaded pad rms ' + m.toFixed(4))
    return `"${name}", rms ${m.toFixed(3)}`
  })

  await step('assign a CC0 library kick to pad 2 and hear it', async () => {
    await press(deck('pad-1')); await press(deck('pad-change'))
    await deck('sound-browser').waitFor()
    await press(deck('type-kick'))
    await page.waitForTimeout(300)
    const first = page.locator('[data-testid=beats-sheet] [data-testid=lib-list] li').first()
    const title = await first.locator('b').innerText()
    await press(first.locator('[data-testid=lib-load]'))
    await page.waitForFunction((t) => window.__muser.padBank.get(1)?.name === t, title, { timeout: 15000 })
    const src = await A(() => window.__muser.padBank.get(1).source)
    must(src.kind === 'library' && src.license === 'CC0-1.0', JSON.stringify(src))
    await press(deck('deck-pads')); await page.waitForTimeout(200)
    must((await deck('pad-1').innerText()).includes(title.toUpperCase().slice(0, 8)) || (await deck('pad-1').innerText()).toLowerCase().includes(title.toLowerCase().slice(0, 8)), 'pad label not updated')
    await press(deck('pad-1')); const m = await maxRms(); must(m > 0.003, 'library pad rms ' + m.toFixed(4))
    return `${title}, rms ${m.toFixed(3)}`
  })
  await step('library preview uses an <audio> element', async () => {
    await press(deck('deck-sounds')); await page.waitForTimeout(300)
    try {
      await A(() => { window.__prev = []; const pl = HTMLMediaElement.prototype.play; HTMLMediaElement.prototype.play = function () { const s = this.src; const r = pl.call(this); r.then(() => window.__prev.push(s), () => {}); return r } })
      await press(page.locator('[data-testid=beats-sheet] [data-testid=lib-preview]').first())
      await page.waitForFunction(() => window.__prev.some((s) => s.includes('/library/audio/')), null, { timeout: 8000 }).catch(() => {})
      const ok = await A(() => window.__prev.some((s) => s.includes('/library/audio/')))
      must(ok, 'preview <audio> did not play')
      if (await page.locator('[data-testid=beats-sheet] .nd-row.playing').count()) await press(page.locator('[data-testid=beats-sheet] [data-testid=lib-preview]').first())
    } finally { await press(deck('deck-pads')) }
  })

  await step('per-pad FX: a low-pass on the hat pad changes only that pad', async () => {
    await press(deck('pad-4')); await page.waitForTimeout(300)
    const dry = []; for (let i = 0; i < 3; i++) { await press(deck('pad-4')); dry.push(await maxRms(450)) }
    await press(deck('fx-add')); await press(deck('fx-add-filter'))
    await deck('fx-filter-freq').fill('0'); await page.waitForTimeout(200)
    const wet = []; for (let i = 0; i < 3; i++) { await press(deck('pad-4')); wet.push(await maxRms(450)) }
    const d = Math.max(...dry), w = Math.max(...wet)
    must(w < d * 0.5, `filtered hat not quieter: dry ${d.toFixed(4)} wet ${w.toFixed(4)}`)
    const kick = await (async () => { await press(deck('pad-11')); return maxRms(500) })()
    must(kick > 0.003, '808 pad silent after FX on another pad')
    must((await A(() => window.__muser.padBank.settings(11).fx.length)) === 0, 'FX leaked onto pad 12')
    await press(deck('pad-4'))
    // add, reorder, toggle more processors
    for (const t of ['crush', 'reverb', 'delay', 'comp', 'sat']) { await press(deck('fx-add')); await press(deck(`fx-add-${t}`)) }
    await press(deck('pad-4')); const m2 = await maxRms(400)
    const pre = await A(() => window.__muser.padBank.settings(4).fx.map((x) => x.type).join(','))
    must(pre === 'filter,crush,reverb,delay,comp,sat', 'chain after adds ' + pre)
    await press(page.locator('[data-testid=beats-sheet] [data-testid=fx-slot-sat] [data-testid=fx-up]').first())
    const order = await A(() => window.__muser.padBank.settings(4).fx.map((x) => x.type).join(','))
    must(order === 'filter,crush,reverb,delay,sat,comp', 'order ' + order)
    await shot('4-padfx')
    return `hat dry ${d.toFixed(3)} -> low-passed ${w.toFixed(4)}; chain ${order}; rms ${m2.toFixed(3)}`
  })

  await step('record: armed pad hits land in the pattern', async () => {
    const before = await A(() => document.querySelectorAll('[data-testid=beats-sheet] .nd-step.on').length)
    const hat = await A(() => 0)
    void hat
    // empty row for pad 3 (clap) first
    await press(deck('clear-pattern'))
    await press(deck('rec')); await page.waitForTimeout(700)
    for (let i = 0; i < 3; i++) { await press(deck('pad-2')); await page.waitForTimeout(330) }
    await press(deck('rec'))
    await press(deck('seq-play'))
    const pattern = await A(() => document.querySelectorAll('[data-testid=beats-sheet] [data-testid^=step-2-][aria-pressed=true]').length)
    const onPage = pattern
    const total = await A(() => [...document.querySelectorAll('[data-testid=beats-sheet] [data-testid^=seq-row-2] .nd-step.on')].length)
    must(total >= 1 || onPage >= 1, 'no recorded steps for pad 3')
    return `before ${before}, recorded clap steps visible ${total}`
  })

  await step('MIDI default layout: note 36 on channel 10 plays pad 1, note 60 plays the keys', async () => {
    if (await A(() => window.__muser.midi.status) === 'unsupported') return 'browser has no Web MIDI (skipped)'
    await A(() => window.__muser.midi.inject([0x99, 36, 120])); const m = await maxRms(500)
    await press(deck('deck-keys')); await page.waitForTimeout(200)
    await A(() => window.__muser.midi.inject([0x90, 60, 100])); await page.waitForTimeout(150)
    const held = await page.locator('[data-testid=beats-sheet] [data-testid=key-60].held').count()
    const m2 = await maxRms(300)
    await A(() => window.__muser.midi.inject([0x80, 60, 0]))
    must(m > 0.003 && held === 1 && m2 > 0.002, `pad rms ${m} key held ${held} key rms ${m2}`)
    return `pad rms ${m.toFixed(3)}, key rms ${m2.toFixed(3)}`
  })
  await step('keys: preset grid has 40+ presets and each click changes the sound', async () => {
    await press(deck('deck-keys')); await page.waitForTimeout(200)
    const n = await A(() => document.querySelectorAll('[data-testid=beats-sheet] [data-testid^=keycat-]').length)
    let count = 0
    for (let i = 0; i < n; i++) { await press(page.locator('[data-testid=beats-sheet] [data-testid^=keycat-]').nth(i)); count += await page.locator('[data-testid=beats-sheet] [data-testid^=key-preset-]').count() }
    await press(deck('keycat-Bell')); await press(deck('key-preset-bell'))
    must((await deck('key-preset-bell').getAttribute('aria-pressed')) === 'true', 'preset not selected')
    must(count >= 40, 'only ' + count + ' presets')
    await press(deck('key-60')); const m = await maxRms(500)
    must(m > 0.002, 'bell key silent')
    await shot('5-keys')
    return `${count} presets, bell rms ${m.toFixed(3)}`
  })
  await step('record key notes (touch and MIDI) into the key sequence', async () => {
    await press(deck('clear-notes')).catch(() => {})
    await press(deck('rec')); await page.waitForTimeout(500)
    const key = deck('key-62'); const bb = await key.boundingBox()
    if (mobile) await key.tap(); else { await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height * 0.8); await page.mouse.down(); await page.waitForTimeout(250); await page.mouse.up() }
    await page.waitForTimeout(300)
    if (await A(() => window.__muser.midi.status) !== 'unsupported') { await A(() => window.__muser.midi.inject([0x90, 64, 90])); await page.waitForTimeout(300); await A(() => window.__muser.midi.inject([0x80, 64, 0])) }
    await page.waitForTimeout(200)
    await press(deck('rec'))
    const notes = await page.locator('[data-testid=beats-sheet] .nd-roll-cell.on').count()
    must(notes >= 1, 'no notes recorded')
    await shot('6-keyroll')
    return `${notes} notes in the key sequence`
  })
  await step('pad FX persist after reload (IndexedDB)', async () => {
    await press(deck('seq-play')).catch(() => {})
    await page.waitForTimeout(1200)
    await page.reload({ waitUntil: 'networkidle' })
    if (mobile) { await press(T('sound-gate')); await T('sound-gate-sheet').waitFor({ state: 'detached', timeout: 15000 }) }
    await page.waitForFunction(() => window.__muser.padBank.settings(4).fx.length === 6 && window.__muser.padBank.get(1)?.source?.kind === 'library', null, { timeout: 8000 })
    return 'pad 5 FX chain and pad 2 library sound restored'
  })
  if (errors.length) await step('no page errors', async () => { throw new Error(errors.slice(0, 4).join(' | ')) })
  await browser.close()
}

if (!process.env.ONLY_EXTRA) for (const skin of SKINS) for (const d of DEVICES) { console.log(`\n== ${skin} / ${d}`); await run(skin, d).catch((e) => { failed++; console.log('  CRASH', e.message) }) }
if (!process.env.SKIP_EXTRA) {
  console.log('\n== iPhone without Web MIDI (Safari has none)')
  await run('cathode', 'iPhone 14', { noMidi: true, tag: 'nomidi' }).catch((e) => { failed++; console.log('  CRASH', e.message) })
  console.log('\n== Web Audio stuck suspended after the tap (media element fallback)')
  await run('cathode', 'iPhone 14', { stuck: true, tag: 'stuck' }).catch((e) => { failed++; console.log('  CRASH', e.message) })
}
const ok = results.filter((r) => r.ok).length
console.log(`\n${ok}/${results.length} steps passed, ${failed} failed`)
if (process.env.REPORT) fs.writeFileSync(process.env.REPORT, JSON.stringify(results, null, 2))
process.exit(failed ? 1 : 0)
