import '@fontsource/geist-sans/300.css'
import '@fontsource/geist-sans/500.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-mono/400.css'
import { useEffect } from 'react'
import './landing.css'

const ITEMS = [
  { id: 'a', n: 'A', name: 'Spectral Terrain', line: 'A live WebGL landscape of your sound, with the whole studio drawn as a monochrome HUD over it.', tags: ['Black', 'Geist', 'WebGL2 terrain'] },
  { id: 'b', n: 'B', name: 'Engraved Score', line: 'Your track as a printed score on paper. Dynamics marks are the macros, vermilion is the playhead.', tags: ['Paper and ink', 'Instrument Serif', 'Bravura notation'] },
  { id: 'c', n: 'C', name: 'Cathode', line: 'A graphite rack with a phosphor oscilloscope as the hero and a shelf of cartridges for vibes and presets.', tags: ['Graphite and phosphor', 'Barlow Condensed', 'WebGL2 persistence'] },
]

export default function Landing() {
  useEffect(() => { document.title = 'The Muser concepts'; document.body.style.background = '#0B0B0C' }, [])
  return (
    <main className="land">
      <header><b>THE MUSER</b><span>Studio front end concepts</span></header>
      <h1>Three directions.<br />No orbs. No gold.</h1>
      <ul>
        {ITEMS.map((c) => (
          <li key={c.id}>
            <i>{c.n}</i>
            <div><h2>{c.name}</h2><p>{c.line}</p><small>{c.tags.join('  /  ')}</small></div>
            <nav><a href={`#/${c.id}/easy`}>Easy</a><a href={`#/${c.id}/advanced`}>Advanced</a></nav>
          </li>
        ))}
      </ul>
      <footer>Press ? inside any concept for shortcuts. Add ?s=made to the URL to open with a finished track.</footer>
    </main>
  )
}
