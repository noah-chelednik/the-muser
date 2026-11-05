import { useEffect, useMemo, useRef } from 'react'
import gsap from 'gsap'
import '@fontsource/geist-sans/300.css'
import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-sans/800.css'
import '@fontsource/geist-mono/400.css'
import '@fontsource/geist-mono/500.css'
import './a.css'
import { ENGINES, FINISH, MACROS, SHORTCUTS, STEMS, TOOLS, VIBES, vibeById, type Family, type StemId } from '../shared/data'
import { engine } from '../shared/engine'
import { stemPeaks } from '../shared/music'
import { actions, fx, getState, useStore } from '../shared/store'
import { useShortcuts } from '../shared/shortcuts'
import { useDrag, useFrame } from '../shared/hooks'
import { ABForm, CAT_LABEL, EngineRows, GenerateForm, MasterForm, SeparateForm, usePresets } from '../shared/ui'
import { Terrain } from './Terrain'

const FAMILY_TERRAIN: Record<Family, [number, number]> = { amb: [0.12, 6], boom: [0.4, 8], four: [0.5, 11], rock: [0.7, 12], latin: [0.55, 10], trap: [0.8, 13], dnb: [0.95, 16] }
const pad = (n: number, w = 2) => String(n).padStart(w, '0')

function TerrainCanvas() {
  const ref = useRef<HTMLCanvasElement>(null)
  const t = useRef<Terrain | null>(null)
  const m = useRef({ x: 0, y: 0 })
  useEffect(() => {
    t.current = new Terrain(ref.current!)
    const mv = (e: PointerEvent) => { m.current.x = (e.clientX / innerWidth) * 2 - 1; m.current.y = (e.clientY / innerHeight) * 2 - 1 }
    const dn = () => fx.hit(0.45)
    const over = (e: PointerEvent) => { if ((e.target as HTMLElement).closest?.('button,input,select,.ca-ruler,.ca-vbar,.ca-wave')) fx.hit(0.1) }
    window.addEventListener('pointermove', mv); window.addEventListener('pointerdown', dn); window.addEventListener('pointerover', over)
    return () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerdown', dn); window.removeEventListener('pointerover', over) }
  }, [])
  useFrame((f, _n, dt) => {
    const st = getState()
    const v = vibeById(st.hoverVibe ?? st.vibeId)
    const [rough, freq] = v ? FAMILY_TERRAIN[v.family] : [0.3, 7]
    fx.pulse *= Math.pow(0.03, dt)
    t.current?.render(f, {
      focus: st.mode === 'advanced' ? 1 : 0, pulse: fx.pulse, mx: m.current.x, my: m.current.y, rough, freq,
      amp: 0.5 + st.macros.energy / 260, making: st.phase === 'making' ? st.progress : 0,
    }, Math.min(dt, 0.05))
  })
  return <canvas ref={ref} className="ca-gl" />
}

function Logo() {
  return <svg className="ca-logo" viewBox="0 0 28 20" aria-hidden><path d="M1 19V1l13 13L27 1v18" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
}

function Timecode() {
  const r = useRef<HTMLSpanElement>(null)
  useFrame(() => { if (r.current) { const t = engine.time; const m = Math.floor(t / 60); r.current.textContent = `${pad(m)}:${pad(Math.floor(t % 60))}.${pad(Math.floor((t % 1) * 1000), 3)}` } })
  return <span ref={r} className="ca-tc">00:00.000</span>
}

