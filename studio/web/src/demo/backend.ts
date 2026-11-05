// In-browser stand-in for the Studio's Python API. Used automatically when /api is unreachable
// (for example on the public Vercel demo). Everything runs locally in the page: nothing is uploaded.
// Audio is DEMO audio from a small procedural synth, never AI-generated.
import type { Api, ChatEvent } from '../api'
import type { Analysis, FxItem, Job, Preset, Status, StemInfo, Track } from '../types'
import * as D from './dsp'
import { normalizeChain, renderChain } from './fx'
import { bandSplit, keyName, parsePrompt, renderSpec, toMidi, type NoteEvent, SR } from './synth'
import { zipFiles } from './zip'
import presetsFx from './fixtures/presets.json'
import categoriesFx from './fixtures/categories.json'
import slidersFx from './fixtures/sliders.json'
import pluginsFx from './fixtures/plugins.json'
import targetsFx from './fixtures/targets.json'
import sepFx from './fixtures/sepmodels.json'
import enginesFx from './fixtures/engines.json'
import hardwareFx from './fixtures/hardware.json'

export const DEMO_NOTE = 'Browser demo synthesizer (DEMO). Not AI-generated audio. The local install runs real AI models.'
const LOCAL_HINT = 'Install NoDAW Studio PRO from github.com/myaiplug/the-muser to run this on your own machine.'

class Friendly extends Error {
  hint: string
  constructor(msg: string, hint = '') { super(msg); this.hint = hint }
}

// ------------------------------------------------------------------ state
type Rec = { pub: Track; audio: D.Audio; hidden: Record<string, D.Audio> | null; notes: NoteEvent[]; analysis?: Analysis }
const recs = new Map<string, Rec>()
const stemAudio = new Map<string, D.Audio>()
const jobs = new Map<string, Job>()
let seq = 0
const uid = (p: string) => `${p}${Date.now().toString(36)}${(seq++).toString(36)}`
const tick = () => new Promise<void>((r) => setTimeout(r, 0))
const urlOf = (a: D.Audio) => URL.createObjectURL(D.encodeWav(a))
const STEM_COLORS: Record<string, string> = { drums: '#ff4d6d', bass: '#ffb703', vocals: '#c77dff', other: '#4cc9f0', no_vocals: '#4cc9f0', chords: '#4cc9f0', lead: '#80ffdb' }
const FALLBACK = ['#ffb703', '#4cc9f0', '#c77dff', '#80ffdb', '#ff4d6d', '#e9c46a']
const colorFor = (name: string, i: number) => STEM_COLORS[name.split(' ')[0]] ?? FALLBACK[i % FALLBACK.length]

function need(id: string): Rec {
  const r = recs.get(id)
  if (!r) throw new Friendly('That song is no longer in the library.', 'Browser demo songs live in this page only. Reloading clears them.')
  return r
}
const pubOf = (r: Rec): Track => ({ ...r.pub, stems: [...r.pub.stems], meta: { ...r.pub.meta } })

function addTrack(p: Partial<Track> & { title: string; source: string }, audio: D.Audio, extra: { hidden?: Record<string, D.Audio> | null; notes?: NoteEvent[] } = {}): Rec {
  const id = uid('t')
  const pub: Track = {
    id, title: p.title, source: p.source, url: urlOf(audio), created: Date.now() / 1000, prompt: p.prompt ?? '',
    bpm: p.bpm ?? null, key: p.key ?? '', duration_s: +D.seconds(audio).toFixed(2), stems: p.stems ?? [],
    stem_method: p.stem_method ?? '', notes: p.notes ?? '', parent_id: p.parent_id ?? '', meta: { browser_demo: true, ...(p.meta ?? {}) },
  }
  const rec: Rec = { pub, audio, hidden: extra.hidden ?? null, notes: extra.notes ?? [] }
  recs.set(id, rec)
  return rec
}
function newChild(parent: Rec, audio: D.Audio, title: string, source: string, notes: string, meta: Record<string, unknown>): Rec {
  const c = addTrack({ title, source, prompt: parent.pub.prompt, bpm: parent.pub.bpm, key: parent.pub.key, parent_id: parent.pub.id, notes, meta, stems: [...parent.pub.stems], stem_method: parent.pub.stem_method }, audio, { hidden: parent.hidden, notes: parent.notes })
  return c
}
function exposeStems(rec: Rec, stems: Record<string, D.Audio>, method: string, note: string) {
  const list: StemInfo[] = Object.entries(stems).map(([name, audio], i) => {
    const id = `${rec.pub.id}:${i}`
    stemAudio.set(id, audio)
    return { id, name, path: `demo://${id}`, url: urlOf(audio), color: colorFor(name, i) }
  })
  rec.pub.stems = list
  rec.pub.stem_method = method
  rec.pub.notes = note
}

