import { useEffect, useMemo, useRef, useState } from 'react'
import { isBrowserDemo } from '../../api'
import '@fontsource/barlow-condensed/500.css'
import '@fontsource/barlow-condensed/600.css'
import '@fontsource/barlow-condensed/700.css'
import '@fontsource/martian-mono/400.css'
import '@fontsource/martian-mono/500.css'
import './cathode.css'
import { audio } from '../../audio/engine'
import { RackBody, RackTabs } from '../../components/pro/RackPanel'
import { ENDS, useEasy } from '../../studio/EasyContext'
import { useStudio } from '../../studio/StudioContext'
import { MACRO_META, TOOLS, barcode, familyOf, fmtTime, tempoWord } from '../../studio/vibe'
import { prefersReducedMotion, stemLevel, useFrame, viz, webgl2Available, type Frame } from '../../studio/viz'
import type { Preset } from '../../types'
import { ComposerPane, DeckPane, LibraryPane } from '../shared/Panes'
import { Overview } from '../shared/Overview'
import { NoDawButton, SkinButton } from '../shared/SkinSwitcher'
import { MasterKnob, StemActions, StemLanes } from '../shared/Stems'
import { DemoBadge, EnginesButton, HistoryControls, SysLeds } from '../shared/TopParts'
import { useDrag, useWheelX } from '../shared/hooks'
import { usePresetShelf, PRESET_CATS } from '../shared/usePresetShelf'
import { useSkin } from '../SkinProvider'
import { Phosphor } from './Phosphor'

const pad = (n: number, w = 3) => String(Math.round(n)).padStart(w, '0')

/* ------------------------------------------------------------ scope */
function draw2d(c: HTMLCanvasElement, f: Frame) {
  const x = c.getContext('2d')
  if (!x) return
  const w = (c.width = c.clientWidth)
  const h = (c.height = c.clientHeight)
  x.fillStyle = '#070808'
  x.fillRect(0, 0, w, h)
  x.strokeStyle = '#9BFF3D'
  x.lineWidth = 1.5
  x.beginPath()
  for (let i = 0; i < f.wave.length; i++) {
    const px = (i / (f.wave.length - 1)) * w
    const py = h * 0.5 + f.wave[i] * h * 0.35
    i ? x.lineTo(px, py) : x.moveTo(px, py)
  }
  x.stroke()
  x.fillStyle = 'rgba(155,255,61,.55)'
  const bw = w / f.spec.length
  for (let i = 0; i < f.spec.length; i++) x.fillRect(i * bw, h - f.spec[i] * h * 0.4, Math.max(1, bw - 1), f.spec[i] * h * 0.4)
}

