import { useEffect, useState } from 'react'
import { audio } from '../audio/engine'
import { useStudio } from '../studio/StudioContext'
import { Deck } from './Deck'

/**
 * Skin-independent entry to the beat deck (pads, keys, sounds, record). A floating button opens it
 * full screen, so it is one tap away on a phone in every skin and mode.
 */
export function BeatsSheet() {
  const { history } = useStudio()
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', k)
    document.body.classList.add('beats-open')
    return () => { window.removeEventListener('keydown', k); document.body.classList.remove('beats-open') }
  }, [open])
  if (!open) {
    return (
      <button className="beats-fab" data-testid="beats-open" onClick={() => { audio.unlock(); setOpen(true) }} aria-label="Open beat maker: pads, keys and sounds">
        <svg viewBox="0 0 18 18" aria-hidden><g fill="currentColor"><rect x="1" y="1" width="7" height="7" /><rect x="10" y="1" width="7" height="7" /><rect x="1" y="10" width="7" height="7" /><rect x="10" y="10" width="7" height="7" opacity=".55" /></g></svg>
        Beats
      </button>
    )
  }
  return (
    <div className="beats-sheet" role="dialog" aria-modal="true" aria-label="Beat maker" data-testid="beats-sheet">
      <div className="beats-sheet-head">
        <b>Beat maker</b>
        <button onClick={() => setOpen(false)} data-testid="beats-close">Close</button>
      </div>
      <div className="beats-sheet-body">
        <Deck history={history} />
      </div>
    </div>
  )
}
