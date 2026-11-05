import { useEffect, useMemo, useRef } from 'react'
import gsap from 'gsap'
import '@fontsource/instrument-serif/400.css'
import '@fontsource/instrument-serif/400-italic.css'
import '@fontsource/instrument-sans/400.css'
import '@fontsource/instrument-sans/500.css'
import '@fontsource/instrument-sans/600.css'
import '@fontsource/dm-mono/400.css'
import '@fontsource/dm-mono/500.css'
import '@fontsource/bravura/400.css'
import './b.css'
import { FINISH, MACROS, SHORTCUTS, STEMS, TOOLS, VIBES, dynFor, fmtTime, tempoWord, vibeById, type StemId } from '../shared/data'
import { NB, engine } from '../shared/engine'
import { stemPeaks } from '../shared/music'
import { actions, getState, fx, useStore } from '../shared/store'
import { useShortcuts } from '../shared/shortcuts'
import { useDrag, useFrame } from '../shared/hooks'
import { ABForm, CAT_LABEL, EngineRows, GenerateForm, MasterForm, PARAM_NAME, PK_LIST, SeparateForm, fmtParam, frac, isBip, unfrac, usePresets, type PK } from '../shared/ui'
import { ENGINES } from '../shared/data'
import { Staff, eventsFor, useScoreMotion } from './Score'

const DYN: Record<string, string> = { ppp: '\uE52A', pp: '\uE52B', p: '\uE520', mp: '\uE52C', mf: '\uE52D', f: '\uE522', ff: '\uE52F', fff: '\uE530' }
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX', 'XXI', 'XXII', 'XXIII', 'XXIV']
const pad = (n: number, w = 2) => String(n).padStart(w, '0')
const STEM_MACRO: Record<StemId, 'energy' | 'bass' | 'brightness' | 'vocals'> = { drums: 'energy', bass: 'bass', keys: 'brightness', voice: 'vocals' }
const STEM_LABEL: Record<StemId, string> = { drums: 'Percussion', bass: 'Bass', keys: 'Keys', voice: 'Voice' }

function Dyn({ v, className }: { v: number; className?: string }) { return <span className={`cb-dyn ${className ?? ''}`}>{DYN[dynFor(v)]}</span> }

function Seismo() {
  const cv = useRef<HTMLCanvasElement>(null)
  useFrame((f) => {
    const c = cv.current!, ctx = c.getContext('2d')!
    const w = c.clientWidth, h = c.clientHeight, d = Math.min(devicePixelRatio, 2)
    if (c.width !== Math.round(w * d)) { c.width = Math.round(w * d); c.height = Math.round(h * d) }
    ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, w, h)
    const n = Math.floor(w / 5)
    ctx.lineWidth = 1
    for (let i = 0; i < n; i++) {
      const t = i / n
      const b = Math.min(NB - 1, Math.floor(Math.pow(t, 0.8) * (NB - 1)))
      const v = Math.min(1, (f.spec[b] ?? 0) * 1.35)
      const x = Math.round(i * (w / n)) + 0.5
      const len = 3 + v * (h - 4)
      ctx.strokeStyle = `rgba(11,11,12,${0.18 + v * 0.8})`
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, len); ctx.stroke()
      if (v > 0.55) { ctx.fillStyle = '#D9361E'; ctx.fillRect(x - 1, len - 1, 3, 2) }
    }
  })
  return <canvas ref={cv} className="cb-seismo" />
}

function Title({ text, small }: { text: string; small?: boolean }) {
  const ref = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const ch = ref.current!.querySelectorAll('.ch > i')
    gsap.fromTo(ch, { yPercent: 105 }, { yPercent: 0, duration: 0.7, ease: 'expo.out', stagger: 0.018 })
  }, [text])
  return (
    <h1 ref={ref} className={`cb-title ${small ? 'sm' : ''}`} aria-label={text}>
      {text.split('').map((c, i) => <span key={i} className="ch" aria-hidden>{<i>{c === ' ' ? '\u00A0' : c}</i>}</span>)}
    </h1>
  )
}