function submit<T>(kind: string, fn: (msg: (m: string) => void) => Promise<T>): Promise<{ job_id: string }> {
  const job: Job<T> = { job_id: uid('j'), kind, status: 'queued', message: 'Starting...', result: null, error: '' }
  jobs.set(job.job_id, job as Job)
  setTimeout(() => {
    job.status = 'running'
    fn((m) => { job.message = m })
      .then((r) => { job.result = r; job.status = 'done'; job.message = 'Done' })
      .catch((e) => { job.status = 'error'; job.error = e instanceof Error ? e.message : String(e); if (e instanceof Friendly && e.hint) job.detail = e.hint })
  }, 30)
  return Promise.resolve({ job_id: job.job_id })
}

// ------------------------------------------------------------------ presets
const factory = presetsFx as unknown as Preset[]
const LS = {
  get<T>(k: string, d: T): T { try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : d } catch { return d } },
  set(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* private mode */ } },
}
const userPresets = (): Preset[] => LS.get<Preset[]>('muser.demo.presets', [])
const favs = (): Set<string> => new Set(LS.get<string[]>('muser.demo.favs', []))
const allPresets = (): Preset[] => [...factory, ...userPresets()]
function presetGet(id: string): Preset {
  const p = allPresets().find((x) => x.id === id)
  if (!p) throw new Friendly(`There is no preset called '${id}'.`)
  return p
}
function chainOf(ref: string | FxItem[] | null | undefined): FxItem[] {
  if (!ref) return []
  if (Array.isArray(ref)) return normalizeChain(ref)
  const p = presetGet(ref)
  if (p.category === 'master') return normalizeChain((p.master as { chain: FxItem[] }).chain)
  return normalizeChain(p.chain)
}
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'preset'

function saveUserPreset(p: Partial<Preset>): Preset {
  const name = String(p.name ?? '').trim()
  if (!name) throw new Friendly('Give the preset a name.')
  const cat = p.category
  if (!cat || !(cat in categoriesFx)) throw new Friendly(`Unknown preset category '${cat}'.`)
  const out: Preset = {
    ...(p as Preset), name: name.slice(0, 80), category: cat, tags: (p.tags ?? []).map((t) => String(t).slice(0, 30)).slice(0, 12),
    description: String(p.description ?? '').slice(0, 300), factory: false,
  }
  if (cat === 'master') {
    const m = p.master as { target: string; chain: FxItem[]; release_ms?: number } | undefined
    if (!m || !(m.target in targetsFx)) throw new Friendly(`Unknown loudness target '${m?.target}'.`)
    out.master = { target: m.target, chain: normalizeChain(m.chain), release_ms: m.release_ms ?? 80 }
  } else if (cat === 'genre') {
    if (!String(p.generate?.prompt ?? '').trim()) throw new Friendly('A genre starter needs a prompt.')
  } else out.chain = normalizeChain(p.chain)
  const list = userPresets()
  const base = `user-${cat}/${slug(name)}`
  let id = base, n = 2
  while ((factory.some((x) => x.id === id) || list.some((x) => x.id === id)) && id !== p.id) id = `${base}-${n++}`
  out.id = id
  LS.set('muser.demo.presets', [...list.filter((x) => x.id !== id), out])
  return out
}

function listing(category?: string, q?: string, favoritesOnly?: boolean): Preset[] {
  const f = favs()
  const terms = (q ?? '').toLowerCase().split(/\s+/).filter(Boolean)
  const items = allPresets()
    .filter((p) => (!category || p.category === category) && (!favoritesOnly || f.has(p.id)))
    .filter((p) => {
      const hay = [p.name, p.description, p.subcategory ?? '', p.category, (p.tags ?? []).join(' ')].join(' ').toLowerCase()
      return terms.every((t) => hay.includes(t))
    })
    .map((p) => ({ ...p, favorite: f.has(p.id), user: !p.factory }))
  items.sort((a, b) => Number(b.favorite) - Number(a.favorite) || a.category.localeCompare(b.category) || (a.subcategory ?? '').localeCompare(b.subcategory ?? '') || a.name.localeCompare(b.name))
  return items
}
function matchVibe(text: string): string {
  const words = new Set(text.toLowerCase().match(/[a-z0-9]+/g) ?? [])
  let best = 'genre/pop', bs = 0
  for (const p of listing('genre')) {
    const hay = new Set(`${p.name} ${(p.tags ?? []).join(' ')} ${p.description} ${p.generate?.prompt ?? ''}`.toLowerCase().match(/[a-z0-9]+/g) ?? [])
    const nm = new Set(`${p.name} ${(p.tags ?? []).join(' ')}`.toLowerCase().match(/[a-z0-9]+/g) ?? [])
    let s = 0
    words.forEach((w) => { if (hay.has(w)) s += 1; if (nm.has(w)) s += 2 })
    if (s > bs) { best = p.id; bs = s }
  }
  return best
}

// ------------------------------------------------------------------ mixing
const ROLE_WORDS: [string, string[]][] = [
  ['vocals', ['vocal', 'vox', 'voice', 'acapella', 'sing']], ['drums', ['drum', 'kick', 'snare', 'perc', 'hat', 'beat']],
  ['bass', ['bass', '808', 'sub', 'low (']], ['guitar', ['guitar']], ['lead', ['lead', 'melody', 'synth', 'high-mid', 'air']],
  ['keys', ['chord', 'key', 'piano', 'pad', 'organ', 'low-mid', 'instrumental', 'other', 'no_vocals']],
]
const roleFor = (name: string) => { const n = name.toLowerCase(); for (const [r, w] of ROLE_WORDS) if (w.some((x) => n.includes(x))) return r; return 'other' }

