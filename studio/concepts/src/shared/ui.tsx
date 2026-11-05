import { useMemo } from 'react'
import { ENGINES, FINISH, FIT_LABEL, PRESETS, PRESET_CATS, STEMS, type PresetItem } from './data'
import { actions, useStore } from './store'

export function usePresets() {
  const cat = useStore((s) => s.presetCat)
  const q = useStore((s) => s.presetQuery)
  const favs = useStore((s) => s.favs)
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: PRESETS.length }
    PRESET_CATS.forEach((k) => (c[k] = PRESETS.filter((p) => p.cat === k).length))
    return c
  }, [])
  const items = useMemo(() => {
    const ql = q.trim().toLowerCase()
    return PRESETS.filter((p) => (cat === 'all' || p.cat === cat) && (!ql || p.name.toLowerCase().includes(ql) || p.cat.includes(ql)))
      .sort((a, b) => Number(favs.includes(b.id)) - Number(favs.includes(a.id)))
  }, [cat, q, favs])
  return { cat, q, favs, counts, items }
}
export const CAT_LABEL: Record<string, string> = { all: 'All', genre: 'Genre', mix: 'Mix', vocal: 'Vocal', fx: 'FX', master: 'Master' }

export function GenerateForm() {
  const g = useStore((s) => s.gen)
  const inst = useStore((s) => s.engineInstalled)
  const engs = ENGINES.filter((e) => e.status !== 'no')
  return (
    <div className="f-form">
      <label className="f-field"><span className="f-label">Engine</span>
        <select className="f-select" value={g.engine} onChange={(e) => actions.gen({ engine: e.target.value })}>
          {engs.map((e) => <option key={e.key}>{e.name}{inst[e.key] ? '' : ' (not installed)'}</option>)}
        </select></label>
      <label className="f-field"><span className="f-label">Prompt</span>
        <textarea className="f-input" rows={2} value={g.prompt} onChange={(e) => actions.gen({ prompt: e.target.value })} /></label>
      <div className="f-row">
        <label className="f-field"><span className="f-label">Length (s)</span><input className="f-input" type="number" min={8} max={180} value={g.length} onChange={(e) => actions.gen({ length: Number(e.target.value) })} /></label>
        <label className="f-field"><span className="f-label">BPM</span><input className="f-input" type="number" min={40} max={220} value={g.bpm} onChange={(e) => actions.gen({ bpm: Number(e.target.value) })} /></label>
        <label className="f-field"><span className="f-label">Key</span>
          <select className="f-select" value={g.key} onChange={(e) => actions.gen({ key: e.target.value })}>{['auto', 'A minor', 'C major', 'D minor', 'F major', 'G minor'].map((k) => <option key={k}>{k}</option>)}</select></label>
      </div>
      <button className="f-btn primary" onClick={() => void actions.runGenerate()}>Generate</button>
      <p className="f-note">Direct generate skips the agent. Demo synth is used when no model is installed.</p>
    </div>
  )
}
export function SeparateForm() {
  const s = useStore((x) => x.sep)
  const split = useStore((x) => x.split)
  return (
    <div className="f-form">
      <label className="f-field"><span className="f-label">Model</span>
        <select className="f-select" value={s.model} onChange={(e) => actions.sep({ model: e.target.value })}>
          {['Roformer 4 stem', 'Demucs htdemucs', 'MDX23C 2 stem', 'Band split (fallback)'].map((m) => <option key={m}>{m}</option>)}</select></label>
      <div className="f-field"><span className="f-label">Stems</span>
        <div className="f-seg">{[2, 4, 6].map((n) => <button key={n} className={s.stems === n ? 'on' : ''} onClick={() => actions.sep({ stems: n })}>{n}</button>)}</div></div>
      <button className="f-btn primary" onClick={() => void actions.runSeparate()}>Separate</button>
      <p className="f-note">{split ? 'Split complete: Drums, Bass, Keys, Voice.' : 'Splits the current mix into stems you can shape one by one.'}</p>
    </div>
  )
}
export function MasterForm() {
  const t = useStore((s) => s.masterTarget)
  const m = useStore((s) => s.measured)
  return (
    <div className="f-form">
      <div className="f-field"><span className="f-label">Target</span>
        <div className="f-seg wrap">{FINISH.map((f) => <button key={f.key} className={t === f.key ? 'on' : ''} onClick={() => actions.masterTarget(f.key)}>{f.label}</button>)}</div></div>
      <div className="f-kv"><span>Loudness</span><b>{FINISH.find((f) => f.key === t)!.lufs} LUFS</b></div>
      <div className="f-kv"><span>True peak</span><b>{FINISH.find((f) => f.key === t)!.tp} dBTP</b></div>
      <div className="f-kv"><span>Measured</span><b>{m ? `${m.lufs.toFixed(1)} LUFS · ${m.tp.toFixed(1)} dBTP` : 'not yet'}</b></div>
      <button className="f-btn primary" onClick={() => void actions.runMaster()}>Master</button>
    </div>
  )
}
export function ABForm() {
  const ab = useStore((s) => s.ab)
  return (
    <div className="f-form">
      <div className="f-field"><span className="f-label">Compare</span>
        <div className="f-seg">{(['A', 'B'] as const).map((k) => <button key={k} className={ab === k ? 'on' : ''} onClick={() => actions.setAB(k)}>{k === 'A' ? 'A  Original' : 'B  Your mix'}</button>)}</div></div>
      <p className="f-note">A plays the track with the sliders at neutral and no chain changes. B is everything you have shaped. Press the same key to flip while it plays.</p>
    </div>
  )
}
export function EngineRows({ onlyHeavy = false }: { onlyHeavy?: boolean }) {
  const inst = useStore((s) => s.engineInstalled)
  return (
    <>
      {ENGINES.filter((e) => !onlyHeavy || e.tier === 'heavy').map((e) => (
        <div className="eng" key={e.key} data-fit={e.status}>
          <span className="eng-fit" data-fit={e.status}>{FIT_LABEL[e.status]}</span>
          <span className="eng-name">{e.name}</span>
          <span className="eng-role">{e.role}</span>
          <span className="eng-vram">{e.vram}{e.note ? ` · ${e.note}` : ''}</span>
          {inst[e.key]
            ? <span className="eng-state">Installed</span>
            : <button className="eng-install" onClick={() => actions.install(e.key)}>{e.status === 'no' ? 'Install anyway' : 'Install'}</button>}
        </div>
      ))}
    </>
  )
}
export const stemName = (id: string) => STEMS.find((s) => s.id === id)?.name ?? id
export type { PresetItem }

