import { useEffect, useMemo, useRef } from 'react'
import { audio } from '../../audio/engine'
import { useStudio } from '../../studio/StudioContext'
import { useFrame } from '../../studio/viz'
import { useDrag } from './hooks'

/** Whole-track overview with playhead. Reads the real decoded buffers, draws in the skin's colours. */
export function Overview({ className = 'ov', bars = 240, color = 'var(--hot)' }: { className?: string; bars?: number; color?: string }) {
  const { channels, buffersVersion } = useStudio()
  const cv = useRef<HTMLCanvasElement>(null)
  const ph = useRef<HTMLDivElement>(null)
  const peaks = useMemo(() => {
    const out = new Float32Array(bars)
    for (const ch of channels) {
      const b = audio.buffer(ch.id)
      if (!b) continue
      const d = b.getChannelData(0)
      const step = Math.max(1, Math.floor(d.length / bars))
      for (let i = 0; i < bars; i++) {
        let m = 0
        for (let j = i * step; j < Math.min(d.length, (i + 1) * step); j += 16) m = Math.max(m, Math.abs(d[j]))
        out[i] += m
      }
    }
    let mx = 0.0001
    for (const v of out) mx = Math.max(mx, v)
    return out.map((v) => v / mx)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channels, buffersVersion, bars])

  useEffect(() => {
    const c = cv.current
    if (!c) return
    const draw = () => {
      const w = c.clientWidth
      const h = c.clientHeight
      const d = Math.min(devicePixelRatio || 1, 2)
      c.width = w * d
      c.height = h * d
      const x = c.getContext('2d')!
      x.setTransform(d, 0, 0, d, 0, 0)
      x.clearRect(0, 0, w, h)
      const css = getComputedStyle(c)
      x.fillStyle = css.getPropertyValue('--wave-grid') || 'rgba(255,255,255,.2)'
      for (let b = 0; b <= 16; b++) x.fillRect(Math.round((b / 16) * (w - 1)), h - (b % 4 === 0 ? 7 : 3), 1, b % 4 === 0 ? 7 : 3)
      x.fillStyle = color.startsWith('var(') ? css.getPropertyValue(color.slice(4, -1)).trim() || '#9BFF3D' : color
      const bw = Math.max(1, w / peaks.length - 1)
      peaks.forEach((p, i) => {
        const hh = Math.max(1, p * (h - 10))
        x.fillRect((i / peaks.length) * w, (h - 8 - hh) / 2 + 1, bw, hh)
      })
    }
    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(c)
    return () => ro.disconnect()
  }, [peaks, color])

  useFrame((f) => {
    if (ph.current) ph.current.style.transform = `translateX(${(audio.duration ? audio.currentTime() / audio.duration : 0) * 100}%)`
    void f
  })
  const seek = useDrag((v) => audio.seek(v * audio.duration))
  return (
    <div className={className} {...seek} role="slider" aria-label="Seek" tabIndex={0} data-testid="overview">
      <canvas ref={cv} />
      <div className="ov-ph"><div ref={ph} /></div>
    </div>
  )
}
