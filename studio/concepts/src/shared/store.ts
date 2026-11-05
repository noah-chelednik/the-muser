import { useSyncExternalStore } from 'react'
import { ENGINES, FINISH, MACROS, NEUTRAL, PRESETS, STEMS, TOOLS, VIBES, vibeById, type FinishKey, type MacroKey, type Macros, type PresetItem, type StemId, type ToolKey } from './data'
import { engine, defaultStem, type StemParams } from './engine'

export type Phase = 'idle' | 'making' | 'ready'
export type AdvTab = 'chains' | 'generate' | 'separate' | 'master' | 'presets' | 'ab'
export interface Version { label: string; macros: Macros; vibeId: string | null }
export interface Toast { id: number; text: string; kind: 'info' | 'ok' | 'error' }
export interface State {
  mode: 'easy' | 'advanced'
  vibeId: string | null
  hoverVibe: string | null
  prompt: string
  phase: Phase
  progress: number
  stage: string
  macros: Macros
  selMacro: MacroKey
  playing: boolean
  finish: FinishKey | null
  measured: { lufs: number; tp: number; target: FinishKey } | null
  exported: { name: string; size: string }[] | null
  busy: string
  split: boolean
  versions: Version[]
  vIdx: number
  stems: Record<StemId, StemParams>
  chainOn: Record<StemId, boolean[]>
  chainPreset: Record<StemId, string>
  selStem: StemId
  advTab: AdvTab
  ab: 'A' | 'B'
  favs: string[]
  presetCat: 'all' | PresetItem['cat']
  presetQuery: string
  previewId: string | null
  enginesOpen: boolean
  helpOpen: boolean
  engineInstalled: Record<string, boolean>
  toasts: Toast[]
  midiReady: boolean
  gen: { engine: string; length: number; bpm: number; key: string; prompt: string }
  sep: { model: string; stems: number }
  masterTarget: FinishKey
}

const initStems = () => ({ drums: defaultStem(), bass: defaultStem(), keys: defaultStem(), voice: defaultStem() })
const initChain = () => ({ drums: [true, true, true, true], bass: [true, true, true], keys: [true, true, true], voice: [true, true, true, true] } as Record<StemId, boolean[]>)

let state: State = {
  mode: 'easy', vibeId: null, hoverVibe: null, prompt: '', phase: 'idle', progress: 0, stage: '',
  macros: { ...NEUTRAL }, selMacro: 'energy', playing: false, finish: null, measured: null, exported: null, busy: '', split: false,
  versions: [], vIdx: -1, stems: initStems(), chainOn: initChain(),
  chainPreset: { drums: 'Punchy Drums', bass: 'Warm Bass', keys: 'Lush Keys', voice: 'Soft Indie Vocal' },
  selStem: 'drums', advTab: 'presets', ab: 'B', favs: ['genre/lo-fi-chill', 'mix/dusty-drums', 'master/spotify-master'], presetCat: 'all', presetQuery: '', previewId: null,
  enginesOpen: false, helpOpen: false, engineInstalled: Object.fromEntries(ENGINES.map((e) => [e.key, e.installed])), toasts: [], midiReady: false,
  gen: { engine: 'ACE-Step 1.5', length: 28, bpm: 78, key: 'auto', prompt: 'lo-fi hip hop, jazzy keys, vinyl crackle' },
  sep: { model: 'Roformer 4 stem', stems: 4 }, masterTarget: 'spotify',
}
const subs = new Set<() => void>()
const set = (patch: Partial<State>) => { state = { ...state, ...patch }; subs.forEach((s) => s()) }
export const getState = () => state
export function useStore<T>(sel: (s: State) => T): T {
  const get = () => sel(state)
  return useSyncExternalStore((cb) => { subs.add(cb); return () => subs.delete(cb) }, get, get)
}

/** One global 'interaction pulse' for visual FX (chromatic aberration bursts etc). */
export const fx = { pulse: 0, hit(a = 0.5) { this.pulse = Math.min(1.5, this.pulse + a) } }

let tid = 0
export const toast = (text: string, kind: Toast['kind'] = 'info') => {
  const id = ++tid
  set({ toasts: [...state.toasts.slice(-3), { id, text, kind }] })
  window.setTimeout(() => set({ toasts: state.toasts.filter((t) => t.id !== id) }), 3800)
}
const wait = (ms: number) => new Promise((r) => window.setTimeout(r, ms))
const pushVersion = (label: string) => {
  const v: Version = { label, macros: { ...state.macros }, vibeId: state.vibeId }
  const versions = [...state.versions.slice(0, state.vIdx + 1), v].slice(-40)
  set({ versions, vIdx: versions.length - 1 })
}
const effMacros = () => (state.ab === 'A' ? NEUTRAL : state.macros)

