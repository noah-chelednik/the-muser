import { useEffect, useRef, useState } from 'react'
import { isBrowserDemo } from '../../api'
import '@fontsource/geist-sans/300.css'
import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-sans/800.css'
import '@fontsource/geist-mono/400.css'
import '@fontsource/geist-mono/500.css'
import './terrain.css'
import { audio } from '../../audio/engine'
import { RackBody, RackTabs } from '../../components/pro/RackPanel'
import { ENDS, useEasy } from '../../studio/EasyContext'
import { useStudio } from '../../studio/StudioContext'
import { MACRO_META, TOOLS, dynFor, familyOf, fmtClock, fmtTime, type Family } from '../../studio/vibe'
import { prefersReducedMotion, stemLevel, useFrame, viz, webgl2Available } from '../../studio/viz'
import type { Preset } from '../../types'
import { ComposerPane, DeckPane, LibraryPane } from '../shared/Panes'
import { Overview } from '../shared/Overview'
import { NoDawButton, SkinButton } from '../shared/SkinSwitcher'
import { MasterKnob, StemActions, StemLanes } from '../shared/Stems'
import { DemoBadge, EnginesButton, HistoryControls, SysLeds } from '../shared/TopParts'
import { useDrag } from '../shared/hooks'
import { useSkin } from '../SkinProvider'
import { Terrain } from './Terrain'

const FAMILY_TERRAIN: Record<Family, [number, number]> = { amb: [0.12, 6], boom: [0.4, 8], four: [0.5, 11], rock: [0.7, 12], latin: [0.55, 10], trap: [0.8, 13], dnb: [0.95, 16] }
const pad = (n: number, w = 2) => String(Math.round(n)).padStart(w, '0')

function TerrainCanvas({ hover }: { hover: Preset | null }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const t = useRef<Terrain | null>(null)
  const m = useRef({ x: 0, y: 0 })
  const easy = useEasy()
  const { mode } = useStudio()
  const [fail, setFail] = useState(!webgl2Available())
  const live = useRef({ hover, easy, mode })
  live.current = { hover, easy, mode }
  const reduced = useRef(prefersReducedMotion())
  const acc = useRef(0)
  useEffect(() => {
    if (fail) return
    try {
      t.current = new Terrain(ref.current!)
    } catch {
      setFail(true)
      return
    }
    const mv = (e: PointerEvent) => {
      m.current.x = (e.clientX / innerWidth) * 2 - 1
      m.current.y = (e.clientY / innerHeight) * 2 - 1
    }
    const dn = () => viz.hit(0.45)
    window.addEventListener('pointermove', mv)
    window.addEventListener('pointerdown', dn)
    return () => {
      window.removeEventListener('pointermove', mv)
      window.removeEventListener('pointerdown', dn)
      t.current = null
    }
  }, [fail])
  useFrame((f, _n, dt) => {
    if (fail) return
    if (reduced.current) {
      acc.current += dt
      if (acc.current < 0.12) return
      dt = acc.current
      acc.current = 0
    }
    const { hover: h, easy: e, mode: md } = live.current
    const v = h ?? e.all.find((p) => p.id === e.genreId)
    const [rough, freq] = v ? FAMILY_TERRAIN[familyOf(v)] : [0.3, 7]
    viz.pulse *= Math.pow(0.03, dt)
    t.current?.render(
      f,
      { focus: md === 'advanced' ? 1 : 0, pulse: reduced.current ? 0 : viz.pulse, mx: reduced.current ? 0 : m.current.x, my: reduced.current ? 0 : m.current.y, rough, freq, amp: 0.5 + e.macros.energy / 260, making: viz.making },
      Math.min(dt, 0.05),
    )
  }, [fail])
  return <canvas key={fail ? 'f' : 'g'} ref={ref} className={`ca-gl ${fail ? 'fail' : ''}`} aria-hidden />
}

function Logo() {
  return <svg className="ca-logo" viewBox="0 0 28 20" aria-hidden><path d="M1 19V1l13 13L27 1v18" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
}

