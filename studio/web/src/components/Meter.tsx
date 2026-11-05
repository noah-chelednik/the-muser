import { useEffect, useRef } from 'react'
import { level } from '../audio/engine'

/** Vertical LED ladder meter driven by an AnalyserNode. */
export function Meter({ getAnalyser, segments = 14, horizontal }: { getAnalyser: () => AnalyserNode | undefined; segments?: number; horizontal?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let raf = 0
    let hold = 0
    const buf = new Float32Array(512)
    const tick = () => {
      const an = getAnalyser()
      const el = ref.current
      if (el) {
        const v = an ? level(an, buf as Float32Array<ArrayBuffer>) : 0
        const db = v > 0 ? 20 * Math.log10(v) : -60
        const n = Math.max(0, Math.min(segments, Math.round(((db + 48) / 48) * segments)))
        hold = Math.max(n, hold - 0.15)
        const kids = el.children
        for (let i = 0; i < kids.length; i++) {
          const on = i < n || i === Math.floor(hold) - 1
          kids[i].classList.toggle('on', on)
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [getAnalyser, segments])
  return (
    <div ref={ref} className={`meter ${horizontal ? 'meter-h' : ''}`}>
      {Array.from({ length: segments }, (_, i) => (
        <span key={i} className={i >= segments - 2 ? 'seg red' : i >= segments - 5 ? 'seg amber' : 'seg'} />
      ))}
    </div>
  )
}