type SliderMap = { scope: string; only?: string; when?: string; op: string; value?: [number, number]; fx?: { type: string; params: Record<string, number | [number, number]> } }
type SliderDef = { key: string; maps: SliderMap[] }
const lerp = (v: number | [number, number], t: number) => (Array.isArray(v) ? v[0] + (v[1] - v[0]) * t : v)
const activeT = (value: number, when = 'both') => {
  const x = Math.min(Math.max(value, 0), 100) / 100
  if (when === 'above') return x <= 0.5 ? null : (x - 0.5) * 2
  if (when === 'below') return x >= 0.5 ? null : x * 2
  return x
}
type Plan = { stems: Record<string, { role: string; chain: FxItem[]; gain_db: number }>; master: FxItem[]; master_preset: string | null; genre: string | null; macros: Record<string, number> }
function planEasy(genreId: string | null | undefined, values: Record<string, number>, stemNames: string[]): Plan {
  const g = genreId ? presetGet(genreId) : null
  const hasStems = stemNames.length > 0
  const plan: Plan = { stems: {}, master: [], master_preset: null, genre: genreId ?? null, macros: {} }
  const roleChains = (g?.stems ?? {}) as Record<string, string | FxItem[]>
  for (const name of stemNames) {
    const role = roleFor(name)
    const ref = roleChains[role] ?? (role === 'other' || role === 'guitar' ? roleChains.keys : undefined)
    plan.stems[name] = { role, chain: ref ? chainOf(ref) : [], gain_db: 0 }
  }
  if (typeof g?.master === 'string') plan.master_preset = g.master
  for (const s of slidersFx as unknown as SliderDef[]) {
    const val = Number(values[s.key] ?? 50)
    plan.macros[s.key] = val
    for (const m of s.maps) {
      if ((m.only === 'stems' && !hasStems) || (m.only === 'mix' && hasStems)) continue
      const t = activeT(val, m.when)
      if (t === null) continue
      const targets = m.scope === 'master' ? null : new Set(m.scope.startsWith('role:') ? [m.scope.slice(5)] : m.scope.split(':')[1].split(','))
      if (m.op === 'gain') {
        const amt = lerp(m.value as [number, number], t)
        for (const st of Object.values(plan.stems)) if (targets?.has(st.role)) st.gain_db += amt
      } else if (m.op === 'insert' && m.fx) {
        const item: FxItem = { type: m.fx.type, params: Object.fromEntries(Object.entries(m.fx.params).map(([k, v]) => [k, lerp(v, t)])) }
        if (!targets) plan.master.push(item)
        else for (const st of Object.values(plan.stems)) if (targets.has(st.role)) st.chain = [...st.chain, structuredClone(item)]
      }
    }
  }
  return plan
}

type Source = { name: string; audio: D.Audio; chain?: FxItem[]; gain_db?: number; pan?: number }
async function renderMix(sources: Source[], master: FxItem[], msg?: (m: string) => void): Promise<D.Audio> {
  if (!sources.length) throw new Friendly('Nothing to render: every stem is muted.')
  const parts: D.Audio[] = []
  for (let i = 0; i < sources.length; i++) {
    const s = sources[i]
    msg?.(`Processing ${s.name} (${i + 1}/${sources.length})`)
    await tick()
    let x = s.chain?.length ? renderChain(s.audio, s.chain) : D.clone(s.audio)
    D.scale(x, D.db2lin(s.gain_db ?? 0))
    x = D.pan(x, s.pan ?? 0)
    parts.push(x)
  }
  msg?.('Master bus ...')
  await tick()
  let mix = D.sum(parts)
  const l0 = D.lufs(mix)
  if (Number.isFinite(l0)) D.scale(mix, D.db2lin(Math.min(Math.max(-18 - l0, -30), 30)))
  if (master.length) mix = renderChain(mix, master)
  return D.masterTo(mix, -16, -1)
}

const stemSources = (rec: Rec): { name: string; audio: D.Audio }[] => {
  if (rec.pub.stems.length) return rec.pub.stems.flatMap((s) => { const a = stemAudio.get(s.id); return a ? [{ name: s.name, audio: a }] : [] })
  if (rec.hidden) return Object.entries(rec.hidden).map(([name, audio]) => ({ name, audio }))
  return []
}

// ------------------------------------------------------------------ operations
async function generateTrack(o: { prompt: string; duration_s: number; bpm?: number | null; key?: string; title?: string; genre?: string | null }, msg: (m: string) => void): Promise<{ track: Track; engine: string }> {
  const spec = parsePrompt(o.prompt, o.bpm, o.key, o.duration_s, o.genre)
  msg(`Browser demo synth: ${spec.genre}, ${spec.bpm} BPM, ${keyName(spec)}`)
  const r = await renderSpec(spec, (p, m) => msg(m + ` (${Math.round(p * 100)}%)`))
  const rec = addTrack(
    { title: o.title || o.prompt.slice(0, 48) || 'Demo loop', source: 'demo-synth', prompt: o.prompt, bpm: spec.bpm, key: keyName(spec), notes: DEMO_NOTE, meta: { demo_synth: true, genre: spec.genre } },
    r.mix, { hidden: r.stems, notes: r.notes },
  )
  return { track: pubOf(rec), engine: 'demo-synth' }
}

