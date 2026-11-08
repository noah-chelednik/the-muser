import type { CSSProperties } from 'react'
import '@fontsource/dm-mono/400.css'
import { useEasy } from '../../studio/EasyContext'
import { useStudio } from '../../studio/StudioContext'
import { Overview } from '../shared/Overview'
import { AdvancedDesk, Brief, Finishing, Macros, StudioTop } from '../shared/NewSkinParts'
import { Transport } from '../shared/TopParts'
import './vend.css'

const COLORS = ['#ff5699', '#6de3ff', '#f6d753', '#b1fa76', '#ab9bff', '#ff874a']
export default function Vend() {
  const { mode, current } = useStudio()
  const easy = useEasy()
  return <div className="ns vend" data-skin-root="vend" data-mode={mode}>
    <StudioTop brand="VEND!" edition="SOUND REFRESHMENT · 24H" />
    <main className="ns-scroll">
      <div className="ve-machine">
        <div className="ve-marquee"><div><span lang="ja">音の自動販売機</span><h1>Fresh sounds.<br /><em>Zero small change.</em></h1></div><span className="ve-24">24<small>HOURS<br />OPEN</small></span><div className="ve-sticker">100%<br />YOUR VIBE</div></div>
        {mode === 'easy' ? <>
          <div className="ve-body"><section className="ve-glass" aria-label="Sound selections"><div className="ve-shelf-label"><span>CHOOSE YOUR FLAVOUR</span><button onClick={() => easy.setShowAll((v) => !v)}>{easy.showAll ? 'HOUSE SELECTION' : 'ALL FLAVOURS'} ↗</button></div>
            <div className="ve-products" data-testid="vibes">{easy.tiles.map((p, i) => <button key={p.id} className="ve-product" style={{ '--drink': COLORS[i % COLORS.length] } as CSSProperties} aria-pressed={easy.genreId === p.id} onClick={() => easy.selectGenre(p)}><span className="ve-window"><span className={`ve-can can-${i % 3}`}><small>THE MUSER</small><b>{p.name}</b><i aria-hidden="true">{['波', '音', '夢'][i % 3]}</i><span>{p.generate?.bpm || '∞'} / BPM</span></span></span><span className="ve-product-code">{String.fromCharCode(65 + Math.floor(i / 3))}{i % 3 + 1}<i>{easy.genreId === p.id ? 'SELECTED' : 'PUSH'}</i><s /></span></button>)}</div>
            <div className="ve-warning">✳ SERVE LOUD. ENJOY RESPONSIBLY. <span>NO COINS REQUIRED</span></div>
          </section><aside className="ve-payment"><div className="ve-status"><span>READY TO REFRESH</span><b role="status">{easy.busy ? 'BREWING…' : current ? 'ENJOY ♫' : 'SELECT A1 →'}</b><Transport /></div><Brief verb="DISPENSE A BEAT" /><div className="ve-coin" aria-hidden="true"><span />NO CASH · JUST CREATIVITY</div><Macros /><Finishing /></aside></div>
          <section className="ve-tray" data-ready={!!current} aria-label="Audio collection tray"><div className="ve-tray-label">PUSH TO COLLECT <span>↓ ↓ ↓</span></div><div className="ve-receipt" key={current?.id || 'empty'}><span>{current ? 'FRESHLY DISPENSED' : 'YOUR NEXT FAVOURITE IS IN HERE'}</span><h2>{current?.title || 'Good things drop here.'}</h2><Overview color="#97fcad" /><small>{current?.key || 'ORIGINAL SOUND'} · {current?.bpm ? `${Math.round(current.bpm)} BPM` : 'MADE TO ORDER'}</small></div></section>
        </> : <div className="ve-service"><div className="ve-service-label">SERVICE HATCH / AUTHORISED IMAGINATION ONLY</div><AdvancedDesk label="Machine service" /></div>}
        <div className="ve-base"><span>V / 006</span><span lang="ja">ありがとうございました</span><span>THE MUSER CO.</span></div>
      </div>
    </main>
  </div>
}
