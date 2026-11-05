import { useCallback, useEffect, useRef, useState } from 'react'
import { audio, type Region } from '../../audio/engine'
import { snapTime } from '../../audio/sampler'

export type Grid = { bpm: number; offset: number; division: number; snap: boolean; show: boolean }

type Props = {
  buffer?: AudioBuffer
  region: Region | null
  onRegion: (r: Region | null) => void
  markers?: number[]
  grid?: Grid
  color?: string
  height?: number
  onSeek?: (t: number) => void
}

const peakCache = new WeakMap<AudioBuffer, Float32Array>()
/** Per-pixel-bucket min/max at a fixed fine resolution, reused across zoom levels. */
function fine(buf: AudioBuffer, n = 6000): Float32Array {
  const hit = peakCache.get(buf)
  if (hit) return hit
  const out = new Float32Array(n * 2)
  const per = Math.max(1, Math.floor(buf.length / n))
  const chans = Array.from({ length: buf.numberOfChannels }, (_, i) => buf.getChannelData(i))
  let peak = 1e-4
  for (let i = 0; i < n; i++) {
    let mn = 0, mx = 0
    const s0 = i * per
    for (let j = 0; j < per; j += 2) for (const ch of chans) { const v = ch[s0 + j] ?? 0; if (v < mn) mn = v; if (v > mx) mx = v }
    out[i * 2] = mn; out[i * 2 + 1] = mx
    peak = Math.max(peak, -mn, mx)
  }
  for (let i = 0; i < out.length; i++) out[i] /= peak
  peakCache.set(buf, out)
  return out
}

/**
 * Waveform with a draggable region (two 32px touch handles, drag the body to move it, drag on empty
 * space to draw a new one), zoom, beat grid with snapping, slice markers and a live playhead.
 */
