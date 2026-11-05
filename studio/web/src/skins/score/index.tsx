import { useEffect, useMemo, useRef, useState } from 'react'
import { isBrowserDemo } from '../../api'
import '@fontsource/instrument-serif/400.css'
import '@fontsource/instrument-serif/400-italic.css'
import '@fontsource/instrument-sans/400.css'
import '@fontsource/instrument-sans/500.css'
import '@fontsource/instrument-sans/600.css'
import '@fontsource/dm-mono/400.css'
import '@fontsource/dm-mono/500.css'
import '@fontsource/bravura/400.css'
import './score.css'
import { audio } from '../../audio/engine'
import { Knob } from '../../components/Knob'
import { RackBody, RackTabs } from '../../components/pro/RackPanel'
import { Waveform } from '../../components/Waveform'
import { ENDS, useEasy } from '../../studio/EasyContext'
import { MASTER, useRack } from '../../studio/RackContext'
import { useStudio, type Channel } from '../../studio/StudioContext'
import { MACRO_META, TOOLS, dynFor, familyOf, fmtTime, tempoWord } from '../../studio/vibe'
import { NB, prefersReducedMotion, stemLevel, useFrame, viz } from '../../studio/viz'
import { ComposerPane, DeckPane, LibraryPane } from '../shared/Panes'
import { Overview } from '../shared/Overview'
import { NoDawButton, SkinButton } from '../shared/SkinSwitcher'
import { MasterKnob, STRIP_PARAMS, StemActions, useStrip, db } from '../shared/Stems'
import { DemoBadge, EnginesButton, HistoryControls, SysLeds } from '../shared/TopParts'
import { useDrag } from '../shared/hooks'
import { useSkin } from '../SkinProvider'
import { transcribe, clefFor } from './notation'
import { Staff, useScoreMotion } from './Staff'

const DYN: Record<string, string> = { ppp: '\uE52A', pp: '\uE52B', p: '\uE520', mp: '\uE52C', mf: '\uE52D', f: '\uE522', ff: '\uE52F', fff: '\uE530' }
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX', 'XXI', 'XXII', 'XXIII', 'XXIV']
const pad = (n: number, w = 2) => String(Math.round(n)).padStart(w, '0')
const MACRO_OF: Record<string, 'energy' | 'bass' | 'brightness' | 'vocals'> = { drums: 'energy', bass: 'bass', vocals: 'vocals', voice: 'vocals', vocal: 'vocals' }
const ROLE_LABEL: Record<string, string> = { drums: 'Percussion', bass: 'Bass', vocals: 'Voice', other: 'Harmony', mix: 'Full mix' }
const PLACEHOLDER: Channel[] = [
  { id: '_p0', name: 'Percussion', color: '', url: '', role: 'drums' },
  { id: '_p1', name: 'Bass', color: '', url: '', role: 'bass' },
  { id: '_p2', name: 'Harmony', color: '', url: '', role: 'other' },
  { id: '_p3', name: 'Voice', color: '', url: '', role: 'vocals' },
]
const labelOf = (c: Channel) => ROLE_LABEL[c.role] ?? (c.name.charAt(0).toUpperCase() + c.name.slice(1))

function Dyn({ v, className }: { v: number; className?: string }) {
  return <span className={`cb-dyn ${className ?? ''}`} aria-hidden>{DYN[dynFor(v)]}</span>
}

