import { memo, useMemo, useRef } from 'react'
import type { StemId } from '../shared/data'
import { engine } from '../shared/engine'
import { midiName, type Note } from '../shared/music'
import { useFrame } from '../shared/hooks'
import { useSize } from '../shared/ui'

const LET = 'CDEFGAB'
function dia(m: number) {
  const n = midiName(m)
  const oct = Number(n.slice(-1))
  return { d: oct * 7 + LET.indexOf(n[0]), acc: n[1] === '#' ? '\uE262' : n[1] === 'b' ? '\uE260' : '' }
}
export type Ev = { bar: number; s: number; l: number; midis: number[]; kind?: 'k' | 'sn' | 'h' | 'oh' }
export function eventsFor(id: StemId): Ev[] {
  const p = engine.pattern
  const out: Ev[] = []
  for (let bar = 0; bar < 4; bar++) {
    if (id === 'drums') {
      for (let s = 0; s < 16; s++) {
        if (p.kick[s]) out.push({ bar, s, l: 1, midis: [], kind: 'k' })
        if (p.snare[s]) out.push({ bar, s, l: 1, midis: [], kind: 'sn' })
        if (p.hat[s]) out.push({ bar, s, l: 1, midis: [], kind: 'h' })
        if (p.ohat[s]) out.push({ bar, s, l: 2, midis: [], kind: 'oh' })
      }
    } else if (id === 'bass') p.bass[bar].forEach((n: Note) => out.push({ bar, s: n.s, l: n.l, midis: [n.m] }))
    else if (id === 'voice') p.lead[bar].forEach((n: Note) => out.push({ bar, s: n.s, l: n.l, midis: [n.m] }))
    else { out.push({ bar, s: 0, l: 8, midis: p.chords[bar % 4] }); out.push({ bar, s: 8, l: 8, midis: p.chords[bar % 4] }) }
  }
  return out
}
const CLEF = { drums: { g: '\uE069', base: 2, dia: 0, name: 'perc' }, bass: { g: '\uE062', base: 1.5, dia: 18, name: 'bass' }, keys: { g: '\uE050', base: 3, dia: 30, name: 'treble' }, voice: { g: '\uE050', base: 3, dia: 30, name: 'treble' } } as const

function StaffSvg({ id, ev, hidden }: { id: StemId; ev: Ev[]; hidden?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const { w, h } = useSize(ref)
  const sp = Math.max(4.5, Math.min(8.5, h / 11.5, w / 90))
  const top = h / 2 - 2 * sp
  const bot = top + 4 * sp
  const x0 = 72
  const bw = (w - x0 - 32) / 4
  const c = CLEF[id]
  const yOf = (d: number) => bot - ((d - (id === 'bass' ? 18 : 30)) * sp) / 2
  const els = useMemo(() => {
    return ev.map((e, i) => {
      const x = x0 + (e.bar + e.s / 16) * bw + 12
      const key = `${e.bar}-${e.s}-${i}`
      if (id === 'drums') {
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
      const refMid = id === 'bass' ? 22 : 34
      const up = mid < refMid
      const lo = ds[0].d, hi = ds[ds.length - 1].d
      const stemX = up ? x + 1.18 * sp - 0.6 : x + 0.5
      const yLo = yOf(lo), yHi = yOf(hi)
      const ledgers: number[] = []
      const base = id === 'bass' ? 18 : 30
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ev, w, h])
  const reveal = hidden ?? 1
  return (
    <div ref={ref} className="cb-staff-svg">
      {w > 0 && (
        <svg width={w} height={h} role="img" aria-label={`${id} staff`}>
          {[0, 1, 2, 3, 4].map((i) => <line key={i} x1={0} x2={w} y1={top + i * sp} y2={top + i * sp} className="b-line" />)}
          <text x={8} y={c.name === 'perc' ? top + 2 * sp : c.name === 'bass' ? top + sp : top + 3 * sp} fontSize={sp * 4} className="b-gl">{c.g}</text>
          <text x={8 + sp * 3.6} y={top + 2 * sp} fontSize={sp * 4} className="b-gl b-ts">{'\uE084'}</text>
          <text x={8 + sp * 3.6} y={top + 4 * sp} fontSize={sp * 4} className="b-gl b-ts">{'\uE084'}</text>
          {[0, 1, 2, 3, 4].map((i) => <line key={i} x1={x0 + i * bw} x2={x0 + i * bw} y1={top} y2={bot} className={i === 0 || i === 4 ? 'b-bar thick' : 'b-bar'} />)}
          <line x1={x0 + 4 * bw - 3} x2={x0 + 4 * bw - 3} y1={top} y2={bot} className="b-bar" />
          <clipPath id={`bcl-${id}`}><rect x={0} y={0} width={Math.max(0, w * reveal)} height={h} /></clipPath>
          <g clipPath={`url(#bcl-${id})`}>{els}</g>
        </svg>
      )}
    </div>
  )
}
export const Staff = memo(StaffSvg)
export { CLEF }

/** Red-pencil playhead + active note highlighting across all staves inside a container. */
export function useScoreMotion(root: React.RefObject<HTMLElement | null>, ph: React.RefObject<HTMLElement | null>, geom: { left: number; right: number } = { left: 0, right: 0 }) {
  const last = useRef(-1)
  useFrame((f) => {
    const cyc = (f.beat % 16) / 16
    const gs = Math.floor(cyc * 64)
    const el = ph.current
    if (el) { const parent = el.parentElement!; const pw = parent.clientWidth; const svgW = pw - geom.left - geom.right; el.style.transform = `translateX(${geom.left + 84 + cyc * (svgW - 104)}px)` }
    if (gs !== last.current && root.current) {
      last.current = gs
      const bar = Math.floor(gs / 16), st = gs % 16
      root.current.querySelectorAll<SVGGElement>('.b-n').forEach((g) => {
        const b = +g.dataset.b!, s = +g.dataset.s!, l = +g.dataset.l!
        const on = b === bar && st >= s && st < s + Math.max(l, 1) && (l > 2 ? true : st === s)
        g.classList.toggle('on', on)
      })
    }
  })
}
