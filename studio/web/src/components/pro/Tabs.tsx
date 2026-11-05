import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import type { EngineInfo, FinishTarget, FxItem, PluginSpec, Preset, Track } from '../../types'
import { Player } from '../Player'
import { ChainEditor } from './ChainEditor'

export function roleFor(name: string): string {
  const n = name.toLowerCase()
  if (/vocal|vox|voice/.test(n)) return 'vocals'
  if (/drum|kick|snare|perc/.test(n)) return 'drums'
  if (/bass|808|sub/.test(n)) return 'bass'
  if (/guitar/.test(n)) return 'guitar'
  if (/lead|melody|synth/.test(n)) return 'lead'
  if (/chord|key|piano|pad|other|instrumental/.test(n)) return 'keys'
  return 'other'
}

export type RunFn = <T>(label: string, start: () => Promise<{ job_id: string }>) => Promise<T | null>
export type Common = { run: RunFn; onTrack: (t: Track) => void; toast: (t: string, k?: 'info' | 'error' | 'ok') => void }

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <em className="muted">{hint}</em>}
    </label>
  )
}

export function GenerateTab({ engines, run, onTrack, toast }: Common & { engines: EngineInfo[] }) {
  const gens = engines.filter((e) => e.tasks.includes('generate'))
  const [p, setP] = useState({ engine: 'auto', prompt: 'warm lo-fi hip hop, dusty drums, jazzy rhodes', lyrics: '', duration_s: 30, steps: 32, guidance: 7, seed: -1, temperature: 1, bpm: 90 })
  const eng = gens.find((g) => g.key === p.engine)
  const set = (k: keyof typeof p, v: string | number) => setP((x) => ({ ...x, [k]: v }))
  return (
    <div className="pro-form">
      <Field label="Model" hint={eng ? `${eng.weights_license}${eng.commercial !== 'yes' ? ` · ${eng.commercial === 'no' ? 'personal use only' : 'commercial: conditions apply'}` : ''}${eng.untested_here ? ' · adapter untested here' : ''}${eng.fit && !eng.fit.recommended ? ` · ${eng.fit.label}` : ''}` : 'Picks the best installed model for your hardware'}>
        <select className="select" value={p.engine} onChange={(e) => set('engine', e.target.value)}>
          <option value="auto">Auto (recommended)</option>
          {gens.map((g) => (
            <option key={g.key} value={g.key} disabled={!g.health.installed && g.key !== 'demo-synth'}>
              {g.name}{g.health.installed ? '' : ' (not installed)'}{g.commercial === 'no' ? ' · NC' : ''}{g.fit && g.fit.status === 'too-big' ? ' · not for your card' : g.fit?.status === 'tight' ? ' · tight fit' : ''}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Prompt"><textarea rows={2} value={p.prompt} onChange={(e) => set('prompt', e.target.value)} /></Field>
      <Field label="Lyrics" hint="Optional. Use [verse] and [chorus] tags."><textarea rows={3} value={p.lyrics} onChange={(e) => set('lyrics', e.target.value)} /></Field>
      <div className="field-row">
        <Field label="Duration (s)"><input className="num" type="number" min={4} max={285} value={p.duration_s} onChange={(e) => set('duration_s', Number(e.target.value))} /></Field>
        <Field label="BPM"><input className="num" type="number" min={40} max={220} value={p.bpm} onChange={(e) => set('bpm', Number(e.target.value))} /></Field>
        <Field label="Steps"><input className="num" type="number" min={1} max={500} value={p.steps} onChange={(e) => set('steps', Number(e.target.value))} /></Field>
        <Field label="Guidance"><input className="num" type="number" step={0.5} min={0} max={30} value={p.guidance} onChange={(e) => set('guidance', Number(e.target.value))} /></Field>
        <Field label="Temperature"><input className="num" type="number" step={0.05} min={0.1} max={2} value={p.temperature} onChange={(e) => set('temperature', Number(e.target.value))} /></Field>
        <Field label="Seed" hint="-1 = random"><input className="num" type="number" value={p.seed} onChange={(e) => set('seed', Number(e.target.value))} /></Field>
      </div>
      <button className="btn pri" disabled={!p.prompt.trim()} onClick={async () => {
        const r = await run<{ track: Track; engine: string }>('Generating...', () => api.advancedGenerate(p))
        if (r) {
          onTrack(r.track)
          toast(`Generated with ${r.engine}.`, 'ok')
        }
      }}>Generate</button>
    </div>
  )
}

export function SeparateTab({ track, engines, models, run, onTrack, toast }: Common & { track: Track | null; engines: EngineInfo[]; models: { file: string; label: string; stems: number; gpu: boolean }[] }) {
  const seps = engines.filter((e) => e.tasks.includes('separate'))
  const [engine, setEngine] = useState('auto')
  const [mode, setMode] = useState<'4stem' | '2stem'>('4stem')
  const [model, setModel] = useState('')
  const list = models.filter((m) => (mode === '4stem' ? m.stems >= 4 : m.stems === 2))
  return (
    <div className="pro-form">
      <div className="field-row">
        <Field label="Engine">
          <select className="select" value={engine} onChange={(e) => setEngine(e.target.value)}>
            <option value="auto">Auto (best installed)</option>
            {seps.map((s) => <option key={s.key} value={s.key} disabled={!s.health.installed}>{s.name}{s.health.installed ? '' : ' (not installed)'}</option>)}
          </select>
        </Field>
        <Field label="Stems">
          <select className="select" value={mode} onChange={(e) => { setMode(e.target.value as '4stem' | '2stem'); setModel('') }}>
            <option value="4stem">4 stems (drums, bass, vocals, other)</option>
            <option value="2stem">2 stems (vocals, instrumental)</option>
          </select>
        </Field>
        <Field label="Model" hint="Audio Separator models download once on first use">
          <select className="select" value={model} onChange={(e) => setModel(e.target.value)} disabled={engine !== 'audio-separator' && engine !== 'auto'}>
            <option value="">Default for this mode</option>
            {list.map((m) => <option key={m.file} value={m.file}>{m.label}{m.gpu ? ' (GPU)' : ''}</option>)}
          </select>
        </Field>
      </div>
      <button className="btn pri" disabled={!track} onClick={async () => {
        const r = await run<{ track: Track; note: string }>('Separating...', () => api.tool('split', { track_id: track!.id, mode, engine, model: model || null }))
        if (r) {
          onTrack(r.track)
          toast(r.note, 'ok')
        }
      }}>Split</button>
    </div>
  )
}

export function MasterTab({ track, targets, plugins, run, onTrack, toast }: Common & { track: Track | null; targets: Record<string, FinishTarget>; plugins: Record<string, PluginSpec> }) {
  const [target, setTarget] = useState('spotify')
  const [lufs, setLufs] = useState<number | ''>('')
  const [tp, setTp] = useState<number | ''>('')
  const [chain, setChain] = useState<FxItem[]>([])
  const [presetId, setPresetId] = useState('')
  const [masters, setMasters] = useState<Preset[]>([])
  const [report, setReport] = useState<Record<string, unknown> | null>(null)
  useEffect(() => {
    api.presets({ category: 'master' }).then((r) => setMasters(r.presets)).catch(() => undefined)
  }, [])
  const t = targets[target]
  return (
    <div className="pro-form master-tab">
      <div className="field-row">
        <Field label="Target" hint={t?.note}>
          <select className="select" value={target} onChange={(e) => setTarget(e.target.value)}>
            {Object.entries(targets).map(([k, v]) => <option key={k} value={k}>{v.label} ({v.lufs} LUFS, {v.true_peak_db} dBTP)</option>)}
          </select>
        </Field>
        <Field label="Custom LUFS" hint="Blank = target"><input className="num" type="number" step={0.5} min={-30} max={-5} value={lufs} onChange={(e) => setLufs(e.target.value === '' ? '' : Number(e.target.value))} /></Field>
        <Field label="Ceiling dBTP" hint="Blank = target"><input className="num" type="number" step={0.1} min={-6} max={0} value={tp} onChange={(e) => setTp(e.target.value === '' ? '' : Number(e.target.value))} /></Field>
        <Field label="Start from preset">
          <select className="select" value={presetId} onChange={async (e) => {
            setPresetId(e.target.value)
            if (!e.target.value) return
            const p = await api.preset(e.target.value)
            if (typeof p.master === 'object' && p.master) {
              setChain(p.master.chain)
              setTarget(p.master.target)
            }
          }}>
            <option value="">Platform default</option>
            {masters.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </Field>
      </div>
      <ChainEditor chain={chain} plugins={plugins} title="Mastering chain (the final limiter and loudness stage are automatic)" onChange={(c) => setChain(c)} />
      <button className="btn pri" disabled={!track} onClick={async () => {
        const r = await run<{ track: Track; report: Record<string, unknown> }>('Mastering...', () => api.finish({
          track_id: track!.id, target, chain: chain.length || presetId ? chain : null, lufs: lufs === '' ? null : lufs, true_peak_db: tp === '' ? null : tp,
        }))
        if (r) {
          onTrack(r.track)
          setReport(r.report)
          toast(`Mastered: ${r.report.lufs} LUFS, ${r.report.true_peak_db} dBTP.`, 'ok')
        }
      }}>Master</button>
      {report && (
        <div className="report">
          {['input_lufs', 'lufs', 'goal_lufs', 'true_peak_db', 'goal_true_peak_db', 'gain_db', 'within_tolerance', 'fx_engine'].map((k) => (
            <div key={k}><span className="muted">{k.replace(/_/g, ' ')}</span><strong>{String(report[k])}</strong></div>
          ))}
        </div>
      )}
    </div>
  )
}

export function ABTab({ track, tracks }: { track: Track | null; tracks: Track[] }) {
  const [a, setA] = useState<string>('')
  const [b, setB] = useState<string>('')
  const [which, setWhich] = useState<'A' | 'B'>('B')
  const [matched, setMatched] = useState(true)
  const [lufs, setLufs] = useState<Record<string, number | null>>({})
  const els = useRef<Record<'A' | 'B', HTMLAudioElement | null>>({ A: null, B: null })
  useEffect(() => {
    if (!track) return
    setB(track.id)
    setA(track.parent_id && tracks.some((t) => t.id === track.parent_id) ? track.parent_id : tracks.find((t) => t.id !== track.id)?.id ?? track.id)
  }, [track, tracks])
  const ta = tracks.find((t) => t.id === a)
  const tb = tracks.find((t) => t.id === b)
  useEffect(() => {
    for (const id of [a, b]) if (id && !(id in lufs)) api.analysis(id).then((r) => setLufs((x) => ({ ...x, [id]: r.analysis.lufs }))).catch(() => undefined)
  }, [a, b, lufs])
  const gains = useMemo(() => {
    const la = lufs[a] ?? null
    const lb = lufs[b] ?? null
    if (!matched || la == null || lb == null) return { A: 1, B: 1 }
    const lo = Math.min(la, lb)
    return { A: 10 ** ((lo - la) / 20), B: 10 ** ((lo - lb) / 20) }
  }, [lufs, a, b, matched])
  useEffect(() => {
    if (els.current.A) els.current.A.volume = Math.min(1, gains.A)
    if (els.current.B) els.current.B.volume = Math.min(1, gains.B)
  }, [gains])
  const flip = () => {
    const from = els.current[which]
    const to = els.current[which === 'A' ? 'B' : 'A']
    const next = which === 'A' ? 'B' : 'A'
    if (from && to) {
      to.currentTime = Math.min(from.currentTime, to.duration || from.currentTime)
      if (!from.paused) {
        from.pause()
        void to.play()
      }
    }
    setWhich(next)
  }
  if (!track) return <p className="muted pad-s">Load a track to compare versions.</p>
  return (
    <div className="ab">
      <div className="field-row">
        <Field label="A"><select className="select" value={a} onChange={(e) => setA(e.target.value)}>{tracks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}</select></Field>
        <Field label="B"><select className="select" value={b} onChange={(e) => setB(e.target.value)}>{tracks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}</select></Field>
        <label className="check"><input type="checkbox" checked={matched} onChange={(e) => setMatched(e.target.checked)} /> Loudness matched (fair compare)</label>
        <button className="btn pri" onClick={flip}>Switch to {which === 'A' ? 'B' : 'A'}</button>
      </div>
      <div className={`ab-row ${which === 'A' ? 'on' : ''}`}>
        <span className="ab-tag">A</span>
        {ta && <Player url={ta.url} title={ta.title} sub={`${lufs[a]?.toFixed(1) ?? '-'} LUFS`} compact audioRef={(el) => (els.current.A = el)} />}
      </div>
      <div className={`ab-row ${which === 'B' ? 'on' : ''}`}>
        <span className="ab-tag">B</span>
        {tb && <Player url={tb.url} title={tb.title} sub={`${lufs[b]?.toFixed(1) ?? '-'} LUFS`} compact audioRef={(el) => (els.current.B = el)} />}
      </div>
    </div>
  )
}