/* ---------------- top ---------------- */
function Top() {
  const mode = useStore((s) => s.mode)
  const vibeId = useStore((s) => s.vibeId)
  const energy = useStore((s) => s.macros.energy)
  const meas = useStore((s) => s.measured)
  const v = vibeById(vibeId)
  const bpm = (v?.bpm ?? 78) * (0.9 + (energy / 100) * 0.22)
  return (
    <header className="cb-top">
      <a className="cb-brand" href="#/"><span>The Muser</span><i>Opus Zero</i></a>
      <nav className="cb-modes" data-mode={mode}>
        <button className={mode === 'easy' ? 'on' : ''} onClick={() => actions.setMode('easy')}>Easy</button>
        <b>/</b>
        <button className={mode === 'advanced' ? 'on' : ''} onClick={() => actions.setMode('advanced')}>Advanced</button>
      </nav>
      <div className="cb-read">
        <span className="cb-r"><span className="cb-gl">{'\uE1D5'}</span> = {Math.round(bpm)}</span>
        <span className="cb-r">{v ? `${v.key} ${v.minor ? 'minor' : 'major'}` : 'A minor'}</span>
        <span className="cb-r">{meas ? `${meas.lufs.toFixed(1)} LUFS` : 'unmastered'}</span>
        <button className="cb-eng" onClick={() => actions.engines(true)}>Engines <b>8 GB</b></button>
        <button className="cb-q" onClick={() => actions.help(true)} aria-label="Shortcuts">?</button>
      </div>
    </header>
  )
}

/* ---------------- catalogue ---------------- */
function MakeBlock() {
  const phase = useStore((s) => s.phase)
  const p = useStore((s) => s.progress)
  const stage = useStore((s) => s.stage)
  const prompt = useStore((s) => s.prompt)
  return (
    <div className="cb-make-block">
      <label className="cb-brief"><span>Brief</span><input data-prompt data-focus-target aria-label="Describe the vibe" placeholder="rainy night drive, warm and dusty" value={prompt} onChange={(e) => actions.setPrompt(e.target.value)} maxLength={300} /></label>
      <button className="cb-make" data-phase={phase} onClick={() => void actions.make()} disabled={phase === 'making'}>
        <span>{phase === 'making' ? stage : phase === 'ready' ? 'Make it again' : 'Make it'}</span>
        <em>{phase === 'making' ? `${Math.round(p * 100)}%` : 'Enter'}</em>
        <s style={{ transform: `scaleX(${phase === 'making' ? p : 0})` }} />
      </button>
    </div>
  )
}
function Catalogue() {
  const sel = useStore((s) => s.vibeId)
  return (
    <>
      <h2 className="cb-h"><span>Catalogue</span><i>{VIBES.length} works</i></h2>
      <ol className="cb-cat" onPointerLeave={() => actions.hoverVibe(null)}>
        {VIBES.map((v, i) => (
          <li key={v.id}>
            <button className={sel === v.id ? 'on' : ''} onPointerEnter={() => actions.hoverVibe(v.id)} onFocus={() => actions.hoverVibe(v.id)} onClick={() => actions.pickVibe(v.id)} aria-pressed={sel === v.id}>
              <i>{ROMAN[i]}</i><b>{v.name}</b><u /><em>{v.bpm}</em>
            </button>
          </li>
        ))}
      </ol>
      <MakeBlock />
    </>
  )
}

