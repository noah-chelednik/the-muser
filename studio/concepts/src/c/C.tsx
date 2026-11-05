import { useEffect, useMemo, useRef, useState } from 'react'
import gsap from 'gsap'
import '@fontsource/barlow-condensed/500.css'
import '@fontsource/barlow-condensed/600.css'
import '@fontsource/barlow-condensed/700.css'
import '@fontsource/martian-mono/400.css'
import '@fontsource/martian-mono/500.css'
import './c.css'
import { ENGINES, FINISH, MACROS, SHORTCUTS, STEMS, TOOLS, VIBES, fmtTime, tempoWord, vibeById, type StemId } from '../shared/data'
import { engine } from '../shared/engine'
import { stemPeaks } from '../shared/music'
import { actions, fx, getState, useStore } from '../shared/store'
import { useShortcuts } from '../shared/shortcuts'
import { useDrag, useFrame } from '../shared/hooks'
import { ABForm, CAT_LABEL, EngineRows, GenerateForm, MasterForm, PARAM_NAME, PK_LIST, SeparateForm, fmtParam, frac, isBip, unfrac, usePresets, type PK } from '../shared/ui'
import { Phosphor } from './Phosphor'

const pad = (n: number, w = 3) => String(Math.round(n)).padStart(w, '0')
const FAMILY_HASH = (s: string) => { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) } return h >>> 0 }
const barcode = (id: string) => { let h = FAMILY_HASH(id); const out: number[] = []; for (let i = 0; i < 7; i++) { out.push(1 + (h & 3)); h = (h >>> 2) | (h << 30) } return out }
const STEM_MACRO: Record<StemId, string> = { drums: 'ENERGY', bass: 'BASS', keys: 'BRIGHT', voice: 'VOCALS' }

/* ------------------------------------------------------------ scope */
function Scope({ compact }: { compact?: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const ph = useRef<Phosphor | null>(null)
  const [fail, setFail] = useState(false)
  useEffect(() => { try { ph.current = new Phosphor(ref.current!) } catch { setFail(true) } }, [])
  useFrame((f, _n, dt) => {
    const st = getState()
    fx.pulse *= Math.pow(0.03, dt)
    ph.current?.render(f, { gain: 0.7 + st.macros.energy / 130, pulse: fx.pulse, making: st.phase === 'making' ? st.progress : 0, seed: 0, compact: compact ? 1 : 0 }, Math.min(dt, 0.05))
  })
  return <canvas ref={ref} className={`cc-scope ${fail ? 'fail' : ''}`} />
}

function Title({ text, small }: { text: string; small?: boolean }) {
  const ref = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const ch = ref.current!.querySelectorAll('.ch')
    gsap.fromTo(ch, { opacity: 0, y: 24, filter: 'blur(6px)' }, { opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.55, ease: 'power3.out', stagger: 0.022 })
  }, [text])
  return <h1 ref={ref} className={`cc-title ${small ? 'sm' : ''}`} aria-label={text}>{text.toUpperCase().split('').map((c, i) => <span className="ch" key={i} aria-hidden>{c === ' ' ? '\u00A0' : c}</span>)}</h1>
}

/* ------------------------------------------------------------ top */
function Top() {
  const mode = useStore((s) => s.mode)
  const vibeId = useStore((s) => s.vibeId)
  const energy = useStore((s) => s.macros.energy)
  const meas = useStore((s) => s.measured)
  const playing = useStore((s) => s.playing)
  const v = vibeById(vibeId)
  const bpm = (v?.bpm ?? 78) * (0.9 + (energy / 100) * 0.22)
  return (
    <header className="cc-top">
      <a className="cc-brand" href="#/"><svg viewBox="0 0 24 24" aria-hidden><path d="M2 12h4l2-7 3 14 3-10 2 3h6" /></svg><b>THE MUSER</b><i>CATHODE</i></a>
      <nav className="cc-modes" data-mode={mode}>
        <button className={mode === 'easy' ? 'on' : ''} onClick={() => actions.setMode('easy')}><i>01</i>EASY</button>
        <button className={mode === 'advanced' ? 'on' : ''} onClick={() => actions.setMode('advanced')}><i>02</i>ADVANCED</button>
        <span className="cc-modeind" />
      </nav>
      <div className="cc-read">
        <span className={`cc-rec ${playing ? 'on' : ''}`}><s />{playing ? 'LIVE' : 'HALT'}</span>
        <span>{Math.round(bpm)} <i>BPM</i></span>
        <span>{v ? `${v.key} ${v.minor ? 'MIN' : 'MAJ'}` : 'A MIN'}</span>
        <span>{meas ? meas.lufs.toFixed(1) : '--.-'} <i>LUFS</i></span>
        <button className="cc-eng" onClick={() => actions.engines(true)}>ENGINES<b>8 GB</b></button>
        <button className="cc-q" onClick={() => actions.help(true)} aria-label="Shortcuts">?</button>
      </div>
    </header>
  )
}