export const actions = {
  setMode(mode: State['mode']) { fx.hit(0.8); set({ mode }) },
  toggleMode() { actions.setMode(state.mode === 'easy' ? 'advanced' : 'easy') },
  hoverVibe(id: string | null) { if (id !== state.hoverVibe) set({ hoverVibe: id }) },
  pickVibe(id: string) {
    const v = vibeById(id); if (!v) return
    fx.hit(0.9)
    engine.setVibe(v)
    set({ vibeId: id, macros: { ...v.macros }, finish: null, measured: null, exported: null })
    engine.setMacros(effMacros())
    if (state.phase === 'ready') pushVersion(`Vibe: ${v.name}`)
  },
  stepVibe(d: number) {
    const i = state.vibeId ? VIBES.findIndex((v) => v.id === state.vibeId) : -1
    actions.pickVibe(VIBES[(i + d + VIBES.length) % VIBES.length].id)
  },
  setPrompt(prompt: string) { set({ prompt }) },
  async make() {
    if (state.phase === 'making') return
    let id = state.vibeId
    if (!id && !state.prompt.trim()) { toast('Pick a vibe or describe one first.', 'info'); return }
    if (!id) {
      const p = state.prompt.toLowerCase()
      id = VIBES.find((v) => p.includes(v.name.toLowerCase().split(' ')[0]))?.id ?? (p.includes('rain') || p.includes('warm') || p.includes('dust') ? 'lo-fi-chill' : 'synthwave')
      actions.pickVibe(id)
    }
    fx.hit(1.4)
    const v = vibeById(id)!
    engine.setVibe(v); engine.setMacros(effMacros())
    set({ phase: 'making', progress: 0, stage: 'Reading the vibe', finish: null, measured: null, exported: null })
    const stages = ['Reading the vibe', 'Writing drums', 'Writing bass', 'Laying keys', 'Writing the voice', 'Mixing down']
    for (let i = 0; i < stages.length; i++) {
      set({ stage: stages[i] })
      for (let k = 0; k < 8; k++) { set({ progress: (i * 8 + k + 1) / (stages.length * 8) }); engine.excite = 0.3 + 0.7 * Math.sin(((i * 8 + k) / 48) * Math.PI); await wait(52) }
    }
    engine.excite = 0
    set({ phase: 'ready', progress: 1, stage: '', versions: [], vIdx: -1, split: false })
    pushVersion('Made it')
    engine.seek(0)
    void actions.play()
    toast('Your track is ready. Shape it with the sliders, then finish it.', 'ok')
  },
  async play() { await engine.play(); set({ playing: true }) },
  pause() { engine.pause(); set({ playing: false }) },
  toggle() { if (state.playing) actions.pause(); else void actions.play() },
  setMacro(k: MacroKey, v: number) {
    set({ macros: { ...state.macros, [k]: Math.max(0, Math.min(100, Math.round(v))) }, selMacro: k })
    engine.setMacros(effMacros())
  },
  commitMacros() { if (state.phase === 'ready') { pushVersion('Shaped'); } },
  selMacro(k: MacroKey) { set({ selMacro: k }) },
  nudge(d: number) { actions.setMacro(state.selMacro, state.macros[state.selMacro] + d); },
  resetMacros() {
    const v = vibeById(state.vibeId); set({ macros: { ...(v?.macros ?? NEUTRAL) } }); engine.setMacros(effMacros()); fx.hit(0.6)
  },
  jump(i: number) {
    const v = state.versions[i]; if (!v) return
    set({ vIdx: i, macros: { ...v.macros } }); engine.setMacros(effMacros()); fx.hit(0.5)
  },
  undo() { if (state.vIdx > 0) actions.jump(state.vIdx - 1) },
  redo() { if (state.vIdx < state.versions.length - 1) actions.jump(state.vIdx + 1) },
  async finishFor(k: FinishKey) {
    if (state.phase !== 'ready' || state.busy) { if (state.phase !== 'ready') toast('Make a track first.'); return }
    const t = FINISH.find((x) => x.key === k)!
    fx.hit(1)
    set({ busy: `Finishing for ${t.label}`, finish: k })
    await wait(1100)
    const m = { lufs: t.lufs - 0.1, tp: t.tp - 0.3, target: k }
    set({ busy: '', measured: m, exported: null })
    pushVersion(`Finished for ${t.label}`)
    toast(`Finished: ${m.lufs.toFixed(1)} LUFS, ${m.tp.toFixed(1)} dBTP.`, 'ok')
  },
  cycleFinish() { const i = FINISH.findIndex((f) => f.key === state.finish); void actions.finishFor(FINISH[(i + 1) % FINISH.length].key) },
  async doExport() {
    if (state.phase !== 'ready' || state.busy) { if (state.phase !== 'ready') toast('Make a track first.'); return }
    fx.hit(1)
    set({ busy: 'Exporting' })
    await wait(1200)
    const base = `${vibeById(state.vibeId)?.id ?? 'track'}-idea${state.finish ? '-' + state.finish : ''}`
    set({ busy: '', exported: [{ name: base + '.wav', size: '4.9 MB' }, { name: base + '.mp3', size: '1.1 MB' }] })
    toast(state.finish ? 'Exported at your finished loudness.' : 'Exported. Tip: finish for a platform first.', 'ok')
  },
  async tool(k: ToolKey) {
    if (state.phase !== 'ready' || state.busy) { if (state.phase !== 'ready') toast('Make a track first.'); return }
    const t = TOOLS.find((x) => x.key === k)!
    fx.hit(1)
    set({ busy: t.busy })
    await wait(1500)
    set({ busy: '', split: k === 'split' ? true : state.split, midiReady: k === 'midi' ? true : state.midiReady })
    pushVersion(t.label)
    toast(t.done, 'ok')
  },
  setStem(id: StemId, patch: Partial<StemParams>) {
    set({ stems: { ...state.stems, [id]: { ...state.stems[id], ...patch } }, selStem: id })
    engine.setStem(id, patch)
  },
  soloExclusive(id: StemId) { actions.setStem(id, { solo: !state.stems[id].solo }) },
  toggleChain(id: StemId, i: number) {
    const a = [...state.chainOn[id]]; a[i] = !a[i]; set({ chainOn: { ...state.chainOn, [id]: a } }); fx.hit(0.4)
  },
  selStem(id: StemId) { set({ selStem: id }) },
  advTab(t: AdvTab) { fx.hit(0.5); set({ advTab: t }) },
  setAB(ab: 'A' | 'B') { set({ ab }); engine.setMacros(ab === 'A' ? NEUTRAL : state.macros); fx.hit(0.7) },
  toggleFav(id: string) { set({ favs: state.favs.includes(id) ? state.favs.filter((f) => f !== id) : [...state.favs, id] }) },
  presetCat(c: State['presetCat']) { set({ presetCat: c }) },
  presetQuery(q: string) { set({ presetQuery: q }) },
  preview(id: string) { set({ previewId: state.previewId === id ? null : id }); fx.hit(0.5); window.setTimeout(() => state.previewId === id && set({ previewId: null }), 2200) },
  applyPreset(p: PresetItem) {
    fx.hit(1)
    if (p.cat === 'genre') {
      const v = VIBES.find((x) => x.name === p.name); if (v) actions.pickVibe(v.id)
      toast(`Applied ${p.name} to the whole track.`, 'ok'); return
    }
    if (p.cat === 'master') { toast(`Master chain set: ${p.name}.`, 'ok'); return }
    const id = state.selStem
    let h = 0; for (const c of p.name) h = (h * 31 + c.charCodeAt(0)) >>> 0
    const patch = { low: ((h % 9) - 4), mid: (((h >> 3) % 7) - 3), high: (((h >> 5) % 9) - 4), comp: 20 + (h % 50), verb: (h >> 2) % 50 }
    actions.setStem(id, patch)
    set({ chainPreset: { ...state.chainPreset, [id]: p.name } })
    pushVersion(`${p.name} on ${STEMS.find((s) => s.id === id)!.name}`)
    toast(`${p.name} applied to ${STEMS.find((s) => s.id === id)!.name}.`, 'ok')
  },
  engines(open: boolean) { fx.hit(0.6); set({ enginesOpen: open }) },
  help(open: boolean) { set({ helpOpen: open }) },
  install(key: string) { set({ engineInstalled: { ...state.engineInstalled, [key]: true } }); toast('Installed. Ready to use.', 'ok') },
  gen(patch: Partial<State['gen']>) { set({ gen: { ...state.gen, ...patch } }) },
  sep(patch: Partial<State['sep']>) { set({ sep: { ...state.sep, ...patch } }) },
  masterTarget(k: FinishKey) { set({ masterTarget: k }) },
  async runGenerate() { toast('Generating with ' + state.gen.engine + '...'); await actions.make() },
  async runSeparate() { await actions.tool('split') },
  async runMaster() { await actions.finishFor(state.masterTarget) },
  /** URL driven demo states for screenshots and demos */
  demo(s: string) {
    const v = vibeById('lo-fi-chill')!
    engine.setVibe(v)
    set({ vibeId: v.id, macros: { ...v.macros }, phase: 'ready', progress: 1, versions: [], vIdx: -1, prompt: 'rainy night, warm and dusty' })
    pushVersion('Made it')
    set({ macros: { energy: 42, vocals: 40, bass: 58, brightness: 34, space: 66 } }); pushVersion('Shaped'); engine.setMacros(state.macros)
    engine.beat = 17.2
    if (s.includes('fin')) {
      set({ finish: 'spotify', measured: { lufs: -14.1, tp: -1.3, target: 'spotify' } }); pushVersion('Finished for Spotify')
      set({ exported: [{ name: 'lo-fi-chill-idea-spotify.wav', size: '4.9 MB' }, { name: 'lo-fi-chill-idea-spotify.mp3', size: '1.1 MB' }] })
    }
    if (s.includes('split')) { set({ split: true }); pushVersion('Split stems') }
    if (s.includes('eng')) set({ enginesOpen: true })
    void actions.play()
  },
}
export { MACROS }