/* ---------------- dynamics (macros) ---------------- */
function DynRow({ k }: { k: (typeof MACROS)[number] }) {
  const val = useStore((s) => s.macros[k.key])
  const base = useStore((s) => vibeById(s.vibeId)?.macros[k.key] ?? 50)
  const sel = useStore((s) => s.selMacro === k.key)
  const drag = useDrag((v) => actions.setMacro(k.key, v * 100), { onEnd: () => actions.commitMacros() })
  return (
    <div className="cb-dr" data-sel={sel} onPointerDown={() => actions.selMacro(k.key)}>
      <div className="cb-dr-h"><span>{k.label}</span><em>{k.dyn}</em><b>{pad(val, 3)}</b></div>
      <div className="cb-track" {...drag} role="slider" aria-label={k.label} aria-valuenow={val} aria-valuemin={0} aria-valuemax={100} tabIndex={0}>
        <div className="cb-tt" />
        <div className="cb-base" style={{ left: `${base}%` }} />
        <div className="cb-thumb" style={{ left: `${val}%` }}><Dyn v={val} /><s /></div>
      </div>
      <div className="cb-ends"><span>{k.lo}</span><span>{k.hi}</span></div>
    </div>
  )
}
function RightEasy() {
  const fin = useStore((s) => s.finish)
  const meas = useStore((s) => s.measured)
  const busy = useStore((s) => s.busy)
  const ready = useStore((s) => s.phase === 'ready')
  const exp = useStore((s) => s.exported)
  return (
    <>
      <h2 className="cb-h"><span>Dynamics</span><button className="cb-link" onClick={actions.resetMacros}>Reset</button></h2>
      <div className="cb-drs">{MACROS.map((m) => <DynRow key={m.key} k={m} />)}</div>
      <h2 className="cb-h"><span>Finish</span><i>LUFS / dBTP</i></h2>
      <div className="cb-fin">
        {FINISH.map((f) => <button key={f.key} className={fin === f.key ? 'on' : ''} disabled={!ready || !!busy} onClick={() => void actions.finishFor(f.key)}><span>{f.label}</span><u /><em>{f.lufs} / {f.tp}</em></button>)}
      </div>
      <div className="cb-meas">{busy ? <span className="cb-busy"><s />{busy}</span> : meas ? <span>Measured <b>{meas.lufs.toFixed(1)} LUFS</b> · <b>{meas.tp.toFixed(1)} dBTP</b> · clean</span> : <span className="dim">No clipping. Pick a target to master.</span>}</div>
      <button className="cb-export" disabled={!ready || !!busy} onClick={() => void actions.doExport()}><span>Export WAV + MP3</span><em>X</em></button>
      {exp && <div className="cb-files">{exp.map((f) => <a key={f.name} href="#/b" onClick={(e) => e.preventDefault()}>{f.name}<i>{f.size}</i></a>)}</div>}
      <h2 className="cb-h"><span>One click</span></h2>
      <div className="cb-tools">{TOOLS.map((t, i) => <button key={t.key} disabled={!ready || !!busy} onClick={() => void actions.tool(t.key)}><i>{i + 1}</i><span>{t.label}</span><em>→</em></button>)}</div>
    </>
  )
}

/* ---------------- score ---------------- */
function Wave({ id, h = 34 }: { id: StemId; h?: number }) {
  const cv = useRef<HTMLCanvasElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  const vibeId = useStore((s) => s.vibeId)
  const ready = useStore((s) => s.phase === 'ready')
  const muted = useStore((s) => s.stems[id].mute)
  const peaks = useMemo(() => stemPeaks(id, engine.pattern, 240), [vibeId, id])
  useEffect(() => {
    const draw = () => {
      const c = cv.current!, ctx = c.getContext('2d')!
      const w = c.clientWidth, hh = c.clientHeight, d = Math.min(devicePixelRatio, 2)
      c.width = w * d; c.height = hh * d; ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, w, hh)
      ctx.fillStyle = 'rgba(11,11,12,.2)'; ctx.fillRect(0, hh / 2, w, 1)
      if (!ready) return
      peaks.forEach((p, i) => { const x = (i / peaks.length) * w; const bh = Math.max(1, p * hh * 0.92); ctx.fillStyle = `rgba(11,11,12,${0.4 + p * 0.55})`; ctx.fillRect(x, (hh - bh) / 2, Math.max(1, w / peaks.length - 1.2), bh) })
    }
    draw(); const ro = new ResizeObserver(draw); ro.observe(cv.current!); return () => ro.disconnect()
  }, [peaks, ready])
  useFrame((f) => { if (ph.current) ph.current.style.transform = `translateX(${f.pos * 100}%)` })
  const seek = useDrag((v) => engine.seek(v))
  return (
    <div className="cb-wave" data-muted={muted} style={{ height: h }} {...seek}>
      <canvas ref={cv} />
      <div className="cb-wph"><div ref={ph}><s /></div></div>
    </div>
  )
}