function Timecode() {
  const r = useRef<HTMLSpanElement>(null)
  useFrame(() => {
    if (r.current) r.current.textContent = fmtClock(audio.currentTime())
  })
  return <span ref={r} className="ca-tc">00:00.00</span>
}

function TopBar() {
  const { mode, setMode, current: track } = useStudio()
  const easy = useEasy()
  const { setHelpOpen } = useSkin()
  const lufs = easy.report?.lufs ?? easy.analysis?.lufs
  return (
    <header className="ca-top">
      <div className="ca-brand"><Logo /><b>NODAW STUDIO PRO</b><i>BUILT ON THE-MUSER</i></div>
      <nav className="ca-modes" data-mode={mode} role="tablist" aria-label="Studio mode">
        <button role="tab" aria-selected={mode === 'easy'} data-testid="mode-easy" className={mode === 'easy' ? 'on' : ''} onClick={() => setMode('easy')}><i>01</i>EASY</button>
        <button role="tab" aria-selected={mode === 'advanced'} data-testid="mode-advanced" className={mode === 'advanced' ? 'on' : ''} onClick={() => setMode('advanced')}><i>02</i>ADVANCED</button>
        <span className="ca-ind" />
      </nav>
      <div className="ca-read">
        <span className="ca-n"><i>BPM</i><b>{track?.bpm ? Math.round(track.bpm) : '---'}</b></span>
        <span className="ca-n"><i>KEY</i><b>{track?.key ? track.key.toUpperCase() : '---'}</b></span>
        <span className="ca-n"><i>LUFS</i><b>{lufs != null ? lufs.toFixed(1) : '--.-'}</b></span>
        <DemoBadge />
        <NoDawButton />
        <SkinButton />
        <SysLeds />
        <EnginesButton><i>ENGINES</i><b>8 GB</b></EnginesButton>
        <button className="ca-help-btn" onClick={() => setHelpOpen(true)} aria-label="Shortcuts">?</button>
      </div>
    </header>
  )
}

/* ---------- precision ruler (macro) ---------- */
function Ruler({ k, idx, genre }: { k: (typeof MACRO_META)[number]; idx: number; genre?: Preset }) {
  const easy = useEasy()
  const { selMacro, setSelMacro } = useSkin()
  const val = Math.round(easy.macros[k.key])
  const base = genre?.macros?.[k.key] ?? 50
  const drag = useDrag((v) => easy.setMacro(k.key, Math.round(v * 100)), { onEnd: () => easy.commitMacros() })
  const [lo, hi] = ENDS[k.key]
  return (
    <div className="ca-macro" data-sel={selMacro === k.key} data-macro={k.key} onPointerDown={() => setSelMacro(k.key)}>
      <div className="ca-macro-head"><i>{pad(idx + 1)}</i><span>{k.label.toUpperCase()}</span><b>{pad(val, 3)}</b></div>
      <div className="ca-ruler" {...drag} role="slider" aria-label={k.label} aria-valuenow={val} aria-valuemin={0} aria-valuemax={100} tabIndex={0} title={k.help}>
        <div className="ca-ticks" />
        <div className="ca-trail" style={{ left: `${Math.min(base, val)}%`, width: `${Math.abs(val - base)}%` }} />
        <div className="ca-ghost" style={{ left: `${base}%` }} />
        <div className="ca-cursor" style={{ left: `${val}%` }}><s /></div>
      </div>
      <div className="ca-ends"><span>{lo.toUpperCase()}</span><em>{dynFor(val).toUpperCase()}</em><span>{hi.toUpperCase()}</span></div>
    </div>
  )
}