/* ------------------------------------------------------------ faders */
function Fader({ k }: { k: (typeof MACROS)[number] }) {
  const val = useStore((s) => s.macros[k.key])
  const base = useStore((s) => vibeById(s.vibeId)?.macros[k.key] ?? 50)
  const sel = useStore((s) => s.selMacro === k.key)
  const drag = useDrag((v) => actions.setMacro(k.key, v * 100), { axis: 'y', onEnd: () => actions.commitMacros() })
  return (
    <div className="cc-fd" data-sel={sel} onPointerDown={() => actions.selMacro(k.key)}>
      <b>{k.label.toUpperCase()}</b>
      <output>{pad(val)}</output>
      <span className="hi">{k.hi.toUpperCase()}</span>
      <div className="cc-ft" {...drag} role="slider" tabIndex={0} aria-label={k.label} aria-valuenow={val} aria-valuemin={0} aria-valuemax={100}>
        <div className="cc-fl" style={{ height: `${val}%` }} />
        <div className="cc-fb" style={{ bottom: `${base}%` }} />
        <div className="cc-fc" style={{ bottom: `${val}%` }}><s /></div>
      </div>
      <span className="lo">{k.lo.toUpperCase()}</span>
    </div>
  )
}

/* ------------------------------------------------------------ shelf */
function Cart({ id, name, sub, on, onClick, onDouble, fav, narrow }: { id: string; name: string; sub: string; on: boolean; onClick: () => void; onDouble?: () => void; fav?: boolean; narrow?: boolean }) {
  const bars = useMemo(() => barcode(id), [id])
  return (
    <button className={`cc-cart ${on ? 'on' : ''} ${narrow ? 'nw' : ''}`} onClick={onClick} onDoubleClick={onDouble} aria-pressed={on} title={name} data-cart={id}>
      <span className="cc-cart-top">{fav ? '★' : ''}</span>
      <span className="cc-cart-name">{name}</span>
      <span className="cc-bars">{bars.map((w, i) => <s key={i} style={{ height: w * 2 + 1 }} />)}</span>
      <span className="cc-cart-sub">{sub}</span>
    </button>
  )
}
function MakeDock() {
  const phase = useStore((s) => s.phase)
  const p = useStore((s) => s.progress)
  const stage = useStore((s) => s.stage)
  const prompt = useStore((s) => s.prompt)
  return (
    <div className="cc-dock">
      <label className="cc-brief"><span>BRIEF</span><input data-prompt data-focus-target aria-label="Describe the vibe" placeholder="rainy night drive, warm and dusty" value={prompt} onChange={(e) => actions.setPrompt(e.target.value)} maxLength={300} /></label>
      <button className="cc-make" data-phase={phase} disabled={phase === 'making'} onClick={() => void actions.make()}>
        <span>{phase === 'making' ? stage.toUpperCase() : phase === 'ready' ? 'MAKE IT AGAIN' : 'MAKE IT'}</span>
        <em>{phase === 'making' ? `${Math.round(p * 100)}%` : 'ENTER'}</em>
        <s style={{ transform: `scaleX(${phase === 'making' ? p : 0})` }} />
      </button>
    </div>
  )
}
function useWheelX() {
  const r = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = r.current!
    const f = (e: WheelEvent) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { el.scrollLeft += e.deltaY; e.preventDefault() } }
    el.addEventListener('wheel', f, { passive: false }); return () => el.removeEventListener('wheel', f)
  }, [])
  return r
}
function VibeShelf() {
  const sel = useStore((s) => s.vibeId)
  const hov = useStore((s) => s.hoverVibe)
  const v = vibeById(hov ?? sel)
  const row = useWheelX()
  useEffect(() => { const r = row.current, el = r?.querySelector<HTMLElement>('.cc-cart.on'); if (r && el) r.scrollTo({ left: el.offsetLeft - r.clientWidth / 2 + el.offsetWidth / 2, behavior: 'smooth' }) }, [sel, row])
  return (
    <section className="cc-shelf">
      <MakeDock />
      <div className="cc-lib">
        <div className="cc-lib-h"><b>LIBRARY</b><i>24 VIBES</i><span className="cc-lib-sel">{v ? <><em>{v.name.toUpperCase()}</em> {v.desc.replace(/\.$/, '')}</> : 'Pick a cartridge or write a brief'}</span><kbd>← →</kbd></div>
        <div className="cc-row" ref={row} onPointerLeave={() => actions.hoverVibe(null)}>
          {VIBES.map((x, i) => <Cart key={x.id} id={x.id} name={x.name} sub={`${pad(i + 1, 2)} · ${x.bpm}`} on={sel === x.id} onClick={() => actions.pickVibe(x.id)} />)}
        </div>
      </div>
    </section>
  )
}
function PresetShelf() {
  const { cat, q, favs, counts, items } = usePresets()
  const [pick, setPick] = useState<string | null>(null)
  const prev = useStore((s) => s.previewId)
  const stem = useStore((s) => s.selStem)
  const row = useWheelX()
  const cur = items.find((p) => p.id === pick) ?? items[0]
  return (
    <section className="cc-shelf adv">
      <div className="cc-pre-side">
        <label className="cc-brief"><span>SEARCH {counts.all} PRESETS</span><input data-focus-target aria-label="Search presets" placeholder="warm, vinyl, wide..." value={q} onChange={(e) => actions.presetQuery(e.target.value)} /></label>
        <div className="cc-cats">{(['all', 'genre', 'mix', 'vocal', 'fx', 'master'] as const).map((c) => <button key={c} className={cat === c ? 'on' : ''} onClick={() => actions.presetCat(c)}>{CAT_LABEL[c].toUpperCase()}<sup>{counts[c]}</sup></button>)}</div>
      </div>
      <div className="cc-lib">
        <div className="cc-lib-h">
          <b>PRESETS</b><i>{items.length} SHOWN</i>
          {cur && <span className="cc-lib-sel"><em>{cur.name.toUpperCase()}</em> {cur.cat} · {cur.blurb}</span>}
          {cur && <span className="cc-acts">
            <button onClick={() => actions.preview(cur.id)}>{prev === cur.id ? 'STOP' : 'HEAR'}</button>
            <button onClick={() => actions.toggleFav(cur.id)}>{favs.includes(cur.id) ? '★' : '☆'}</button>
            <button className="go" onClick={() => actions.applyPreset(cur)}>APPLY TO {STEMS.find((s) => s.id === stem)!.name.toUpperCase()}</button>
          </span>}
        </div>
        <div className="cc-row" ref={row}>
          {items.map((p, i) => <Cart key={p.id} id={p.id} name={p.name} narrow fav={favs.includes(p.id)} sub={pad(i + 1, 3)} on={cur?.id === p.id} onClick={() => setPick(p.id)} onDouble={() => actions.applyPreset(p)} />)}
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------ easy */
function Transport() {
  const playing = useStore((s) => s.playing)
  const versions = useStore((s) => s.versions)
  const idx = useStore((s) => s.vIdx)
  const vibeId = useStore((s) => s.vibeId)
  const phase = useStore((s) => s.phase)
  const cv = useRef<HTMLCanvasElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  const tc = useRef<HTMLSpanElement>(null)
  const peaks = useMemo(() => { const a = stemPeaks('drums', engine.pattern, 320), b = stemPeaks('bass', engine.pattern, 320), c = stemPeaks('keys', engine.pattern, 320); return Array.from(a, (x, i) => Math.min(1, x * 0.55 + b[i] * 0.45 + c[i] * 0.3)) }, [vibeId])
  useEffect(() => {
    const c = cv.current!, ctx = c.getContext('2d')!, w = c.clientWidth, h = c.clientHeight, d = Math.min(devicePixelRatio, 2)
    c.width = w * d; c.height = h * d; ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, w, h)
    for (let b = 0; b <= 16; b++) { ctx.fillStyle = 'rgba(237,235,230,.28)'; ctx.fillRect(Math.round((b / 16) * (w - 1)), h - (b % 4 === 0 ? 8 : 4), 1, b % 4 === 0 ? 8 : 4) }
    if (phase !== 'ready') return
    peaks.forEach((p, i) => { const x = (i / peaks.length) * w, hh = Math.max(1, p * (h - 10)); ctx.fillStyle = 'rgba(155,255,61,.85)'; ctx.fillRect(x, (h - 10 - hh) / 2 + 2, Math.max(1, w / peaks.length - 1.2), hh) })
  }, [peaks, phase])
  useFrame((f) => { if (ph.current) ph.current.style.transform = `translateX(${f.pos * 100}%)`; if (tc.current) tc.current.textContent = fmtTime(engine.time) })
  const seek = useDrag((v) => engine.seek(v))
  return (
    <div className="cc-transport">
      <button className="cc-play" onClick={actions.toggle} data-playing={playing} aria-label={playing ? 'Pause' : 'Play'}>{playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}</button>
      <div className="cc-tc"><span ref={tc}>0:00</span><i>/ {fmtTime(engine.duration)}</i></div>
      <div className="cc-ov" {...seek}><canvas ref={cv} /><div className="cc-oph"><div ref={ph} /></div></div>
      <div className="cc-revs">
        <button onClick={actions.undo} disabled={idx <= 0}>UNDO</button><button onClick={actions.redo} disabled={idx >= versions.length - 1}>REDO</button>
        <ol>{versions.map((x, i) => <li key={i}><button className={i === idx ? 'on' : ''} onClick={() => actions.jump(i)}><i>R{i + 1}</i>{x.label.toUpperCase()}</button></li>)}</ol>
      </div>
    </div>
  )
}
function Mons() {
  return (
    <div className="cc-mons">
      <h2 className="cc-h"><b>STEM LEVELS</b><i>LIVE</i></h2>
      {STEMS.map((st) => <HMeter key={st.id} id={st.id} name={st.name} />)}
    </div>
  )
}
function HMeter({ id, name }: { id: StemId; name: string }) {
  const r = useRef<HTMLDivElement>(null)
  const pk = useRef<HTMLElement>(null)
  const peak = useRef(0)
  useFrame((f, _n, dt) => {
    const v = Math.min(1, f.stem[id] ** 0.9 * 1.15)
    peak.current = Math.max(v, peak.current - dt * 0.35)
    if (r.current) r.current.style.width = `${v * 100}%`
    if (pk.current) pk.current.style.left = `${peak.current * 100}%`
  })
  return <div className="cc-hm"><span>{name.toUpperCase()}</span><div className="cc-hmt"><div ref={r} /><s ref={pk} /></div></div>
}
function EasyRight() {
  const fin = useStore((s) => s.finish)
  const meas = useStore((s) => s.measured)
  const busy = useStore((s) => s.busy)
  const ready = useStore((s) => s.phase === 'ready')
  const exp = useStore((s) => s.exported)
  return (
    <aside className="cc-right">
      <h2 className="cc-h"><b>FINISH</b><i>LUFS / dBTP</i></h2>
      <div className="cc-fin">{FINISH.map((f) => <button key={f.key} className={fin === f.key ? 'on' : ''} disabled={!ready || !!busy} onClick={() => void actions.finishFor(f.key)}><b>{f.label.toUpperCase()}</b><em>{f.lufs} / {f.tp}</em></button>)}</div>
      <div className="cc-meas">{busy ? <span className="cc-busy"><s />{busy.toUpperCase()}</span> : meas ? <span>MEASURED <b>{meas.lufs.toFixed(1)}</b> LUFS · <b>{meas.tp.toFixed(1)}</b> dBTP · CLEAN</span> : <span className="dim">NO CLIPPING. PICK A TARGET.</span>}</div>
      <button className="cc-export" disabled={!ready || !!busy} onClick={() => void actions.doExport()}><span>EXPORT WAV + MP3</span><kbd>X</kbd></button>
      {exp && <div className="cc-files">{exp.map((f) => <a key={f.name} href="#/c" onClick={(e) => e.preventDefault()}>{f.name}<i>{f.size}</i></a>)}</div>}
      <h2 className="cc-h"><b>ONE CLICK</b><i>1 to 5</i></h2>
      <div className="cc-tools">{TOOLS.map((t, i) => <button key={t.key} disabled={!ready || !!busy} onClick={() => void actions.tool(t.key)}><i>{i + 1}</i><span>{t.label.toUpperCase()}</span></button>)}</div>
      <Mons />
    </aside>
  )
}
function EasyMain() {
  const hov = useStore((s) => s.hoverVibe)
  const vibeId = useStore((s) => s.vibeId)
  const phase = useStore((s) => s.phase)
  const energy = useStore((s) => s.macros.energy)
  const v = vibeById(hov ?? vibeId)
  const bpm = v ? v.bpm * (0.9 + (energy / 100) * 0.22) : 0
  return (
    <div className="cc-main easy">
      <aside className="cc-macros">
        <h2 className="cc-h"><b>MACROS</b><button className="cc-link" onClick={actions.resetMacros}>RESET</button></h2>
        <div className="cc-fds">{MACROS.map((m) => <Fader key={m.key} k={m} />)}</div>
      </aside>
      <section className="cc-stage">
        <Scope />
        <div className="cc-hud">
          <p className="cc-kick"><s />{phase === 'making' ? 'WRITING' : phase === 'idle' && !v ? 'STANDBY' : 'SIGNAL LOCKED'}<span>CH 01 · {v ? v.family.toUpperCase() : '---'}</span></p>
          <Title text={v ? v.name : 'Choose a vibe'} />
          <p className="cc-sub">{v ? <>{tempoWord(bpm).toUpperCase()} <span>/</span> {Math.round(bpm)} BPM <span>/</span> {v.key} {v.minor ? 'MIN' : 'MAJ'} <span>/</span> 4/4</> : 'PICK A CARTRIDGE BELOW'}</p>
        </div>
        <Transport />
      </section>
      <EasyRight />
    </div>
  )
}

/* ------------------------------------------------------------ advanced */
function MiniWave({ id }: { id: StemId }) {
  const cv = useRef<HTMLCanvasElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  const vibeId = useStore((s) => s.vibeId)
  const ready = useStore((s) => s.phase === 'ready')
  const muted = useStore((s) => s.stems[id].mute)
  const peaks = useMemo(() => stemPeaks(id, engine.pattern, 120), [vibeId, id])
  useEffect(() => {
    const draw = () => {
      const c = cv.current!, ctx = c.getContext('2d')!, w = c.clientWidth, h = c.clientHeight, d = Math.min(devicePixelRatio, 2)
      c.width = w * d; c.height = h * d; ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, w, h)
      ctx.fillStyle = 'rgba(237,235,230,.14)'; ctx.fillRect(0, h / 2, w, 1)
      if (!ready) return
      peaks.forEach((p, i) => { const x = (i / peaks.length) * w, hh = Math.max(1, p * h * 0.9); ctx.fillStyle = 'rgba(155,255,61,.9)'; ctx.fillRect(x, (h - hh) / 2, Math.max(1, w / peaks.length - 1), hh) })
    }
    draw(); const ro = new ResizeObserver(draw); ro.observe(cv.current!); return () => ro.disconnect()
  }, [peaks, ready])
  useFrame((f) => { if (ph.current) ph.current.style.transform = `translateX(${f.pos * 100}%)` })
  const seek = useDrag((v) => engine.seek(v))
  return <div className="cc-mw" data-muted={muted} {...seek}><canvas ref={cv} /><div className="cc-oph"><div ref={ph} /></div></div>
}
function HSlider({ id, k }: { id: StemId; k: PK }) {
  const val = useStore((s) => s.stems[id][k]) as number
  const f = frac(k, val)
  const drag = useDrag((v) => actions.setStem(id, { [k]: unfrac(k, v) }))
  const bip = isBip(k)
  return (
    <div className="cc-hs" onDoubleClick={() => actions.setStem(id, { [k]: 0 })}>
      <span>{PARAM_NAME[k].toUpperCase()}</span>
      <div className="cc-ht" {...drag} role="slider" tabIndex={0} aria-label={`${id} ${k}`} aria-valuenow={val}>
        <div className="cc-hf" style={bip ? { left: `${Math.min(50, f * 100)}%`, width: `${Math.abs(f - 0.5) * 100}%` } : { left: 0, width: `${f * 100}%` }} />
        <div className="cc-hk" style={{ left: `${f * 100}%` }} />
      </div>
      <b>{fmtParam(k, val)}</b>
    </div>
  )
}
function Led({ id }: { id: StemId }) {
  const r = useRef<HTMLDivElement>(null)
  const pk = useRef<HTMLDivElement>(null)
  const peak = useRef(0)
  useFrame((f, _n, dt) => {
    const v = Math.min(1, f.stem[id] ** 0.9 * 1.15)
    peak.current = Math.max(v, peak.current - dt * 0.35)
    if (r.current) r.current.style.height = `${v * 100}%`
    if (pk.current) pk.current.style.bottom = `${peak.current * 100}%`
  })
  return <div className="cc-led"><div ref={r} /><s ref={pk} /></div>
}
function Strip({ id }: { id: StemId }) {
  const s = STEMS.find((x) => x.id === id)!
  const p = useStore((x) => x.stems[id])
  const sel = useStore((x) => x.selStem === id)
  const chainOn = useStore((x) => x.chainOn[id])
  const preset = useStore((x) => x.chainPreset[id])
  const drag = useDrag((v) => actions.setStem(id, { vol: unfrac('vol', v) }), { axis: 'y' })
  const f = frac('vol', p.vol)
  return (
    <section className="cc-strip" data-sel={sel} onPointerDown={() => actions.selStem(id)}>
      <header><b>{s.name.toUpperCase()}</b><i>{s.short}</i><div><button className={p.mute ? 'on' : ''} onClick={() => actions.setStem(id, { mute: !p.mute })} aria-label="Mute">M</button><button className={p.solo ? 'on' : ''} onClick={() => actions.setStem(id, { solo: !p.solo })} aria-label="Solo">S</button></div></header>
      <MiniWave id={id} />
      <div className="cc-fm">
        <div className="cc-vt" {...drag} role="slider" tabIndex={0} aria-label={`${id} level`} aria-valuenow={p.vol} onDoubleClick={() => actions.setStem(id, { vol: 0 })}>
          <div className="cc-vz" style={{ bottom: `${frac('vol', 0) * 100}%` }} />
          <div className="cc-vc" style={{ bottom: `${f * 100}%` }}><s /></div>
        </div>
        <Led id={id} />
        <div className="cc-fv"><b>{fmtParam('vol', p.vol)}</b><span>dB</span><em>{preset.toUpperCase()}</em></div>
      </div>
      <div className="cc-pm">{PK_LIST.filter((k) => k !== 'vol').map((k) => <HSlider key={k} id={id} k={k} />)}</div>
      <div className="cc-chain">{s.chain.map((c, j) => <button key={c} className={chainOn[j] ? 'on' : ''} onClick={() => actions.toggleChain(id, j)}>{c.toUpperCase()}</button>)}</div>
    </section>
  )
}
function AdvRight() {
  const tab = useStore((s) => s.advTab)
  const tabs: [string, string][] = [['generate', 'GENERATE'], ['separate', 'SEPARATE'], ['master', 'MASTER'], ['ab', 'A / B']]
  const cur = tab === 'presets' ? 'generate' : tab
  return (
    <aside className="cc-right adv">
      <div className="cc-tabs" role="tablist">{tabs.map(([k, l], i) => <button role="tab" key={k} className={cur === k ? 'on' : ''} onClick={() => actions.advTab(k as never)}><i>{i + 1}</i>{l}</button>)}</div>
      <div className="cc-tabbody">
        {cur === 'generate' && <GenerateForm />}
        {cur === 'separate' && <SeparateForm />}
        {cur === 'master' && <MasterForm />}
        {cur === 'ab' && <ABForm />}
      </div>
    </aside>
  )
}
function AdvMain() {
  const vibeId = useStore((s) => s.vibeId)
  const ab = useStore((s) => s.ab)
  const v = vibeById(vibeId)
  return (
    <div className="cc-main adv">
      <section className="cc-stage mini">
        <Scope compact />
        <div className="cc-hud">
          <p className="cc-kick"><s />4 STEMS · LIVE<span>{v?.key} {v?.minor ? 'MIN' : 'MAJ'} · {v?.bpm} BPM</span></p>
          <Title text={v?.name ?? 'Untitled'} small />
        </div>
        <div className="cc-adv-actions">
          <button onClick={() => void actions.tool('split')}>SPLIT 4 STEMS</button>
          <button onClick={() => void actions.tool('remove_vocals')}>VOCALS / INST</button>
          <button className="go" onClick={() => void actions.doExport()}>EXPORT</button>
          <div className="cc-ab"><button className={ab === 'A' ? 'on' : ''} onClick={() => actions.setAB('A')}>A</button><button className={ab === 'B' ? 'on' : ''} onClick={() => actions.setAB('B')}>B</button></div>
        </div>
        <Transport />
      </section>
      <div className="cc-strips">{STEMS.map((s) => <Strip key={s.id} id={s.id} />)}</div>
      <AdvRight />
    </div>
  )
}

