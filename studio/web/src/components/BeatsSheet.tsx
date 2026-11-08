import { useEffect, useRef, useState } from 'react'
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
  const fab = useRef<HTMLButtonElement>(null)
  // Keep the button off fixed or sticky controls a skin pins to the bottom (a composer bar, a transport).
  useEffect(() => {
    if (open) return
    const el = fab.current
    if (!el) return
    const INTERACTIVE = 'button,a,input,textarea,select,[role=button],[role=tab],[contenteditable=true]'
    const pinned = (n: Element | null) => {
      for (let x = n; x && x !== document.body; x = x.parentElement) {
        const pos = getComputedStyle(x).position
        if (pos === 'fixed' || pos === 'sticky') return x
      }
      return null
    }
    const place = () => {
      el.style.bottom = ''
      const r = el.getBoundingClientRect()
      if (!r.width) return
      let top = Infinity
      for (const fx of [0.1, 0.5, 0.9]) for (const fy of [0.15, 0.5, 0.85]) {
        const under = document.elementsFromPoint(r.left + r.width * fx, r.top + r.height * fy).find((n) => n !== el && !el.contains(n))
        const hit = under?.closest(INTERACTIVE)
        const bar = hit ? pinned(hit) : null
        if (bar) top = Math.min(top, bar.getBoundingClientRect().top)
      }
      if (top < Infinity) el.style.bottom = `${Math.max(0, window.innerHeight - top) + 8}px`
    }
    place()
    const t = window.setInterval(place, 1500)
    window.addEventListener('resize', place)
    return () => { window.clearInterval(t); window.removeEventListener('resize', place) }
  }, [open])
  if (!open) {
    return (
      <button ref={fab} className="beats-fab" data-testid="beats-open" onClick={() => { audio.unlock(); setOpen(true) }} aria-label="Open beat maker: pads, keys and sounds">
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