function Scope({ compact }: { compact?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const ph = useRef<Phosphor | null>(null)
  const [fail, setFail] = useState(!webgl2Available())
  const easy = useEasy()
  const energy = useRef(50)
  energy.current = easy.macros.energy
  const reduced = useRef(prefersReducedMotion())
  const acc = useRef(0)
  useEffect(() => {
    if (fail) return
    try {
      ph.current = new Phosphor(ref.current!)
    } catch {
      setFail(true)
    }
    return () => {
      ph.current = null
    }
  }, [fail])
  useFrame((f, _n, dt) => {
    if (reduced.current) {
      acc.current += dt
      if (acc.current < 0.15) return
      dt = acc.current
      acc.current = 0
      viz.pulse = 0
    }
    viz.pulse *= Math.pow(0.03, dt)
    if (fail) return ref.current && draw2d(ref.current, f)
    ph.current?.render(f, { gain: 0.7 + energy.current / 130, pulse: viz.pulse, making: viz.making, seed: 0, compact: compact ? 1 : 0 }, Math.min(dt, 0.05))
  }, [fail])
  return <canvas key={fail ? 'f' : 'g'} ref={ref} className={`cc-scope ${fail ? 'fail' : ''}`} aria-hidden />
}

function Title({ text, small }: { text: string; small?: boolean }) {
  return (
    <h1 key={text} className={`cc-title ${small ? 'sm' : ''}`} aria-label={text} style={{ ['--n' as string]: Math.max(5, text.length) }}>
      {text.toUpperCase().split('').map((c, i) => (
        <span className="ch" key={i} aria-hidden style={{ ['--i' as string]: i }}>{c === ' ' ? '\u00A0' : c}</span>
      ))}
    </h1>
  )
}

/* ------------------------------------------------------------ top */
function Top() {
  const { mode, setMode, current: track } = useStudio()
  const easy = useEasy()
  const { setHelpOpen } = useSkin()
  const [, force] = useState(0)
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])
  const lufs = easy.report?.lufs ?? easy.analysis?.lufs
  return (
    <header className="cc-top">
      <div className="cc-brand">
        <svg viewBox="0 0 24 24" aria-hidden><path d="M2 12h4l2-7 3 14 3-10 2 3h6" /></svg>
        <b>NODAW STUDIO <u>PRO</u></b>
        <i>CATHODE</i>
      </div>
      <nav className="cc-modes mode-toggle" data-mode={mode} role="tablist" aria-label="Studio mode">
        <button role="tab" aria-selected={mode === 'easy'} data-testid="mode-easy" className={mode === 'easy' ? 'on' : ''} onClick={() => setMode('easy')}><i>01</i>EASY</button>
        <button role="tab" aria-selected={mode === 'advanced'} data-testid="mode-advanced" className={mode === 'advanced' ? 'on' : ''} onClick={() => setMode('advanced')}><i>02</i>ADVANCED</button>
        <span className="cc-modeind" />
      </nav>
      <div className="cc-read">
        <span className={`cc-rec ${audio.playing ? 'on' : ''}`}><s />{audio.playing ? 'LIVE' : 'HALT'}</span>
        <span>{track?.bpm ? Math.round(track.bpm) : '---'} <i>BPM</i></span>
        <span>{track?.key ? track.key.toUpperCase() : '---'}</span>
        <span>{lufs != null ? lufs.toFixed(1) : '--.-'} <i>LUFS</i></span>
        <DemoBadge />
        <NoDawButton />
        <SkinButton />
        <SysLeds />
        <EnginesButton>ENGINES<b>8 GB</b></EnginesButton>
        <button className="cc-q" onClick={() => setHelpOpen(true)} aria-label="Shortcuts">?</button>
      </div>
    </header>
  )
}

/* ------------------------------------------------------------ faders */
function Fader({ k, genre }: { k: (typeof MACRO_META)[number]; genre?: Preset }) {
  const easy = useEasy()
  const { selMacro, setSelMacro } = useSkin()
  const val = Math.round(easy.macros[k.key])
  const base = genre?.macros?.[k.key] ?? 50
  const sel = selMacro === k.key
  const drag = useDrag((v) => easy.setMacro(k.key, Math.round(v * 100)), { axis: 'y', onEnd: () => easy.commitMacros() })
  const [lo, hi] = ENDS[k.key]
  return (
    <div className="cc-fd" data-sel={sel} data-macro={k.key} onPointerDown={() => setSelMacro(k.key)}>
      <b>{k.label.toUpperCase()}</b>
      <output>{pad(val)}</output>
      <span className="hi">{hi.toUpperCase()}</span>
      <div className="cc-ft" {...drag} role="slider" tabIndex={0} aria-label={k.label} aria-valuenow={val} aria-valuemin={0} aria-valuemax={100} title={k.help}>
        <div className="cc-fl" style={{ height: `${val}%` }} />
        <div className="cc-fb" style={{ bottom: `${base}%` }} />
        <div className="cc-fc" style={{ bottom: `${val}%` }}><s /></div>
      </div>
      <span className="lo">{lo.toUpperCase()}</span>
    </div>
  )
}

