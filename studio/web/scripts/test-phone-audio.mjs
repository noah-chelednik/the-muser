/** Engine regression tests with deterministic browser/audio doubles, not speaker audibility claims.
 * Run: npm run test:phone-audio. Real iOS/Android device QA is still required.
 */
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import ts from 'typescript'

const engineSource = await readFile(new URL('../src/audio/engine.ts', import.meta.url), 'utf8')
const typeSource = await readFile(new URL('../src/types.ts', import.meta.url), 'utf8')
const compile = (source) => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const settle = () => new Promise((resolve) => setImmediate(resolve))

async function browser({ apple = true, touch = true } = {}) {
  const media = [], counters = { sources: 0, streams: 0, bounces: 0 }
  const param = () => ({ value: 1, cancelScheduledValues() {}, setTargetAtTime(v) { this.value = v }, setValueAtTime(v) { this.value = v } })
  const node = () => ({ connect() { return this }, disconnect() {}, gain: param(), threshold: param(), knee: param(), ratio: param(), attack: param(), release: param(), fftSize: 1024, getFloatTimeDomainData(a) { a.fill(0) } })
  const buffer = (seconds = 1) => ({ duration: seconds, length: seconds * 44100, numberOfChannels: 2, sampleRate: 44100 })
  class AudioContext {
    state = 'running'; currentTime = 0; sampleRate = 44100; destination = node()
    createGain = node; createDynamicsCompressor = node; createAnalyser = node
    resume() { this.state = 'running'; return Promise.resolve() }
    createBuffer() { return buffer() }
    createBufferSource() { counters.sources++; return { ...node(), start() {}, stop() {} } }
    createMediaStreamDestination() { counters.streams++; return { ...node(), stream: {} } }
    decodeAudioData() { return Promise.resolve(buffer()) }
  }
  class OfflineAudioContext extends AudioContext {
    constructor(_channels, length, sampleRate) { super(); this.result = buffer(length / sampleRate) }
    startRendering() { counters.bounces++; return Promise.resolve(this.result) }
  }
  const document = {
    ...(touch ? { ontouchend: null } : {}), visibilityState: 'visible', addEventListener() {},
    body: { appendChild() {} },
    createElement() {
      const f = { paused: true, src: '', currentTime: 0, readyState: 1, loop: false, muted: false, volume: 1, plays: 0, style: {}, attrs: {},
        setAttribute(k, v) { this.attrs[k] = v }, getAttribute(k) { return k === 'src' ? this.src : this.attrs[k] },
        addEventListener() {},
        play() { this.plays++; if (this.rejectNext) { const error = this.rejectNext; this.rejectNext = null; return Promise.reject(error) } this.paused = false; return Promise.resolve() },
        pause() { this.paused = true },
      }
      media.push(f); return f
    },
  }
  const window = { AudioContext, addEventListener() {}, setTimeout }
  const context = vm.createContext({ window, document, navigator: { userAgent: apple ? 'iPhone' : 'Chrome', maxTouchPoints: touch ? 5 : 0, userActivation: { isActive: true } }, location: { search: '?route=stream' }, localStorage: { getItem: () => 'stream', setItem() {} }, matchMedia: () => ({ matches: touch }), OfflineAudioContext, AudioBuffer: class { copyToChannel() {} }, URL, URLSearchParams, Blob, console, setTimeout, clearTimeout, fetch: async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }) })
  // Desktop/Android normal route, Apple must ignore even an old explicit stream override.
  if (!apple) { context.location.search = ''; context.localStorage.getItem = () => null }
  const types = new vm.SourceTextModule(compile(typeSource), { context })
  const chain = () => ({ input: node(), output: node(), apply() {}, dispose() {} })
  const fx = new vm.SyntheticModule(['buildChain', 'dbToGain'], function () { this.setExport('buildChain', chain); this.setExport('dbToGain', (v) => 10 ** (v / 20)) }, { context })
  const wav = new vm.SyntheticModule(['bufferToWav'], function () { this.setExport('bufferToWav', () => new Blob(['wav'], { type: 'audio/wav' })) }, { context })
  const mod = new vm.SourceTextModule(compile(engineSource), { context })
  await mod.link((specifier) => ({ '../types': types, './fx': fx, './wav': wav })[specifier])
  await mod.evaluate()
  return { audio: mod.namespace.audio, media, counters, buffer, defaults: types.namespace.DEFAULT_STEM }
}

test('iPhone: running context + stale stream preference still uses the SAME primed file-media element', async () => {
  const { audio, media, counters } = await browser()
  audio.unlock()
  const fallback = media.at(-1)
  await settle()
  assert.equal(fallback.paused, false, 'priming must not pause before async make finishes')
  assert.equal(fallback.loop, true)
  await audio.load([{ id: 'mix', url: '/stem.wav' }], { mediaUrl: '/generated.wav' })
  audio.play(); await settle()
  assert.equal(audio.ctx.state, 'running')
  assert.equal(audio.path, 'media')
  assert.equal(fallback.src, '/generated.wav')
  assert.equal(fallback.muted, false)
  assert.equal(fallback.volume, 1)
  assert.equal(media.at(-1), fallback)
  assert.equal(counters.streams, 0, 'never create a silent Safari MediaStream speaker route')
  assert.equal(audio.directGain.gain.value, 1, 'do not mute the direct/instrument path')
  audio.pause(); assert.equal(fallback.paused, true)
  audio.unlock(); await settle(); assert.equal(fallback.paused, true, 'unrelated gestures must not restart paused music')
  audio.play(); await settle(); assert.equal(fallback.paused, false)
  assert.equal(media.at(-1), fallback)
  audio.stop()
})