export const RANGES = { vol: [-24, 6], pan: [-1, 1], low: [-12, 12], mid: [-12, 12], high: [-12, 12], comp: [0, 100], verb: [0, 100], room: [0, 100] } as const
export type PK = keyof typeof RANGES
export const PK_LIST = Object.keys(RANGES) as PK[]
export const PARAM_NAME: Record<PK, string> = { vol: 'Level', pan: 'Pan', low: 'Low', mid: 'Mid', high: 'High', comp: 'Comp', verb: 'Verb', room: 'Room' }
export const isBip = (k: PK) => k === 'pan' || k === 'low' || k === 'mid' || k === 'high'
export const fmtParam = (k: PK, v: number) => k === 'pan' ? (Math.abs(v) < 0.03 ? 'C' : `${v < 0 ? 'L' : 'R'}${Math.round(Math.abs(v) * 100)}`)
  : k === 'comp' || k === 'verb' || k === 'room' ? `${Math.round(v)}` : `${v > 0 && k !== 'vol' ? '+' : ''}${v.toFixed(1)}`
export const frac = (k: PK, v: number) => (v - RANGES[k][0]) / (RANGES[k][1] - RANGES[k][0])
export const unfrac = (k: PK, f: number) => RANGES[k][0] + f * (RANGES[k][1] - RANGES[k][0])
export const homeVal = (k: PK) => (isBip(k) ? 0 : k === 'vol' ? 0 : 0)

import { useEffect, useState, type RefObject } from 'react'
export function useSize(ref: RefObject<HTMLElement | null>) {
  const [s, set] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current!
    const ro = new ResizeObserver(() => set({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el); set({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [ref])
  return s
}
