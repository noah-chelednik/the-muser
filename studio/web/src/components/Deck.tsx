import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { cloneSteps, ensureBeat, syncActivePattern } from '../audio/arrange'
import { audio } from '../audio/engine'
import { PADS, allNotesOff, noteOff, noteOn, sequencer } from '../audio/instruments'
import { KEY_CATS, KEY_PRESETS, keySampler, presetById } from '../audio/keys'
import { padBank } from '../audio/samples'
import * as soundfont from '../audio/soundfont'
import { UploadError, validateAudioFile } from '../audio/upload'
import { midi, routeNote, type MidiRouting } from '../midi'
import type { History } from '../state/history'
import type { KeyNote, Project, SynthParams } from '../types'
import { Arranger } from './Arranger'
import { claimDeck, ownsInput } from './deck/focus'
import { PadEditor } from './deck/PadEditor'
import { Slider } from './deck/Slider'
import { SoundBrowser } from './deck/SoundBrowser'
import './deck/deck.css'

type Props = { history: History<Project> }
type View = 'pads' | 'keys' | 'sounds' | 'arrange'

const KEY_MAP = ['a', 'w', 's', 'e', 'd', 'f', 't', 'g', 'y', 'h', 'u', 'j', 'k', 'o', 'l', 'p', ';', "'"]
const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const isBlack = (n: number) => [1, 3, 6, 8, 10].includes(n % 12)
const noteName = (n: number) => `${NOTE_NAMES[n % 12]}${Math.floor(n / 12) - 1}`
const WAVES: OscillatorType[] = ['sawtooth', 'square', 'triangle', 'sine']
const typing = (e: KeyboardEvent) => {
  const t = e.target as HTMLElement
  return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
}