/* ------------------------------------------------------------ overlays */
function Drawer() {
  const open = useStore((s) => s.enginesOpen)
  return (
    <>
      <div className="cc-scrim" data-open={open} onClick={() => actions.engines(false)} />
      <aside className="cc-drawer" data-open={open} aria-hidden={!open}>
        <div className="cc-dh"><h2>ENGINES</h2><span>RTX 8 GB · FIT CHECK</span><button onClick={() => actions.engines(false)}>CLOSE · ESC</button></div>
        <div className="cc-dsum">{(['fits', 'tight', 'no'] as const).map((k) => <span key={k} data-k={k}><b>{ENGINES.filter((e) => e.status === k).length}</b>{k === 'no' ? 'NO' : k === 'fits' ? 'FIT' : 'TIGHT'}</span>)}</div>
        <div className="cc-elist"><EngineRows /></div>
        <p className="cc-dn">RTX 20 series or older runs models in fp16. The Studio picks low-memory settings and hides models that will not fit.</p>
      </aside>
    </>
  )
}
function Help() {
  const open = useStore((s) => s.helpOpen)
  if (!open) return null
  return <div className="cc-help" onClick={() => actions.help(false)}><div onClick={(e) => e.stopPropagation()}><h2>KEYBOARD</h2><dl>{SHORTCUTS.map(([k, d]) => <div key={k}><dt>{k}</dt><dd>{d}</dd></div>)}</dl></div></div>
}
function Toasts() { const t = useStore((s) => s.toasts); return <div className="cc-toasts" aria-live="polite">{t.map((x) => <div key={x.id}>{x.text}</div>)}</div> }

export default function C() {
  const mode = useStore((s) => s.mode)
  useShortcuts()
  useEffect(() => { document.title = 'C · Cathode · The Muser'; document.body.style.background = '#0D0E0F' }, [])
  useEffect(() => { const dn = () => fx.hit(0.5); window.addEventListener('pointerdown', dn); return () => window.removeEventListener('pointerdown', dn) }, [])
  return (
    <div className="cc" data-mode={mode}>
      <Top />
      {mode === 'easy' ? <EasyMain /> : <AdvMain />}
      {mode === 'easy' ? <VibeShelf /> : <PresetShelf />}
      <Drawer /><Help /><Toasts />
    </div>
  )
}
