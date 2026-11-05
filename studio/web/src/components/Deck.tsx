import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { PADS, noteOff, noteOn, sequencer } from '../audio/instruments'
import { padBank } from '../audio/samples'
import { audio } from '../audio/engine'
import { midi } from '../midi'
import type { History } from '../state/history'
import type { PadParams, Project, SynthParams } from '../types'
import { Knob } from './Knob'

type Props = { history: History<Project> }

const KEY_MAP = ['a', 'w', 's', 'e', 'd', 'f', 't', 'g', 'y', 'h', 'u', 'j', 'k', 'o', 'l', 'p', ';', "'"]
const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const isBlack = (n: number) => [1, 3, 6, 8, 10].includes(n % 12)
const WAVES: OscillatorType[] = ['sawtooth', 'square', 'triangle', 'sine']

const typing = (e: KeyboardEvent) => {
  const t = e.target as HTMLElement
  return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
}

export function Deck({ history }: Props) {
  const [tab, setTab] = useState<'pads' | 'keys'>('pads')
  useSyncExternalStore(padBank.subscribe, padBank.version)
  const padName = (i: number) => padBank.get(i)?.name ?? PADS[i].name
  const [hitPads, setHitPads] = useState<Set<number>>(new Set())
  const [held, setHeld] = useState<Set<number>>(new Set())
  const [step, setStep] = useState(-1)
  const [seqOn, setSeqOn] = useState(false)
  const [selPad, setSelPad] = useState(0)
  const proj = history.state
  const projRef = useRef(proj)
  projRef.current = proj

  const base = 48 + proj.synth.octave * 12 // C3 at octave 0

  const flash = (i: number) => {
    setHitPads((s) => new Set(s).add(i))
    window.setTimeout(() => setHitPads((s) => { const n = new Set(s); n.delete(i); return n }), 140)
  }
  const hitPad = useCallback((i: number) => {
    const ctx = audio.ensure()
    PADS[i].play(ctx.currentTime + 0.005, projRef.current.pads)
    flash(i)
  }, [])

  const on = useCallback((n: number, vel = 0.8) => {
    noteOn(n, projRef.current.synth, vel)
    setHeld((s) => new Set(s).add(n))
  }, [])
  const off = useCallback((n: number) => {
    noteOff(n, projRef.current.synth)
    setHeld((s) => { const x = new Set(s); x.delete(n); return x })
  }, [])

  // MIDI control for pads and keys
  useEffect(() => {
    const onMidi = (e: Event) => {
      const { target, value } = (e as CustomEvent).detail
      if (target.kind === 'pad' && value > 0.1) hitPad(target.index)
      if (target.kind === 'key') {
        if (value > 0.05) on(target.note, value)
        else off(target.note)
      }
    }
    window.addEventListener('midi-control', onMidi)
    return () => window.removeEventListener('midi-control', onMidi)
  }, [hitPad, on, off])

  // sequencer wiring
  useEffect(() => {
    sequencer.getPattern = () => projRef.current.pattern
    sequencer.getBpm = () => projRef.current.bpm
    sequencer.getPad = () => projRef.current.pads
    sequencer.onStep = (s) => {
      setStep(s)
      if (s >= 0) projRef.current.pattern.forEach((row, p) => row[s] && flash(p))
    }
    return () => sequencer.stop()
  }, [])

  // computer keyboard
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.repeat || typing(e) || e.ctrlKey || e.metaKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (tab === 'pads') {
        const i = PADS.findIndex((p) => p.key === k)
        if (i >= 0) { e.preventDefault(); hitPad(i) }
      } else {
        const i = KEY_MAP.indexOf(k)
        if (i >= 0) { e.preventDefault(); on(base + i) }
        if (k === 'z') history.commit('Octave down', (s) => ({ ...s, synth: { ...s.synth, octave: Math.max(-2, s.synth.octave - 1) } }))
        if (k === 'x') history.commit('Octave up', (s) => ({ ...s, synth: { ...s.synth, octave: Math.min(2, s.synth.octave + 1) } }))
      }
    }
    const up = (e: KeyboardEvent) => {
      if (tab !== 'keys') return
      const i = KEY_MAP.indexOf(e.key.toLowerCase())
      if (i >= 0) off(base + i)
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [tab, base, hitPad, on, off, history])

  const synthKnob = (key: keyof SynthParams, label: string, min: number, max: number, def: number, fmt: (v: number) => string) => (
    <Knob
      key={key}
      midiId={`synth-${key}`}
      label={label}
      value={proj.synth[key] as number}
      min={min}
      max={max}
      defaultValue={def}
      size={50}
      color="var(--k2)"
      format={fmt}
      onBegin={() => history.begin(`Synth ${label}`)}
      onChange={(v) => history.preview((s) => ({ ...s, synth: { ...s.synth, [key]: v } }))}
      onEnd={history.end}
      onCommit={(v) => history.commit(`Synth ${label}`, (s) => ({ ...s, synth: { ...s.synth, [key]: v } }))}
    />
  )
  const padKnob = (key: keyof PadParams, label: string, min: number, max: number, def: number, fmt: (v: number) => string, step = 0) => (
    <Knob
      key={key}
      midiId={`pads-${key}`}
      label={label}
      value={proj.pads[key]}
      min={min}
      max={max}
      step={step}
      defaultValue={def}
      size={50}
      bipolar={key === 'pitch'}
      color="var(--k3)"
      format={fmt}
      onBegin={() => history.begin(`Pads ${label}`)}
      onChange={(v) => history.preview((s) => ({ ...s, pads: { ...s.pads, [key]: v } }))}
      onEnd={history.end}
      onCommit={(v) => history.commit(`Pads ${label}`, (s) => ({ ...s, pads: { ...s.pads, [key]: v } }))}
    />
  )

  const toggleStep = (pad: number, st: number) =>
    history.commit(`${PADS[pad].name} step ${st + 1}`, (s) => ({
      ...s,
      pattern: s.pattern.map((row, p) => (p === pad ? row.map((v, i) => (i === st ? !v : v)) : row)),
    }))

  // 2 octaves + top C
  const keys = Array.from({ length: 25 }, (_, i) => base + i)
  const whites = keys.filter((n) => !isBlack(n))
  const pointerNote = useRef<number | null>(null)

  return (
    <section className="panel deck">
      <div className="panel-head">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'pads'} className={tab === 'pads' ? 'on' : ''} onClick={() => setTab('pads')}>
            Pads + Sequencer
          </button>
          <button role="tab" aria-selected={tab === 'keys'} className={tab === 'keys' ? 'on' : ''} onClick={() => setTab('keys')}>
            Keys
          </button>
        </div>
        <div className="deck-hint">
          {tab === 'pads' ? 'Keys 1-4 / Q-R / A-F / Z-V trigger pads · right-click pads or knobs for MIDI learn' : 'Keys A-; play notes, W E T Y U O P sharps, Z / X octave · right-click knobs for MIDI learn'}
        </div>
      </div>

      {tab === 'pads' ? (
        <div className="deck-body pads-body">
          <div className="pad-grid">
            {PADS.map((p, i) => (
              <button
                key={p.name}
                className={`pad ${hitPads.has(i) ? 'hit' : ''} ${selPad === i ? 'sel' : ''}`}
                onPointerDown={(e) => { e.preventDefault(); hitPad(i); setSelPad(i) }}
                onContextMenu={(e) => { e.preventDefault(); midi.startLearn({ kind: 'pad', index: i }) }}
              >
                <span className="pad-name">{padName(i)}</span>
                <span className="pad-key">{p.key.toUpperCase()}</span>
              </button>
            ))}
          </div>
          <div className="seq">
            <div className="seq-head">
              <button
                className={`btn ${seqOn ? 'pri' : ''}`}
                onClick={() => {
                  if (sequencer.running) { sequencer.stop(); setSeqOn(false) } else { sequencer.start(); setSeqOn(true) }
                }}
              >
                {seqOn ? '■ Stop' : '▶ Play pattern'}
              </button>
              <Knob
                midiId="bpm"
                label="BPM"
                value={proj.bpm}
                min={60}
                max={180}
                step={1}
                defaultValue={96}
                size={42}
                format={(v) => v.toFixed(0)}
                onBegin={() => history.begin('BPM')}
                onChange={(v) => history.preview((s) => ({ ...s, bpm: v }))}
                onEnd={history.end}
                onCommit={(v) => history.commit('BPM', (s) => ({ ...s, bpm: v }))}
              />
              <button className="btn ghost" onClick={() => history.commit('Clear pattern', (s) => ({ ...s, pattern: s.pattern.map((r) => r.map(() => false)) }))}>
                Clear
              </button>
              <div className="pad-knobs">
                {padKnob('volume', 'Level', 0, 1.5, 0.8, (v) => `${Math.round(v * 100)}%`)}
                {padKnob('pitch', 'Pitch', -12, 12, 0, (v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}st`, 1)}
                {padKnob('tone', 'Tone', 0, 1, 0.5, (v) => `${Math.round(v * 100)}%`)}
              </div>
            </div>
            <div className="seq-rows">
              {[0, 1, 4, 5, 2, 11, 12, selPad].filter((v, i, a) => a.indexOf(v) === i).map((pad) => (
                <div className={`seq-row ${pad === selPad ? 'sel' : ''}`} key={pad}>
                  <span className="seq-label" onClick={() => setSelPad(pad)}>{padName(pad)}</span>
                  {proj.pattern[pad].map((on, st) => (
                    <button
                      key={st}
                      className={`step ${on ? 'on' : ''} ${st === step ? 'now' : ''} ${st % 4 === 0 ? 'beat' : ''}`}
                      onClick={() => toggleStep(pad, st)}
                      aria-label={`${PADS[pad].name} step ${st + 1}`}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="deck-body keys-body">
          <div className="synth-controls">
            <div className="wave-select">
              {WAVES.map((w) => (
                <button
                  key={w}
                  className={`led-btn wide ${proj.synth.wave === w ? 'on' : ''}`}
                  onClick={() => history.commit(`Wave ${w}`, (s) => ({ ...s, synth: { ...s.synth, wave: w } }))}
                >
                  {w.slice(0, 3).toUpperCase()}
                </button>
              ))}
            </div>
            {synthKnob('cutoff', 'Cutoff', 0, 1, 0.65, (v) => `${Math.round(120 * Math.pow(2, v * 7.5))}Hz`)}
            {synthKnob('reso', 'Reso', 0, 1, 0.15, (v) => `${Math.round(v * 100)}%`)}
            {synthKnob('attack', 'Attack', 0.002, 1.5, 0.01, (v) => `${Math.round(v * 1000)}ms`)}
            {synthKnob('release', 'Release', 0.02, 3, 0.4, (v) => `${v.toFixed(2)}s`)}
            {synthKnob('detune', 'Detune', 0, 30, 8, (v) => `${v.toFixed(0)}c`)}
            {synthKnob('volume', 'Level', 0, 1, 0.7, (v) => `${Math.round(v * 100)}%`)}
            <div className="octave">
              <button className="btn ghost" onClick={() => history.commit('Octave down', (s) => ({ ...s, synth: { ...s.synth, octave: Math.max(-2, s.synth.octave - 1) } }))}>−</button>
              <span className="lcd small">OCT {proj.synth.octave >= 0 ? '+' : ''}{proj.synth.octave}</span>
              <button className="btn ghost" onClick={() => history.commit('Octave up', (s) => ({ ...s, synth: { ...s.synth, octave: Math.min(2, s.synth.octave + 1) } }))}>+</button>
            </div>
          </div>
          <div
            className="piano"
            onPointerLeave={() => { if (pointerNote.current !== null) { off(pointerNote.current); pointerNote.current = null } }}
          >
            {whites.map((n) => (
              <div key={n} className="white-slot">
                <PianoKey n={n} black={false} held={held.has(n)} pointerNote={pointerNote} on={on} off={off} />
                {!isBlack(n + 1) || n === keys[keys.length - 1] ? null : (
                  <PianoKey n={n + 1} black held={held.has(n + 1)} pointerNote={pointerNote} on={on} off={off} />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function PianoKey({ n, black, held, pointerNote, on, off }: {
  n: number; black: boolean; held: boolean
  pointerNote: React.MutableRefObject<number | null>
  on: (n: number, v?: number) => void; off: (n: number) => void
}) {
  const label = NOTE_NAMES[n % 12] === 'C' ? `C${Math.floor(n / 12) - 1}` : ''
  const vel = (e: React.PointerEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    return 0.35 + 0.65 * Math.min(1, (e.clientY - r.top) / r.height)
  }
  return (
    <div
      className={`pkey ${black ? 'black' : 'white'} ${held ? 'held' : ''}`}
      onPointerDown={(e) => {
        e.preventDefault()
        e.stopPropagation()
        ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
        pointerNote.current = n
        on(n, vel(e))
      }}
      onPointerEnter={(e) => {
        if (e.buttons & 1 && pointerNote.current !== null && pointerNote.current !== n) {
          off(pointerNote.current)
          pointerNote.current = n
          on(n, vel(e))
        }
      }}
      onPointerUp={(e) => {
        e.stopPropagation()
        if (pointerNote.current !== null) off(pointerNote.current)
        pointerNote.current = null
      }}
      onContextMenu={(e) => { e.preventDefault(); midi.startLearn({ kind: 'key', note: n }) }}
      data-note={n}
    >
      {label && <span className="pkey-label">{label}</span>}
    </div>
  )
}