async function splitTrack(id: string, mode: string, msg: (m: string) => void) {
  const rec = need(id)
  await tick()
  if (rec.hidden && mode === '4stem') {
    msg('Exposing the demo synth source tracks...')
    exposeStems(rec, rec.hidden, 'demo-synth', "Stems are the browser demo synthesizer's own source tracks (exact, not separated).")
  } else {
    msg('Browser demo: splitting into 4 frequency bands...')
    exposeStems(rec, bandSplit(rec.audio), 'band-split', 'Browser demo: frequency-band split (crossover), not true source separation. The local install runs Demucs and other real separators.')
  }
  return { track: pubOf(rec), method: rec.pub.stem_method, note: rec.pub.notes }
}

async function easyRender(body: Record<string, unknown>, msg?: (m: string) => void) {
  const t = need(String(body.track_id))
  const rootId = t.pub.meta?.easy_root as string | undefined
  const base = (rootId && recs.get(rootId)) || t
  const keys = ['energy', 'vocals', 'bass', 'brightness', 'space']
  const values = Object.fromEntries(keys.map((k) => [k, Number(body[k] ?? 50)]))
  const stems = stemSources(base)
  const plan = planEasy((body.genre_id as string) ?? null, values, stems.map((s) => s.name))
  const sources: Source[] = stems.length ? stems.map((s) => ({ ...s, chain: plan.stems[s.name].chain, gain_db: plan.stems[s.name].gain_db })) : [{ name: 'mix', audio: base.audio }]
  const audio = await renderMix(sources, plan.master, msg)
  const label = Object.entries(values).filter(([, v]) => Math.abs(v - 50) >= 1).map(([k, v]) => `${k[0].toUpperCase()}${k.slice(1)} ${Math.round(v)}`).join(', ') || 'vibe defaults'
  const child = newChild(base, audio, `${base.pub.title} (tuned)`, 'easy-mix', `Easy mix: ${label}.`, { easy_root: base.pub.id, plan, fx_engines: ['browser-dsp'], analysis: D.analyze(audio) })
  return { track: pubOf(child), plan }
}

function target(key: string) {
  const t = (targetsFx as Record<string, { label: string; lufs: number; true_peak_db: number }>)[key]
  if (!t) throw new Friendly(`Unknown platform '${key}'.`)
  return t
}
async function finishTrack(body: Record<string, unknown>, msg: (m: string) => void) {
  const t = need(String(body.track_id))
  const key = String(body.target ?? 'spotify')
  const tg = target(key)
  let chain = body.chain as FxItem[] | null | undefined
  let presetUsed: string | null = null
  if (!chain) {
    const pid = (body.preset_id as string) || `master/${slug(tg.label + ' master')}`
    const p = allPresets().find((x) => x.id === pid)
    if (p && typeof p.master === 'object' && p.master) { chain = p.master.chain; presetUsed = pid } else chain = []
  }
  msg(`Mastering for ${tg.label} ...`)
  await tick()
  const lufsT = Number(body.lufs ?? tg.lufs), tpT = Number(body.true_peak_db ?? tg.true_peak_db)
  const y = D.masterTo(renderChain(t.audio, chain), lufsT, tpT)
  const lufs = D.lufs(y), tp = D.truePeakDb(y)
  const report = {
    lufs: +lufs.toFixed(2), true_peak_db: +tp.toFixed(2), target: { key, label: tg.label, lufs: lufsT, true_peak_db: tpT },
    within_tolerance: Math.abs(lufs - lufsT) <= 0.6 && tp <= tpT + 0.3, preset: presetUsed, engine: 'browser-dsp',
  }
  const child = newChild(t, y, `${t.pub.title} (${tg.label})`, 'master', `Finished for ${tg.label}: ${report.lufs.toFixed(1)} LUFS, ${report.true_peak_db.toFixed(1)} dBTP.`, { master: report, easy_root: t.pub.meta?.easy_root ?? '', finished: true })
  return { track: pubOf(child), report }
}

async function bandRms(a: D.Audio, lo: number, hi: number): Promise<number> {
  const c = D.clone(a)
  D.biquad(c, 'highpass', lo); D.biquad(c, 'lowpass', hi)
  return D.rmsDb(c)
}

