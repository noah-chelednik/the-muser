import { useState } from 'react'
import { audio } from '../../audio/engine'
import { bufferToWav, download, safeName } from '../../audio/wav'
import { zipFiles } from '../../demo/zip'
import { MASTER_CH, useStudio, type Channel } from '../../studio/StudioContext'
import { DEFAULT_STEM, type StemParams } from '../../types'
import { Knob } from '../Knob'

type K = { key: keyof StemParams; label: string; min: number; max: number; def: number; step?: number; bipolar?: boolean; fmt?: (v: number) => string }
const db = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)} dB`
const pc = (v: number) => `${Math.round(v * 100)}%`
const hz = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${Math.round(v)}`)

type Section = { id: string; title: string; byp: keyof StemParams; knobs: K[] }
const SECTIONS: Section[] = [
  { id: 'eq', title: 'EQ and parametric', byp: 'byp_eq', knobs: [
    { key: 'eq_low_db', label: 'Low', min: -12, max: 12, def: 0, bipolar: true, fmt: db },
    { key: 'eq_mid_db', label: 'Mid', min: -12, max: 12, def: 0, bipolar: true, fmt: db },
    { key: 'eq_high_db', label: 'High', min: -12, max: 12, def: 0, bipolar: true, fmt: db },
    { key: 'peq_freq', label: 'P.Freq', min: 80, max: 12000, def: 2500, step: 10, fmt: hz },
    { key: 'peq_gain', label: 'P.Gain', min: -15, max: 15, def: 0, bipolar: true, fmt: db },
    { key: 'peq_q', label: 'P.Q', min: 0.3, max: 10, def: 1.2, fmt: (v) => v.toFixed(1) },
  ] },
  { id: 'comp', title: 'Compressor', byp: 'byp_comp', knobs: [{ key: 'comp', label: 'Amount', min: 0, max: 1, def: 0, fmt: pc }] },
  { id: 'sat', title: 'Saturation', byp: 'byp_sat', knobs: [{ key: 'sat', label: 'Drive', min: 0, max: 1, def: 0, fmt: pc }] },
  { id: 'filter', title: 'Filter sweep', byp: 'byp_filter', knobs: [
    { key: 'filter', label: 'Sweep', min: -1, max: 1, def: 0, bipolar: true, fmt: (v) => (Math.abs(v) < 0.02 ? 'off' : v < 0 ? `LP ${pc(-v)}` : `HP ${pc(v)}`) },
    { key: 'filter_q', label: 'Reso', min: 0.3, max: 12, def: 0.8, fmt: (v) => v.toFixed(1) },
  ] },
  { id: 'delay', title: 'Delay', byp: 'byp_delay', knobs: [
    { key: 'delay_mix', label: 'Mix', min: 0, max: 1, def: 0, fmt: pc },
    { key: 'delay_time', label: 'Time', min: 0.05, max: 1, def: 0.375, fmt: (v) => `${Math.round(v * 1000)} ms` },
    { key: 'delay_fb', label: 'Feedback', min: 0, max: 0.9, def: 0.35, fmt: pc },
  ] },
  { id: 'verb', title: 'Reverb', byp: 'byp_verb', knobs: [
    { key: 'reverb', label: 'Mix', min: 0, max: 1, def: 0, fmt: pc },
    { key: 'room', label: 'Room', min: 0, max: 1, def: 0.5, fmt: pc },
  ] },
  { id: 'width', title: 'Stereo width', byp: 'byp_width', knobs: [{ key: 'width', label: 'Width', min: 0, max: 2, def: 1, fmt: (v) => `${Math.round(v * 100)}%` }] },
]

const KEEP: (keyof StemParams)[] = ['gain_db', 'pan', 'mute', 'solo']
const SCENES: { name: string; set: Partial<StemParams> }[] = [
  { name: 'Warm', set: { eq_low_db: 2.5, eq_high_db: -2, sat: 0.3, comp: 0.3 } },
  { name: 'Lo-fi', set: { filter: -0.55, sat: 0.45, eq_high_db: -5, width: 0.7, reverb: 0.12 } },
  { name: 'Space', set: { reverb: 0.45, room: 0.85, delay_mix: 0.25, delay_time: 0.375, delay_fb: 0.5, width: 1.4 } },
  { name: 'Telephone', set: { filter: 0.55, peq_freq: 1600, peq_gain: 7, peq_q: 1.8, eq_low_db: -12, eq_high_db: -6, width: 0 } },
  { name: 'Punch', set: { comp: 0.7, sat: 0.2, eq_low_db: 1.5, eq_high_db: 2, peq_freq: 4000, peq_gain: 3 } },
]