function TopBar() {
  const mode = useStore((s) => s.mode)
  const vibeId = useStore((s) => s.vibeId)
  const energy = useStore((s) => s.macros.energy)
  const meas = useStore((s) => s.measured)
  const v = vibeById(vibeId)
  const bpm = (v?.bpm ?? 78) * (0.9 + (energy / 100) * 0.22)
  return (
    <header className="ca-top">
      <a className="ca-brand" href="#/"><Logo /><b>THE MUSER</b><i>NODAW LABS / STUDIO</i></a>
      <nav className="ca-modes" data-mode={mode}>
        <button className={mode === 'easy' ? 'on' : ''} onClick={() => actions.setMode('easy')}><i>01</i>EASY</button>
        <button className={mode === 'advanced' ? 'on' : ''} onClick={() => actions.setMode('advanced')}><i>02</i>ADVANCED</button>
        <span className="ca-ind" />
      </nav>
      <div className="ca-read">
        <span><i>BPM</i><b>{bpm.toFixed(1).padStart(5, '0')}</b></span>
        <span><i>KEY</i><b>{v ? `${v.key} ${v.minor ? 'MIN' : 'MAJ'}` : 'A MIN'}</b></span>
        <span><i>LUFS</i><b>{meas ? meas.lufs.toFixed(1) : '--.-'}</b></span>
        <button className="ca-eng-btn" onClick={() => actions.engines(true)}><i>ENGINES</i><b>8 GB</b><u>[<s />]</u></button>
        <button className="ca-help-btn" onClick={() => actions.help(true)} aria-label="Shortcuts">?</button>
      </div>
    </header>
  )
}

/* ---------- precision ruler (macro) ---------- */
function Ruler({ k, idx }: { k: (typeof MACROS)[number]; idx: number }) {
  const val = useStore((s) => s.macros[k.key])
  const sel = useStore((s) => s.selMacro === k.key)
  const base = useStore((s) => vibeById(s.vibeId)?.macros[k.key] ?? 50)
  const ready = useStore((s) => s.phase === 'ready')
  const drag = useDrag((v) => actions.setMacro(k.key, v * 100), { onEnd: () => actions.commitMacros() })
  return (
    <div className="ca-macro" data-sel={sel} data-ready={ready} onPointerDown={() => actions.selMacro(k.key)}>
      <div className="ca-macro-head"><i>{pad(idx + 1)}</i><span>{k.label.toUpperCase()}</span><b>{pad(val, 3)}</b></div>
      <div className="ca-ruler" {...drag} role="slider" aria-label={k.label} aria-valuenow={val} aria-valuemin={0} aria-valuemax={100} tabIndex={0}>
        <div className="ca-ticks" />
        <div className="ca-trail" style={{ left: `${Math.min(base, val)}%`, width: `${Math.abs(val - base)}%` }} />
        <div className="ca-ghost" style={{ left: `${base}%` }} />
        <div className="ca-cursor" style={{ left: `${val}%` }}><s /></div>
      </div>
      <div className="ca-ends"><span>{k.lo.toUpperCase()}</span><em>{k.dyn.toUpperCase()}</em><span>{k.hi.toUpperCase()}</span></div>
    </div>
  )
}

function MakeButton() {
  const phase = useStore((s) => s.phase)
  const p = useStore((s) => s.progress)
  const stage = useStore((s) => s.stage)
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => { if (phase === 'ready' && ref.current) gsap.fromTo(ref.current, { letterSpacing: '0.6em' }, { letterSpacing: '0.28em', duration: 0.9, ease: 'expo.out' }) }, [phase])
  return (
    <button ref={ref} className="ca-make" data-phase={phase} onClick={() => void actions.make()} disabled={phase === 'making'}>
      <span className="ca-make-fill" style={{ transform: `scaleX(${phase === 'making' ? p : 0})` }} />
      <span className="ca-make-label">{phase === 'making' ? `${stage.toUpperCase()} ${pad(Math.round(p * 100))}%` : phase === 'ready' ? 'MAKE IT AGAIN' : 'MAKE IT'}</span>
      <kbd>ENTER</kbd>
    </button>
  )
}

