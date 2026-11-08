import { useEffect, useState } from 'react'
import { clipAt, cloneSteps, ensureBeat, makePattern, uid } from '../audio/arrange'
import { syncArrangeGraph } from '../audio/arrangeGraph'
import { downloadArrangement } from '../audio/beatExport'
import { sequencer } from '../audio/instruments'
import type { History } from '../state/history'
import { DEFAULT_STEM, type Arrangement, type Project, type StemParams } from '../types'
import { Knob } from './Knob'
import './Arranger.css'

const COLORS = ['#ff4d6d', '#ffb703', '#4cc9f0', '#c77dff', '#80ffdb', '#ffd166']
const colorFor = (id: string) => {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 33 + id.charCodeAt(i)) | 0
  return COLORS[Math.abs(h) % COLORS.length]
}

const applyFx = (project: Project, target: number | 'master', patch: Partial<StemParams>): Project => {
  const beat = ensureBeat(project)
  const arr = beat.arrangement!
  if (target === 'master') return { ...beat, arrangement: { ...arr, masterFx: { ...arr.masterFx, ...patch } } }
  return {
    ...beat,
    arrangement: { ...arr, tracks: arr.tracks.map((track, i) => (i === target ? { ...track, fx: { ...track.fx, ...patch } } : track)) },
  }
}

const setArr = (history: History<Project>, label: string, fn: (arr: Arrangement, beat: Project) => Arrangement) => {
  history.commit(label, (state) => {
    const beat = ensureBeat(state)
    return { ...beat, arrangement: fn(beat.arrangement!, beat) }
  })
}