function MakeButton() {
  const easy = useEasy()
  const fill = useRef<HTMLSpanElement>(null)
  useFrame(() => {
    if (fill.current) fill.current.style.transform = `scaleX(${easy.busy ? Math.max(0.05, viz.making) : 0})`
  }, [easy.busy])
  const phase = easy.busy ? 'making' : easy.track ? 'ready' : 'idle'
  return (
    <button className="ca-make" data-testid="make" data-phase={phase} onClick={() => void easy.make()} disabled={!!easy.busy}>
      <span className="ca-make-fill" ref={fill} />
      <span className="ca-make-label">{easy.busy ? easy.busy.replace(/\.+$/, '').toUpperCase() : easy.track ? 'MAKE IT AGAIN' : 'MAKE IT'}</span>
      <kbd>ENTER</kbd>
    </button>
  )
}

function VibeList({ onHover }: { onHover: (p: Preset | null) => void }) {
  const easy = useEasy()
  const sel = easy.all.find((p) => p.id === easy.genreId)
  const [hov, setHov] = useState<Preset | null>(null)
  const v = hov ?? sel
  const set = (p: Preset | null) => {
    setHov(p)
    onHover(p)
  }
  return (
    <>
      <h2 className="ca-h"><i>01</i>VIBE<em>{easy.tiles.length}</em><button className="ca-mini" data-testid="show-all" onClick={() => easy.setShowAll((s) => !s)}>{easy.showAll ? 'CURATED' : `ALL ${easy.all.length}`}</button></h2>
      <ol className="ca-vibes" data-testid="vibes" onPointerLeave={() => set(null)}>
        {easy.tiles.map((x, i) => (
          <li key={x.id}>
            <button className={sel?.id === x.id ? 'on' : ''} data-cart={x.id} onPointerEnter={() => set(x)} onFocus={() => set(x)} onBlur={() => set(null)} onClick={() => easy.selectGenre(x)} aria-pressed={sel?.id === x.id}>
              <i>{pad(i + 1)}</i><b>{x.name}</b><em>{x.generate?.bpm ?? ''}</em>
            </button>
          </li>
        ))}
      </ol>
      <div className="ca-spec">
        {v ? (
          <>
            <div className="ca-spec-t">{v.name.toUpperCase()}<span>{v.description.replace(/\.$/, '')}</span></div>
            <div className="ca-spec-bars">{MACRO_META.map((m) => <span key={m.key} title={m.label}><s style={{ height: `${v.macros?.[m.key] ?? 50}%` }} /></span>)}</div>
          </>
        ) : <div className="ca-spec-t dim">NO VIBE SELECTED<span>Pick one, or describe it below</span></div>}
      </div>
      <div className="ca-prompt">
        <i>&gt;</i>
        <input data-prompt data-focus-target data-testid="prompt" aria-label="Describe the vibe" placeholder="or describe it: rainy night drive" value={easy.vibe} onChange={(e) => easy.setVibe(e.target.value)} maxLength={300} />
      </div>
      <MakeButton />
      <button className="ca-link" onClick={easy.pickUpload}>OR USE YOUR OWN AUDIO</button>
    </>
  )
}

function Finish() {
  const easy = useEasy()
  const lock = !easy.track || !!easy.busy
  const cur = easy.report?.target?.key
  return (
    <>
      <h2 className="ca-h"><i>03</i>FINISH<em>LUFS / dBTP</em></h2>
      <div className="ca-fin" data-testid="finish">
        {Object.entries(easy.targets).map(([k, f]) => (
          <button key={k} className={cur === k ? 'on' : ''} disabled={lock} title={f.note} onClick={() => void easy.finish(k)}>
            <b>{f.label.toUpperCase()}</b><span>{f.lufs} / {f.true_peak_db}</span>
          </button>
        ))}
      </div>
      <div className="ca-meas" data-testid="measure">
        {easy.busy ? <span className="ca-busy"><s />{easy.busy.toUpperCase()}</span>
          : easy.report ? <><span>MEASURED</span><b>{easy.report.lufs.toFixed(1)}</b><span>LUFS</span><b>{easy.report.true_peak_db.toFixed(1)}</b><span>dBTP</span><u /></>
          : easy.analysis ? <><span>MEASURED</span><b>{easy.analysis.lufs?.toFixed(1) ?? '--'}</b><span>LUFS</span><b>{easy.analysis.true_peak_db.toFixed(1)}</b><span>dBTP</span></>
          : <span className="dim">NO CLIPPING. PICK A TARGET TO MASTER.</span>}
      </div>
      <button className="ca-export" data-testid="export" disabled={lock} onClick={() => void easy.doExport()}>{isBrowserDemo() ? 'EXPORT WAV + STEMS' : 'EXPORT WAV + MP3'}<kbd>X</kbd></button>
      {(easy.files || easy.midi) && (
        <div className="ca-files" data-testid="files">
          {easy.files && Object.entries(easy.files).map(([k, url]) => <a key={k} href={url} download>{decodeURIComponent(url.split('/').pop() ?? k)}<span>{k.toUpperCase()}</span></a>)}
          {easy.midi && <a href={easy.midi} download>MIDI<span>MID</span></a>}
        </div>
      )}
    </>
  )
}

