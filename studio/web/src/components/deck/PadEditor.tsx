import { useRef, useState, useSyncExternalStore } from 'react'
import { BASE_PAD_NAMES } from '../../audio/instruments'
import { importUserSound, assignUserSound } from '../../audio/library'
import { newSlot, SLOT_DEFS, SLOT_ORDER, type FxSlot, type SlotType } from '../../audio/padfx'
import { padBank } from '../../audio/samples'
import { ACCEPT } from '../../audio/upload'
import { Slider } from './Slider'

type Props = {
  pad: number
  onAudition: () => void
  onBrowse: () => void
}

/** Sound and FX for one pad. Changes apply to this pad only and autosave with the kit. */
export function PadEditor({ pad, onAudition, onBrowse }: Props) {
  useSyncExternalStore(padBank.subscribe, padBank.version)
  const s = padBank.get(pad)
  const st = padBank.settings(pad)
  const file = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState(false)

  const src = s?.source?.kind === 'library' ? `Library, ${s.source.license === 'CC0-1.0' ? 'CC0' : s.source.license}` : s?.source?.kind === 'upload' ? 'Your upload' : s ? 'Sampler chop' : 'Built-in synth'

  const upload = async (f: File | undefined) => {
    if (!f) return
    setErr(''); setBusy(true)
    try {
      const { sound } = await importUserSound(f)
      assignUserSound(pad, sound)
      onAudition()
    } catch (e) {
      setErr((e as Error).message)
    } finally { setBusy(false) }
  }

  const fx = st.fx
  const setFx = (next: FxSlot[]) => padBank.setFx(pad, next)
  const patch = (id: string, p: Partial<FxSlot>) => setFx(fx.map((x) => (x.id === id ? { ...x, ...p } : x)))
  const move = (i: number, d: number) => {
    const j = i + d
    if (j < 0 || j >= fx.length) return
    const next = fx.slice()
    ;[next[i], next[j]] = [next[j], next[i]]
    setFx(next)
  }
  const add = (t: SlotType) => { setFx([...fx, newSlot(t)]); setAdding(false) }

  return (
    <div className="nd-editor" data-testid="pad-editor">
      <div className="nd-ed-head">
        <div className="nd-ed-title">
          <b>Pad {pad + 1}</b>
          <span data-testid="pad-sound-name">{s?.name ?? BASE_PAD_NAMES[pad]}</span>
          <em className={`nd-src ${s ? 'has' : ''}`}>{src}</em>
        </div>
        <button className="nd-btn pri" onClick={onAudition} data-testid="pad-audition">Play</button>
      </div>

      <div className="nd-ed-actions">
        <button className="nd-btn" onClick={onBrowse} data-testid="pad-change">Change sound</button>
        <button className="nd-btn" onClick={() => file.current?.click()} disabled={busy} data-testid="pad-upload-btn">{busy ? 'Checking file' : 'Upload sound'}</button>
        <input ref={file} type="file" accept={ACCEPT} hidden data-testid="pad-upload" onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = '' }} />
        <button className="nd-btn ghost" onClick={() => padBank.set(pad, null)} disabled={!s} data-testid="pad-use-synth">Use synth hit</button>
        <button className="nd-btn ghost" onClick={() => padBank.resetPad(pad)} data-testid="pad-reset">Reset pad</button>
      </div>
      {err && <p className="nd-err" role="alert" data-testid="upload-error">{err}</p>}

      <div className="nd-ed-sound">
        <Slider label="Level" value={st.gain} min={0} max={2} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => padBank.setSettings(pad, { gain: v })} testId="pad-level" />
        <Slider label="Pitch" value={st.pitch} min={-24} max={24} step={1} format={(v) => `${v > 0 ? '+' : ''}${v} st`} onChange={(v) => padBank.setSettings(pad, { pitch: v })} testId="pad-pitch" />
      </div>

      <div className="nd-fx">
        <div className="nd-fx-head">
          <b>Pad FX</b>
          <span>{fx.length ? `${fx.filter((x) => x.on).length} of ${fx.length} on` : 'Dry'}</span>
          <button className="nd-btn small" onClick={() => setAdding((v) => !v)} aria-expanded={adding} data-testid="fx-add">{adding ? 'Close' : 'Add effect'}</button>
        </div>
        {adding && (
          <div className="nd-fx-menu" role="menu">
            {SLOT_ORDER.map((t) => <button key={t} role="menuitem" className="nd-chip" onClick={() => add(t)} data-testid={`fx-add-${t}`}>{SLOT_DEFS[t].label}</button>)}
          </div>
        )}
        {fx.length === 0 && !adding && <p className="nd-muted">No effects on this pad yet. Add a filter, EQ, compressor, saturation, bitcrush, delay, reverb, width or pan. They only change this pad.</p>}
        <ol className="nd-fx-list">
          {fx.map((x, i) => (
            <li key={x.id} className={`nd-slot ${x.on ? '' : 'off'}`} data-testid={`fx-slot-${x.type}`}>
              <div className="nd-slot-head">
                <button className={`nd-led ${x.on ? 'on' : ''}`} aria-pressed={x.on} aria-label={`${SLOT_DEFS[x.type].label} on`} onClick={() => patch(x.id, { on: !x.on })} data-testid="fx-toggle" />
                <b>{SLOT_DEFS[x.type].label}</b>
                <span className="nd-slot-tools">
                  <button className="nd-icon" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)} data-testid="fx-up">▲</button>
                  <button className="nd-icon" aria-label="Move down" disabled={i === fx.length - 1} onClick={() => move(i, 1)} data-testid="fx-down">▼</button>
                  <button className="nd-icon" aria-label="Remove" onClick={() => setFx(fx.filter((y) => y.id !== x.id))} data-testid="fx-remove">✕</button>
                </span>
              </div>
              <div className="nd-slot-params">
                {SLOT_DEFS[x.type].params.map((d) => (
                  <Slider key={d.key} label={d.label} value={x.p[d.key] ?? d.def} min={d.min} max={d.max} step={d.step} log={d.log} format={d.fmt}
                    onChange={(v) => patch(x.id, { p: { ...x.p, [d.key]: v } })} testId={`fx-${x.type}-${d.key}`} />
                ))}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