export function Arranger({ history }: { history: History<Project> }) {
  const beat = ensureBeat(history.state)
  const arr = beat.arrangement!
  const [selPattern, setSelPattern] = useState(beat.activePatternId || beat.patterns![0].id)
  const [selClip, setSelClip] = useState<string | null>(null)
  const [fxTarget, setFxTarget] = useState<number | 'master'>(0)
  const [playOn, setPlayOn] = useState(false)
  const [playAbs, setPlayAbs] = useState(-1)
  const [exporting, setExporting] = useState(false)
  const [msg, setMsg] = useState('')
  const playBar = playAbs < 0 ? -1 : Math.floor(playAbs / 16) % Math.max(1, arr.bars)
  const selected = arr.clips.find((c) => c.id === selClip) ?? null
  const fx = fxTarget === 'master' ? arr.masterFx : (arr.tracks[fxTarget]?.fx ?? arr.masterFx)
  const cols = `88px repeat(${arr.bars}, 36px)`

  useEffect(() => {
    const prev = sequencer.onStep
    sequencer.onStep = (step) => {
      prev?.(step)
      setPlayAbs(step)
      if (step < 0) setPlayOn(false)
    }
    return () => { sequencer.onStep = prev }
  }, [])

  useEffect(() => { syncArrangeGraph(arr) }, [arr])

  const pickPattern = (id: string) => {
    setSelPattern(id)
    history.commit('Select pattern', (state) => {
      const next = ensureBeat(state)
      const pat = next.patterns!.find((item) => item.id === id)
      if (!pat) return next
      return { ...next, activePatternId: id, pattern: cloneSteps(pat.steps) }
    })
  }

  const place = (track: number, bar: number) => {
    const existing = clipAt(arr, track, bar)
    if (existing) {
      setSelClip(existing.id)
      return
    }
    setArr(history, 'Place clip', (a) => ({
      ...a,
      clips: [...a.clips, { id: uid('clip'), patternId: selPattern, track, startBar: bar, lengthBars: 1 }],
    }))
  }

  const togglePlay = () => {
    if (sequencer.running && sequencer.mode === 'arrange') {
      sequencer.stop()
      setPlayOn(false)
      return
    }
    if (sequencer.running) sequencer.stop()
    syncArrangeGraph(arr)
    sequencer.mode = 'arrange'
    sequencer.start()
    setPlayOn(true)
  }

  const doExport = async (opts: { bitDepth?: 16 | 24; normalize?: boolean }) => {
    setExporting(true)
    setMsg('')
    try {
      await downloadArrangement(ensureBeat(history.state), opts)
      setMsg(`Exported ${opts.bitDepth ?? 16}-bit WAV`)
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const fxKnob = (key: keyof StemParams, label: string, min: number, max: number, def: number, fmt: (v: number) => string, bipolar = false) => (
    <Knob
      key={`${fxTarget}-${key}`}
      midiId={`arr-${fxTarget}-${key}`}
      label={label}
      value={fx[key] as number}
      min={min}
      max={max}
      defaultValue={def}
      size={42}
      bipolar={bipolar}
      format={fmt}
      onBegin={() => history.begin(`Arrange ${label}`)}
      onChange={(v) => history.preview((s) => applyFx(s, fxTarget, { [key]: v }))}
      onEnd={history.end}
      onCommit={(v) => history.commit(`Arrange ${label}`, (s) => applyFx(s, fxTarget, { [key]: v }))}
    />
  )

  return (
    <div className="arranger" data-testid="arranger">
      <div className="arr-col">
        <div className="arr-toolbar">
          <button className="btn ghost" onClick={() => {
            const pat = makePattern(`Pattern ${beat.patterns!.length + 1}`)
            history.commit('New pattern', (state) => {
              const next = ensureBeat(state)
              return { ...next, patterns: [...next.patterns!, pat], activePatternId: pat.id, pattern: cloneSteps(pat.steps) }
            })
            setSelPattern(pat.id)
          }}>New pattern</button>
          <button className="btn ghost" onClick={() => {
            const src = beat.patterns!.find((p) => p.id === selPattern) ?? beat.patterns![0]
            const pat = makePattern(`${src.name} copy`, src.steps)
            history.commit('Duplicate pattern', (state) => {
              const next = ensureBeat(state)
              return { ...next, patterns: [...next.patterns!, pat], activePatternId: pat.id, pattern: cloneSteps(pat.steps) }
            })
            setSelPattern(pat.id)
          }}>Duplicate</button>
        </div>
        <div className="arr-patterns">
          {beat.patterns!.map((pat) => (
            <div key={pat.id} className={`arr-pat ${pat.id === selPattern ? 'on' : ''}`} onClick={() => pickPattern(pat.id)}>
              <span className="arr-swatch" style={{ background: colorFor(pat.id) }} />
              <input
                value={pat.name}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => {
                  const name = e.target.value
                  history.commit('Rename pattern', (state) => {
                    const next = ensureBeat(state)
                    return { ...next, patterns: next.patterns!.map((item) => (item.id === pat.id ? { ...item, name } : item)) }
                  })
                }}
              />
            </div>
          ))}
        </div>
        <p className="arr-msg">Select a pattern, then click an empty bar to place it. Click a clip to select it.</p>
      </div>

      <div className="arr-col">
        <div className="arr-toolbar">
          <button className={`btn ${playOn ? 'pri' : ''}`} onClick={togglePlay}>{playOn ? '■ Stop' : '▶ Play arrangement'}</button>
          <label>Bars
            <input
              className="num"
              type="number"
              min={1}
              max={64}
              value={arr.bars}
              onChange={(e) => setArr(history, 'Arrangement length', (a) => ({ ...a, bars: Math.max(1, Math.min(64, Number(e.target.value) || 1)) }))}
            />
          </label>
          <button className="btn ghost" onClick={() => setArr(history, 'Add track', (a) => ({
            ...a,
            tracks: [...a.tracks, { name: `Track ${a.tracks.length + 1}`, fx: { ...DEFAULT_STEM } }],
          }))}>Add track</button>
          {selected && (
            <>
              <button className="btn ghost" onClick={() => setArr(history, 'Move clip', (a) => ({
                ...a,
                clips: a.clips.map((c) => c.id === selected.id ? { ...c, startBar: Math.max(0, c.startBar - 1) } : c),
              }))}>←</button>
              <button className="btn ghost" onClick={() => setArr(history, 'Move clip', (a) => ({
                ...a,
                clips: a.clips.map((c) => c.id === selected.id ? { ...c, startBar: Math.min(a.bars - 1, c.startBar + 1) } : c),
              }))}>→</button>
              <button className="btn ghost" onClick={() => setArr(history, 'Lengthen clip', (a) => ({
                ...a,
                clips: a.clips.map((c) => c.id === selected.id ? { ...c, lengthBars: Math.min(a.bars - c.startBar, c.lengthBars + 1) } : c),
              }))}>+ bar</button>
              <button className="btn ghost" onClick={() => setArr(history, 'Shorten clip', (a) => ({
                ...a,
                clips: a.clips.map((c) => c.id === selected.id ? { ...c, lengthBars: Math.max(1, c.lengthBars - 1) } : c),
              }))}>− bar</button>
              <button className="btn ghost" onClick={() => {
                setArr(history, 'Delete clip', (a) => ({ ...a, clips: a.clips.filter((c) => c.id !== selected.id) }))
                setSelClip(null)
              }}>Delete clip</button>
            </>
          )}
        </div>
        <div className="arr-timeline">
          <div className="arr-ruler" style={{ gridTemplateColumns: cols }}>
            <span />
            {Array.from({ length: arr.bars }, (_, bar) => (
              <span key={bar} className={playBar === bar ? 'now' : ''}>{bar + 1}</span>
            ))}
          </div>
          {arr.tracks.map((track, ti) => (
            <div className="arr-row" key={ti} style={{ gridTemplateColumns: cols }}>
              <div
                className={`arr-label ${fxTarget === ti ? 'on' : ''}`}
                onClick={() => setFxTarget(ti)}
              >
                <input
                  value={track.name}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => {
                    const name = e.target.value
                    setArr(history, 'Rename track', (a) => ({
                      ...a,
                      tracks: a.tracks.map((item, i) => (i === ti ? { ...item, name } : item)),
                    }))
                  }}
                />
              </div>
              <div className="arr-lane" style={{ gridColumn: `2 / span ${arr.bars}`, gridTemplateColumns: `repeat(${arr.bars}, 36px)` }}>
                {Array.from({ length: arr.bars }, (_, bar) => (
                  <div
                    key={bar}
                    className={`arr-cell ${playBar === bar ? 'now' : ''}`}
                    onClick={() => place(ti, bar)}
                  />
                ))}
                {arr.clips.filter((c) => c.track === ti).map((clip) => (
                  <div
                    key={clip.id}
                    className={`arr-clip ${selClip === clip.id ? 'on' : ''}`}
                    style={{
                      gridColumn: `${clip.startBar + 1} / span ${Math.max(1, clip.lengthBars)}`,
                      background: colorFor(clip.patternId),
                    }}
                    onClick={(e) => { e.stopPropagation(); setSelClip(clip.id) }}
                  >
                    {beat.patterns!.find((p) => p.id === clip.patternId)?.name ?? 'Pattern'}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="arr-col">
        <div className="arr-toolbar">
          {arr.tracks.map((track, i) => (
            <button key={i} className={`btn ghost ${fxTarget === i ? 'pri' : ''}`} onClick={() => setFxTarget(i)}>{track.name}</button>
          ))}
          <button className={`btn ghost ${fxTarget === 'master' ? 'pri' : ''}`} onClick={() => setFxTarget('master')}>Master</button>
        </div>
        <div className="arr-fx">
          {fxKnob('gain_db', 'Gain', -24, 12, 0, (v) => `${v.toFixed(1)} dB`, true)}
          {fxKnob('pan', 'Pan', -1, 1, 0, (v) => (v === 0 ? 'C' : `${v > 0 ? 'R' : 'L'}${Math.abs(v * 100).toFixed(0)}`), true)}
          {fxKnob('eq_low_db', 'Low', -12, 12, 0, (v) => `${v.toFixed(1)} dB`, true)}
          {fxKnob('eq_mid_db', 'Mid', -12, 12, 0, (v) => `${v.toFixed(1)} dB`, true)}
          {fxKnob('eq_high_db', 'High', -12, 12, 0, (v) => `${v.toFixed(1)} dB`, true)}
          {fxKnob('comp', 'Comp', 0, 1, 0, (v) => `${Math.round(v * 100)}%`)}
          {fxKnob('sat', 'Sat', 0, 1, 0, (v) => `${Math.round(v * 100)}%`)}
          {fxKnob('delay_mix', 'Delay', 0, 1, 0, (v) => `${Math.round(v * 100)}%`)}
          {fxKnob('reverb', 'Reverb', 0, 1, 0, (v) => `${Math.round(v * 100)}%`)}
        </div>
        <div className="arr-export">
          <button className="btn pri" disabled={exporting} onClick={() => void doExport({ bitDepth: 16 })}>Export 16-bit</button>
          <button className="btn" disabled={exporting} onClick={() => void doExport({ bitDepth: 24 })}>Export 24-bit</button>
          <button className="btn ghost" disabled={exporting} onClick={() => void doExport({ bitDepth: 16, normalize: true })}>Export + normalize</button>
        </div>
        {msg && <div className="arr-msg">{msg}</div>}
      </div>
    </div>
  )
}