async function runTool(name: string, body: Record<string, unknown>, msg: (m: string) => void) {
  const id = String(body.track_id)
  if (name === 'split') return splitTrack(id, String(body.mode ?? '4stem'), msg)
  const t = need(id)
  if (name === 'remove_vocals') {
    msg('Browser demo: cancelling the centre of the stereo image...')
    await tick()
    const n = D.length(t.audio), inst = D.silence(t.audio.sr, n), voc = D.silence(t.audio.sr, n)
    for (let i = 0; i < n; i++) {
      const m = (t.audio.ch[0][i] + t.audio.ch[1][i]) / 2, s = (t.audio.ch[0][i] - t.audio.ch[1][i]) / 2
      inst.ch[0][i] = s; inst.ch[1][i] = -s; voc.ch[0][i] = m; voc.ch[1][i] = m
    }
    D.scale(inst, 1.4)
    const child = newChild(t, inst, `${t.pub.title} (instrumental)`, 'instrumental', 'Browser demo: centre-channel cancel. It removes anything panned dead centre, not just vocals. This is not AI separation; the local install runs real separators.', { tool: 'remove_vocals', engine: 'center-cancel' })
    const vurl = urlOf(voc)
    child.pub.meta = { ...child.pub.meta, vocals_url: vurl }
    return { track: pubOf(child), vocals_url: vurl }
  }
  if (name === 'denoise') {
    msg('Browser demo: rumble filter and noise gate...')
    await tick()
    const s = Number(body.strength ?? 0.8)
    let y = D.biquad(D.clone(t.audio), 'highpass', 60)
    y = D.gate(y, -62 + 24 * s, 3 + 3 * s, 3, 160)
    const child = newChild(t, y, `${t.pub.title} (clean)`, 'denoise', 'Browser demo: rumble filter plus a noise gate. It is not AI denoising.', { tool: 'denoise', engine: 'browser-dsp' })
    return { track: pubOf(child), engine: 'browser-dsp' }
  }
  if (name === 'match') {
    if (!body.reference_track_id) throw new Friendly('Upload or pick a reference song first.')
    const r = need(String(body.reference_track_id))
    const amount = Number(body.amount ?? 1)
    msg('Browser demo: matching tone and loudness to your reference...')
    await tick()
    const bands: [number, number, number][] = [[40, 120, 80], [120, 400, 220], [400, 1500, 800], [1500, 5000, 2800], [5000, 16000, 8000]]
    let y = D.clone(t.audio)
    const ref = r.audio
    for (const [lo, hi, f] of bands) {
      const diff = (await bandRms(ref, lo, hi)) - (await bandRms(t.audio, lo, hi))
      y = D.biquad(y, 'peak', f, 0.8, Math.min(Math.max(diff * amount, -9), 9))
    }
    const rl = D.lufs(ref)
    if (Number.isFinite(rl)) y = D.masterTo(y, D.lufs(t.audio) + (rl - D.lufs(t.audio)) * amount, -1)
    const child = newChild(t, y, `${t.pub.title} (matched to ${r.pub.title})`, 'match', `Matched to '${r.pub.title}' with a 5-band EQ match (browser demo).`, { tool: 'match', engine: 'browser-dsp', reference: r.pub.id })
    return { track: pubOf(child), engine: 'browser-dsp' }
  }
  if (name === 'midi') {
    msg('Browser demo: writing the synth notes as MIDI...')
    await tick()
    if (!t.notes.length) throw new Friendly('Audio-to-MIDI needs the local install.', 'The browser demo can only export MIDI for songs made by its own synth. ' + LOCAL_HINT)
    const bytes = toMidi(t.notes, t.pub.bpm ?? 96)
    const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: 'audio/midi' }))
    return { midi_url: url, notes: t.notes.length, engine: 'demo-synth', note: 'Notes the browser demo synth played (exact, not transcribed).' }
  }
  throw new Friendly('Unknown tool')
}

async function previewChain(body: Record<string, unknown>) {
  let chain: FxItem[]
  if (Array.isArray(body.chain)) chain = normalizeChain(body.chain as FxItem[])
  else if (body.preset_id) {
    const p = presetGet(String(body.preset_id))
    chain = p.category === 'genre' ? (typeof p.master === 'string' ? chainOf(p.master) : []) : chainOf(String(body.preset_id))
  } else throw new Friendly('Pick a preset to preview.')
  let src: D.Audio | undefined
  const rec = body.track_id ? recs.get(String(body.track_id)) : undefined
  if (rec) src = (body.stem_id ? stemAudio.get(String(body.stem_id)) : undefined) ?? rec.audio
  if (!src) src = (await demoLoop()).mix
  const seconds = Number(body.seconds ?? 8), n = Math.floor(seconds * src.sr)
  const s0 = Math.min(Math.floor(D.length(src) * 0.3), Math.max(0, D.length(src) - n))
  const seg: D.Audio = { sr: src.sr, ch: [src.ch[0].slice(s0, s0 + n), src.ch[1].slice(s0, s0 + n)] }
  const y = renderChain(seg, chain)
  const a = D.lufs(seg), b = D.lufs(y)
  if (Number.isFinite(a) && Number.isFinite(b)) D.scale(y, D.db2lin(Math.min(Math.max(a - b, -24), 24)))
  D.limit(y, -1.6)
  return { url: urlOf(y), dry_url: urlOf(seg), engine: 'browser-dsp', seconds: D.seconds(seg) }
}
let loopCache: Promise<Awaited<ReturnType<typeof renderSpec>>> | null = null
const demoLoop = () => (loopCache ??= renderSpec(parsePrompt('lofi hip hop, 85 bpm, in A minor', null, null, 16)))