function Tools() {
  const easy = useEasy()
  const lock = !easy.track || !!easy.busy
  return (
    <>
      <h2 className="ca-h"><i>04</i>TOOLS<em>ONE CLICK</em></h2>
      <div className="ca-tools" data-testid="tools">
        {TOOLS.map((t, i) => (
          <button key={t.name} disabled={lock} data-tool={t.name} onClick={() => ('reference' in t ? easy.pickReference() : void easy.tool(t.name, t.label, 'extra' in t ? (t.extra as Record<string, unknown>) : undefined))}>
            <i>{pad(i + 1)}</i>{t.label.toUpperCase()}<span>→</span>
          </button>
        ))}
      </div>
    </>
  )
}

function Levels() {
  const { channels } = useStudio()
  const list = channels.length > 1 ? channels : []
  if (!list.length) return null
  return (
    <div className="ca-levels">
      {list.map((c) => <Lv key={c.id} id={c.id} name={c.name} />)}
    </div>
  )
}
function Lv({ id, name }: { id: string; name: string }) {
  const r = useRef<HTMLDivElement>(null)
  useFrame(() => {
    if (r.current) r.current.style.transform = `scaleY(${Math.min(1, stemLevel(id) ** 0.9 * 1.15)})`
  })
  return <span title={name}><div><s ref={r} /></div><i>{name.slice(0, 3).toUpperCase()}</i></span>
}

function TransportBar({ adv }: { adv?: boolean }) {
  const easy = useEasy()
  const [, force] = useState(0)
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])
  const { versions, idx, setIdx } = easy
  return (
    <div className="ca-transport">
      {!adv && (
        <div className="ca-hist" data-testid="versions" data-count={versions.length}>
          <button onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={idx <= 0}>UNDO</button>
          <button onClick={() => setIdx((i) => Math.min(versions.length - 1, i + 1))} disabled={idx >= versions.length - 1}>REDO</button>
          <div className="ca-vers">{versions.map((v, i) => <button key={i} className={i === idx ? 'on' : ''} onClick={() => setIdx(i)}><i>{pad(i + 1)}</i>{v.label.toUpperCase()}</button>)}</div>
        </div>
      )}
      <div className="ca-play-row">
        <button className="ca-play" data-testid="play" onClick={() => (audio.playing ? audio.pause() : audio.play())} aria-label={audio.playing ? 'Pause' : 'Play'} data-playing={audio.playing}>
          {audio.playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}
          <kbd>SPACE</kbd>
        </button>
        <Timecode />
        <Overview className="ca-over" color="var(--tx)" />
        <span className="ca-dur">/ {fmtTime(audio.duration)}</span>
      </div>
    </div>
  )
}

