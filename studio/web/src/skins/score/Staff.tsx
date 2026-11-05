import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { audio } from '../../audio/engine'
import { useFrame } from '../../studio/viz'
import { midiName, type Clef, type Ev } from './notation'

function useSize(ref: React.RefObject<HTMLElement | null>) {
  const [s, setS] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => setS({ w: el.clientWidth, h: el.clientHeight }))
    ro.observe(el)
    setS({ w: el.clientWidth, h: el.clientHeight })
    return () => ro.disconnect()
  }, [ref])
  return s
}

const LET = 'CDEFGAB'
function dia(m: number) {
  const n = midiName(m)
  const oct = Number(n.slice(-1))
  return { d: oct * 7 + LET.indexOf(n[0]), acc: n[1] === '#' ? '\uE262' : n[1] === 'b' ? '\uE260' : '' }
}
const CLEF: Record<Clef, { g: string; name: string }> = {
  perc: { g: '\uE069', name: 'perc' },
  bass: { g: '\uE062', name: 'bass' },
  treble: { g: '\uE050', name: 'treble' },
}

function StaffSvg({ id, clef, ev, hidden }: { id: string; clef: Clef; ev: Ev[]; hidden?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const cid = id.replace(/[^a-z0-9]/gi, '_')
  const { w, h } = useSize(ref)
  const sp = Math.max(4.5, Math.min(8.5, h / 11.5, w / 90))
  const top = h / 2 - 2 * sp
  const bot = top + 4 * sp
  const x0 = 72
  const bw = (w - x0 - 32) / 4
  const c = CLEF[clef]
  const yOf = (d: number) => bot - ((d - (clef === 'bass' ? 18 : 30)) * sp) / 2
  const els = useMemo(() => {
    return ev.map((e, i) => {
      const x = x0 + (e.bar + e.s / 16) * bw + 12
      const key = `${e.bar}-${e.s}-${i}`
      if (clef === 'perc') {
        const pos = e.kind === 'k' ? 1 : e.kind === 'sn' ? 7 : 9
        const y = bot - (pos * sp) / 2
        const up = e.kind !== 'k'
        const stemX = up ? x + 1.15 * sp - 0.6 : x + 0.5
        return (
          <g key={key} className="b-n" data-b={e.bar} data-s={e.s} data-l={e.l}>
            {e.kind === 'h' || e.kind === 'oh' ? <text x={x} y={y} fontSize={sp * 4} className="b-gl">{'\uE0A9'}</text> : <text x={x} y={y} fontSize={sp * 4} className="b-gl">{'\uE0A4'}</text>}
            {e.kind === 'oh' && <text x={x + 0.1 * sp} y={y - sp * 1.2} fontSize={sp * 3} className="b-gl">{'\uE0B3'}</text>}
            <line x1={stemX} x2={stemX} y1={y} y2={up ? y - sp * 3.2 : y + sp * 3.2} className="b-stem" />
          </g>
        )
      }
      const ds = e.midis.map(dia).sort((a, b) => a.d - b.d)
      const mid = (ds[0].d + ds[ds.length - 1].d) / 2
      const refMid = clef === 'bass' ? 22 : 34
      const up = mid < refMid
      const lo = ds[0].d, hi = ds[ds.length - 1].d
      const stemX = up ? x + 1.18 * sp - 0.6 : x + 0.5
      const yLo = yOf(lo), yHi = yOf(hi)
      const ledgers: number[] = []
      const base = clef === 'bass' ? 18 : 30
      ds.forEach((n) => { for (let d = base - 2; d >= n.d; d -= 2) ledgers.push(d); for (let d = base + 10; d <= n.d; d += 2) ledgers.push(d) })
      const head = e.l >= 12 ? '\uE0A2' : e.l >= 4 ? '\uE0A3' : '\uE0A4'
      return (
        <g key={key} className="b-n" data-b={e.bar} data-s={e.s} data-l={e.l}>
          {[...new Set(ledgers)].map((d) => <line key={d} x1={x - sp * 0.45} x2={x + sp * 1.65} y1={yOf(d)} y2={yOf(d)} className="b-ledger" />)}
          {e.l < 16 && <line x1={stemX} x2={stemX} y1={up ? yLo : yHi} y2={up ? yHi - sp * 3.3 : yLo + sp * 3.3} className="b-stem" />}
          {e.l <= 2 && <path d={up ? `M${stemX} ${yHi - sp * 3.3} q ${sp * 1.2} ${sp * 0.9} ${sp * 0.7} ${sp * 2.3}` : `M${stemX} ${yLo + sp * 3.3} q ${sp * 1.2} ${-sp * 0.9} ${sp * 0.7} ${-sp * 2.3}`} className="b-flag" />}
          {ds.map((n, k) => {
            const y = yOf(n.d)
            const offs = k > 0 && n.d - ds[k - 1].d === 1 ? (up ? sp * 1.1 : -sp * 1.1) : 0
            return (
              <g key={k}>
                <text x={x + offs} y={y} fontSize={sp * 4} className="b-gl b-head">{head}</text>
                {n.acc && <text x={x - sp * 1.15 + offs} y={y} fontSize={sp * 4} className="b-gl b-acc">{n.acc}</text>}
              </g>
            )
          })}
        </g>
      )
    })
  }, [ev, w, h, clef])
  const reveal = hidden ?? 1
  return (
    <div ref={ref} className="cb-staff-svg">
      {w > 0 && (
        <svg width={w} height={h} role="img" aria-label={`${clef} staff`}>
          {[0, 1, 2, 3, 4].map((i) => <line key={i} x1={0} x2={w} y1={top + i * sp} y2={top + i * sp} className="b-line" />)}
          <text x={8} y={c.name === 'perc' ? top + 2 * sp : c.name === 'bass' ? top + sp : top + 3 * sp} fontSize={sp * 4} className="b-gl">{c.g}</text>
          <text x={8 + sp * 3.6} y={top + 2 * sp} fontSize={sp * 4} className="b-gl b-ts">{'\uE084'}</text>
          <text x={8 + sp * 3.6} y={top + 4 * sp} fontSize={sp * 4} className="b-gl b-ts">{'\uE084'}</text>
          {[0, 1, 2, 3, 4].map((i) => <line key={i} x1={x0 + i * bw} x2={x0 + i * bw} y1={top} y2={bot} className={i === 0 || i === 4 ? 'b-bar thick' : 'b-bar'} />)}
          <line x1={x0 + 4 * bw - 3} x2={x0 + 4 * bw - 3} y1={top} y2={bot} className="b-bar" />
          <clipPath id={`bcl-${cid}`}><rect x={0} y={0} width={Math.max(0, w * reveal)} height={h} /></clipPath>
          <g clipPath={`url(#bcl-${cid})`}>{els}</g>
        </svg>
      )}
    </div>
  )
}
export const Staff = memo(StaffSvg)

/** Which 4-bar window the playhead is in, and where inside it (0..1). Driven by the real transport. */
export function useScoreMotion(
  root: React.RefObject<HTMLElement | null>,
  ph: React.RefObject<HTMLElement | null>,
  bpm: number,
  win: number,
  setWin: (w: number) => void,
) {
  const last = useRef(-1)
  useFrame(() => {
    const step = audio.currentTime() / (60 / bpm / 4)
    const w = Math.max(0, Math.floor(step / 64))
    if (w !== win) setWin(w)
    const cyc = Math.max(0, Math.min(1, (step - win * 64) / 64))
    const gs = Math.floor(cyc * 64)
    const el = ph.current
    if (el) {
      const pw = el.parentElement!.clientWidth
      el.style.transform = `translateX(${84 + cyc * (pw - 104)}px)`
    }
    if (gs !== last.current && root.current) {
      last.current = gs
      const bar = Math.floor(gs / 16)
      const st = gs % 16
      root.current.querySelectorAll<SVGGElement>('.b-n').forEach((g) => {
        const b = +g.dataset.b!
        const s = +g.dataset.s!
        const l = +g.dataset.l!
        g.classList.toggle('on', b === bar && st >= s && st < s + Math.max(l, 1) && (l > 2 ? true : st === s))
      })
    }
  }, [bpm, win])
}