function useNarrow(px = 600) {
  const q = `(max-width: ${px}px)`
  const [n, setN] = useState(() => typeof window !== 'undefined' && matchMedia(q).matches)
  useEffect(() => {
    const m = matchMedia(q)
    const on = () => setN(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [q])
  return n
}

/**
 * The beat deck: 16 pads with per-pad sounds and FX, a 16-step sequencer, the keys with a preset
 * grid and a key sequence, and the sound library. Record writes pad hits, key notes and MIDI notes
 * into the pattern on the nearest 16th. Built mobile first: every control is finger sized.
 */
export function Deck({ history }: Props) {
  const [view, setView] = useState<View>('pads')
  useSyncExternalStore(padBank.subscribe, padBank.version)
  const midiRev = useSyncExternalStore((fn) => midi.subscribe(fn), () => `${midi.status}|${midi.inputs.join(',')}|${midi.routing}|${midi.lastNote}`)
  void midiRev
  const narrow = useNarrow()
  const padName = (i: number) => padBank.get(i)?.name ?? PADS[i].name
  const [hitPads, setHitPads] = useState<Set<number>>(new Set())
  const [held, setHeld] = useState<Set<number>>(new Set())
  const [step, setStep] = useState(-1)
  const [seqOn, setSeqOn] = useState(false)
  const [rec, setRec] = useState(false)
  const [metro, setMetro] = useState(true)
  const [selPad, setSelPad] = useState(0)
  const [page, setPage] = useState(0)
  const [allRows, setAllRows] = useState(false)
  const [cat, setCat] = useState<string>('Keys')
  const [showEditor, setShowEditor] = useState(true)
  const proj = history.state
  const projRef = useRef(proj)
  projRef.current = proj
  const live = useRef({ rec, view, selPad })
  live.current = { rec, view, selPad }
  const owner = useRef<{ id: number; release: () => void } | null>(null)
  if (!owner.current) owner.current = claimDeck()
  useEffect(() => () => owner.current?.release(), [])
  const mine = () => ownsInput(owner.current!.id)

  const base = 48 + proj.synth.octave * 12 // C3 at octave 0
  keySampler.pad = selPad

  const flash = (i: number) => {
    setHitPads((s) => new Set(s).add(i))
    window.setTimeout(() => setHitPads((s) => { const n = new Set(s); n.delete(i); return n }), 140)
  }

  // ---- record helpers
  const recStep = () => (audio.ctx ? sequencer.stepAt(audio.ctx.currentTime) : 0)
  const writePad = (i: number) => {
    const st = recStep()
    history.commit(`Record ${padName(i)} on step ${st + 1}`, (s) =>
      s.pattern[i][st] ? s : syncActivePattern(s, s.pattern.map((row, p) => (p === i ? row.map((v, k) => (k === st ? true : v)) : row))))
  }
  const pendingNotes = useRef(new Map<number, { t: number; step: number; vel: number }>())

  const hitPad = useCallback((i: number, vel = 1) => {
    audio.unlock()
    const ctx = audio.ensure()
    PADS[i].play(ctx.currentTime + 0.005, projRef.current.pads, undefined, vel)
    flash(i)
    if (live.current.rec && sequencer.running) writePad(i)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const on = useCallback((n: number, vel = 0.8) => {
    audio.unlock()
    noteOn(n, projRef.current.synth, vel)
    setHeld((s) => new Set(s).add(n))
    if (live.current.rec && sequencer.running && audio.ctx) pendingNotes.current.set(n, { t: audio.ctx.currentTime, step: recStep(), vel })
  }, [])
  const off = useCallback((n: number) => {
    noteOff(n, projRef.current.synth)
    setHeld((s) => { const x = new Set(s); x.delete(n); return x })
    const p = pendingNotes.current.get(n)
    if (p && audio.ctx) {
      pendingNotes.current.delete(n)
      const len = Math.max(1, Math.min(16, Math.round((audio.ctx.currentTime - p.t) / sequencer.stepSeconds)))
      const note: KeyNote = { step: p.step, note: n, len, vel: Math.round(p.vel * 100) / 100 }
      history.commit(`Record ${noteName(n)} on step ${p.step + 1}`, (s) => ({ ...s, keyNotes: [...s.keyNotes.filter((k) => !(k.step === note.step && k.note === note.note)), note] }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // MIDI: learned targets, and unlearned notes through the default layout
  useEffect(() => {
    const onMidi = (e: Event) => {
      if (!mine()) return
      const { target, value } = (e as CustomEvent).detail
      if (target.kind === 'pad' && value > 0.01) hitPad(target.index, Math.max(0.2, value))
      if (target.kind === 'key') { if (value > 0) on(target.note, value); else off(target.note) }
    }
    const onNote = (e: Event) => {
      if (!mine()) return
      const { note, value, channel } = (e as CustomEvent).detail as { note: number; value: number; channel: number }
      const t = routeNote(note, channel, midi.routing, live.current.view === 'keys' ? 'keys' : live.current.view === 'pads' ? 'pads' : 'other')
      if (t.kind === 'pad') { if (value > 0) { hitPad(t.index, Math.max(0.2, value)); setSelPad(t.index) } }
      else if (value > 0) on(t.note, value)
      else off(t.note)
    }
    window.addEventListener('midi-control', onMidi)
    window.addEventListener('midi-note', onNote)
    return () => { window.removeEventListener('midi-control', onMidi); window.removeEventListener('midi-note', onNote) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hitPad, on, off])

  // sequencer wiring
  useEffect(() => {
    sequencer.getPattern = () => projRef.current.pattern
    sequencer.getBpm = () => projRef.current.bpm
    sequencer.getPad = () => projRef.current.pads
    sequencer.getKeyNotes = () => projRef.current.keyNotes ?? []
    sequencer.getSynth = () => projRef.current.synth
    sequencer.getArrangement = () => {
      const beat = ensureBeat(projRef.current)
      return { arrangement: beat.arrangement!, patterns: beat.patterns! }
    }
    sequencer.onStep = (s) => {
      const st = s < 0 ? -1 : s % 16
      setStep(st)
      if (st >= 0) projRef.current.pattern.forEach((row, p) => row[st] && flash(p))
    }
    setSeqOn(sequencer.running)
  }, [])
  useEffect(() => { sequencer.metronome = rec && metro }, [rec, metro])
  useEffect(() => () => { if (mine()) { sequencer.metronome = false } }, [])

  const togglePlay = () => {
    audio.unlock()
    if (sequencer.running) { sequencer.stop(); setSeqOn(false); setRec(false) } else { sequencer.mode = 'pattern'; sequencer.start(); setSeqOn(true) }
  }
  const toggleRec = () => {
    audio.unlock()
    if (rec) { setRec(false); return }
    setRec(true)
    if (sequencer.running && sequencer.mode === 'arrange') sequencer.stop()
    if (!sequencer.running) { sequencer.mode = 'pattern'; sequencer.start(); setSeqOn(true) }
  }

  // computer keyboard
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (!mine() || e.repeat || typing(e) || e.ctrlKey || e.metaKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (view === 'pads') {
        const i = PADS.findIndex((p) => p.key === k)
        if (i >= 0) { e.preventDefault(); hitPad(i); setSelPad(i) }
      } else if (view === 'keys') {
        const i = KEY_MAP.indexOf(k)
        if (i >= 0) { e.preventDefault(); on(base + i) }
        if (k === 'z') history.commit('Octave down', (s) => ({ ...s, synth: { ...s.synth, octave: Math.max(-2, s.synth.octave - 1) } }))
        if (k === 'x') history.commit('Octave up', (s) => ({ ...s, synth: { ...s.synth, octave: Math.min(2, s.synth.octave + 1) } }))
      }
    }
    const up = (e: KeyboardEvent) => {
      if (view !== 'keys' || !mine()) return
      const i = KEY_MAP.indexOf(e.key.toLowerCase())
      if (i >= 0) off(base + i)
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, base, hitPad, on, off, history])

  useEffect(() => () => allNotesOff(), [])

  const toggleStep = (pad: number, st: number) => {
    audio.unlock()
    history.commit(`${padName(pad)} step ${st + 1}`, (s) =>
      syncActivePattern(s, s.pattern.map((row, p) => (p === pad ? row.map((v, i) => (i === st ? !v : v)) : row))))
  }

  const setSynth = (label: string, patch: Partial<SynthParams>) => history.commit(label, (s) => ({ ...s, synth: { ...s.synth, ...patch } }))
  const pickPreset = (id: string) => {
    audio.unlock()
    const p = presetById(id)
    if (!p) return
    if (soundfont.hasFont()) soundfont.unloadFont()
    setSynth(`Keys preset ${p.name}`, { wave: 'sawtooth', ...p.base, preset: id, volume: projRef.current.synth.volume, octave: p.base.octave ?? 0 })
    // a short preview note
    window.setTimeout(() => { noteOn(60 + (p.base.octave ?? 0) * 12, { ...projRef.current.synth }, 0.8); window.setTimeout(() => noteOff(60 + (p.base.octave ?? 0) * 12, projRef.current.synth), 260) }, 0)
  }

  const beat = ensureBeat(proj)
  const [dropPad, setDropPad] = useState<number | null>(null)
  const [dropErr, setDropErr] = useState('')
  const sfRef = useRef<HTMLInputElement>(null)
  const [, bumpFont] = useState(0)
  /** A file dropped on a pad goes through the same checks as an upload. */
  const dropOnPad = async (i: number, file: File) => {
    setDropErr('')
    try {
      const v = await validateAudioFile(file)
      padBank.set(i, { name: v.name, buffer: v.buffer, pitch: 0, rate: 1, gain: 1, source: { kind: 'upload' } })
      setSelPad(i)
      hitPad(i)
    } catch (e) {
      setDropErr(e instanceof UploadError ? e.message : 'Could not load that file.')
    }
  }
  const loadFont = async (file: File) => {
    setDropErr('')
    try {
      if (!/\.sf2$/i.test(file.name)) throw new Error('Pick an .sf2 soundfont.')
      if (file.size > 200 * 1024 * 1024) throw new Error('That soundfont is over 200 MB.')
      await soundfont.loadFile(file)
      bumpFont((n) => n + 1)
    } catch (e) {
      setDropErr(e instanceof Error ? e.message : 'Could not load that soundfont.')
    }
  }

  const rows = useMemo(() => {
    if (allRows) return PADS.map((_, i) => i)
    const set = new Set([0, 1, 2, 4, 5, 11, selPad])
    proj.pattern.forEach((r, i) => { if (r.some(Boolean)) set.add(i) })
    return [...set].sort((a, b) => a - b)
  }, [allRows, selPad, proj.pattern])
  const steps = narrow ? Array.from({ length: 8 }, (_, i) => i + page * 8) : Array.from({ length: 16 }, (_, i) => i)

  // keys: one octave on phones, two on wider screens
  const span = narrow ? 13 : 25
  const keys = Array.from({ length: span }, (_, i) => base + i)
  const whites = keys.filter((n) => !isBlack(n))
  const pointerNote = useRef<number | null>(null)
  const cur = presetById(proj.synth.preset)
  const rollNotes = [...new Set((proj.keyNotes ?? []).map((n) => n.note))].sort((a, b) => b - a)

  const midiChip = () => {
    if (midi.status === 'unsupported') return <span className="nd-midi none" data-testid="midi-status" title="Safari on iPhone and iPad has no Web MIDI">No Web MIDI here. Use touch, or Chrome on a computer or Android.</span>
    if (midi.status === 'ready') return (
      <span className="nd-midi ready" data-testid="midi-status">
        <b>MIDI</b> {midi.inputs.length ? midi.inputs.join(', ') : 'no device plugged in'}
        <select aria-label="MIDI layout" value={midi.routing} onChange={(e) => midi.setRouting(e.target.value as MidiRouting)}>
          <option value="auto">Auto</option><option value="pads">Pads 36-51</option><option value="keys">All to keys</option>
        </select>
        {midi.lastNote && <i>{midi.lastNote}</i>}
      </span>
    )
    return <button className="nd-btn small" data-testid="midi-connect" onClick={() => void midi.connect()} disabled={midi.status === 'pending'}>{midi.status === 'denied' ? 'MIDI blocked, retry' : midi.status === 'pending' ? 'Connecting' : 'Connect MIDI'}</button>
  }

  return (
    <section className="panel deck nd" data-testid="deck" data-view={view}>
      <div className="nd-head">
        <div className="nd-tabs" role="tablist" aria-label="Deck">
          {([['pads', 'Pads'], ['keys', 'Keys'], ['sounds', 'Sounds'], ['arrange', 'Arrange']] as [View, string][]).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={view === k} className={view === k ? 'on' : ''} onClick={() => setView(k)} data-testid={`deck-${k}`}>{l}</button>
          ))}
        </div>
        <div className="nd-transport">
          <button className={`nd-btn ${seqOn ? 'pri' : ''}`} onClick={togglePlay} data-testid="seq-play" aria-pressed={seqOn}>{seqOn ? '■ Stop' : '▶ Play'}</button>
          <button className={`nd-btn rec ${rec ? 'armed' : ''}`} onClick={toggleRec} data-testid="rec" aria-pressed={rec}>● {rec ? 'Recording' : 'Rec'}</button>
          <button className={`nd-btn small ghost ${metro ? 'on' : ''}`} onClick={() => setMetro((m) => !m)} aria-pressed={metro} title="Click while recording">Click</button>
          <span className="nd-bpm">
            <button className="nd-icon" aria-label="Slower" onClick={() => history.commit('BPM', (s) => ({ ...s, bpm: Math.max(60, s.bpm - 1) }))}>−</button>
            <span data-testid="bpm-value">{proj.bpm} BPM</span>
            <button className="nd-icon" aria-label="Faster" onClick={() => history.commit('BPM', (s) => ({ ...s, bpm: Math.min(180, s.bpm + 1) }))}>+</button>
          </span>
        </div>
        <div className="nd-midi-wrap">{midiChip()}</div>
      </div>

      {view === 'pads' && (
        <div className="nd-body nd-pads">
          <div className="nd-pad-col">
            <div className="nd-grid" data-testid="pad-grid">
              {PADS.map((p, i) => {
                const s = padBank.get(i)
                const fx = padBank.settings(i).fx.filter((x) => x.on).length
                return (
                  <button
                    key={i}
                    className={`nd-pad ${hitPads.has(i) ? 'hit' : ''} ${selPad === i ? 'sel' : ''} ${s ? 'smp' : ''} ${dropPad === i ? 'drop' : ''}`}
                    data-testid={`pad-${i}`}
                    onPointerDown={(e) => { e.preventDefault(); hitPad(i); setSelPad(i) }}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); hitPad(i); setSelPad(i) } }}
                    onContextMenu={(e) => { e.preventDefault(); if (midi.supported) midi.startLearn({ kind: 'pad', index: i }) }}
                    onDragOver={(e) => { e.preventDefault(); setDropPad(i) }}
                    onDragLeave={() => setDropPad((c) => (c === i ? null : c))}
                    onDrop={(e) => { e.preventDefault(); setDropPad(null); const f = e.dataTransfer.files[0]; if (f) void dropOnPad(i, f) }}
                    aria-label={`Pad ${i + 1} ${padName(i)}`}
                  >
                    <span className="nd-pad-n">{padName(i)}</span>
                    <span className="nd-pad-m">
                      <em>{i + 1}</em>
                      {fx > 0 && <i>FX {fx}</i>}
                      {!narrow && <kbd>{p.key.toUpperCase()}</kbd>}
                    </span>
                  </button>
                )
              })}
            </div>
            <p className="nd-hint">{narrow ? 'Tap a pad to play it and edit it below.' : 'Keys 1-4, Q-R, A-F, Z-V play pads. Drop an audio file on a pad. Right-click a pad to MIDI learn.'}</p>
            {dropErr && <p className="nd-err" role="alert">{dropErr}</p>}
          </div>

          <div className="nd-side">
            <div className="nd-seq" data-testid="sequencer">
              <div className="nd-seq-head">
                <b>Pattern</b>
                {narrow && (
                  <span className="nd-seg small">
                    <button className={page === 0 ? 'on' : ''} onClick={() => setPage(0)} data-testid="page-0">1-8</button>
                    <button className={page === 1 ? 'on' : ''} onClick={() => setPage(1)} data-testid="page-1">9-16</button>
                  </span>
                )}
                <button className="nd-btn small ghost" onClick={() => setAllRows((v) => !v)}>{allRows ? 'Fewer rows' : 'All 16 rows'}</button>
                <button className="nd-btn small ghost" onClick={() => history.commit('Clear pattern', (s) => syncActivePattern(s, s.pattern.map((r) => r.map(() => false))))} data-testid="clear-pattern">Clear</button>
                <select
                  className="nd-select"
                  aria-label="Pattern"
                  value={beat.activePatternId}
                  onChange={(e) => {
                    const id = e.target.value
                    history.commit('Select pattern', (s) => {
                      const next = ensureBeat(s)
                      const pat = next.patterns!.find((item) => item.id === id)
                      return pat ? { ...next, activePatternId: id, pattern: cloneSteps(pat.steps) } : next
                    })
                  }}
                  data-testid="pattern-select"
                >
                  {beat.patterns!.map((pat) => <option key={pat.id} value={pat.id}>{pat.name}</option>)}
                </select>
              </div>
              <div className="nd-seq-rows" style={{ ['--steps' as string]: steps.length }}>
                {rows.map((pad) => (
                  <div className={`nd-seq-row ${pad === selPad ? 'sel' : ''}`} key={pad} data-testid={`seq-row-${pad}`}>
                    {narrow
                      ? <span className="nd-seq-label">{pad + 1} {padName(pad)}</span>
                      : <button className="nd-seq-label" onClick={() => setSelPad(pad)}>{pad + 1} {padName(pad)}</button>}
                    <div className="nd-steps">
                      {steps.map((st) => (
                        <button
                          key={st}
                          className={`nd-step ${proj.pattern[pad][st] ? 'on' : ''} ${st === step ? 'now' : ''} ${st % 4 === 0 ? 'beat' : ''}`}
                          onClick={() => toggleStep(pad, st)}
                          aria-pressed={proj.pattern[pad][st]}
                          aria-label={`${padName(pad)} step ${st + 1}`}
                          data-testid={`step-${pad}-${st}`}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="nd-ed-wrap">
              <button className="nd-ed-toggle" onClick={() => setShowEditor((v) => !v)} aria-expanded={showEditor}>
                {showEditor ? 'Hide' : 'Show'} pad {selPad + 1} sound and FX
              </button>
              {showEditor && <PadEditor pad={selPad} onAudition={() => hitPad(selPad)} onBrowse={() => setView('sounds')} />}
            </div>
          </div>
        </div>
      )}

      {view === 'arrange' && (
        <div className="nd-body nd-arrange" data-testid="deck-arrange-body">
          <Arranger history={history} />
        </div>
      )}

      {view === 'sounds' && (
        <div className="nd-body">
          <SoundBrowser pad={selPad} setPad={setSelPad} onAssigned={(i) => { hitPad(i); setSelPad(i) }} onKeys={() => { pickPreset('lib-sampler'); setView('keys') }} />
        </div>
      )}

      {view === 'keys' && (
        <div className="nd-body nd-keys">
          <div className="nd-presets">
            <div className="nd-chips" role="group" aria-label="Preset category">
              {KEY_CATS.map((c) => <button key={c} className={`nd-chip ${cat === c ? 'on' : ''}`} onClick={() => setCat(c)} data-testid={`keycat-${c}`}>{c}</button>)}
            </div>
            <div className="nd-preset-grid" data-testid="key-presets">
              {KEY_PRESETS.filter((p) => p.cat === cat).map((p) => (
                <button key={p.id} className={`nd-preset ${proj.synth.preset === p.id ? 'on' : ''}`} onClick={() => pickPreset(p.id)} data-testid={`key-preset-${p.id}`} aria-pressed={proj.synth.preset === p.id}>
                  <b>{p.name}</b>
                  <i>{p.sample === 'pad' ? `Pad ${selPad + 1}: ${padName(selPad)}` : p.sample === 'library' ? (keySampler.libraryName || 'Pick in Sounds') : p.cat}</i>
                </button>
              ))}
            </div>
            <p className="nd-hint">
              {KEY_PRESETS.length} presets, all synthesized in the browser. <b>{soundfont.hasFont() ? `Soundfont: ${soundfont.fontName()}` : (cur?.name ?? 'Custom')}</b> is loaded.{' '}
              <button className="nd-btn small ghost" onClick={() => sfRef.current?.click()} data-testid="load-sf2">Load .sf2</button>
              <input ref={sfRef} type="file" hidden accept=".sf2" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void loadFont(f) }} />
            </p>
            {view === 'keys' && dropErr && <p className="nd-err" role="alert">{dropErr}</p>}
          </div>

          <div className="nd-oct">
              <button className="nd-icon" aria-label="Octave down" onClick={() => setSynth('Octave down', { octave: Math.max(-2, proj.synth.octave - 1) })} data-testid="oct-down">−</button>
              <span>Octave {proj.synth.octave >= 0 ? '+' : ''}{proj.synth.octave}</span>
              <button className="nd-icon" aria-label="Octave up" onClick={() => setSynth('Octave up', { octave: Math.min(2, proj.synth.octave + 1) })} data-testid="oct-up">+</button>
            </div>
          <div
            className="nd-piano"
            data-testid="piano"
            onPointerLeave={() => { if (pointerNote.current !== null) { off(pointerNote.current); pointerNote.current = null } }}
          >
            {whites.map((n) => (
              <div key={n} className="nd-white-slot">
                <PianoKey n={n} black={false} held={held.has(n)} pointerNote={pointerNote} on={on} off={off} />
                {!isBlack(n + 1) || n === keys[keys.length - 1] ? null : (
                  <PianoKey n={n + 1} black held={held.has(n + 1)} pointerNote={pointerNote} on={on} off={off} />
                )}
              </div>
            ))}
          </div>
          <p className="nd-hint">{narrow ? 'Use the octave buttons to reach higher or lower notes.' : 'Keys A to ; play notes, W E T Y U O P for sharps, Z and X change octave.'} Press Rec, then play: notes land in the key sequence below.</p>

          <div className="nd-roll" data-testid="key-roll">
            <div className="nd-seq-head">
              <b>Key sequence</b>
              <span className="nd-muted">{(proj.keyNotes ?? []).length} notes, plays with the pattern</span>
              <button className="nd-btn small ghost" onClick={() => history.commit('Clear key notes', (s) => ({ ...s, keyNotes: [] }))} disabled={!(proj.keyNotes ?? []).length} data-testid="clear-notes">Clear</button>
            </div>
            {rollNotes.length ? (
              <div className="nd-roll-grid" style={{ ['--steps' as string]: 16 }}>
                {rollNotes.map((n) => (
                  <div key={n} className="nd-roll-row">
                    <span className="nd-roll-label">{noteName(n)}</span>
                    <div className="nd-roll-cells">
                      {Array.from({ length: 16 }, (_, st) => {
                        const k = proj.keyNotes.find((x) => x.note === n && x.step === st)
                        const covered = proj.keyNotes.some((x) => x.note === n && st > x.step && st < x.step + x.len)
                        return (
                          <button key={st} className={`nd-roll-cell ${k ? 'on' : covered ? 'tail' : ''} ${st === step ? 'now' : ''} ${st % 4 === 0 ? 'beat' : ''}`}
                            aria-label={`${noteName(n)} step ${st + 1}`}
                            onClick={() => history.commit(k ? 'Remove note' : 'Add note', (s) => ({ ...s, keyNotes: k ? s.keyNotes.filter((x) => x !== k) : [...s.keyNotes, { step: st, note: n, len: 1, vel: 0.8 }] }))} />
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="nd-muted">Nothing recorded yet.</p>}
          </div>
          <details className="nd-synth" open={!narrow}>
            <summary>Shape the sound</summary>
            <div className="nd-seg" role="group" aria-label="Wave">
              {WAVES.map((w) => <button key={w} className={proj.synth.wave === w ? 'on' : ''} onClick={() => setSynth(`Wave ${w}`, { wave: w })}>{w.slice(0, 3).toUpperCase()}</button>)}
            </div>
            <div className="nd-synth-sliders">
              <Slider label="Cutoff" value={proj.synth.cutoff} min={0} max={1} format={(v) => `${Math.round(120 * Math.pow(2, v * 7.5))} Hz`} onChange={(v) => history.preview((s) => ({ ...s, synth: { ...s.synth, cutoff: v } }))} />
              <Slider label="Reso" value={proj.synth.reso} min={0} max={1} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => history.preview((s) => ({ ...s, synth: { ...s.synth, reso: v } }))} />
              <Slider label="Attack" value={proj.synth.attack} min={0.002} max={1.5} log format={(v) => `${Math.round(v * 1000)} ms`} onChange={(v) => history.preview((s) => ({ ...s, synth: { ...s.synth, attack: v } }))} />
              <Slider label="Release" value={proj.synth.release} min={0.02} max={3} log format={(v) => `${v.toFixed(2)} s`} onChange={(v) => history.preview((s) => ({ ...s, synth: { ...s.synth, release: v } }))} />
              <Slider label="Detune" value={proj.synth.detune} min={0} max={30} format={(v) => `${v.toFixed(0)} c`} onChange={(v) => history.preview((s) => ({ ...s, synth: { ...s.synth, detune: v } }))} />
              <Slider label="Level" value={proj.synth.volume} min={0} max={1} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => history.preview((s) => ({ ...s, synth: { ...s.synth, volume: v } }))} />
            </div>
          </details>
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
    return 0.4 + 0.6 * Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))
  }
  return (
    <div
      className={`nd-key ${black ? 'black' : 'white'} ${held ? 'held' : ''}`}
      role="button"
      aria-label={`Note ${noteName(n)}`}
      onPointerDown={(e) => {
        e.preventDefault()
        e.stopPropagation()
        ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
        pointerNote.current = n
        on(n, vel(e))
      }}
      onPointerEnter={(e) => {
        if ((e.buttons & 1 || e.pointerType === 'touch') && pointerNote.current !== null && pointerNote.current !== n) {
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
      onPointerCancel={() => { if (pointerNote.current !== null) off(pointerNote.current); pointerNote.current = null }}
      onContextMenu={(e) => { e.preventDefault(); if (midi.supported) midi.startLearn({ kind: 'key', note: n }) }}
      data-note={n}
      data-testid={`key-${n}`}
    >
      {label && <span className="nd-key-label">{label}</span>}
    </div>
  )
}
