import { useEffect, useRef } from 'react'
import { engine, type Frame } from './engine'

/** Run a per-frame callback with the live engine frame. */
export function useFrame(cb: (f: Frame, now: number, dt: number) => void, deps: unknown[] = []) {
  const ref = useRef(cb)
  ref.current = cb
  useEffect(() => {
    let raf = 0, last = performance.now()
    const loop = (now: number) => { const dt = (now - last) / 1000; last = now; ref.current(engine.frame(now), now, dt); raf = requestAnimationFrame(loop) }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

/** Drag a 0..1 value across an element's rect. */
export function useDrag(onChange: (v: number, e: PointerEvent) => void, opts: { axis?: 'x' | 'y'; onEnd?: () => void } = {}) {
  const el = useRef<HTMLElement | null>(null)
  const cbs = useRef({ onChange, ...opts })
  cbs.current = { onChange, ...opts }
  const down = (e: React.PointerEvent<HTMLElement>) => {
    const node = e.currentTarget
    el.current = node
    node.setPointerCapture(e.pointerId)
    const calc = (ev: PointerEvent) => {
      const r = node.getBoundingClientRect()
      const v = cbs.current.axis === 'y' ? 1 - (ev.clientY - r.top) / r.height : (ev.clientX - r.left) / r.width
      cbs.current.onChange(Math.max(0, Math.min(1, v)), ev)
    }
    calc(e.nativeEvent)
    const mv = (ev: PointerEvent) => calc(ev)
    const up = () => { node.removeEventListener('pointermove', mv); node.removeEventListener('pointerup', up); node.removeEventListener('pointercancel', up); cbs.current.onEnd?.() }
    node.addEventListener('pointermove', mv); node.addEventListener('pointerup', up); node.addEventListener('pointercancel', up)
  }
  return { onPointerDown: down }
}