/** Spectrum drawn as seismograph ticks. Throttled and static-friendly under reduced motion. */
function Seismo() {
  const cv = useRef<HTMLCanvasElement>(null)
  const reduced = useRef(prefersReducedMotion())
  const tick = useRef(0)
  useFrame((f) => {
    const c = cv.current
    if (!c) return
    if (reduced.current && tick.current++ % 12) return
    const ctx = c.getContext('2d')!
    const w = c.clientWidth
    const h = c.clientHeight
    const d = Math.min(devicePixelRatio, 2)
    if (c.width !== Math.round(w * d)) {
      c.width = Math.round(w * d)
      c.height = Math.round(h * d)
    }
    ctx.setTransform(d, 0, 0, d, 0, 0)
    ctx.clearRect(0, 0, w, h)
    const n = Math.floor(w / 5)
    ctx.lineWidth = 1
    const cs = getComputedStyle(c)
    const hot = cs.getPropertyValue('--hot').trim() || '#D9361E'
    for (let i = 0; i < n; i++) {
      const t = i / n
      const b = Math.min(NB - 1, Math.floor(Math.pow(t, 0.8) * (NB - 1)))
      const v = Math.min(1, (f.spec[b] ?? 0) * 1.35)
      const x = Math.round(i * (w / n)) + 0.5
      const len = 3 + v * (h - 4)
      ctx.strokeStyle = `rgba(11,11,12,${0.18 + v * 0.8})`
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, len)
      ctx.stroke()
      if (v > 0.55) {
        ctx.fillStyle = hot
        ctx.fillRect(x - 1, len - 1, 3, 2)
      }
    }
  })
  return <canvas ref={cv} className="cb-seismo" aria-hidden />
}

function Title({ text, small }: { text: string; small?: boolean }) {
  return (
    <h1 key={text} className={`cb-title ${small ? 'sm' : ''}`} aria-label={text} style={{ ['--n' as string]: Math.max(small ? 10 : 7, text.length) }}>
      {text.split('').map((c, i) => (
        <span key={i} className="ch" aria-hidden><i style={{ animationDelay: `${i * 18}ms` }}>{c === ' ' ? '\u00A0' : c}</i></span>
      ))}
    </h1>
  )
}

/* ---------------- top ---------------- */
function Top() {
  const { mode, setMode, current: track } = useStudio()
  const easy = useEasy()
  const { setHelpOpen } = useSkin()
  const lufs = easy.report?.lufs ?? easy.analysis?.lufs
  return (
    <header className="cb-top">
      <a className="cb-brand" href="#/" onClick={(e) => e.preventDefault()}><span>NoDAW Studio <em>PRO</em></span><i>built on the-muser</i></a>
      <nav className="cb-modes" data-mode={mode} role="tablist" aria-label="Studio mode">
        <button role="tab" aria-selected={mode === 'easy'} data-testid="mode-easy" className={mode === 'easy' ? 'on' : ''} onClick={() => setMode('easy')}>Easy</button>
        <b>/</b>
        <button role="tab" aria-selected={mode === 'advanced'} data-testid="mode-advanced" className={mode === 'advanced' ? 'on' : ''} onClick={() => setMode('advanced')}>Advanced</button>
      </nav>
      <div className="cb-read">
        <span className="cb-r"><span className="cb-gl">{'\uE1D5'}</span> = {track?.bpm ? Math.round(track.bpm) : '--'}</span>
        <span className="cb-r">{track?.key ?? 'no key'}</span>
        <span className="cb-r">{lufs != null ? `${lufs.toFixed(1)} LUFS` : 'unmastered'}</span>
        <DemoBadge />
        <NoDawButton />
        <SkinButton />
        <SysLeds />
        <EnginesButton>Engines <b>8 GB</b></EnginesButton>
        <button className="cb-q" onClick={() => setHelpOpen(true)} aria-label="Shortcuts">?</button>
      </div>
    </header>
  )
}

/* ---------------- catalogue ---------------- */
function MakeBlock() {
  const easy = useEasy()
  const fill = useRef<HTMLElement>(null)
  useFrame(() => {
    if (fill.current) fill.current.style.transform = `scaleX(${easy.busy ? Math.max(0.04, viz.making) : 0})`
  }, [easy.busy])
  const phase = easy.busy ? 'making' : easy.track ? 'ready' : 'idle'
  return (
    <div className="cb-make-block">
      <label className="cb-brief"><span>Brief</span><input data-prompt data-focus-target data-testid="prompt" aria-label="Describe the vibe" placeholder="rainy night drive, warm and dusty" value={easy.vibe} onChange={(e) => easy.setVibe(e.target.value)} maxLength={300} /></label>
      <button className="cb-make" data-testid="make" data-phase={phase} onClick={() => void easy.make()} disabled={!!easy.busy}>
        <span>{easy.busy ? easy.busy.replace(/\.+$/, '') : phase === 'ready' ? 'Make it again' : 'Make it'}</span>
        <em>Enter</em>
        <s ref={fill} />
      </button>
      <button className="cb-link own" onClick={easy.pickUpload}>or use your own audio</button>
    </div>
  )
}