/* ------------------------------------------------------------ shelf */
function Cart({ id, name, sub, on, onClick, onDouble, fav, narrow, onHover }: { id: string; name: string; sub: string; on: boolean; onClick: () => void; onDouble?: () => void; fav?: boolean; narrow?: boolean; onHover?: (h: boolean) => void }) {
  const bars = useMemo(() => barcode(id, 7), [id])
  return (
    <button className={`cc-cart ${on ? 'on' : ''} ${narrow ? 'nw' : ''}`} onClick={onClick} onDoubleClick={onDouble} onPointerEnter={() => onHover?.(true)} onPointerLeave={() => onHover?.(false)} aria-pressed={on} title={name} data-cart={id}>
      <span className="cc-cart-top">{fav ? '★' : ''}</span>
      <span className="cc-cart-name">{name}</span>
      <span className="cc-bars">{bars.map((w, i) => <s key={i} style={{ height: w * 2 + 1 }} />)}</span>
      <span className="cc-cart-sub">{sub}</span>
    </button>
  )
}

function MakeDock() {
  const easy = useEasy()
  const bar = useRef<HTMLElement>(null)
  useFrame(() => {
    if (bar.current) bar.current.style.transform = `scaleX(${easy.busy ? Math.max(0.04, viz.making) : 0})`
  }, [easy.busy])
  const making = /writ|mak|render|generat/i.test(easy.busy)
  return (
    <div className="cc-dock">
      <label className="cc-brief"><span>BRIEF</span><input data-prompt data-focus-target data-testid="prompt" aria-label="Describe the vibe" placeholder="rainy night drive, warm and dusty" value={easy.vibe} onChange={(e) => easy.setVibe(e.target.value)} maxLength={300} /></label>
      <button className="cc-make" data-testid="make" data-phase={easy.busy ? 'making' : easy.track ? 'ready' : 'idle'} disabled={!!easy.busy} onClick={() => void easy.make()}>
        <span>{easy.busy ? (making ? 'WORKING' : easy.busy.replace(/\.+$/, '').toUpperCase()) : easy.track ? 'MAKE IT AGAIN' : 'MAKE IT'}</span>
        <em>{easy.busy ? '...' : 'ENTER'}</em>
        <s ref={bar} />
      </button>
      <button className="cc-link up" onClick={easy.pickUpload}>OR USE YOUR OWN AUDIO</button>
    </div>
  )
}

