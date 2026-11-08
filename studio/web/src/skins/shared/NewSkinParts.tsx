import { useState } from 'react'
import { audio } from '../../audio/engine'
import { RackBody, RackTabs } from '../../components/pro/RackPanel'
import { ENDS, useEasy } from '../../studio/EasyContext'
import { useStudio } from '../../studio/StudioContext'
import { MACRO_META } from '../../studio/vibe'
import type { MacroKey } from '../../types'
import { useSkin } from '../SkinProvider'
import { ComposerPane, DeckPane, LibraryPane } from './Panes'
import { SkinButton, NoDawButton } from './SkinSwitcher'
import { DemoBadge, EnginesButton, HistoryControls, ModeToggle, SysLeds, Transport } from './TopParts'
import { StemActions, StemLanes } from './Stems'
import './new-skins.css'

export function StudioTop({ brand, edition }: { brand: string; edition: string }) {
  const { setHelpOpen } = useSkin()
  return <header className="ns-top studio-top">
    <div className="studio-top-scroll" tabIndex={0} aria-label="Studio toolbar; scroll for more controls">
      <a href="#/" onClick={(e) => e.preventDefault()} className="ns-brand">{brand}<small>{edition}</small></a>
      <ModeToggle /><DemoBadge /><NoDawButton /><SysLeds /><EnginesButton />
      <button onClick={() => setHelpOpen(true)} aria-label="Keyboard shortcuts">?</button>
    </div><div className="studio-top-pin"><SkinButton /></div>
  </header>
}

export function Brief({ verb = 'Make it', number = '01' }: { verb?: string; number?: string }) {
  const easy = useEasy()
  return <section className="ns-brief" aria-label="Create music">
    <label><small>{number} / YOUR DIRECTION</small><input data-testid="prompt" data-prompt data-focus-target value={easy.vibe} onChange={(e) => easy.setVibe(e.target.value)} placeholder="rainy night drive, warm and dusty" aria-label="Describe the vibe" maxLength={300} /></label>
    <button className="ns-make" data-testid="make" disabled={!!easy.busy} onPointerDown={() => audio.unlock()} onClick={() => void easy.make()}>{easy.busy || verb}<span aria-hidden>↗</span></button>
    <button className="ns-upload" onClick={() => { audio.unlock(); easy.pickUpload() }}>Use your own audio</button>
  </section>
}

export function Macro({ name }: { name: MacroKey }) {
  const easy = useEasy()
  const m = MACRO_META.find((m) => m.key === name)!
  return <label className="ns-macro" title={m.help}><span>{m.label}<b>{Math.round(easy.macros[name])}</b></span>
    <input type="range" min={0} max={100} value={easy.macros[name]} aria-label={m.label} onChange={(e) => easy.setMacro(name, +e.target.value)} onPointerUp={easy.commitMacros} onKeyUp={(e) => { if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) easy.commitMacros() }} />
    <small>{ENDS[name].join(' / ')}</small></label>
}
export function Macros() { return <div className="ns-macros" data-testid="macros">{MACRO_META.map((m) => <Macro key={m.key} name={m.key} />)}</div> }

export function Finishing() {
  const easy = useEasy()
  const lock = !easy.track || !!easy.busy
  return <section className="ns-finishing" aria-label="Finish and export">
    <div className="ns-revisions"><button disabled={easy.idx <= 0} onClick={() => easy.setIdx((i) => i - 1)}>↶ Version</button><span>{easy.idx + 1} / {easy.versions.length}</span><button disabled={easy.idx >= easy.versions.length - 1} onClick={() => easy.setIdx((i) => i + 1)}>Version ↷</button></div>
    <div className="ns-targets">{Object.entries(easy.targets).map(([k, v]) => <button key={k} disabled={lock} onClick={() => void easy.finish(k)} title={v.note}>{v.label}<small>{v.lufs} LUFS</small></button>)}</div>
    <button className="ns-export" data-testid="export" disabled={lock} onClick={() => void easy.doExport()}>Export audio ↓</button>
    {easy.files && <div className="ns-files">{Object.entries(easy.files).map(([k, url]) => <a key={k} href={url} download>{k} ↓</a>)}</div>}
    <p role="status">{easy.report ? `${easy.report.lufs.toFixed(1)} LUFS · ${easy.report.true_peak_db.toFixed(1)} dBTP` : easy.busy || 'Pick a destination to finish your sound.'}</p>
  </section>
}

/** Existing instrument, mixer, FX, library and composer logic; no second DAW implementation. */
export function AdvancedDesk({ label }: { label: string }) {
  const { current } = useStudio()
  const [dock, setDock] = useState('mix')
  return <section className="ns-advanced" aria-label={`${label} advanced studio`}>
    <div className="ns-adv-head"><div><small>{label} / CONTROL ROOM</small><h2>{current?.title || 'Your next movement'}</h2></div><Transport /><HistoryControls /><StemActions /></div>
    <nav className="ns-docks" aria-label="Studio workspaces">{['mix', 'deck', 'library', 'compose'].map((d) => <button key={d} aria-pressed={dock === d} onClick={() => setDock(d)}>{d === 'deck' ? 'Pads · Keys · Arranger' : d}</button>)}</nav>
    {dock === 'mix' ? <div className="ns-mix"><div className="ns-lanes"><StemLanes knobSize={40} /></div><aside className="ns-rack"><RackTabs /><RackBody /></aside></div> : <div className="ns-pane">{dock === 'deck' ? <DeckPane /> : dock === 'library' ? <LibraryPane /> : <ComposerPane />}</div>}
  </section>
}