function StaffRow({ id, adv }: { id: StemId; adv: boolean }) {
  const vibeId = useStore((s) => s.vibeId)
  const phase = useStore((s) => s.phase)
  const prog = useStore((s) => s.progress)
  const macro = useStore((s) => s.macros[STEM_MACRO[id]])
  const sel = useStore((s) => s.selStem === id)
  const p = useStore((s) => s.stems[id])
  const ev = useMemo(() => eventsFor(id), [vibeId, id])
  const idle = phase === 'idle'
  const reveal = phase === 'making' ? Math.min(1, prog * 1.15) : idle ? 0 : 1
  const lv = useRef<HTMLDivElement>(null)
  useFrame((f) => { if (lv.current) lv.current.style.transform = `scaleX(${Math.min(1, f.stem[id] ** 1.4)})` })
  return (
    <div className="cb-row" data-sel={sel} onPointerDown={() => actions.selStem(id)}>
      <div className="cb-rh">
        <div className="cb-rn"><span>{STEM_LABEL[id]}</span><Dyn v={macro} /></div>
        {adv && (
          <div className="cb-rc">
            <button className={p.mute ? 'on' : ''} onClick={() => actions.setStem(id, { mute: !p.mute })} aria-label="Mute">M</button>
            <button className={p.solo ? 'on' : ''} onClick={() => actions.setStem(id, { solo: !p.solo })} aria-label="Solo">S</button>
            <em>{fmtParam('vol', p.vol)} dB</em>
          </div>
        )}
        <div className="cb-lv"><div ref={lv} /></div>
      </div>
      <Staff id={id} ev={ev} hidden={reveal} />
    </div>
  )
}

function Score({ adv }: { adv: boolean }) {
  const root = useRef<HTMLDivElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  useScoreMotion(root, ph)
  return (
    <div className="cb-score" ref={root}>
      <div className="cb-bars">{[1, 2, 3, 4].map((n, i) => <span key={n} style={{ ['--i' as string]: i }}>{n}</span>)}</div>
      <div className="cb-rows">{STEMS.map((s) => <StaffRow key={s.id} id={s.id} adv={adv} />)}</div>
      <div className="cb-phlayer"><div className="cb-ph" ref={ph}><s /></div></div>
    </div>
  )
}

function Timecode() {
  const r = useRef<HTMLSpanElement>(null)
  useFrame(() => { if (r.current) r.current.textContent = `${fmtTime(engine.time)}` })
  return <span ref={r} className="cb-tc">0:00</span>
}
function Transport() {
  const playing = useStore((s) => s.playing)
  const versions = useStore((s) => s.versions)
  const idx = useStore((s) => s.vIdx)
  const ph = useRef<HTMLDivElement>(null)
  const cv = useRef<HTMLCanvasElement>(null)
  const vibeId = useStore((s) => s.vibeId)
  const phase = useStore((s) => s.phase)
  const peaks = useMemo(() => { const a = stemPeaks('drums', engine.pattern, 300), b = stemPeaks('bass', engine.pattern, 300); return Array.from(a, (x, i) => Math.min(1, x * 0.6 + b[i] * 0.5)) }, [vibeId])
  useEffect(() => {
    const c = cv.current!, ctx = c.getContext('2d')!, w = c.clientWidth, h = c.clientHeight, d = Math.min(devicePixelRatio, 2)
    c.width = w * d; c.height = h * d; ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, w, h)
    for (let b = 0; b <= 16; b++) { ctx.fillStyle = 'rgba(11,11,12,.35)'; ctx.fillRect(Math.round((b / 16) * (w - 1)), 0, 1, b % 4 === 0 ? 8 : 4) }
    if (phase !== 'ready') return
    peaks.forEach((p, i) => { const x = (i / peaks.length) * w, hh = Math.max(1, p * (h - 12)); ctx.fillStyle = 'rgba(11,11,12,.8)'; ctx.fillRect(x, 12 + (h - 12 - hh) / 2, Math.max(1, w / peaks.length - 1), hh) })
  }, [peaks, phase])
  useFrame((f) => { if (ph.current) ph.current.style.transform = `translateX(${f.pos * 100}%)` })
  const seek = useDrag((v) => engine.seek(v))
  return (
    <div className="cb-transport">
      <div className="cb-revs">
        <button onClick={actions.undo} disabled={idx <= 0}>Undo</button><button onClick={actions.redo} disabled={idx >= versions.length - 1}>Redo</button>
        <ol>{versions.map((v, i) => <li key={i}><button className={i === idx ? 'on' : ''} onClick={() => actions.jump(i)}><i>Rev. {i + 1}</i> {v.label}</button></li>)}</ol>
      </div>
      <div className="cb-tr-row">
        <button className="cb-play" onClick={actions.toggle} data-playing={playing} aria-label={playing ? 'Pause' : 'Play'}>
          {playing ? <svg viewBox="0 0 16 16"><path d="M3 2h3.5v12H3zM9.5 2H13v12H9.5z" /></svg> : <svg viewBox="0 0 16 16"><path d="M3 1.5v13L14 8z" /></svg>}
        </button>
        <Timecode /><span className="cb-dur">/ {fmtTime(engine.duration)}</span>
        <div className="cb-ov" {...seek}><canvas ref={cv} /><div className="cb-wph"><div ref={ph}><s /></div></div></div>
        <kbd>Space</kbd>
      </div>
    </div>
  )
}

