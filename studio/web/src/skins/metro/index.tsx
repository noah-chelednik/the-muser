import { useRef, type CSSProperties } from 'react'
import { audio } from '../../audio/engine'
import { useEasy } from '../../studio/EasyContext'
import { useStudio } from '../../studio/StudioContext'
import { useFrame } from '../../studio/viz'
import { Overview } from '../shared/Overview'
import { AdvancedDesk, Brief, Finishing, Macros, StudioTop } from '../shared/NewSkinParts'
import { Transport } from '../shared/TopParts'
import './metro.css'

const LINES = ['#e52a2e', '#0075be', '#f6b900', '#008966']
function RunningLines() {
  const { channels } = useStudio()
  const train = useRef<HTMLDivElement>(null)
  useFrame(() => { if (train.current) train.current.style.left = `${audio.duration ? audio.currentTime() / audio.duration * 92 : 0}%` })
  return <section className="me-running" aria-label="Track lines"><div className="me-platform"><span>NOW RUNNING</span><Transport /></div>
    <div className="me-lines">{(channels.length ? channels.map((c) => c.name) : ['Rhythm', 'Bass', 'Harmony', 'Voice']).map((name, i) => <div key={`${name}-${i}`} className="me-line" style={{ '--line': LINES[i % 4] } as CSSProperties}><span>{String(i + 1).padStart(2, '0')}</span><b>{name}</b><i /><i /><i /><i /></div>)}<div ref={train} className="me-train" aria-hidden="true"><span>▶</span></div></div><Overview color="#181818" />
  </section>
}
export default function Metro() {
  const { mode, current } = useStudio()
  const easy = useEasy()
  return <div className="ns metro" data-skin-root="metro" data-mode={mode}>
    <StudioTop brand="Ⓜ METRO" edition="SOUND TRANSIT AUTHORITY" />
    <main className="ns-scroll">
      <div className="me-banner"><div><span>THE MUSER NETWORK / SERVICE 006</span><h1>{mode === 'easy' ? <>Next stop:<br /><em>your sound.</em></> : <>Network<br /><em>control.</em></>}</h1></div><div className="me-arrow" aria-hidden="true">↗</div><p>EVERY IDEA<br />IS A DEPARTURE.<br /><b>{current?.bpm ? `${Math.round(current.bpm)} BPM` : 'ALL SERVICES ON TIME'}</b></p></div>
      {mode === 'easy' ? <>
        <div className="me-journey"><section className="me-map" aria-label="Vibe stations"><div className="me-section-title"><span>01</span><h2>Choose your station</h2><button onClick={() => easy.setShowAll((v) => !v)}>{easy.showAll ? 'Local' : 'Full network'}</button></div>
          <div className="me-stations" data-testid="vibes">{easy.tiles.map((p, i) => <button key={p.id} className="me-station" style={{ '--line': LINES[Math.floor(i / 3) % 4] } as CSSProperties} aria-pressed={easy.genreId === p.id} onClick={() => easy.selectGenre(p)}><span className="me-stop" /><span><b>{p.name}</b><small>{p.generate?.bpm ? `${p.generate.bpm} BPM` : 'TRANSFER HERE'} / {String(i + 1).padStart(2, '0')}</small></span></button>)}</div>
          <div className="me-legend">● LOCAL SERVICE <span>◎ INTERCHANGE</span><span>→ ONE WAY TO SOMETHING NEW</span></div>
        </section><aside className="me-ticket"><div className="me-ticket-top"><span>BOARDING PASS</span><b>M / 01</b></div><Brief verb="DEPART" number="02" /><div className="me-ticket-tear" /><Macros /><Finishing /></aside></div>
        <RunningLines />
      </> : <><RunningLines /><AdvancedDesk label="Network operations" /></>}
    </main>
  </div>
}