function VibeShelf({ onHover }: { onHover: (p: Preset | null) => void }) {
  const easy = useEasy()
  const row = useWheelX<HTMLDivElement>()
  const sel = easy.all.find((p) => p.id === easy.genreId)
  useEffect(() => {
    const r = row.current
    const el = r?.querySelector<HTMLElement>('.cc-cart.on')
    if (r && el) r.scrollTo({ left: el.offsetLeft - r.clientWidth / 2 + el.offsetWidth / 2, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }, [easy.genreId, row, easy.tiles])
  return (
    <section className="cc-shelf" aria-label="Vibes">
      <MakeDock />
      <div className="cc-lib">
        <div className="cc-lib-h">
          <b>LIBRARY</b>
          <i>{easy.tiles.length} VIBES</i>
          <span className="cc-lib-sel">{sel ? <><em>{sel.name.toUpperCase()}</em> {sel.description.replace(/\.$/, '')}</> : 'Pick a cartridge or write a brief'}</span>
          <button className="cc-link inl" data-testid="show-all" onClick={() => easy.setShowAll((v) => !v)}>{easy.showAll ? 'SHOW CURATED' : `SHOW ALL ${easy.all.length}`}</button>
          <kbd>[ ]</kbd>
        </div>
        <div className="cc-row" ref={row} data-testid="vibes">
          {easy.tiles.map((x, i) => (
            <Cart key={x.id} id={x.id} name={x.name} sub={`${pad(i + 1, 2)}${x.generate?.bpm ? ` · ${x.generate.bpm}` : ''}`} on={easy.genreId === x.id} onClick={() => easy.selectGenre(x)} onHover={(h) => onHover(h ? x : null)} />
          ))}
        </div>
      </div>
    </section>
  )
}

type Dock = 'presets' | 'deck' | 'library' | 'compose'
const DOCKS: [Dock, string][] = [['presets', 'PRESETS'], ['deck', 'DECK'], ['library', 'LIBRARY'], ['compose', 'COMPOSE']]

function PresetShelf({ dock, setDock }: { dock: Dock; setDock: (d: Dock) => void }) {
  const ps = usePresetShelf()
  const row = useWheelX<HTMLDivElement>()
  return (
    <section className="cc-shelf adv" aria-label="Presets and tools">
      <div className="cc-pre-side">
        <div className="cc-cats docks" role="tablist">
          {DOCKS.map(([k, l]) => <button key={k} role="tab" aria-selected={dock === k} data-dock-tab={k} className={dock === k ? 'on' : ''} onClick={() => setDock(k)}>{l}</button>)}
        </div>
        {dock === 'presets' && (
          <>
            <label className="cc-brief"><span>SEARCH {ps.total} PRESETS</span><input data-focus-target aria-label="Search presets" placeholder="warm, vinyl, wide..." value={ps.q} onChange={(e) => ps.setQ(e.target.value)} /></label>
            <div className="cc-cats">{PRESET_CATS.map((c) => <button key={c} className={ps.cat === c ? 'on' : ''} onClick={() => ps.setCat(c)}>{(c ? (ps.labels[c] ?? c) : 'All').toUpperCase()}<sup>{c ? (ps.counts[c] ?? 0) : ps.total}</sup></button>)}</div>
          </>
        )}
      </div>
      {dock === 'presets' && (
        <div className="cc-lib">
          <div className="cc-lib-h">
            <b>PRESETS</b><i>{ps.items.length} SHOWN</i>
            {ps.cur && <span className="cc-lib-sel"><em>{ps.cur.name.toUpperCase()}</em> {ps.cur.category} · {ps.cur.description}</span>}
            {ps.cur && (
              <span className="cc-acts">
                <button onClick={() => void ps.hear(ps.cur!)}>{ps.hearing === ps.cur.id ? 'STOP' : 'HEAR'}</button>
                <button onClick={() => void ps.fav(ps.cur!)} aria-label="Favorite">{ps.cur.favorite ? '★' : '☆'}</button>
                <button className="go" data-testid="apply-preset" onClick={() => void ps.apply(ps.cur!)}>APPLY TO {ps.target}</button>
              </span>
            )}
          </div>
          <div className="cc-row" ref={row} data-testid="presets">
            {ps.items.map((p, i) => <Cart key={p.id} id={p.id} name={p.name} narrow fav={p.favorite} sub={pad(i + 1, 3)} on={ps.cur?.id === p.id} onClick={() => ps.setPick(p.id)} onDouble={() => void ps.apply(p)} />)}
          </div>
        </div>
      )}
      {dock !== 'presets' && (
        <div className="cc-lib cc-dockbody">
          {dock === 'deck' && <DeckPane />}
          {dock === 'library' && <LibraryPane />}
          {dock === 'compose' && <ComposerPane />}
        </div>
      )}
    </section>
  )
}

/* ------------------------------------------------------------ easy */
function Transport({ adv }: { adv?: boolean }) {
  const easy = useEasy()
  const [, force] = useState(0)
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])
  const tc = useRef<HTMLSpanElement>(null)
  useFrame(() => {
    if (tc.current) tc.current.textContent = fmtTime(audio.currentTime())
  })
  const { versions, idx, setIdx } = easy
  return (
    <div className="cc-transport">
      <button className="cc-play" data-testid="play" onClick={() => (audio.playing ? audio.pause() : audio.play())} data-playing={audio.playing} aria-label={audio.playing ? 'Pause' : 'Play'}>
        {audio.playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}
      </button>
      <div className="cc-tc"><span ref={tc}>00:00</span><i>/ {fmtTime(audio.duration)}</i></div>
      <Overview className="cc-ov" />
      {adv && <div className="cc-tx"><HistoryControls /><MasterKnob size={34} /></div>}
      {!adv && (
        <div className="cc-revs" data-testid="versions" data-count={versions.length}>
          <button onClick={() => setIdx((i) => Math.max(0, i - 1))} disabled={idx <= 0}>UNDO</button>
          <button onClick={() => setIdx((i) => Math.min(versions.length - 1, i + 1))} disabled={idx >= versions.length - 1}>REDO</button>
          <ol>{versions.map((x, i) => <li key={i}><button className={i === idx ? 'on' : ''} onClick={() => setIdx(i)}><i>R{i + 1}</i>{x.label.toUpperCase()}</button></li>)}</ol>
        </div>
      )}
    </div>
  )
}