test('Android touch uses media for tracks; desktop retains direct Web Audio', async () => {
  for (const touch of [true, false]) {
    const { audio, media, counters } = await browser({ apple: false, touch })
    audio.unlock(); await audio.load([{ id: 'mix', url: '/stem.wav' }], { mediaUrl: '/mix.wav' })
    audio.play(); await settle()
    assert.equal(audio.path, touch ? 'media' : 'webaudio')
    assert.equal(media.length, touch ? 1 : 0)
    assert.equal(audio.directGain.gain.value, 1)
    if (!touch) assert.ok(counters.sources > 0)
    audio.stop()
  }
})

test('no mix URL bounces offline; equal-length replacement invalidates WAV cache', async () => {
  const { audio, media, counters, buffer } = await browser()
  audio.unlock(); audio.loadBuffers([{ id: 'mix', buffer: buffer() }])
  audio.play(); await settle()
  const first = media.at(-1).src
  assert.match(first, /^blob:/); assert.equal(counters.bounces, 1)
  audio.pause(); audio.play(); await settle()
  assert.equal(counters.bounces, 1, 'reuse an unchanged bounced mix')
  audio.setBuffer('mix', buffer()); await settle()
  assert.equal(counters.bounces, 2)
  assert.notEqual(media.at(-1).src, first)
  audio.stop()
})

test('stop cancels an in-flight render and never starts stale audio', async () => {
  const { audio, media, buffer } = await browser()
  audio.unlock(); audio.loadBuffers([{ id: 'mix', buffer: buffer() }])
  let finish
  audio.bounce = () => new Promise((resolve) => { finish = resolve })
  const f = media.at(-1), silent = f.src
  audio.play(); audio.stop(); finish(buffer()); await settle()
  assert.equal(audio.playing, false); assert.equal(f.paused, true); assert.equal(f.src, silent)
})

test('blocked media is retryable and a broken mix URL falls back to an offline WAV', async () => {
  const { audio, media, counters } = await browser()
  audio.unlock(); await settle()
  await audio.load([{ id: 'mix', url: '/stem.wav' }], { mediaUrl: '/mix.wav' })
  const f = media.at(-1)
  f.rejectNext = Object.assign(new Error('gesture needed'), { name: 'NotAllowedError' })
  audio.play(); await settle()
  assert.equal(audio.blocked, true); assert.equal(audio.playing, false)
  audio.play(); await settle(); assert.equal(audio.blocked, false)
  audio.pause()
  f.rejectNext = Object.assign(new Error('missing media'), { name: 'NotSupportedError' })
  audio.play(); await settle()
  assert.equal(audio.path, 'media'); assert.match(f.src, /^blob:/); assert.equal(counters.bounces, 1)
  audio.stop()
})

test('phone mixer edits re-bounce the same offline FX graph while desktop export stays intact', async () => {
  const { audio, defaults, counters, media } = await browser()
  audio.unlock(); await audio.load([{ id: 'mix', url: '/stem.wav' }], { mediaUrl: '/mix.wav' })
  audio.play(); await settle()
  audio.applyParams('mix', { ...defaults, mute: true }, false)
  await new Promise((resolve) => setTimeout(resolve, 220))
  assert.equal(counters.bounces, 1); assert.match(media.at(-1).src, /^blob:/)
  const out = await audio.bounce({ mixer: { mix: defaults }, masterGainDb: 0, sampleRate: 48000 })
  assert.ok(out.duration >= audio.duration)
  audio.stop()
})

// UI wiring checks deliberately avoid claiming a mocked DOM proves Safari audibility.
test('Make primes synchronously and generated phone tracks explicitly request auto-start', async () => {
  const easy = await readFile(new URL('../src/studio/EasyContext.tsx', import.meta.url), 'utf8')
  const studio = await readFile(new URL('../src/studio/StudioContext.tsx', import.meta.url), 'utf8')
  assert.match(easy, /const make = async \(\) => \{\s*audio\.unlock\(\)/)
  assert.match(studio, /onGenerate[^=]*= async \(args\) => \{\s*audio\.unlock\(\)/)
  assert.match(studio, /loadTrack\(res.track, false, true\)/)
  assert.match(studio, /shouldPlay && isTouchDevice\(\) && audio.gestured\) audio.play\(\)/)
})

test('first-run phone chime re-arms a looping silent source on the same media element', async () => {
  const { audio, media } = await browser()
  const result = await audio.verify()
  const f = media.at(-1), chime = f.src
  assert.equal(result.path, 'media')
  assert.equal(f.loop, false)
  f.onended(); await settle()
  assert.equal(f.loop, true); assert.equal(f.paused, false); assert.notEqual(f.src, chime)
})
