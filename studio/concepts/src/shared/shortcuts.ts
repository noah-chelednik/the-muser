import { useEffect } from 'react'
import { actions, getState } from './store'
import { MACROS } from './data'

export function useShortcuts(extra?: (e: KeyboardEvent) => boolean | void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')
      if (e.key === 'Escape') { actions.help(false); actions.engines(false); (t as HTMLElement)?.blur?.(); return }
      if (typing) { if (e.key === 'Enter' && t.getAttribute('data-prompt') !== null) { e.preventDefault(); void actions.make() } return }
      if (e.metaKey || e.ctrlKey) {
        if (e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? actions.redo() : actions.undo() }
        return
      }
      if (extra && extra(e) === true) return
      const s = getState()
      const k = e.key
      if (k === ' ') { e.preventDefault(); actions.toggle() }
      else if (k === 'Enter') { e.preventDefault(); void actions.make() }
      else if (k === '[') actions.stepVibe(-1)
      else if (k === ']') actions.stepVibe(1)
      else if (/^[1-5]$/.test(k)) actions.selMacro(MACROS[Number(k) - 1].key)
      else if (k === 'ArrowLeft' || k === 'ArrowDown') { e.preventDefault(); actions.nudge(e.shiftKey ? -10 : -1) }
      else if (k === 'ArrowRight' || k === 'ArrowUp') { e.preventDefault(); actions.nudge(e.shiftKey ? 10 : 1) }
      else if (k.toLowerCase() === 'f') actions.cycleFinish()
      else if (k.toLowerCase() === 'x') void actions.doExport()
      else if (k.toLowerCase() === 'e') actions.toggleMode()
      else if (k.toLowerCase() === 'z') e.shiftKey ? actions.redo() : actions.undo()
      else if (k.toLowerCase() === 'g') actions.engines(!s.enginesOpen)
      else if (k === '?') actions.help(!s.helpOpen)
      else if (k === '/') { e.preventDefault(); (document.querySelector('[data-focus-target]') as HTMLElement | null)?.focus() }
    }
    window.addEventListener('keydown', onKey)
    const onUp = () => actions.commitMacros()
    const keyup = (e: KeyboardEvent) => { if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key) && !(e.target as HTMLElement)?.tagName?.match(/INPUT|SELECT/)) onUp() }
    window.addEventListener('keyup', keyup)
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('keyup', keyup) }
  }, [extra])
}