export function RegionWave({ buffer, region, onRegion, markers = [], grid, color, height = 150, onSeek }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [zoom, setZoom] = useState(1)
  const [wpx, setWpx] = useState(300)
  const dur = buffer?.duration ?? 0
  const drag = useRef<{ mode: 'new' | 'l' | 'r' | 'move'; anchor: number; r0: Region | null; moved: boolean } | null>(null)
  const latest = useRef({ region, onRegion, grid, dur, wpx })
  latest.current = { region, onRegion, grid, dur, wpx }

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(() => setWpx(Math.max(160, el.clientWidth * zoom)))
    ro.observe(el)
    setWpx(Math.max(160, el.clientWidth * zoom))
    return () => ro.disconnect()
  }, [zoom])

  const toT = useCallback((clientX: number) => {
    const cv = canvas.current!
    const r = cv.getBoundingClientRect()
    return Math.min(latest.current.dur, Math.max(0, ((clientX - r.left) / r.width) * latest.current.dur))
  }, [])
  const snap = (t: number) => {
    const g = latest.current.grid
    return g && g.snap ? Math.min(latest.current.dur, Math.max(0, snapTime(t, g.bpm, g.offset, g.division))) : t
  }

  useEffect(() => {
    let raf = 0
    const cs = canvas.current ? getComputedStyle(canvas.current) : null
    const v = (n: string, d: string) => cs?.getPropertyValue(n).trim() || d
    const rest = v('--wave-rest', 'rgba(255,255,255,.3)'), gridC = v('--wave-grid', 'rgba(255,255,255,.08)')
    const head = v('--wave-head', '#fff'), tint = color || v('--stem', '#fff'), hot = v('--hot', '#9bff3d'), ln2 = v('--ln2', '#555')
    const draw = () => {
      const cv = canvas.current
      if (!cv) return
      const dpr = window.devicePixelRatio || 1
      const w = cv.clientWidth, h = cv.clientHeight
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr) }
      const g = cv.getContext('2d')!
      g.setTransform(dpr, 0, 0, dpr, 0, 0)
      g.clearRect(0, 0, w, h)
      if (!buffer || !dur) { raf = requestAnimationFrame(draw); return }
      const { region: rg, grid: gr } = latest.current
      const X = (t: number) => (t / dur) * w
      // grid
      if (gr?.show && gr.bpm > 0) {
        const step = 60 / gr.bpm / gr.division
        const pxStep = X(step)
        if (pxStep > 5) {
          for (let t = gr.offset; t < dur; t += step) {
            const beat = Math.round(((t - gr.offset) / (60 / gr.bpm)) * gr.division) % gr.division === 0
            g.strokeStyle = gridC
            g.globalAlpha = beat ? 1.6 : 0.8
            g.beginPath(); g.moveTo(Math.round(X(t)) + 0.5, 0); g.lineTo(Math.round(X(t)) + 0.5, h); g.stroke()
          }
          g.globalAlpha = 1
        }
      }
      const pk = fine(buffer)
      const n = pk.length / 2
      const mid = h / 2
      for (let x = 0; x < w; x++) {
        const i0 = Math.floor((x / w) * n), i1 = Math.max(i0 + 1, Math.floor(((x + 1) / w) * n))
        let mn = 0, mx = 0
        for (let i = i0; i < i1 && i < n; i++) { mn = Math.min(mn, pk[i * 2]); mx = Math.max(mx, pk[i * 2 + 1]) }
        const t = (x / w) * dur
        const inR = rg && t >= rg.start && t <= rg.end
        g.fillStyle = inR ? tint : rest
        g.fillRect(x, mid - mx * mid * 0.92, 1, Math.max(1, (mx - mn) * mid * 0.92))
      }
      if (rg) {
        g.fillStyle = hot; g.globalAlpha = 0.12
        g.fillRect(X(rg.start), 0, X(rg.end) - X(rg.start), h)
        g.globalAlpha = 1
      }
      g.strokeStyle = ln2; g.lineWidth = 1
      g.beginPath(); g.moveTo(0, mid + 0.5); g.lineTo(w, mid + 0.5); g.stroke()
      // slice markers
      g.strokeStyle = hot; g.fillStyle = hot; g.setLineDash([3, 3])
      markers.forEach((t, i) => {
        const x = Math.round(X(t)) + 0.5
        g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke()
        g.font = '9px monospace'; g.fillText(String(i + 1), x + 3, 10)
      })
      g.setLineDash([])
      // playhead
      if (audio.duration) {
        const px = X(audio.currentTime())
        g.fillStyle = head
        g.fillRect(px - 0.5, 0, 1.5, h)
      }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [buffer, color, markers, dur])

  const down = (e: React.PointerEvent, mode: 'new' | 'l' | 'r' | 'move') => {
    if (!dur) return
    e.stopPropagation()
    if (mode !== 'new') e.preventDefault()
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    const t = toT(e.clientX)
    drag.current = { mode, anchor: mode === 'new' ? snap(t) : t, r0: region, moved: false }
  }
  const move = (e: React.PointerEvent) => {
    const d = drag.current
    if (!d) return
    const t = toT(e.clientX)
    const minLen = Math.min(0.02, dur / 10)
    if (d.mode === 'new') {
      if (Math.abs(e.clientX - (e.currentTarget as HTMLElement).getBoundingClientRect().left) < 0) return
      const s = snap(t)
      if (Math.abs(s - d.anchor) * (latest.current.wpx / dur) < 4 && !d.moved) return
      d.moved = true
      onRegion({ start: Math.min(d.anchor, s), end: Math.max(d.anchor, s) })
    } else if (d.r0) {
      d.moved = true
      if (d.mode === 'l') onRegion({ start: Math.min(snap(t), d.r0.end - minLen), end: d.r0.end })
      else if (d.mode === 'r') onRegion({ start: d.r0.start, end: Math.max(snap(t), d.r0.start + minLen) })
      else {
        const len = d.r0.end - d.r0.start
        const s = Math.min(dur - len, Math.max(0, snap(d.r0.start + (t - d.anchor))))
        onRegion({ start: s, end: s + len })
      }
    }
  }
  const up = (e: React.PointerEvent) => {
    const d = drag.current
    drag.current = null
    if (d && d.mode === 'new' && !d.moved) {
      // a plain tap seeks (and clears nothing)
      onSeek?.(toT(e.clientX))
    }
  }

  const pct = (t: number) => `${(t / (dur || 1)) * 100}%`
  return (
    <div className="rw">
      <div className="rw-scroll" ref={wrap}>
        <div className="rw-stage" style={{ width: wpx, height }} data-testid="region-wave">
          <canvas ref={canvas} className="rw-canvas" style={{ height }} onPointerDown={(e) => down(e, 'new')} onPointerMove={move} onPointerUp={up} onPointerCancel={up} />
          {region && dur > 0 && (
            <>
              <div className="rw-body" style={{ left: pct(region.start), width: `calc(${pct(region.end - region.start)})` }} onPointerDown={(e) => down(e, 'move')} onPointerMove={move} onPointerUp={up} />
              <div className="rw-handle l" data-testid="handle-l" style={{ left: pct(region.start) }} onPointerDown={(e) => down(e, 'l')} onPointerMove={move} onPointerUp={up} onPointerCancel={up}><i /></div>
              <div className="rw-handle r" data-testid="handle-r" style={{ left: pct(region.end) }} onPointerDown={(e) => down(e, 'r')} onPointerMove={move} onPointerUp={up} onPointerCancel={up}><i /></div>
            </>
          )}
        </div>
      </div>
      <div className="rw-tools">
        <button className="chip-btn" onClick={() => setZoom((z) => Math.max(1, z / 2))} disabled={zoom <= 1} aria-label="Zoom out">-</button>
        <span className="muted">{zoom}x</span>
        <button className="chip-btn" onClick={() => setZoom((z) => Math.min(32, z * 2))} aria-label="Zoom in">+</button>
        <span className="muted rw-read">
          {region ? `${region.start.toFixed(2)}s to ${region.end.toFixed(2)}s (${(region.end - region.start).toFixed(2)}s)` : 'Drag on the waveform to select a region'}
        </span>
        {region && <button className="chip-btn" onClick={() => onRegion(null)}>Clear</button>}
      </div>
    </div>
  )
}