function Catalogue({ onHover }: { onHover: (id: string | null) => void }) {
  const easy = useEasy()
  return (
    <>
      <h2 className="cb-h"><span>Catalogue</span><i>{easy.tiles.length} works</i><button className="cb-link" data-testid="show-all" onClick={() => easy.setShowAll((s) => !s)}>{easy.showAll ? 'curated' : `all ${easy.all.length}`}</button></h2>
      <ol className="cb-cat" data-testid="vibes" onPointerLeave={() => onHover(null)}>
        {easy.tiles.map((p, i) => (
          <li key={p.id}>
            <button className={easy.genreId === p.id ? 'on' : ''} data-cart={p.id} onPointerEnter={() => onHover(p.id)} onFocus={() => onHover(p.id)} onBlur={() => onHover(null)} onClick={() => easy.selectGenre(p)} aria-pressed={easy.genreId === p.id}>
              <i>{ROMAN[i] ?? i + 1}</i><b>{p.name}</b><u /><em>{p.generate?.bpm ?? ''}</em>
            </button>
          </li>
        ))}
      </ol>
      <MakeBlock />
    </>
  )
}

/* ---------------- dynamics (macros) ---------------- */
function DynRow({ k }: { k: (typeof MACRO_META)[number] }) {
  const easy = useEasy()
  const { selMacro, setSelMacro } = useSkin()
  const val = Math.round(easy.macros[k.key])
  const genre = easy.all.find((p) => p.id === easy.genreId)
  const base = genre?.macros?.[k.key] ?? 50
  const drag = useDrag((v) => easy.setMacro(k.key, Math.round(v * 100)), { onEnd: () => easy.commitMacros() })
  const [lo, hi] = ENDS[k.key]
  return (
    <div className="cb-dr" data-sel={selMacro === k.key} data-macro={k.key} onPointerDown={() => setSelMacro(k.key)}>
      <div className="cb-dr-h"><span>{k.label}</span><em>{dynFor(val)}</em><b>{pad(val, 3)}</b></div>
      <div className="cb-track" {...drag} role="slider" aria-label={k.label} aria-valuenow={val} aria-valuemin={0} aria-valuemax={100} tabIndex={0} title={k.help}>
        <div className="cb-tt" />
        <div className="cb-base" style={{ left: `${base}%` }} />
        <div className="cb-thumb" style={{ left: `${val}%` }}><Dyn v={val} /><s /></div>
      </div>
      <div className="cb-ends"><span>{lo}</span><span>{hi}</span></div>
    </div>
  )
}