/** Realtime per-stem and master effect chains. Every move is smooth, bypassable and undoable. */
export function LiveFxTab() {
  const { channels, mixer, master, history, bindStem, bindMaster, setStem, current, toast } = useStudio()
  const [target, setTarget] = useState<string>('__master__')
  const [bits, setBits] = useState<16 | 24 | 32>(24)
  const [scope, setScope] = useState<'all' | 'region'>('all')
  const [busy, setBusy] = useState(false)
  const all: Channel[] = [...channels, MASTER_CH]
  const ch = all.find((c) => c.id === target) ?? MASTER_CH
  const isMaster = ch.id === MASTER_CH.id
  const p = (mixer[ch.id] ?? DEFAULT_STEM) as StemParams
  const limiter = master.limiter !== false

  const commitFx = (label: string, patch: Partial<StemParams>) =>
    history.commit(label, (s) => ({ ...s, mixer: { ...s.mixer, [ch.id]: { ...(s.mixer[ch.id] ?? DEFAULT_STEM), ...patch } } }))
  const reset = () => {
    const patch: Partial<StemParams> = {}
    for (const k of Object.keys(DEFAULT_STEM) as (keyof StemParams)[]) if (!KEEP.includes(k)) (patch as Record<string, unknown>)[k] = DEFAULT_STEM[k]
    commitFx(`${ch.name} reset FX`, patch)
  }

  const bounce = async (only?: string[], mixOverride?: Record<string, StemParams>) =>
    audio.bounce({ mixer: mixOverride ?? mixer, masterGainDb: master.gain_db, limiter, range: scope === 'region' ? audio.region : null, only })

  const exportMix = async () => {
    setBusy(true)
    try {
      const buf = await bounce()
      download(bufferToWav(buf, bits), `${safeName(current?.title ?? 'mix')}_fx.wav`)
      toast('Exported what you hear (same FX chain, rendered offline)', 'ok')
    } catch (e) { toast(`Export failed: ${(e as Error).message}`, 'error') } finally { setBusy(false) }
  }
  const exportStems = async () => {
    setBusy(true)
    try {
      const neutral: Record<string, StemParams> = {}
      for (const [k, v] of Object.entries(mixer)) neutral[k] = { ...v, solo: false, mute: false }
      const files: { name: string; blob: Blob }[] = []
      for (const c of channels) {
        const buf = await audio.bounce({ mixer: neutral, masterGainDb: 0, limiter: false, range: scope === 'region' ? audio.region : null, only: [c.id] })
        files.push({ name: `${safeName(c.name)}.wav`, blob: bufferToWav(buf, bits) })
      }
      download(await zipFiles(files), `${safeName(current?.title ?? 'stems')}_fx_stems.zip`)
    } catch (e) { toast(`Export failed: ${(e as Error).message}`, 'error') } finally { setBusy(false) }
  }

  return (
    <div className="pro-form livefx" data-testid="livefx-tab">
      <div className="fx-top">
        <div className="chips fx-targets" role="tablist" aria-label="FX target">
          {all.map((c) => (
            <button key={c.id} role="tab" aria-selected={c.id === ch.id} className={`chip ${c.id === ch.id ? 'on' : ''}`} onClick={() => setTarget(c.id)} data-testid={`fx-target-${c.role}`}>
              <i className="dot" style={{ background: c.color }} /> {c.name}
            </button>
          ))}
        </div>
        <div className="btn-row">
          <button className="btn small" onClick={history.undo} disabled={!history.canUndo} aria-label="Undo">Undo</button>
          <button className="btn small" onClick={history.redo} disabled={!history.canRedo} aria-label="Redo">Redo</button>
          <button className={`btn small ${p.bypass ? 'on' : ''}`} aria-pressed={p.bypass} onClick={() => setStem(ch.id, ch.name, 'bypass', !p.bypass, `${ch.name} bypass all`)} data-testid="fx-bypass-all">Bypass all</button>
          <button className="btn small ghost" onClick={reset}>Reset FX</button>
        </div>
      </div>

      <div className="fx-scenes" aria-label="Quick looks">
        {SCENES.map((s) => <button key={s.name} className="btn small ghost" onClick={() => commitFx(`${ch.name} ${s.name}`, { ...DEFAULT_STEM, ...s.set, gain_db: p.gain_db, pan: p.pan, mute: p.mute, solo: p.solo })}>{s.name}</button>)}
      </div>

      <div className={`fx-grid ${p.bypass ? 'is-bypassed' : ''}`}>
        <section className="fx-sec">
          <header><h4>Level</h4></header>
          <div className="fx-knobs">
            {isMaster ? (
              <>
                <Knob label="Gain" min={-24} max={12} defaultValue={0} bipolar size={46} color="var(--hot)" format={db} {...bindMaster()} />
                <button className={`btn small ${limiter ? 'on' : ''}`} aria-pressed={limiter} onClick={() => history.commit('Limiter', (s) => ({ ...s, master: { ...s.master, limiter: !limiter } }))} data-testid="fx-limiter">Limiter {limiter ? 'on' : 'off'}</button>
              </>
            ) : (
              <>
                <Knob label="Gain" min={-60} max={12} defaultValue={0} bipolar size={46} color={ch.color} format={db} {...bindStem(ch, 'gain_db', 'Gain')} />
                <Knob label="Pan" min={-1} max={1} defaultValue={0} bipolar size={46} color={ch.color} format={(v) => (Math.abs(v) < 0.02 ? 'C' : v < 0 ? `L${Math.round(-v * 100)}` : `R${Math.round(v * 100)}`)} {...bindStem(ch, 'pan', 'Pan')} />
              </>
            )}
          </div>
        </section>
        {SECTIONS.map((s) => {
          const off = !!p[s.byp]
          return (
            <section key={s.id} className={`fx-sec ${off ? 'is-off' : ''}`} data-testid={`fx-sec-${s.id}`}>
              <header>
                <h4>{s.title}</h4>
                <button className={`led-btn ${off ? '' : 'on'}`} aria-pressed={!off} aria-label={`${s.title} ${off ? 'enable' : 'bypass'}`} onClick={() => setStem(ch.id, ch.name, s.byp, !off, `${ch.name} ${s.title} ${off ? 'on' : 'bypass'}`)}>{off ? 'OFF' : 'ON'}</button>
              </header>
              <div className="fx-knobs">
                {s.knobs.map((k) => (
                  <Knob key={k.key} label={k.label} min={k.min} max={k.max} defaultValue={k.def} step={k.step} bipolar={k.bipolar} size={44} color={ch.color} format={k.fmt} {...bindStem(ch, k.key, k.label)} />
                ))}
              </div>
            </section>
          )
        })}
      </div>

      <div className="fx-export">
        <h4>Export with FX</h4>
        <p className="muted sp-note">Rendered through an OfflineAudioContext with the same chains you hear, so the file matches the speakers.</p>
        <div className="btn-row">
          <select className="select" value={bits} onChange={(e) => setBits(Number(e.target.value) as 16 | 24 | 32)} aria-label="Bit depth">
            <option value={16}>16-bit</option><option value={24}>24-bit</option><option value={32}>32-bit float</option>
          </select>
          <select className="select" value={scope} onChange={(e) => setScope(e.target.value as 'all' | 'region')} aria-label="Range">
            <option value="all">Whole track</option>
            <option value="region" disabled={!audio.region}>Selected region</option>
          </select>
          <button className="btn pri small" disabled={busy || !channels.length} onClick={() => void exportMix()} data-testid="fx-export-mix">{busy ? 'Rendering...' : 'Export mix WAV'}</button>
          <button className="btn small" disabled={busy || !channels.length} onClick={() => void exportStems()}>Export stems (zip)</button>
        </div>
      </div>
    </div>
  )
}