function EasyCenter() {
  const hov = useStore((s) => s.hoverVibe)
  const vibeId = useStore((s) => s.vibeId)
  const v = vibeById(hov ?? vibeId)
  const phase = useStore((s) => s.phase)
  const energy = useStore((s) => s.macros.energy)
  const bpm = v ? v.bpm * (0.9 + (energy / 100) * 0.22) : 0
  return (
    <section className="cb-center">
      <div className="cb-head">
        <p className="cb-kicker">{phase === 'idle' && !v ? 'No. 0 · Unwritten' : `Idea 01 · ${phase === 'making' ? 'Writing' : 'Fair copy'}`}</p>
        <Title text={v ? v.name : 'Choose a vibe'} />
        <p className="cb-sub">
          {v ? <><em>{tempoWord(bpm)}</em><span>·</span><span className="cb-gl">{'\uE1D5'}</span> = {Math.round(bpm)}<span>·</span>{v.key} {v.minor ? 'minor' : 'major'}<span>·</span>4/4<span>·</span><i>{v.desc.replace(/\.$/, '')}</i></> : <i>Pick one from the catalogue, or write a brief and press Enter.</i>}
        </p>
        <Seismo />
      </div>
      <Score adv={false} />
      <Transport />
    </section>
  )
}

/* ---------------- advanced ---------------- */
function Dial({ id, k }: { id: StemId; k: PK }) {
  const val = useStore((s) => s.stems[id][k]) as number
  const f = frac(k, val)
  const drag = useDrag((v) => actions.setStem(id, { [k]: unfrac(k, v) }), { axis: 'y' })
  const a0 = -225, sweep = 270
  const ang = (a0 + f * sweep) * (Math.PI / 180)
  const R = 22, C = 30
  const pt = (a: number, r: number) => [C + r * Math.cos(a), C + r * Math.sin(a)]
  const arc = (from: number, to: number) => {
    const [x1, y1] = pt(from, R), [x2, y2] = pt(to, R)
    return `M${x1} ${y1} A${R} ${R} 0 ${Math.abs(to - from) > Math.PI ? 1 : 0} ${to > from ? 1 : 0} ${x2} ${y2}`
  }
  const rad = (d: number) => (d * Math.PI) / 180
  const zero = isBip(k) ? rad(a0 + 135) : rad(a0)
  const [px1, py1] = pt(ang, 9), [px2, py2] = pt(ang, R + 2)
  return (
    <div className="cb-dial">
      <div className="cb-dsvg" {...drag} role="slider" tabIndex={0} aria-label={`${id} ${k}`} aria-valuenow={val} onDoubleClick={() => actions.setStem(id, { [k]: 0 })}><svg viewBox="0 0 60 60">
        <path d={arc(rad(a0), rad(a0 + sweep))} className="d-bg" />
        {Math.abs(ang - zero) > 0.01 && <path d={arc(Math.min(zero, ang), Math.max(zero, ang))} className="d-fg" />}
        {Array.from({ length: 11 }, (_, i) => { const a = rad(a0 + (i / 10) * sweep); const [x1, y1] = pt(a, R + 4), [x2, y2] = pt(a, R + (i % 5 === 0 ? 8 : 6)); return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} className="d-t" /> })}
        <line x1={px1} y1={py1} x2={px2} y2={py2} className="d-p" />
      </svg></div>
      <b>{fmtParam(k, val)}</b><span>{PARAM_NAME[k]}</span>
    </div>
  )
}
function Rack() {
  const id = useStore((s) => s.selStem)
  const chainOn = useStore((s) => s.chainOn[id])
  const preset = useStore((s) => s.chainPreset[id])
  const macro = useStore((s) => s.macros[STEM_MACRO[id]])
  const stem = STEMS.find((s) => s.id === id)!
  return (
    <>
      <h2 className="cb-h"><span>Rack</span><i>{STEM_LABEL[id]}</i></h2>
      <div className="cb-rack-t"><h3>{stem.name}</h3><Dyn v={macro} /></div>
      <p className="cb-preset">Preset <i>{preset}</i></p>
      <div className="cb-dials">{PK_LIST.map((k) => <Dial key={k} id={id} k={k} />)}</div>
      <h2 className="cb-h"><span>Chain</span><i>click to bypass</i></h2>
      <ol className="cb-chain">{stem.chain.map((c, j) => <li key={c}><button className={chainOn[j] ? 'on' : ''} onClick={() => actions.toggleChain(id, j)}><i>{j + 1}</i><span>{c}</span><u /><em>{chainOn[j] ? 'On' : 'Bypassed'}</em></button></li>)}</ol>
      <h2 className="cb-h"><span>Stems</span></h2>
      <div className="cb-stemsel">{STEMS.map((s) => <button key={s.id} className={id === s.id ? 'on' : ''} onClick={() => actions.selStem(s.id)}>{s.name}</button>)}</div>
    </>
  )
}
function PresetPanel() {
  const { cat, q, favs, counts, items } = usePresets()
  const prev = useStore((s) => s.previewId)
  const selStem = useStore((s) => s.selStem)
  return (
    <div className="cb-presets">
      <label className="cb-search"><span>Search</span><input data-focus-target aria-label="Search presets" placeholder={`${counts.all} presets`} value={q} onChange={(e) => actions.presetQuery(e.target.value)} /></label>
      <div className="cb-cats">{(['all', 'genre', 'mix', 'vocal', 'fx', 'master'] as const).map((c) => <button key={c} className={cat === c ? 'on' : ''} onClick={() => actions.presetCat(c)}>{CAT_LABEL[c]}<sup>{counts[c]}</sup></button>)}</div>
      <div className="cb-plist">
        {items.map((p, i) => (
          <div key={p.id} className="cb-prow" data-prev={prev === p.id}>
            <button className={`cb-fav ${favs.includes(p.id) ? 'on' : ''}`} onClick={() => actions.toggleFav(p.id)} aria-label="Favourite">{favs.includes(p.id) ? '★' : '☆'}</button>
            <div><b>{p.name}</b><span>{p.cat} · {p.blurb}</span></div>
            <button className="cb-pv" onClick={() => actions.preview(p.id)}>{prev === p.id ? 'Stop' : 'Hear'}</button>
            <button className="cb-pa" onClick={() => actions.applyPreset(p)}>Apply</button>
            <i>{i + 1}</i>
          </div>
        ))}
      </div>
      <div className="cb-pfoot">Applies to <b>{STEMS.find((s) => s.id === selStem)!.name}</b></div>
    </div>
  )
}
function LeftAdv() {
  const tab = useStore((s) => s.advTab)
  const tabs: [string, string][] = [['generate', 'Generate'], ['separate', 'Separate'], ['master', 'Master'], ['presets', 'Presets'], ['ab', 'A / B']]
  return (
    <>
      <div className="cb-tabs" role="tablist">{tabs.map(([k, l]) => <button role="tab" key={k} className={tab === k ? 'on' : ''} onClick={() => actions.advTab(k as never)}>{l}</button>)}</div>
      <div className="cb-tabbody">
        {tab === 'presets' && <PresetPanel />}
        {tab === 'generate' && <GenerateForm />}
        {tab === 'separate' && <SeparateForm />}
        {tab === 'master' && <MasterForm />}
        {tab === 'ab' && <ABForm />}
      </div>
    </>
  )
}
function AdvCenter() {
  const vibeId = useStore((s) => s.vibeId)
  const v = vibeById(vibeId)
  const ab = useStore((s) => s.ab)
  return (
    <section className="cb-center adv">
      <div className="cb-head adv">
        <div><p className="cb-kicker">Full score · 4 stems</p><Title text={v?.name ?? 'Untitled'} small /></div>
        <div className="cb-adv-actions">
          <button className="cb-chip" onClick={() => void actions.tool('split')}>Split 4 stems</button>
          <button className="cb-chip" onClick={() => void actions.tool('remove_vocals')}>Vocals / inst</button>
          <button className="cb-chip solid" onClick={() => void actions.doExport()}>Export</button>
          <div className="cb-ab"><button className={ab === 'A' ? 'on' : ''} onClick={() => actions.setAB('A')}>A</button><button className={ab === 'B' ? 'on' : ''} onClick={() => actions.setAB('B')}>B</button></div>
        </div>
        <Seismo />
      </div>
      <Score adv />
      <div className="cb-lanes">
        <h4>Lanes <i>full length</i></h4>
        {STEMS.map((s) => <div key={s.id} className="cb-lane"><span>{s.name}</span><Wave id={s.id} h={30} /></div>)}
      </div>
      <Transport />
    </section>
  )
}