async function decodeUpload(file: File): Promise<D.Audio> {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const ctx = new Ctx()
  try {
    const buf = await ctx.decodeAudioData(await file.arrayBuffer())
    const l = buf.getChannelData(0), r = buf.numberOfChannels > 1 ? buf.getChannelData(1) : l
    const max = Math.min(l.length, Math.floor(buf.sampleRate * 360))
    return D.resample({ sr: buf.sampleRate, ch: [l.slice(0, max), r.slice(0, max)] }, SR)
  } catch {
    throw new Friendly("This browser couldn't decode that file.", 'Try a WAV or MP3.')
  } finally {
    void ctx.close()
  }
}

// ------------------------------------------------------------------ chat
async function chat(body: { message: string }, onEvent: (e: ChatEvent) => void, signal?: AbortSignal) {
  const say = async (text: string) => {
    for (const w of text.match(/\S+\s*/g) ?? []) {
      if (signal?.aborted) return
      onEvent({ event: 'token', data: { text: w } })
      await new Promise((r) => setTimeout(r, 18))
    }
  }
  onEvent({ event: 'session', data: { session_id: 'browser-demo' } })
  const msg = body.message
  if (/(make|generate|create|write|compose|beat|track|song|loop)/i.test(msg)) {
    await say('Browser demo: there is no language model here, so I will hand your words to the built-in synth. ')
    onEvent({ event: 'tool_start', data: { name: 'demo_synth' } })
    try {
      const out = await generateTrack({ prompt: msg, duration_s: 16 }, () => undefined)
      onEvent({ event: 'tool_end', data: { name: 'demo_synth', status: 'success', result: {} } })
      onEvent({ event: 'track', data: { track: out.track } })
      await say(`Done: ${out.track.bpm} BPM, ${out.track.key}. This is DEMO audio from a procedural synth, not AI. Install NoDAW Studio PRO locally for real generation.`)
    } catch (e) {
      onEvent({ event: 'tool_end', data: { name: 'demo_synth', status: 'error', result: { error: String(e) } } })
    }
  } else {
    await say('This is the browser demo, so the chat has no language model behind it. Try "make a lofi beat at 80 bpm" to hear the built-in synth, or switch to Easy mode and press Make. The local install connects a real LLM and the full toolset.')
  }
  onEvent({ event: 'final', data: { text: '' } })
}

// ------------------------------------------------------------------ status, hardware
const cap = (key: string, label: string, available: boolean, detail: string, hint = '') => ({ key, label, available, detail, hint })
const status = (): Status => ({
  mode: 'demo', demo_forced: true, tool_count: 46,
  mode_detail: 'Browser demo: sounds come from a small in-browser synthesizer, not AI. Real AI generation needs the local install.',
  items: {
    browser: cap('browser', 'Browser demo', true, 'Everything runs in this page. Nothing is uploaded and there is no server.'),
    ollama: cap('ollama', 'Ollama LLM', false, 'No language model in the browser demo.', 'Install the local app and Ollama (ollama.com).'),
    gpu: cap('gpu', 'NVIDIA GPU', false, 'The browser demo does not use a GPU.', 'AI generation wants an NVIDIA GPU. 8 GB runs ACE-Step 1.5 with low-memory settings.'),
    acestep: cap('acestep', 'ACE-Step', false, 'Needs the local install.', 'github.com/myaiplug/the-muser'),
    demucs: cap('demucs', 'Demucs stems', false, 'Generated demo songs expose their own synth tracks. The Split tab runs Demucs (ONNX) in this tab on your own audio.', 'The local install runs the full Demucs and Roformer stack.'),
  },
  ollama_models: [], llm_models: [],
  browser_demo: true,
} as Status)

let session: Record<string, unknown> = {}
const fileOf = async (f: File) => JSON.parse(await f.text()) as unknown