function RightEasy() {
  const easy = useEasy()
  const lock = !easy.track || !!easy.busy
  const cur = easy.report?.target?.key
  return (
    <>
      <h2 className="cb-h"><span>Dynamics</span><button className="cb-link" onClick={easy.resetMacros}>Reset</button></h2>
      <div className="cb-drs" data-testid="macros">{MACRO_META.map((m) => <DynRow key={m.key} k={m} />)}</div>
      <h2 className="cb-h"><span>Finish</span><i>LUFS / dBTP</i></h2>
      <div className="cb-fin" data-testid="finish">
        {Object.entries(easy.targets).map(([k, f]) => (
          <button key={k} className={cur === k ? 'on' : ''} disabled={lock} title={f.note} onClick={() => void easy.finish(k)}><span>{f.label}</span><u /><em>{f.lufs} / {f.true_peak_db}</em></button>
        ))}
      </div>
      <div className="cb-meas" data-testid="measure">
        {easy.busy ? <span className="cb-busy"><s />{easy.busy}</span>
          : easy.report ? <span>Measured <b>{easy.report.lufs.toFixed(1)} LUFS</b> · <b>{easy.report.true_peak_db.toFixed(1)} dBTP</b></span>
          : easy.analysis ? <span>Measured <b>{easy.analysis.lufs?.toFixed(1) ?? '--'} LUFS</b> · <b>{easy.analysis.true_peak_db.toFixed(1)} dBTP</b></span>
          : <span className="dim">No clipping. Pick a target to master.</span>}
      </div>
      <button className="cb-export" data-testid="export" disabled={lock} onClick={() => void easy.doExport()}><span>{isBrowserDemo() ? 'Export WAV + stems' : 'Export WAV + MP3'}</span><em>X</em></button>
      {(easy.files || easy.midi) && (
        <div className="cb-files" data-testid="files">
          {easy.files && Object.entries(easy.files).map(([k, url]) => <a key={k} href={url} download>{decodeURIComponent(url.split('/').pop() ?? k)}<i>{k}</i></a>)}
          {easy.midi && <a href={easy.midi} download>MIDI<i>mid</i></a>}
        </div>
      )}
      <h2 className="cb-h"><span>One click</span></h2>
      <div className="cb-tools" data-testid="tools">
        {TOOLS.map((t, i) => (
          <button key={t.name} disabled={lock} data-tool={t.name} onClick={() => ('reference' in t ? easy.pickReference() : void easy.tool(t.name, t.label, 'extra' in t ? (t.extra as Record<string, unknown>) : undefined))}>
            <i>{i + 1}</i><span>{t.label}</span><em>→</em>
          </button>
        ))}
      </div>
    </>
  )
}

/* ---------------- score ---------------- */
function StaffRow({ ch, adv, win, bpm, reveal }: { ch: Channel; adv: boolean; win: number; bpm: number; reveal: number }) {
  const { buffersVersion, mixer } = useStudio()
  const rack = useRack()
  const easy = useEasy()
  const strip = useStrip(ch)
  const clef = clefFor(ch.role)
  const real = !ch.id.startsWith('_p')
  // buffersVersion changes when decoded audio changes, which the buffer lookup itself cannot signal
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const ev = useMemo(() => (real ? transcribe(audio.buffer(ch.id) ?? null, bpm, clef, win * 4) : []), [real, ch.id, bpm, clef, win, buffersVersion])
  const mk = MACRO_OF[ch.role] ?? 'brightness'
  const lv = useRef<HTMLDivElement>(null)
  useFrame(() => {
    if (lv.current) lv.current.style.transform = `scaleX(${real ? Math.min(1, stemLevel(ch.id) ** 0.9 * 1.15) : 0})`
  })
  const gain = mixer[ch.id]?.gain_db ?? 0
  return (
    <div className={`cb-row ${strip.audible ? '' : 'is-silent'}`} data-testid="lane" data-sel={rack.sel === ch.id} data-stem={ch.role} onPointerDown={() => real && rack.setSel(ch.id)}>
      <div className="cb-rh">
        <div className="cb-rn"><span>{labelOf(ch)}</span><Dyn v={easy.macros[mk]} /></div>
        {adv && real && (
          <div className="cb-rc">
            <button className={strip.p.mute ? 'on' : ''} onClick={strip.toggleMute} aria-pressed={strip.p.mute} aria-label={`Mute ${ch.name}`}>M</button>
            <button className={strip.p.solo ? 'on' : ''} onClick={strip.toggleSolo} aria-pressed={strip.p.solo} aria-label={`Solo ${ch.name}`}>S</button>
            <em>{db(gain)} dB</em>
          </div>
        )}
        <div className="cb-lv"><div ref={lv} /></div>
      </div>
      <Staff id={ch.id} clef={clef} ev={ev} hidden={reveal} />
    </div>
  )
}