function Drawer() {
  const open = useStore((s) => s.enginesOpen)
  return (
    <>
      <div className="cb-scrim" data-open={open} onClick={() => actions.engines(false)} />
      <aside className="cb-drawer" data-open={open} aria-hidden={!open}>
        <div className="cb-dh"><h2>Engines</h2><span>On your 8 GB card</span><button onClick={() => actions.engines(false)}>Close · Esc</button></div>
        <div className="cb-dsum">{(['fits', 'tight', 'no'] as const).map((k) => <span key={k}><b>{ENGINES.filter((e) => e.status === k).length}</b>{k === 'no' ? 'Not recommended' : k === 'fits' ? 'Fit' : 'Tight'}</span>)}</div>
        <div className="cb-elist"><EngineRows /></div>
        <p className="cb-dn">RTX 20 series or older runs models in fp16. The Studio picks low-memory settings and hides models that will not fit.</p>
      </aside>
    </>
  )
}
function Help() {
  const open = useStore((s) => s.helpOpen)
  if (!open) return null
  return <div className="cb-help" onClick={() => actions.help(false)}><div onClick={(e) => e.stopPropagation()}><h2>Keyboard</h2><dl>{SHORTCUTS.map(([k, d]) => <div key={k}><dt>{k}</dt><dd>{d}</dd></div>)}</dl></div></div>
}
function Toasts() { const t = useStore((s) => s.toasts); return <div className="cb-toasts" aria-live="polite">{t.map((x) => <div key={x.id}>{x.text}</div>)}</div> }

export default function B() {
  const mode = useStore((s) => s.mode)
  useShortcuts()
  useEffect(() => { document.title = 'B · Opus Zero · The Muser'; document.body.style.background = '#EBE8E1' }, [])
  useEffect(() => {
    const dn = () => fx.hit(0.3); window.addEventListener('pointerdown', dn); void getState; return () => window.removeEventListener('pointerdown', dn)
  }, [])
  return (
    <div className="cb" data-mode={mode}>
      <i className="cb-crop tl" /><i className="cb-crop tr" /><i className="cb-crop bl" /><i className="cb-crop br" />
      <Top />
      <main className="cb-main">
        <aside className="cb-left">{mode === 'easy' ? <Catalogue /> : <LeftAdv />}</aside>
        {mode === 'easy' ? <EasyCenter /> : <AdvCenter />}
        <aside className="cb-right">{mode === 'easy' ? <RightEasy /> : <Rack />}</aside>
      </main>
      <Drawer /><Help /><Toasts />
    </div>
  )
}