function HMeter({ id, name }: { id: string; name: string }) {
  const r = useRef<HTMLDivElement>(null)
  const pk = useRef<HTMLElement>(null)
  const peak = useRef(0)
  useFrame((f, _n, dt) => {
    const v = Math.min(1, (id === 'mix' ? f.level : stemLevel(id)) ** 0.9 * 1.15)
    peak.current = Math.max(v, peak.current - dt * 0.35)
    if (r.current) r.current.style.width = `${v * 100}%`
    if (pk.current) pk.current.style.left = `${peak.current * 100}%`
  })
  return <div className="cc-hm"><span>{name.toUpperCase()}</span><div className="cc-hmt"><div ref={r} /><s ref={pk} /></div></div>
}

function Mons() {
  const { channels } = useStudio()
  const list = channels.length > 1 ? channels : [{ id: 'mix', name: 'Mix' }]
  return (
    <div className="cc-mons">
      <h2 className="cc-h"><b>STEM LEVELS</b><i>LIVE</i></h2>
      {list.map((c) => <HMeter key={c.id} id={c.id} name={c.name} />)}
    </div>
  )
}

function EasyRight() {
  const easy = useEasy()
  const ready = !!easy.track
  const lock = !ready || !!easy.busy
  const cur = easy.report?.target?.key
  return (
    <aside className="cc-right" aria-label="Finish and tools">
      <h2 className="cc-h"><b>FINISH</b><i>LUFS / dBTP</i></h2>
      <div className="cc-fin" data-testid="finish">
        {Object.entries(easy.targets).map(([k, f]) => (
          <button key={k} className={cur === k ? 'on' : ''} disabled={lock} onClick={() => void easy.finish(k)} title={f.note}><b>{f.label.toUpperCase()}</b><em>{f.lufs} / {f.true_peak_db}</em></button>
        ))}
      </div>
      <div className="cc-meas" data-testid="measure">
        {easy.busy ? <span className="cc-busy"><s />{easy.busy.toUpperCase()}</span>
          : easy.report ? <span>MEASURED <b>{easy.report.lufs.toFixed(1)}</b> LUFS · <b>{easy.report.true_peak_db.toFixed(1)}</b> dBTP{easy.report.within_tolerance === false ? '' : ' · CLEAN'}</span>
          : easy.analysis ? <span>MEASURED <b>{easy.analysis.lufs?.toFixed(1) ?? '--'}</b> LUFS · <b>{easy.analysis.true_peak_db.toFixed(1)}</b> dBTP</span>
          : <span className="dim">NO CLIPPING. PICK A TARGET.</span>}
      </div>
      <button className="cc-export" data-testid="export" disabled={lock} onClick={() => void easy.doExport()}><span>{isBrowserDemo() ? 'EXPORT WAV + STEMS' : 'EXPORT WAV + MP3'}</span><kbd>X</kbd></button>
      {easy.files && (
        <div className="cc-files" data-testid="files">
          {Object.entries(easy.files).map(([k, url]) => <a key={k} href={url} download>{decodeURIComponent(url.split('/').pop() ?? k)}<i>{k.toUpperCase()}</i></a>)}
        </div>
      )}
      {easy.midi && <div className="cc-files"><a href={easy.midi} download>MIDI<i>MID</i></a></div>}
      <h2 className="cc-h"><b>ONE CLICK</b><i>TOOLS</i></h2>
      <div className="cc-tools" data-testid="tools">
        {TOOLS.map((t, i) => (
          <button key={t.name} disabled={lock} data-tool={t.name} onClick={() => ('reference' in t ? easy.pickReference() : void easy.tool(t.name, t.label, 'extra' in t ? (t.extra as Record<string, unknown>) : undefined))}><i>{i + 1}</i><span>{t.label.toUpperCase()}</span></button>
        ))}
      </div>
      <Mons />
    </aside>
  )
}