function Score({ adv }: { adv: boolean }) {
  const { channels, current: track } = useStudio()
  const easy = useEasy()
  const root = useRef<HTMLDivElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  const bpm = track?.bpm || viz.bpm || 120
  const [win, setWin] = useState(0)
  const [reveal, setReveal] = useState(track ? 1 : 0)
  useScoreMotion(root, ph, bpm, win, setWin)
  useFrame(() => {
    const target = easy.busy ? Math.min(1, viz.making * 1.15) : track ? 1 : 0
    setReveal((r) => (Math.abs(r - target) > 0.015 ? target : r))
  }, [easy.busy, track])
  const rows = track && channels.length ? channels.slice(0, 6) : PLACEHOLDER
  return (
    <div className="cb-score" ref={root}>
      <div className="cb-bars" aria-hidden>{[1, 2, 3, 4].map((n, i) => <span key={n} style={{ ['--i' as string]: i }}>{win * 4 + n}</span>)}</div>
      <div className="cb-rows" data-testid="strips" style={{ gridTemplateRows: `repeat(${rows.length},minmax(0,1fr))` }}>
        {rows.map((c) => <StaffRow key={c.id} ch={c} adv={adv} win={win} bpm={bpm} reveal={reveal} />)}
      </div>
      <div className="cb-phlayer"><div className="cb-ph" ref={ph}><s /></div></div>
    </div>
  )
}

function Timecode() {
  const r = useRef<HTMLSpanElement>(null)
  useFrame(() => {
    if (r.current) r.current.textContent = fmtTime(audio.currentTime())
  })
  return <span ref={r} className="cb-tc">0:00</span>
}

function Transport({ adv, onDock, dock }: { adv?: boolean; onDock?: (d: Dock) => void; dock?: Dock }) {
  const easy = useEasy()
  const [, force] = useState(0)
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])
  const { versions, idx, setIdx } = easy
  return (
    <div className="cb-transport">
      {!adv && (
        <div className="cb-revs" data-testid="versions" data-count={versions.length}>
          <button onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={idx <= 0}>Undo</button>
          <button onClick={() => setIdx((i) => Math.min(versions.length - 1, i + 1))} disabled={idx >= versions.length - 1}>Redo</button>
          <ol>{versions.map((v, i) => <li key={i}><button className={i === idx ? 'on' : ''} onClick={() => setIdx(i)}><i>Rev. {i + 1}</i>{v.label}</button></li>)}</ol>
        </div>
      )}
      <div className="cb-tr-row">
        <button className="cb-play" data-testid="play" onClick={() => (audio.playing ? audio.pause() : audio.play())} data-playing={audio.playing} aria-label={audio.playing ? 'Pause' : 'Play'}>
          {audio.playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}
        </button>
        <Timecode /><span className="cb-dur">/ {fmtTime(audio.duration)}</span>
        <Overview className="ov cb-ov" color="var(--tx)" />
        {adv ? (
          <>
            <HistoryControls />
            <MasterKnob size={34} />
            <div className="cb-docks">
              {DOCKS.map(([k, l]) => <button key={k} data-dock-tab={k} className={dock === k ? 'on' : ''} onClick={() => onDock?.(k)}>{l}</button>)}
            </div>
          </>
        ) : <kbd>Space</kbd>}
      </div>
    </div>
  )
}

function EasyCenter({ hover }: { hover: string | null }) {
  const easy = useEasy()
  const { current: track } = useStudio()
  const p = easy.all.find((x) => x.id === (hover ?? easy.genreId))
  const bpm = track?.bpm ?? p?.generate?.bpm ?? 0
  const fam = p ? familyOf(p) : null
  const title = p ? p.name : 'Choose a vibe'
  return (
    <section className="cb-center">
      <div className="cb-head">
        <p className="cb-kicker">{easy.busy ? `Idea ${pad(Math.max(1, easy.idx + 1))} · Writing` : track ? `Idea ${pad(Math.max(1, easy.idx + 1))} · Fair copy` : 'No. 0 · Unwritten'}</p>
        <Title text={title} />
        <p className="cb-sub">
          {p ? (
            <>
              {bpm ? <><em>{tempoWord(bpm)}</em><span>·</span><span className="cb-gl">{'\uE1D5'}</span> = {Math.round(bpm)}<span>·</span></> : null}
              {track?.key ? <>{track.key}<span>·</span></> : null}4/4{fam ? <><span>·</span></> : null}<i>{p.description.replace(/\.$/, '')}</i>
            </>
          ) : <i>Pick one from the catalogue, or write a brief and press Enter.</i>}
        </p>
        <Seismo />
      </div>
      <Score adv={false} />
      <Transport />
    </section>
  )
}