function Easy({ hover, setHover }: { hover: Preset | null; setHover: (p: Preset | null) => void }) {
  const easy = useEasy()
  const { current: track } = useStudio()
  const genre = easy.all.find((p) => p.id === easy.genreId)
  const v = hover ?? genre
  const title = v ? v.name.toUpperCase() : 'SELECT A VIBE'
  return (
    <section className="ca-easy">
      <aside className="ca-col ca-left"><VibeList onHover={setHover} /></aside>
      <div className="ca-center">
        <div className="ca-title-wrap">
          <h1 key={title} className="ca-title" data-dim={!v} aria-label={title} style={{ ['--n' as string]: Math.max(6, title.length) }}>{title}</h1>
          <div className="ca-meta">
            <span>IDEA {pad(Math.max(1, easy.idx + 1))}</span>
            <span>{track?.bpm ? `${Math.round(track.bpm)} BPM` : v?.generate?.bpm ? `${v.generate.bpm} BPM` : '--- BPM'}</span>
            <span>{track?.key ? track.key.toUpperCase() : '--'}</span>
            <span>{easy.busy ? 'GENERATING' : track ? `${track.duration_s.toFixed(1)} S / ${track.stems.length || 1} STEMS` : 'AWAITING INPUT'}</span>
          </div>
        </div>
        <TransportBar />
      </div>
      <aside className="ca-col ca-right">
        <h2 className="ca-h"><i>02</i>SHAPE<button className="ca-mini" onClick={easy.resetMacros}>RESET</button></h2>
        <div className="ca-macros" data-testid="macros">{MACRO_META.map((m, i) => <Ruler key={m.key} k={m} idx={i} genre={genre} />)}</div>
        <Finish />
        <Tools />
        <Levels />
      </aside>
    </section>
  )
}

/* ---------- advanced ---------- */
type Sheet = '' | 'deck' | 'library' | 'compose'
function Advanced() {
  const { current: track } = useStudio()
  const [sheet, setSheet] = useState<Sheet>('')
  const toggle = (s: Sheet) => setSheet((c) => (c === s ? '' : s))
  const [, force] = useState(0)
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])
  return (
    <section className="ca-adv">
      <div className="ca-adv-main">
        <div className="ca-strip">
          <div className="ca-strip-l">
            <h1 key={track?.title} className="ca-title sm" style={{ ['--n' as string]: Math.max(10, (track?.title ?? 'No track').length) }}>{(track?.title ?? 'No track').toUpperCase()}</h1>
            <div className="ca-meta"><span>ADVANCED MIX</span><span>{track?.stems.length ? `${track.stems.length} SOURCES` : 'FULL MIX'}</span><span>{(track?.key ?? '').toUpperCase()}</span></div>
          </div>
          <div className="ca-strip-r"><StemActions /></div>
        </div>
        <div className="ca-lanes" data-testid="strips"><StemLanes knobSize={26} /></div>
        {sheet && (
          <div className="ca-sheet" data-sheet={sheet} role="region" aria-label={sheet}>
            <div className="ca-sheet-in">
              {sheet === 'deck' && <DeckPane />}
              {sheet === 'library' && <LibraryPane />}
              {sheet === 'compose' && <ComposerPane />}
            </div>
          </div>
        )}
        <div className="ca-adv-bot">
          <button className="ca-play sm" data-testid="play" onClick={() => (audio.playing ? audio.pause() : audio.play())} data-playing={audio.playing} aria-label="Play">{audio.playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}</button>
          <Timecode />
          <Overview className="ca-over ca-over-s" color="var(--tx)" />
          <HistoryControls />
          <MasterKnob size={30} />
          <div className="ca-docks">
            {(['deck', 'library', 'compose'] as const).map((s) => <button key={s} data-dock-tab={s} className={sheet === s ? 'on' : ''} onClick={() => toggle(s)}>{s.toUpperCase()}</button>)}
          </div>
        </div>
      </div>
      <aside className="ca-col ca-panel">
        <RackTabs />
        <div className="ca-tabbody"><RackBody /></div>
      </aside>
    </section>
  )
}

export default function TerrainSkin() {
  const { mode } = useStudio()
  const [hover, setHover] = useState<Preset | null>(null)
  return (
    <div className="ca" data-mode={mode} data-skin-root="terrain">
      <TerrainCanvas hover={hover} />
      <TopBar />
      <main className="ca-main">{mode === 'easy' ? <Easy hover={hover} setHover={setHover} /> : <Advanced />}</main>
    </div>
  )
}