function EasyMain({ hover }: { hover: Preset | null }) {
  const easy = useEasy()
  const { current: track } = useStudio()
  const genre = easy.all.find((p) => p.id === easy.genreId)
  const v = hover ?? genre
  const bpm = track?.bpm ?? v?.generate?.bpm ?? 0
  const making = !!easy.busy
  return (
    <div className="cc-main easy">
      <aside className="cc-macros" aria-label="Macros">
        <h2 className="cc-h"><b>MACROS</b><button className="cc-link" onClick={easy.resetMacros}>RESET</button></h2>
        <div className="cc-fds" data-testid="macros">{MACRO_META.map((m) => <Fader key={m.key} k={m} genre={genre} />)}</div>
      </aside>
      <section className="cc-stage">
        <Scope />
        <div className="cc-hud">
          <p className="cc-kick"><s />{making ? 'WRITING' : !v ? 'STANDBY' : 'SIGNAL LOCKED'}<span>CH 01 · {v ? familyOf(v).toUpperCase() : '---'}</span></p>
          <Title text={v ? v.name : 'Choose a vibe'} />
          <p className="cc-sub">{v ? <>{bpm ? <>{tempoWord(bpm).toUpperCase()} <span>/</span> {Math.round(bpm)} BPM <span>/</span> </> : null}{(track?.key ?? '').toUpperCase() || 'KEY AUTO'} <span>/</span> 4/4</> : 'PICK A CARTRIDGE BELOW'}</p>
        </div>
        <Transport />
      </section>
      <EasyRight />
    </div>
  )
}

/* ------------------------------------------------------------ advanced */
function AdvMain() {
  const { current: track } = useStudio()
  return (
    <div className="cc-main adv">
      <section className="cc-stage mini">
        <Scope compact />
        <div className="cc-hud">
          <p className="cc-kick"><s />{track?.stems.length ? `${track.stems.length} STEMS` : 'FULL MIX'} · LIVE<span>{track?.key ?? ''} {track?.bpm ? `· ${Math.round(track.bpm)} BPM` : ''}</span></p>
          <Title text={track?.title ?? 'No track'} small />
        </div>
        <div className="cc-adv-actions"><StemActions /></div>
        <Transport adv />
      </section>
      <div className="cc-strips" data-testid="strips"><StemLanes knobSize={34} /></div>
      <aside className="cc-right adv" aria-label="Rack">
        <RackTabs />
        <div className="cc-tabbody"><RackBody /></div>
      </aside>
    </div>
  )
}

export default function Cathode() {
  const { mode } = useStudio()
  const [hover, setHover] = useState<Preset | null>(null)
  const [dock, setDock] = useState<Dock>('presets')
  useEffect(() => {
    const dn = () => viz.hit(0.5)
    window.addEventListener('pointerdown', dn)
    return () => window.removeEventListener('pointerdown', dn)
  }, [])
  return (
    <div className="cc" data-mode={mode} data-dock={dock} data-skin-root="cathode">
      <Top />
      {mode === 'easy' ? <EasyMain hover={hover} /> : <AdvMain />}
      {mode === 'easy' ? <VibeShelf onHover={setHover} /> : <PresetShelf dock={dock} setDock={setDock} />}
    </div>
  )
}