/* ---------------- advanced ---------------- */
type Dock = '' | 'deck' | 'library' | 'compose'
const DOCKS: [Exclude<Dock, ''>, string][] = [['deck', 'Deck'], ['library', 'Library'], ['compose', 'Compose']]

function Rack() {
  const { channels, current: track, bindStem } = useStudio()
  const rack = useRack()
  const ch = channels.find((c) => c.id === rack.sel)
  return (
    <aside className="cb-right cb-rackcol">
      <div className="cb-rack-t"><h3>{ch ? labelOf(ch) : 'Master'}</h3></div>
      <p className="cb-preset">{ch ? 'Per-stem controls. Double-click a dial to reset.' : 'Output of the whole mix.'}</p>
      {ch ? (
        <div className="cb-dials" data-testid="rack-knobs">
          {STRIP_PARAMS.map((k) => {
            const b = bindStem(ch, k.key, k.label)
            return (
              <div className="cb-dial" key={k.key}>
                <Knob label={k.label} min={k.min} max={k.max} defaultValue={k.def} bipolar={k.bipolar} size={52} color="var(--ink)" format={k.fmt} {...b} />
              </div>
            )
          })}
        </div>
      ) : <div className="cb-dials one"><div className="cb-dial"><MasterKnob size={64} /></div></div>}
      {ch && <div className="cb-wave"><Waveform buffer={audio.buffer(ch.id)} height={56} onSeek={(t) => audio.seek(t)} /></div>}
      <div className="cb-stemsel" data-testid="stem-select">
        {track && channels.map((c) => <button key={c.id} className={rack.sel === c.id ? 'on' : ''} onClick={() => rack.setSel(c.id)}>{labelOf(c)}</button>)}
        <button className={rack.sel === MASTER ? 'on' : ''} onClick={() => rack.setSel(MASTER)}>Master</button>
      </div>
    </aside>
  )
}

function Advanced() {
  const { current: track } = useStudio()
  const [dock, setDock] = useState<Dock>('')
  const toggle = (d: Dock) => setDock((c) => (c === d ? '' : d))
  return (
    <>
      <aside className="cb-left">
        <RackTabs />
        <div className="cb-tabbody"><RackBody /></div>
      </aside>
      <section className="cb-center">
        <div className="cb-head adv">
          <div>
            <p className="cb-kicker">Advanced mix · {track?.stems.length ? `${track.stems.length} parts` : 'full mix'}</p>
            <Title text={track?.title ?? 'No track yet'} small />
          </div>
          <div className="cb-adv-actions"><StemActions /></div>
        </div>
        <div className="cb-scorewrap">
          <Score adv />
          {dock && (
            <div className="cb-sheet" data-sheet={dock} role="region" aria-label={dock}>
              <div className="cb-sheet-in">
                {dock === 'deck' && <DeckPane />}
                {dock === 'library' && <LibraryPane />}
                {dock === 'compose' && <ComposerPane />}
              </div>
            </div>
          )}
        </div>
        <Transport adv dock={dock} onDock={toggle} />
      </section>
      <Rack />
    </>
  )
}

export default function ScoreSkin() {
  const { mode } = useStudio()
  const [hover, setHover] = useState<string | null>(null)
  return (
    <div className="cb" data-mode={mode} data-skin-root="score">
      <Top />
      <main className="cb-main">
        {mode === 'easy' ? (
          <>
            <aside className="cb-left"><Catalogue onHover={setHover} /></aside>
            <EasyCenter hover={hover} />
            <aside className="cb-right"><RightEasy /></aside>
          </>
        ) : <Advanced />}
      </main>
      {['tl', 'tr', 'bl', 'br'].map((c) => <i key={c} className={`cb-crop ${c}`} aria-hidden />)}
    </div>
  )
}
