import { useEffect, useRef, useState } from 'react'
import { audio } from '../audio/engine'
import { tapAudioElement } from '../studio/viz'

/** Lightweight file player with a drawn waveform. Used by Easy mode and A/B compare. */
const peakCache = new Map<string, Float32Array>()

async function loadPeaks(url: string, n = 600): Promise<Float32Array> {
  const hit = peakCache.get(url)
  if (hit) return hit
  const buf = await audio.decodeBytes(await (await fetch(url)).arrayBuffer())
  const ch = buf.getChannelData(0)
  const per = Math.max(1, Math.floor(ch.length / n))
  const out = new Float32Array(n)
  let peak = 1e-6
  for (let i = 0; i < n; i++) {
    let m = 0
    for (let j = 0; j < per; j += 8) m = Math.max(m, Math.abs(ch[i * per + j] ?? 0))
    out[i] = m
    peak = Math.max(peak, m)
  }
  for (let i = 0; i < n; i++) out[i] /= peak
  peakCache.set(url, out)
  return out
}

const fmt = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`

export function Player({ url, title, sub, compact = false, audioRef }: {
  url: string
  title?: string
  sub?: string
  compact?: boolean
  audioRef?: (el: HTMLAudioElement | null) => void
}) {
  const el = useRef<HTMLAudioElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [peaks, setPeaks] = useState<Float32Array | null>(null)
  const [playing, setPlaying] = useState(false)
  const [t, setT] = useState(0)
  const [dur, setDur] = useState(0)

  useEffect(() => {
    let live = true
    setPeaks(null)
    loadPeaks(url).then((p) => live && setPeaks(p)).catch(() => undefined)
    return () => {
      live = false
    }
  }, [url])

  useEffect(() => {
    const c = canvas.current
    if (!c) return
    const dpr = window.devicePixelRatio || 1
    const w = c.clientWidth
    const h = c.clientHeight
    c.width = w * dpr
    c.height = h * dpr
    const g = c.getContext('2d')!
    g.scale(dpr, dpr)
    g.clearRect(0, 0, w, h)
    if (!peaks) return
    const n = peaks.length
    const bw = w / n
    const prog = dur ? t / dur : 0
    const cs = getComputedStyle(c)
    const accent = cs.getPropertyValue('--hot').trim() || '#fff'
    const rest = cs.getPropertyValue('--dim-wave').trim() || 'rgba(255,255,255,0.22)'
    for (let i = 0; i < n; i++) {
      const v = Math.max(0.04, peaks[i]) * (h / 2 - 2)
      g.fillStyle = i / n < prog ? accent : rest
      g.fillRect(i * bw, h / 2 - v, Math.max(1, bw - 0.6), v * 2)
    }
  }, [peaks, t, dur])

  const toggle = () => {
    const a = el.current
    if (!a) return
    if (a.paused) void a.play()
    else a.pause()
  }

  return (
    <div className={`player ${compact ? 'compact' : ''}`}>
      <audio
        ref={(a) => {
          ;(el as React.MutableRefObject<HTMLAudioElement | null>).current = a
          audioRef?.(a)
        }}
        src={url}
        preload="auto"
        onPlay={(e) => { setPlaying(true); tapAudioElement(e.currentTarget) }}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDur(e.currentTarget.duration)}
      />
      <button className={`play-btn ${playing ? 'on' : ''}`} onClick={toggle} aria-label={playing ? 'Pause preview' : 'Play preview'}>
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="player-body">
        {(title || sub) && (
          <div className="player-meta">
            {title && <strong>{title}</strong>}
            {sub && <span className="muted">{sub}</span>}
          </div>
        )}
        <canvas
          ref={canvas}
          className="player-wave"
          onClick={(e) => {
            const a = el.current
            if (!a || !dur) return
            const r = e.currentTarget.getBoundingClientRect()
            a.currentTime = ((e.clientX - r.left) / r.width) * dur
          }}
        />
      </div>
      <span className="player-time">{fmt(t)} / {fmt(dur)}</span>
    </div>
  )
}