function VibeList() {
  const sel = useStore((s) => s.vibeId)
  const hov = useStore((s) => s.hoverVibe)
  const v = vibeById(hov ?? sel)
  return (
    <>
      <h2 className="ca-h"><i>01</i>VIBE<em>{VIBES.length}</em></h2>
      <ol className="ca-vibes" onPointerLeave={() => actions.hoverVibe(null)}>
        {VIBES.map((x, i) => (
          <li key={x.id}>
            <button className={sel === x.id ? 'on' : ''} onPointerEnter={() => actions.hoverVibe(x.id)} onFocus={() => actions.hoverVibe(x.id)} onClick={() => actions.pickVibe(x.id)} aria-pressed={sel === x.id}>
              <i>{pad(i + 1)}</i><b>{x.name}</b><em>{x.bpm}</em>
            </button>
          </li>
        ))}
      </ol>
      <div className="ca-spec">
        {v ? (
          <>
            <div className="ca-spec-t">{v.name.toUpperCase()}<span>{v.desc.replace(/\.$/, '')}</span></div>
            <div className="ca-spec-bars">{MACROS.map((m) => <span key={m.key} title={m.label}><s style={{ height: `${v.macros[m.key]}%` }} /></span>)}</div>
          </>
        ) : <div className="ca-spec-t dim">NO VIBE SELECTED<span>Pick one, or describe it below</span></div>}
      </div>
      <div className="ca-prompt">
        <i>&gt;</i>
        <input data-prompt data-focus-target aria-label="Describe the vibe" placeholder="or describe it: rainy night drive" value={useStore((s) => s.prompt)} onChange={(e) => actions.setPrompt(e.target.value)} maxLength={300} />
      </div>
      <MakeButton />
    </>
  )
}

function Finish() {
  const fin = useStore((s) => s.finish)
  const meas = useStore((s) => s.measured)
  const busy = useStore((s) => s.busy)
  const exp = useStore((s) => s.exported)
  const ready = useStore((s) => s.phase === 'ready')
  return (
    <>
      <h2 className="ca-h"><i>03</i>FINISH<em>LUFS / dBTP</em></h2>
      <div className="ca-fin">
        {FINISH.map((f) => (
          <button key={f.key} className={fin === f.key ? 'on' : ''} disabled={!ready || !!busy} onClick={() => void actions.finishFor(f.key)}>
            <b>{f.label.toUpperCase()}</b><span>{f.lufs} / {f.tp}</span>
          </button>
        ))}
      </div>
      <div className="ca-meas">
        {busy ? <span className="ca-busy"><s />{busy.toUpperCase()}</span>
          : meas ? <><span>MEASURED</span><b>{meas.lufs.toFixed(1)}</b><span>LUFS</span><b>{meas.tp.toFixed(1)}</b><span>dBTP</span><u data-ok /></>
            : <span className="dim">NO CLIPPING. PICK A TARGET TO MASTER.</span>}
      </div>
      <button className="ca-export" disabled={!ready || !!busy} onClick={() => void actions.doExport()}>EXPORT WAV + MP3<kbd>X</kbd></button>
      {exp && <div className="ca-files">{exp.map((f) => <a key={f.name} href="#/a" onClick={(e) => e.preventDefault()}>↓ {f.name}<span>{f.size}</span></a>)}</div>}
    </>
  )
}

function Tools() {
  const ready = useStore((s) => s.phase === 'ready')
  const busy = useStore((s) => s.busy)
  return (
    <>
      <h2 className="ca-h"><i>04</i>TOOLS<em>ONE CLICK</em></h2>
      <div className="ca-tools">
        {TOOLS.map((t, i) => <button key={t.key} disabled={!ready || !!busy} onClick={() => void actions.tool(t.key)}><i>{pad(i + 1)}</i>{t.label.toUpperCase()}<span>→</span></button>)}
      </div>
    </>
  )
}

