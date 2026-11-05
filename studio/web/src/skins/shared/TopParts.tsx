import { useEffect, useRef, useState } from 'react'
import { audio } from '../../audio/engine'
import { useStudio } from '../../studio/StudioContext'
import { fmtClock } from '../../studio/vibe'
import { useSkin } from '../SkinProvider'

const LED_KEYS: [string, string][] = [
  ['ollama', 'LLM'],
  ['gpu', 'GPU'],
  ['acestep', 'ACE'],
  ['demucs', 'STEMS'],
  ['ffmpeg', 'FX'],
]

export function Lcd({ className = 'lcd' }: { className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    let raf = 0
    const tick = () => {
      if (ref.current) ref.current.textContent = fmtClock(audio.currentTime())
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
  return <span ref={ref} className={className} data-testid="lcd">00:00.00</span>
}

export function Transport({ lcd = true }: { lcd?: boolean }) {
  const [, force] = useState(0)
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])
  return (
    <div className="transport" role="group" aria-label="Transport">
      <button className="tbtn" onClick={() => audio.stop()} title="Stop (return to start)" aria-label="Stop">■</button>
      <button className={`tbtn play ${audio.playing ? 'on' : ''}`} data-testid="play" onClick={() => (audio.playing ? audio.pause() : audio.play())} title="Play / pause (Space)" aria-label={audio.playing ? 'Pause' : 'Play'}>
        {audio.playing ? '❚❚' : '▶'}
      </button>
      <button className={`tbtn ${audio.loop ? 'on' : ''}`} onClick={() => audio.setLoop(!audio.loop)} title="Loop" aria-label="Loop" aria-pressed={audio.loop}>⟲</button>
      {lcd && <Lcd />}
    </div>
  )
}

export function HistoryControls() {
  const { history } = useStudio()
  const [open, setOpen] = useState(false)
  return (
    <div className="hist" data-testid="history">
      <button className="tbtn" disabled={!history.canUndo} onClick={history.undo} title={`Undo ${history.undoLabel} (Ctrl+Z)`} aria-label="Undo">↶</button>
      <button className="tbtn" disabled={!history.canRedo} onClick={history.redo} title={`Redo ${history.redoLabel} (Ctrl+Shift+Z)`} aria-label="Redo">↷</button>
      <button className="hist-count" onClick={() => setOpen((v) => !v)} title="Edit history" aria-expanded={open}>
        {history.depth} <small>edits</small>
      </button>
      {open && (
        <div className="hist-pop" onMouseLeave={() => setOpen(false)}>
          <div className="hist-pop-title">History</div>
          {history.entries.length === 0 && <div className="muted">No edits yet</div>}
          {[...history.entries].reverse().slice(0, 14).map((e, i) => (
            <div key={i} className={i === 0 ? 'cur' : ''}>{e}</div>
          ))}
          {history.redoLabel && <div className="muted">Redo: {history.redoLabel}</div>}
        </div>
      )}
    </div>
  )
}

export function SysLeds() {
  const { status, setShowSystem } = useStudio()
  const { setDrawerTab } = useSkin()
  return (
    <button className="leds" data-testid="sys-leds" onClick={() => { setDrawerTab('system'); setShowSystem(true) }} title="System status">
      {LED_KEYS.map(([k, label]) => {
        const it = status?.items[k]
        const cls = !status ? 'off' : it?.available ? 'ok' : k === 'ollama' || k === 'ffmpeg' ? 'bad' : 'warn'
        return (
          <span key={k} className={`sys-led ${cls}`}>
            <i />
            {label}
          </span>
        )
      })}
    </button>
  )
}

export function EnginesButton({ children = 'Engines' }: { children?: React.ReactNode }) {
  const { setShowSystem } = useStudio()
  const { setDrawerTab } = useSkin()
  return (
    <button className="eng-btn" data-testid="engines-button" onClick={() => { setDrawerTab('engines'); setShowSystem(true) }} title="Engines and 8 GB fit (Alt G)">
      {children}
    </button>
  )
}

export function ModeToggle({ labels = ['Easy', 'Advanced'] }: { labels?: [string, string] }) {
  const { mode, setMode } = useStudio()
  return (
    <div className="mode-toggle" role="tablist" aria-label="Studio mode" data-mode={mode}>
      <button role="tab" aria-selected={mode === 'easy'} className={mode === 'easy' ? 'on' : ''} data-testid="mode-easy" onClick={() => setMode('easy')}>{labels[0]}</button>
      <button role="tab" aria-selected={mode === 'advanced'} className={mode === 'advanced' ? 'on' : ''} data-testid="mode-advanced" onClick={() => setMode('advanced')}>{labels[1]}</button>
    </div>
  )
}

export function DemoBadge() {
  const { status, setShowSystem } = useStudio()
  const { setDrawerTab } = useSkin()
  if (status?.mode !== 'demo') return null
  return (
    <button className="demo-badge" data-testid="demo-badge" onClick={() => { setDrawerTab('system'); setShowSystem(true) }} title={status.browser_demo ? 'Browser demo: tracks come from a small in-browser synthesizer, not AI. Real AI needs the local install. Click for details.' : 'No LLM or audio models are connected, so tracks come from the built-in demo synthesizer. Click to see what is missing.'}>
      {status.browser_demo ? 'Browser demo' : 'Demo mode'}
    </button>
  )
}
