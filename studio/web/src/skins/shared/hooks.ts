import { useEffect, useRef } from 'react'

/** Drag a 0..1 value across an element's rect (axis x or y; y is bottom-up). */
export function useDrag(onChange: (v: number, e: PointerEvent) => void, opts: { axis?: 'x' | 'y'; onEnd?: () => void } = {}) {
  const cbs = useRef({ onChange, ...opts })
  cbs.current = { onChange, ...opts }
  const down = (e: React.PointerEvent<HTMLElement>) => {
    const node = e.currentTarget
    node.setPointerCapture(e.pointerId)
    const calc = (ev: PointerEvent) => {
      const r = node.getBoundingClientRect()
      const v = cbs.current.axis === 'y' ? 1 - (ev.clientY - r.top) / r.height : (ev.clientX - r.left) / r.width
      cbs.current.onChange(Math.max(0, Math.min(1, v)), ev)
    }
    calc(e.nativeEvent)
    const mv = (ev: PointerEvent) => calc(ev)
    const up = () => {
      node.removeEventListener('pointermove', mv)
      node.removeEventListener('pointerup', up)
      node.removeEventListener('pointercancel', up)
      cbs.current.onEnd?.()
    }
    node.addEventListener('pointermove', mv)
    node.addEventListener('pointerup', up)
    node.addEventListener('pointercancel', up)
  }
  return { onPointerDown: down }
}

/** Translate vertical wheel into horizontal scroll on a shelf. */
export function useWheelX<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const on = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        el.scrollLeft += e.deltaY
        e.preventDefault()
      }
    }
    el.addEventListener('wheel', on, { passive: false })
    return () => el.removeEventListener('wheel', on)
  }, [])
  return ref
}

/** Keep the selected child centred in a scroller without scrolling the page. */
export function centerChild(scroller: HTMLElement | null, child: HTMLElement | null) {
  if (!scroller || !child) return
  scroller.scrollTo({ left: child.offsetLeft - scroller.clientWidth / 2 + child.clientWidth / 2, behavior: 'smooth' })
}