function Easy() {
  const vibeId = useStore((s) => s.vibeId)
  const hov = useStore((s) => s.hoverVibe)
  const phase = useStore((s) => s.phase)
  const v = vibeById(hov ?? vibeId)
  const title = v ? v.name.toUpperCase() : 'SELECT A VIBE'
  const tl = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (tl.current) gsap.fromTo(tl.current, { clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)', duration: 0.5, ease: 'power3.out' }) }, [title])
  const macros = useStore((s) => s.macros)
  const reset = actions.resetMacros
  return (
    <section className="ca-easy">
      <aside className="ca-col ca-left"><VibeList /></aside>
      <div className="ca-center">
        <div className="ca-title-wrap">
          <h1 ref={tl} className="ca-title" data-dim={!v}>{title}</h1>
          <div className="ca-meta">
            <span>IDEA 01</span><span>{v ? `${v.bpm} BPM` : '--- BPM'}</span><span>{v ? `${v.key} ${v.minor ? 'MINOR' : 'MAJOR'}` : '--'}</span>
            <span>{phase === 'ready' ? '26.2 S / 4 STEMS' : phase === 'making' ? 'GENERATING' : 'AWAITING INPUT'}</span>
          </div>
        </div>
        <TransportBar />
      </div>
      <aside className="ca-col ca-right">
        <h2 className="ca-h"><i>02</i>SHAPE<button className="ca-mini" onClick={reset}>RESET</button></h2>
        <div className="ca-macros">{MACROS.map((m, i) => <Ruler key={m.key} k={m} idx={i} />)}</div>
        <span hidden>{macros.energy}</span>
        <Finish />
        <Tools />
      </aside>
    </section>
  )
}

/* ---------- transport / overview ---------- */
function Overview({ className }: { className?: string }) {
  const cv = useRef<HTMLCanvasElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  const vibeId = useStore((s) => s.vibeId)
  const phase = useStore((s) => s.phase)
  const peaks = useMemo(() => stemPeaks('drums', engine.pattern, 360).map((x, i) => Math.min(1, x * 0.6 + stemPeaks('bass', engine.pattern, 360)[i] * 0.5)), [vibeId])
  useEffect(() => {
    const c = cv.current!, ctx = c.getContext('2d')!
    const w = c.clientWidth, h = c.clientHeight, d = Math.min(devicePixelRatio, 2)
    c.width = w * d; c.height = h * d; ctx.scale(d, d)
    ctx.clearRect(0, 0, w, h)
    if (phase !== 'ready') { ctx.fillStyle = 'rgba(255,255,255,.18)'; for (let x = 0; x < w; x += 4) ctx.fillRect(x, h / 2, 2, 1); return }
    peaks.forEach((p, i) => { const x = (i / peaks.length) * w; ctx.fillStyle = 'rgba(255,255,255,.75)'; const hh = Math.max(1, p * h * 0.9); ctx.fillRect(x, (h - hh) / 2, Math.max(1, w / peaks.length - 1), hh) })
  }, [peaks, phase])
  useFrame((f) => { if (ph.current) ph.current.style.transform = `translateX(${f.pos * 100}%)` })
  const seek = useDrag((v) => { engine.seek(v) })
  return (
    <div className={`ca-over ${className ?? ''}`} {...seek}>
      <canvas ref={cv} />
      <div className="ca-ph-track"><div ref={ph} className="ca-ph"><s /></div></div>
    </div>
  )
}

function TransportBar() {
  const playing = useStore((s) => s.playing)
  const versions = useStore((s) => s.versions)
  const idx = useStore((s) => s.vIdx)
  return (
    <div className="ca-transport">
      <div className="ca-hist">
        <button onClick={actions.undo} disabled={idx <= 0}>UNDO</button><button onClick={actions.redo} disabled={idx >= versions.length - 1}>REDO</button>
        <div className="ca-vers">{versions.map((v, i) => <button key={i} className={i === idx ? 'on' : ''} onClick={() => actions.jump(i)}><i>{pad(i + 1)}</i>{v.label.toUpperCase()}</button>)}</div>
      </div>
      <div className="ca-play-row">
        <button className="ca-play" onClick={actions.toggle} aria-label={playing ? 'Pause' : 'Play'} data-playing={playing}>
          {playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}
          <kbd>SPACE</kbd>
        </button>
        <Timecode />
        <Overview />
        <span className="ca-dur">/ {engine.duration.toFixed(1)}S</span>
      </div>
    </div>
  )
}

/* ---------- advanced ---------- */
const RANGES = { vol: [-24, 6, 'dB'], pan: [-1, 1, ''], low: [-12, 12, 'dB'], mid: [-12, 12, 'dB'], high: [-12, 12, 'dB'], comp: [0, 100, '%'], verb: [0, 100, '%'], room: [0, 100, '%'] } as const
type PK = keyof typeof RANGES
function VBar({ id, k }: { id: StemId; k: PK }) {
  const val = useStore((s) => s.stems[id][k]) as number
  const [lo, hi] = RANGES[k]
  const frac = (val - lo) / (hi - lo)
  const bip = k !== 'vol' && k !== 'comp' && k !== 'verb' && k !== 'room'
  const drag = useDrag((v) => actions.setStem(id, { [k]: lo + v * (hi - lo) }), { axis: 'y' })
  const txt = k === 'pan' ? (Math.abs(val) < 0.03 ? 'C' : `${val < 0 ? 'L' : 'R'}${Math.round(Math.abs(val) * 100)}`) : `${val > 0 && bip ? '+' : ''}${(k === 'vol' || bip ? val.toFixed(1) : Math.round(val))}`
  const dbl = () => actions.setStem(id, { [k]: bip ? 0 : k === 'vol' ? 0 : 0 })
  return (
    <div className="ca-vb" onDoubleClick={dbl}>
      <div className="ca-vbar" {...drag} role="slider" aria-label={`${id} ${k}`} aria-valuenow={val}>
        <div className="ca-vticks" />
        <div className="ca-vfill" style={bip ? { bottom: `${Math.min(frac, 0.5) * 100}%`, height: `${Math.abs(frac - 0.5) * 100}%` } : { bottom: 0, height: `${frac * 100}%` }} />
        <div className="ca-vcap" style={{ bottom: `${frac * 100}%` }} />
      </div>
      <em>{txt}</em><span>{k.toUpperCase()}</span>
    </div>
  )
}

function Wave({ id }: { id: StemId }) {
  const cv = useRef<HTMLCanvasElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  const lv = useRef<HTMLDivElement>(null)
  const vibeId = useStore((s) => s.vibeId)
  const ready = useStore((s) => s.phase === 'ready')
  const muted = useStore((s) => s.stems[id].mute)
  const peaks = useMemo(() => stemPeaks(id, engine.pattern, 300), [vibeId, id])
  useEffect(() => {
    const draw = () => {
      const c = cv.current!, ctx = c.getContext('2d')!
      const w = c.clientWidth, h = c.clientHeight, d = Math.min(devicePixelRatio, 2)
      c.width = w * d; c.height = h * d; ctx.scale(d, d); ctx.clearRect(0, 0, w, h)
      ctx.fillStyle = 'rgba(255,255,255,.1)'; ctx.fillRect(0, h / 2, w, 1)
      if (!ready) return
      peaks.forEach((p, i) => { const x = (i / peaks.length) * w; const hh = Math.max(1, p * h * 0.92); ctx.fillStyle = `rgba(240,244,250,${0.35 + p * 0.55})`; ctx.fillRect(x, (h - hh) / 2, Math.max(1, w / peaks.length - 1), hh) })
    }
    draw()
    const ro = new ResizeObserver(draw); ro.observe(cv.current!)
    return () => ro.disconnect()
  }, [peaks, ready])
  const seek = useDrag((v) => engine.seek(v))
  useFrame((f) => {
    if (ph.current) ph.current.style.transform = `translateX(${f.pos * 100}%)`
    if (lv.current) lv.current.style.transform = `scaleY(${Math.min(1, f.stem[id] ** 1.6 * 0.8)})`
  })
  return (
    <div className="ca-wave" data-muted={muted} {...seek}>
      <canvas ref={cv} />
      <div className="ca-ph-track"><div ref={ph} className="ca-ph"><s /></div></div>
      <div className="ca-lv"><div ref={lv} /></div>
    </div>
  )
}

function Lane({ id, i }: { id: StemId; i: number }) {
  const p = useStore((s) => s.stems[id])
  const sel = useStore((s) => s.selStem === id)
  const chainOn = useStore((s) => s.chainOn[id])
  const preset = useStore((s) => s.chainPreset[id])
  const stem = STEMS.find((s) => s.id === id)!
  return (
    <div className="ca-lane" data-sel={sel} onPointerDown={() => actions.selStem(id)}>
      <div className="ca-lane-id">
        <div className="ca-lane-name"><i>{pad(i + 1)}</i><b>{stem.name.toUpperCase()}</b></div>
        <div className="ca-ms">
          <button className={p.mute ? 'on' : ''} onClick={() => actions.setStem(id, { mute: !p.mute })} aria-label="Mute">M</button>
          <button className={p.solo ? 'on' : ''} onClick={() => actions.setStem(id, { solo: !p.solo })} aria-label="Solo">S</button>
        </div>
        <div className="ca-chain" title={preset}>{stem.chain.map((c, j) => <button key={c} className={chainOn[j] ? 'on' : ''} onClick={() => actions.toggleChain(id, j)}>{c.toUpperCase()}</button>)}</div>
        <div className="ca-preset">▸ {preset}</div>
      </div>
      <div className="ca-lane-params">{(Object.keys(RANGES) as PK[]).map((k) => <VBar key={k} id={id} k={k} />)}</div>
      <Wave id={id} />
    </div>
  )
}

function PresetPanel() {
  const { cat, q, favs, counts, items } = usePresets()
  const prev = useStore((s) => s.previewId)
  const selStem = useStore((s) => s.selStem)
  return (
    <div className="ca-presets">
      <div className="ca-search"><i>/</i><input data-focus-target aria-label="Search presets" placeholder={`search ${counts.all} presets`} value={q} onChange={(e) => actions.presetQuery(e.target.value)} /></div>
      <div className="ca-cats">
        {(['all', 'genre', 'mix', 'vocal', 'fx', 'master'] as const).map((c) => <button key={c} className={cat === c ? 'on' : ''} onClick={() => actions.presetCat(c)}>{CAT_LABEL[c].toUpperCase()}<i>{counts[c]}</i></button>)}
      </div>
      <div className="ca-plist" role="list">
        {items.map((p) => (
          <div key={p.id} className="ca-prow" role="listitem" data-prev={prev === p.id}>
            <button className={`ca-fav ${favs.includes(p.id) ? 'on' : ''}`} onClick={() => actions.toggleFav(p.id)} aria-label="Favorite">{favs.includes(p.id) ? '◆' : '◇'}</button>
            <div className="ca-pn"><b>{p.name}</b><span>{p.cat.toUpperCase()} · {p.blurb}</span></div>
            <button className="ca-pv" onClick={() => actions.preview(p.id)}>{prev === p.id ? 'STOP' : 'PREV'}</button>
            <button className="ca-pa" onClick={() => actions.applyPreset(p)}>APPLY</button>
          </div>
        ))}
        {!items.length && <div className="ca-none">NO MATCH</div>}
      </div>
      <div className="ca-pfoot">APPLY TARGETS <b>{STEMS.find((s) => s.id === selStem)!.name.toUpperCase()}</b></div>
    </div>
  )
}

function Advanced() {
  const tab = useStore((s) => s.advTab)
  const title = useStore((s) => vibeById(s.vibeId)?.name ?? 'Untitled')
  const ab = useStore((s) => s.ab)
  const playing = useStore((s) => s.playing)
  const vers = useStore((s) => s.versions)
  const idx = useStore((s) => s.vIdx)
  const tabs: [string, string][] = [['generate', 'GENERATE'], ['separate', 'SEPARATE'], ['master', 'MASTER'], ['presets', 'PRESETS'], ['ab', 'A / B']]
  return (
    <section className="ca-adv">
      <div className="ca-adv-main">
        <div className="ca-strip">
          <div className="ca-strip-l">
            <h1 className="ca-title sm">{title.toUpperCase()} <em>/ IDEA 01</em></h1>
            <div className="ca-meta"><span>ADVANCED MIX</span><span>4 SOURCES</span><span>{engine.pattern.keyName.toUpperCase()}</span></div>
          </div>
          <div className="ca-strip-r">
            <button className="ca-chip" onClick={() => void actions.tool('split')}>SPLIT 4 STEMS</button>
            <button className="ca-chip" onClick={() => void actions.tool('remove_vocals')}>VOCALS / INST</button>
            <button className="ca-chip pri" onClick={() => void actions.doExport()}>EXPORT</button>
            <div className="ca-ab"><button className={ab === 'A' ? 'on' : ''} onClick={() => actions.setAB('A')}>A</button><button className={ab === 'B' ? 'on' : ''} onClick={() => actions.setAB('B')}>B</button></div>
          </div>
        </div>
        <div className="ca-lanes">
          {STEMS.map((s, i) => <Lane key={s.id} id={s.id} i={i} />)}
        </div>
        <div className="ca-adv-bot">
          <button className="ca-play sm" onClick={actions.toggle} data-playing={playing} aria-label="Play">{playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}</button>
          <Timecode />
          <div className="ca-hist"><button onClick={actions.undo} disabled={idx <= 0}>UNDO</button><button onClick={actions.redo} disabled={idx >= vers.length - 1}>REDO</button></div>
          <div className="ca-vers">{vers.map((v, i) => <button key={i} className={i === idx ? 'on' : ''} onClick={() => actions.jump(i)}><i>{pad(i + 1)}</i>{v.label.toUpperCase()}</button>)}</div>
          <button className="ca-chip" onClick={() => actions.setMode('easy')}>← EASY</button>
        </div>
      </div>
      <aside className="ca-col ca-panel">
        <div className="ca-tabs" role="tablist">{tabs.map(([k, l], i) => <button role="tab" key={k} className={tab === k ? 'on' : ''} onClick={() => actions.advTab(k as never)}><i>{pad(i + 1)}</i>{l}</button>)}</div>
        <div className="ca-tabbody">
          {tab === 'presets' && <PresetPanel />}
          {tab === 'generate' && <GenerateForm />}
          {tab === 'separate' && <SeparateForm />}
          {tab === 'master' && <MasterForm />}
          {tab === 'ab' && <ABForm />}
        </div>
      </aside>
    </section>
  )
}

function Drawer() {
  const open = useStore((s) => s.enginesOpen)
  return (
    <>
      <div className="ca-scrim" data-open={open} onClick={() => actions.engines(false)} />
      <aside className="ca-drawer" data-open={open} aria-hidden={!open}>
        <div className="ca-drawer-h"><h2>ENGINES</h2><span>ON YOUR 8 GB CARD</span><button onClick={() => actions.engines(false)}>CLOSE ESC</button></div>
        <div className="ca-drawer-sum">
          {(['fits', 'tight', 'no'] as const).map((k) => <span key={k}><b>{ENGINES.filter((e) => e.status === k).length}</b>{k === 'no' ? 'NOT RECOMMENDED' : k.toUpperCase()}</span>)}
        </div>
        <div className="ca-eng-list"><EngineRows /></div>
        <p className="ca-drawer-n">RTX 20 series or older: models run in fp16. The Studio picks low-memory settings and hides models that will not fit.</p>
      </aside>
    </>
  )
}
function Help() {
  const open = useStore((s) => s.helpOpen)
  if (!open) return null
  return (
    <div className="ca-help" onClick={() => actions.help(false)}>
      <div onClick={(e) => e.stopPropagation()}>
        <h2>KEYBOARD</h2>
        <dl>{SHORTCUTS.map(([k, d]) => <div key={k}><dt>{k}</dt><dd>{d}</dd></div>)}</dl>
      </div>
    </div>
  )
}
function Toasts() {
  const t = useStore((s) => s.toasts)
  return <div className="ca-toasts" aria-live="polite">{t.map((x) => <div key={x.id} data-k={x.kind}>{x.text}</div>)}</div>
}

export default function A() {
  const mode = useStore((s) => s.mode)
  useShortcuts()
  useEffect(() => { document.title = 'A · Nihil Field · The Muser'; document.body.style.background = '#000' }, [])
  return (
    <div className="ca" data-mode={mode}>
      <TerrainCanvas />
      <TopBar />
      <main className="ca-main">{mode === 'easy' ? <Easy /> : <Advanced />}</main>
      <Drawer />
      <Help />
      <Toasts />
    </div>
  )
}
