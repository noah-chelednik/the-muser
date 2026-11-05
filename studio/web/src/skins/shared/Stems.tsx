import { useCallback } from 'react'
import { audio } from '../../audio/engine'
import { Knob } from '../../components/Knob'
import { Meter } from '../../components/Meter'
import { Waveform } from '../../components/Waveform'
import { METHOD_LABEL, useStudio, type Channel } from '../../studio/StudioContext'
import { DEFAULT_STEM, type StemParams } from '../../types'

export const db = (v: number) => (v <= -59.9 ? '-inf' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`)
export const pct = (v: number) => `${Math.round(v * 100)}%`
export const panFmt = (v: number) => (Math.abs(v) < 0.02 ? 'C' : v < 0 ? `L${Math.round(-v * 100)}` : `R${Math.round(v * 100)}`)

export const STRIP_PARAMS: { key: keyof StemParams; label: string; min: number; max: number; def: number; fmt: (v: number) => string; bipolar?: boolean }[] = [
  { key: 'gain_db', label: 'Vol', min: -60, max: 12, def: 0, fmt: db },
  { key: 'pan', label: 'Pan', min: -1, max: 1, def: 0, fmt: panFmt, bipolar: true },
  { key: 'eq_low_db', label: 'Low', min: -18, max: 18, def: 0, fmt: db, bipolar: true },
  { key: 'eq_mid_db', label: 'Mid', min: -18, max: 18, def: 0, fmt: db, bipolar: true },
  { key: 'eq_high_db', label: 'High', min: -18, max: 18, def: 0, fmt: db, bipolar: true },
  { key: 'comp', label: 'Comp', min: 0, max: 1, def: 0, fmt: pct },
  { key: 'reverb', label: 'Verb', min: 0, max: 1, def: 0, fmt: pct },
  { key: 'room', label: 'Room', min: 0, max: 1, def: 0.5, fmt: pct },
]

/** Per-stem audibility and mute/solo toggles shared by every skin. */
export function useStrip(ch: Channel) {
  const { mixer, channels, history } = useStudio()
  const p = mixer[ch.id] ?? DEFAULT_STEM
  const anySolo = channels.some((c) => mixer[c.id]?.solo)
  const audible = !p.mute && (!anySolo || p.solo)
  const set = useCallback(
    (key: keyof StemParams, v: number | boolean) =>
      history.commit(`${key === 'mute' ? (v ? 'Mute' : 'Unmute') : v ? 'Solo' : 'Unsolo'} ${ch.name}`, (s) => ({
        ...s,
        mixer: { ...s.mixer, [ch.id]: { ...(s.mixer[ch.id] ?? DEFAULT_STEM), [key]: v } },
      })),
    [history, ch.id, ch.name],
  )
  return { p, audible, toggleMute: () => set('mute', !p.mute), toggleSolo: () => set('solo', !p.solo) }
}

export function StemLane({ ch, knobSize = 42, wave = true, knobs = STRIP_PARAMS }: { ch: Channel; knobSize?: number; wave?: boolean; knobs?: typeof STRIP_PARAMS }) {
  const { bindStem, buffersVersion } = useStudio()
  const { p, audible, toggleMute, toggleSolo } = useStrip(ch)
  return (
    <div className={`lane ${audible ? '' : 'is-silent'}`} data-version={buffersVersion} data-stem={ch.role} data-testid="lane">
      <div className="lane-head">
        <div className="lane-name">
          <span className="lane-dot" />
          <span>{ch.name}</span>
        </div>
        <div className="ms">
          <button className={`led-btn mute ${p.mute ? 'on' : ''}`} onClick={toggleMute} aria-pressed={p.mute} aria-label={`Mute ${ch.name}`}>
            M
          </button>
          <button className={`led-btn solo ${p.solo ? 'on' : ''}`} onClick={toggleSolo} aria-pressed={p.solo} aria-label={`Solo ${ch.name}`}>
            S
          </button>
        </div>
        <Meter getAnalyser={() => audio.analyser(ch.id)} segments={12} horizontal />
      </div>
      {wave && (
        <div className="lane-wave">
          <Waveform buffer={audio.buffer(ch.id)} dim={!audible} onSeek={(t) => audio.seek(t)} />
        </div>
      )}
      <div className="lane-knobs">
        {knobs.map((k) => {
          const b = bindStem(ch, k.key, k.label)
          return <Knob key={k.key} label={k.label} min={k.min} max={k.max} defaultValue={k.def} bipolar={k.bipolar} size={knobSize} color="var(--stem)" format={k.fmt} {...b} />
        })}
      </div>
    </div>
  )
}

export function TrackChips() {
  const { current: track } = useStudio()
  if (!track) return null
  return (
    <div className="chips">
      <span className={`chip src-${track.source}`}>{track.source}</span>
      {track.key && <span className="chip">{track.key}</span>}
      {track.bpm ? <span className="chip">{track.bpm} BPM</span> : null}
      <span className="chip">{track.duration_s.toFixed(1)}s</span>
      {track.stem_method && <span className="chip pri">{METHOD_LABEL[track.stem_method] ?? track.stem_method}</span>}
    </div>
  )
}

export function StemActions() {
  const { current: track, busy, onSplit, onRender, setShowExport } = useStudio()
  const hasStems = !!track?.stems.length
  return (
    <div className="mixer-actions">
      <button className="btn" disabled={!!busy || !track} onClick={() => void onSplit('4stem')} title="Drums, bass, other, vocals (Demucs htdemucs)">
        Split 4 stems
      </button>
      <button className="btn" disabled={!!busy || !track} onClick={() => void onSplit('2stem')} title="Vocals and accompaniment (Demucs two stems)">
        Vocals / Inst
      </button>
      <button className="btn pri" disabled={!!busy || !hasStems} onClick={() => void onRender()} title="Render the mix on the server with the effect and mix tools">
        Render mix
      </button>
      <button className="btn" disabled={!!busy || !track} onClick={() => setShowExport(true)}>
        Export
      </button>
    </div>
  )
}

export function StemLanes({ knobSize, wave }: { knobSize?: number; wave?: boolean }) {
  const { current: track, channels, busy } = useStudio()
  if (!track)
    return (
      <div className="empty-state">
        <p>Describe a track in the composer, or pick one from the library.</p>
        <p className="muted">Then split it into stems and sculpt each one.</p>
      </div>
    )
  return (
    <>
      {track.notes && <div className="note">{track.notes}</div>}
      {busy && (
        <div className="busy">
          <span className="spinner" /> {busy}
        </div>
      )}
      <div className="lanes">
        {channels.map((ch) => (
          <StemLane key={ch.id} ch={ch} knobSize={knobSize} wave={wave} />
        ))}
      </div>
      {!track.stems.length && <div className="hint-row">Playing the full mix. Split the track to get one lane per sound.</div>}
    </>
  )
}

export function MasterKnob({ size = 44 }: { size?: number }) {
  const { bindMaster } = useStudio()
  return <Knob label="Master" min={-24} max={12} defaultValue={0} bipolar size={size} color="var(--hot)" format={db} {...bindMaster()} />
}