export function createDemoApi(): Api {
  const impl: Api = {
    status: async () => status(),
    tracks: async () => [...recs.values()].map(pubOf).sort((a, b) => b.created - a.created),
    deleteTrack: async (id: string) => { recs.delete(id); return { deleted: true } },
    generate: (b) => submit('generate', (m) => generateTrack({ prompt: b.prompt, duration_s: b.duration_s, bpm: b.bpm, key: b.key }, m)),
    split: (id, mode) => submit('split', (m) => splitTrack(id, mode, m)),
    mix: (b: unknown) => submit('mix', async (m) => {
      const req = b as { track_id: string; stems: Record<string, unknown>[]; master_gain_db?: number; normalize?: boolean }
      const t = need(req.track_id)
      const any = req.stems.some((s) => s.solo)
      const sources: Source[] = []
      for (const s of req.stems) {
        const a = stemAudio.get(String(s.stem_id))
        if (!a || s.mute || (any && !s.solo)) continue
        const chain: FxItem[] = []
        if (s.eq_low_db) chain.push({ type: 'lowshelf', params: { cutoff_hz: 200, gain_db: Number(s.eq_low_db), q: 0.7 } })
        if (s.eq_mid_db) chain.push({ type: 'peak', params: { freq_hz: 1000, gain_db: Number(s.eq_mid_db), q: 1 } })
        if (s.eq_high_db) chain.push({ type: 'highshelf', params: { cutoff_hz: 5000, gain_db: Number(s.eq_high_db), q: 0.7 } })
        if (Number(s.comp) > 0) chain.push({ type: 'compressor', params: { threshold_db: -12 - 12 * Number(s.comp), ratio: 1.5 + 4 * Number(s.comp), attack_ms: 10, release_ms: 120, makeup_db: 3 * Number(s.comp) } })
        if (Number(s.reverb) > 0) chain.push({ type: 'reverb', params: { room_size: Number(s.room ?? 0.5), damping: 0.5, width: 1, mix: Number(s.reverb) * 0.5 } })
        sources.push({ name: stemInfoName(t, String(s.stem_id)), audio: a, chain, gain_db: Number(s.gain_db ?? 0), pan: Number(s.pan ?? 0) })
      }
      if (!sources.length) throw new Friendly('All stems are muted.')
      m('Summing stems...')
      await tick()
      const parts = sources.map((s) => { const x = s.chain?.length ? renderChain(s.audio, s.chain) : D.clone(s.audio); D.scale(x, D.db2lin(s.gain_db ?? 0)); return D.pan(x, s.pan ?? 0) })
      let mixed = D.sum(parts)
      D.scale(mixed, D.db2lin(req.master_gain_db ?? 0))
      if (req.normalize !== false) { const p = D.peak(mixed); if (p > 0) D.scale(mixed, 0.89 / p) }
      mixed = D.limit(mixed, -1)
      const child = newChild(t, mixed, `${t.pub.title} (mix)`, 'mixdown', `Mixdown of ${sources.length} stem(s) in the browser demo.`, { analysis: D.analyze(mixed) })
      return { track: pubOf(child) }
    }),
    export: (b: unknown) => submit('export', async (m) => {
      const req = b as { track_id: string; formats?: string[]; include_stems?: boolean; normalize?: boolean }
      const t = need(req.track_id)
      m('Exporting WAV (the browser demo has no MP3 or FLAC encoder)...')
      await tick()
      let out = t.audio
      if (req.normalize !== false) out = D.masterTo(D.clone(t.audio), -14, -1)
      const files: Record<string, string> = { wav: urlOf(out) }
      if (t.pub.stems.length) { // the demo always bundles the stems, there is no MP3 to offer instead
        const zip = await zipFiles(t.pub.stems.flatMap((s) => { const a = stemAudio.get(s.id); return a ? [{ name: `${s.name.replace(/\s+/g, '_')}.wav`, blob: D.encodeWav(a) }] : [] }))
        files.stems_zip = URL.createObjectURL(zip)
      }
      return { files }
    }),
    job: async <T,>(id: string) => {
      const j = jobs.get(id)
      if (!j) throw new Error('Unknown job')
      return { ...j } as Job<T>
    },
    upload: async (file: File) => {
      const audio = await decodeUpload(file)
      const rec = addTrack({ title: file.name.replace(/\.[^.]+$/, ''), source: 'upload' }, audio)
      return { track: pubOf(rec) }
    },
    track: async (id: string) => pubOf(need(id)),

    hardware: async () => hardwareFx as never,
    engines: async () => enginesFx as never,
    installEngine: (key: string) => submit('install', async () => {
      throw new Friendly(`${key} can't be installed from the browser demo.`, 'Engines are real AI models that run on your own machine. ' + LOCAL_HINT)
    }),
    plugins: async () => ({ plugins: pluginsFx as never }),
    targets: async () => ({ targets: targetsFx as never }),
    presets: async (o = {}) => {
      const counts: Record<string, number> = Object.fromEntries(Object.keys(categoriesFx).map((k) => [k, 0]))
      for (const p of allPresets()) counts[p.category] = (counts[p.category] ?? 0) + 1
      return { presets: listing(o.category, o.q, o.favorites), counts, categories: categoriesFx as Record<string, string> }
    },
    preset: async (id: string) => presetGet(id),
    savePreset: async (p) => ({ preset: saveUserPreset(p) }),
    deletePreset: async (id: string) => {
      const p = presetGet(id)
      if (p.factory) throw new Friendly("Factory presets can't be deleted.")
      LS.set('muser.demo.presets', userPresets().filter((x) => x.id !== id))
      return { deleted: true }
    },
    favoritePreset: async (id: string) => {
      presetGet(id)
      const f = favs(), on = !f.has(id)
      if (on) f.add(id); else f.delete(id)
      LS.set('muser.demo.favs', [...f].sort())
      return { favorite: on }
    },
    importPresets: async (file: File) => {
      let data = await fileOf(file).catch(() => { throw new Friendly('That file is not valid JSON.') }) as unknown
      const d = data as { presets?: unknown }
      if (d && typeof d === 'object' && 'presets' in d) data = d.presets
      const items = Array.isArray(data) ? data : data && typeof data === 'object' ? [data] : []
      if (!items.length) throw new Friendly('That file has no presets in it.')
      const imported = items.slice(0, 500).map((p) => { const { id: _id, ...rest } = p as Preset; void _id; return saveUserPreset(rest).id })
      return { imported }
    },
    exportPresetsUrl: (ids: string[] = []) => {
      const src = ids.length ? allPresets().filter((p) => ids.includes(p.id)) : userPresets()
      const bundle = { format: 'muser-presets', version: 1, exported: Date.now() / 1000, presets: src }
      return URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' }))
    },
    previewPreset: (b) => submit('preview', async (m) => { m('Rendering a preview in the browser...'); await tick(); return previewChain(b as Record<string, unknown>) }),
    vibes: async () => ({
      vibes: listing('genre').filter((p) => p.easy), sliders: (slidersFx as unknown) as never,
      finish: Object.fromEntries(Object.entries(targetsFx).filter(([, v]) => (v as { easy: boolean }).easy)) as never,
    }),
    easyMake: (b) => submit('easy-make', async (m) => {
      const vibe = String(b.vibe ?? '').trim()
      if (!b.genre_id && !vibe) throw new Friendly('Pick a vibe tile or describe the vibe first.')
      const gid = (b.genre_id as string) || matchVibe(vibe)
      const g = presetGet(gid), gen = g.generate!
      m(`Writing a ${g.name} loop with the browser demo synth...`)
      const res = await generateTrack({ prompt: vibe ? `${vibe}, ${gen.prompt}` : gen.prompt, duration_s: Number(b.duration_s ?? gen.duration_s ?? 30), bpm: gen.bpm, title: `${g.name} idea`, genre: gid }, m)
      const root = need(res.track.id)
      root.pub.meta = { ...root.pub.meta, genre_id: gid, easy: true }
      m('Splitting into stems so the sliders can shape each part...')
      await splitTrack(root.pub.id, '4stem', m)
      const macros = Object.fromEntries(['energy', 'vocals', 'bass', 'brightness', 'space'].map((k) => [k, (b[k] as number | null | undefined) ?? (g.macros as Record<string, number>)[k]]))
      m('Mixing with your vibe...')
      const out = await easyRender({ track_id: root.pub.id, genre_id: gid, ...macros }, m)
      return { ...out, root_id: root.pub.id, genre_id: gid, macros, engine: 'demo-synth' }
    }),
    easyRender: (b) => submit('easy-render', (m) => easyRender(b, m)),
    finish: (b) => submit('finish', (m) => finishTrack(b, m)),
    tool: (name, b) => submit(name, (m) => runTool(name, b, m)),
    advancedRender: (b: unknown) => submit('advanced-render', async (m) => {
      const req = b as { track_id: string; stems?: { stem_id: string; chain?: FxItem[]; gain_db?: number; pan?: number; mute?: boolean; solo?: boolean }[]; master_chain?: FxItem[] }
      const t = need(req.track_id)
      const stems = req.stems ?? []
      const any = stems.some((s) => s.solo)
      const sources: Source[] = []
      stems.forEach((s, i) => {
        const info = t.pub.stems.find((x) => x.id === s.stem_id) ?? (stems.length === t.pub.stems.length ? t.pub.stems[i] : undefined)
        const a = info && stemAudio.get(info.id)
        if (!info || !a || s.mute || (any && !s.solo)) return
        sources.push({ name: info.name, audio: a, chain: normalizeChain(s.chain), gain_db: s.gain_db ?? 0, pan: s.pan ?? 0 })
      })
      if (!t.pub.stems.length) sources.push({ name: 'mix', audio: t.audio })
      const audio = await renderMix(sources, normalizeChain(req.master_chain), m)
      const child = newChild(t, audio, `${t.pub.title} (advanced mix)`, 'mixdown', `Advanced render of ${sources.length} source(s) in the browser demo.`, { fx_engines: ['browser-dsp'], analysis: D.analyze(audio) })
      return { track: pubOf(child) }
    }),
    advancedGenerate: (b: unknown) => submit('advanced-generate', async (m) => {
      const r = b as { prompt: string; engine?: string; duration_s?: number; bpm?: number | null; title?: string }
      if (r.engine && !['auto', 'demo-synth', 'acestep'].includes(r.engine)) throw new Friendly(`${r.engine} runs only in the local install.`, LOCAL_HINT)
      return generateTrack({ prompt: r.prompt, duration_s: Math.min(r.duration_s ?? 16, 40), bpm: r.bpm, title: r.title }, m)
    }),
    sepModels: async () => sepFx as never,
    analysis: async (id: string) => {
      const r = need(id)
      r.analysis ??= D.analyze(r.audio)
      return { analysis: r.analysis, meta: { ...r.pub.meta } }
    },
    session: async () => ({ ...session }),
    saveSession: async (b: unknown) => { session = { ...session, ...(b as Record<string, unknown>) }; return { ok: true } },
  }
  return impl
}
const stemInfoName = (t: Rec, id: string) => t.pub.stems.find((s) => s.id === id)?.name ?? 'stem'

export const demoChat = chat
