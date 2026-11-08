import type { CSSProperties, PointerEvent } from 'react'
import type { MacroKey } from '../../types'
import '@fontsource/instrument-serif/400.css'
import '@fontsource/instrument-serif/400-italic.css'
import '@fontsource/dm-mono/400.css'
import { useEasy } from '../../studio/EasyContext'
import { useStudio } from '../../studio/StudioContext'
import { MACRO_META } from '../../studio/vibe'
import { Overview } from '../shared/Overview'
import { AdvancedDesk, Brief, Finishing, Macro, StudioTop } from '../shared/NewSkinParts'
import { Lcd, Transport } from '../shared/TopParts'
import './horology.css'

export default function Horology() {
  const { mode, current } = useStudio()
  const easy = useEasy()
  const turnRing = (e: PointerEvent<SVGCircleElement>, key: MacroKey, i: number) => {
    const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect()
    const angle = Math.atan2(e.clientY - box.top - box.height / 2, e.clientX - box.left - box.width / 2) * 180 / Math.PI
    const travel = (angle - (-90 + i * 55) + 720) % 360
    easy.setMacro(key, Math.round(Math.min(100, travel / 259.2 * 100)))
  }
  const genre = easy.all.find((p) => p.id === easy.genreId) ?? easy.vibes.find((p) => p.id === easy.genreId)
  return <div className="ns horology" data-skin-root="horology" data-mode={mode}>
    <StudioTop brand="HOROLOGY" edition="THE MUSER · CALIBRE 005" />
    <main className="ns-scroll">
      {mode === 'easy' ? <>
        <div className="ho-heading"><p className="ns-kicker">Mechanical imagination / Automatic composition</p><h1>A movement<br /><em>of your own.</em></h1><span className="ho-edition">Nº {String(Math.max(1, easy.idx + 1)).padStart(3, '0')}<br />FIVE COMPLICATIONS</span></div>
        <div className="ho-movement">
          <div className="ho-dial" data-busy={!!easy.busy}>
            <svg className="ho-rings" viewBox="0 0 600 600" role="group" aria-label="Radial macro controls">
              <circle cx="300" cy="300" r="289" className="ho-case" />
              {Array.from({ length: 60 }, (_, i) => <line key={i} x1="300" y1={i % 5 ? 20 : 14} x2="300" y2={i % 5 ? 26 : 33} transform={`rotate(${i * 6} 300 300)`} className={i % 5 ? 'minor' : 'major'} />)}
              {MACRO_META.map((m, i) => <g key={m.key} transform={`rotate(${-90 + i * 55} 300 300)`}><circle cx="300" cy="300" r={249 - i * 23} className="ho-ring-bg" /><circle cx="300" cy="300" r={249 - i * 23} className="ho-arc" pathLength="100" strokeDasharray={`${easy.macros[m.key] * .72} 100`} /><circle cx="300" cy="300" r={249 - i * 23} className="ho-ring-hit" role="slider" tabIndex={0} aria-label={`${m.label} ring`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(easy.macros[m.key])} onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); turnRing(e, m.key, i) }} onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) turnRing(e, m.key, i) }} onPointerUp={(e) => { e.currentTarget.releasePointerCapture(e.pointerId); easy.commitMacros() }} onKeyDown={(e) => { const delta = ['ArrowUp', 'ArrowRight'].includes(e.key) ? 1 : ['ArrowDown', 'ArrowLeft'].includes(e.key) ? -1 : 0; if (!delta && e.key !== 'Home' && e.key !== 'End') return; e.preventDefault(); easy.setMacro(m.key, e.key === 'Home' ? 0 : e.key === 'End' ? 100 : Math.max(0, Math.min(100, easy.macros[m.key] + delta))) }} onKeyUp={(e) => { if (['ArrowUp', 'ArrowRight', 'ArrowDown', 'ArrowLeft', 'Home', 'End'].includes(e.key)) easy.commitMacros() }} /></g>)}
              <path className="ho-hand" d="M297 306 L300 92 L304 306Z" />
              <circle cx="300" cy="300" r="7" fill="#ba9650" />
            </svg>
            <span className="ho-roman ho-xii">XII</span><span className="ho-roman ho-vi">VI</span><span className="ho-roman ho-ix">IX</span><span className="ho-roman ho-iii">III</span>
            <div className="ho-center"><small>THE MUSER</small><h2>{genre?.name || 'Unwound'}</h2><Lcd /><span>{current?.bpm ? `${Math.round(current.bpm)} BPM` : 'AUTOMATIC'} · {current?.key || '4/4'}</span></div>
            <div className="ho-complications" data-testid="macros">{MACRO_META.map((m, i) => <div key={m.key} className={`ho-comp ho-comp-${i}`} style={{ '--comp': i } as CSSProperties}><Macro name={m.key} /></div>)}</div>
          </div>
          <div className="ho-crown"><span>WIND / PLAY</span><Transport lcd={false} /></div>
        </div>
        <section className="ho-selection"><div><p className="ns-kicker">01 / Select a calibre</p><div className="ho-calibres" data-testid="vibes">{easy.tiles.map((p, i) => <button key={p.id} aria-pressed={p.id === easy.genreId} onClick={() => easy.selectGenre(p)}><small>{String(i + 1).padStart(2, '0')}</small>{p.name}<span>↗</span></button>)}</div><button className="ho-all" onClick={() => easy.setShowAll((v) => !v)}>{easy.showAll ? 'Curated calibres' : 'All calibres'}</button></div><div><Brief verb="Wind the movement" number="02" /><div className="ho-proof"><Overview color="#244f78" /><span>{current?.title || 'Your musical mechanism awaits.'}</span></div><Finishing /></div></section>
      </> : <><div className="ho-advanced-seal" aria-hidden="true">◎<span>ATELIER / HOROLOGY</span></div><AdvancedDesk label="Atelier" /></>}
    </main>
  </div>
}
