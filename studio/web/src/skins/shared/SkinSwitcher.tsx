import { useEffect, useRef } from 'react'
import { SKINS, type SkinId } from '../registry'
import { useSkin } from '../SkinProvider'

/** Tiny inline previews: real colours and shapes of each skin, no images to load. */
export function Thumb({ id }: { id: SkinId }) {
  if (id === 'cathode')
    return (
      <svg viewBox="0 0 160 96" role="img" aria-label="Cathode preview">
        <rect width="160" height="96" fill="#0D0E0F" />
        <rect x="0" y="0" width="160" height="9" fill="#141517" />
        <rect x="6" y="3" width="22" height="3" fill="#9BFF3D" />
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <rect x={10 + i * 9} y="16" width="1" height="52" fill="#2A2C30" />
            <rect x={7 + i * 9} y={26 + ((i * 11) % 26)} width="7" height="3" fill="#EDEBE6" />
          </g>
        ))}
        <rect x="62" y="14" width="92" height="56" fill="#000" stroke="#2A2C30" />
        <path d="M64 46 Q74 20 84 46 T104 46 T124 46 T152 40" fill="none" stroke="#9BFF3D" strokeWidth="1.6" />
        <path d="M64 46 Q74 30 84 46 T104 46 T124 46 T152 40" fill="none" stroke="#9BFF3D" strokeWidth=".6" opacity=".5" />
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <rect key={i} x={6 + i * 25} y="76" width="21" height="14" fill="#1A1B1E" stroke={i === 2 ? '#9BFF3D' : '#2A2C30'} />
        ))}
      </svg>
    )
  if (id === 'terrain')
    return (
      <svg viewBox="0 0 160 96" role="img" aria-label="Terrain preview">
        <rect width="160" height="96" fill="#000" />
        {Array.from({ length: 11 }, (_, r) => {
          const y = 40 + r * 5
          let d = `M0 ${y}`
          for (let x = 0; x <= 160; x += 8) d += ` L${x} ${y - Math.max(0, Math.sin(x * 0.07 + r * 0.6) * Math.sin(x * 0.03 + 1) * (18 - r * 1.3))}`
          return <path key={r} d={d} fill="#000" stroke="#eef1f5" strokeOpacity={0.25 + r * 0.06} strokeWidth=".8" />
        })}
        <rect x="0" y="0" width="160" height="9" fill="none" stroke="#eef1f5" strokeOpacity=".14" />
        <rect x="6" y="3" width="22" height="2" fill="#eef1f5" />
        <rect x="70" y="86" width="20" height="1.5" fill="#2ff3ff" />
        <rect x="68" y="86" width="2" height="1.5" fill="#ff2e7a" />
      </svg>
    )
  return (
    <svg viewBox="0 0 160 96" role="img" aria-label="Score preview">
      <rect width="160" height="96" fill="#ECE9E2" />
      <rect x="0" y="0" width="160" height="9" fill="none" stroke="#0B0B0C" strokeWidth=".6" />
      <text x="6" y="7" fontFamily="Georgia, serif" fontStyle="italic" fontSize="7" fill="#0B0B0C">NoDAW Studio PRO</text>
      {[0, 1, 2, 3, 4].map((i) => (
        <line key={i} x1="8" x2="152" y1={30 + i * 5} y2={30 + i * 5} stroke="#0B0B0C" strokeWidth=".6" />
      ))}
      {[22, 40, 58, 80, 100, 124].map((x, i) => (
        <g key={x}>
          <ellipse cx={x} cy={50 - ((i * 7) % 20)} rx="3" ry="2.2" fill="#0B0B0C" transform={`rotate(-20 ${x} ${50 - ((i * 7) % 20)})`} />
          <line x1={x + 2.8} x2={x + 2.8} y1={50 - ((i * 7) % 20)} y2={34 - ((i * 7) % 20)} stroke="#0B0B0C" strokeWidth=".7" />
        </g>
      ))}
      <circle cx="80" cy="70" r="9" fill="none" stroke="#0B0B0C" strokeWidth=".8" />
      <line x1="80" y1="70" x2="86" y2="64" stroke="#D9361E" strokeWidth="1.4" />
      <text x="116" y="80" fontFamily="Georgia, serif" fontStyle="italic" fontWeight="700" fontSize="14" fill="#0B0B0C">mf</text>
    </svg>
  )
}

export const SkinIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden>
    <rect x="1.5" y="1.5" width="5.5" height="5.5" />
    <rect x="9" y="1.5" width="5.5" height="5.5" />
    <rect x="1.5" y="9" width="5.5" height="5.5" />
    <rect x="9" y="9" width="5.5" height="5.5" fill="currentColor" stroke="none" />
  </svg>
)

/** Top bar trigger. The popover is rendered by SkinPopover in Chrome so it sits above every skin. */
export function SkinButton() {
  const { skin, switcherOpen, setSwitcherOpen, preload } = useSkin()
  const def = SKINS.find((s) => s.id === skin)!
  return (
    <button
      className="sw-btn"
      data-testid="skin-button"
      aria-haspopup="dialog"
      aria-expanded={switcherOpen}
      onClick={() => {
        SKINS.forEach((s) => preload(s.id))
        setSwitcherOpen((v) => !v)
      }}
      title="Switch skin (Alt S cycles, Ctrl K opens the palette)"
    >
      <SkinIcon />
      <span>{def.name}</span>
    </button>
  )
}

/** Top bar entry for the NoDAW mode (v2) teaser. */
export function NoDawButton() {
  const { setNodawOpen } = useSkin()
  return (
    <button className="sw-btn nodaw-btn" data-testid="nodaw-button" onClick={() => setNodawOpen(true)} title="NoDAW mode: v2 coming soon">
      <span>NoDAW</span>
      <em>v2 soon</em>
    </button>
  )
}

export function SkinPopover() {
  const { skin, setSkin, switcherOpen, setSwitcherOpen } = useSkin()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!switcherOpen) return
    const off = (e: MouseEvent) => {
      const t = e.target as HTMLElement
      if (!ref.current?.contains(t) && !t.closest('[data-testid=skin-button]')) setSwitcherOpen(false)
    }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setSwitcherOpen(false)
    window.addEventListener('mousedown', off)
    window.addEventListener('keydown', esc)
    return () => {
      window.removeEventListener('mousedown', off)
      window.removeEventListener('keydown', esc)
    }
  }, [switcherOpen, setSwitcherOpen])
  if (!switcherOpen) return null
  return (
    <div className="sw-pop" ref={ref} role="dialog" aria-label="Choose a skin" data-testid="skin-popover">
      <h3>
        <span>Skins</span>
        <span>
          <kbd>Alt S</kbd>
          <kbd>Ctrl K</kbd>
        </span>
      </h3>
      <div className="sw-grid" role="radiogroup">
        {SKINS.map((s) => (
          <button key={s.id} role="radio" aria-checked={skin === s.id} className="sw-card" data-skin-option={s.id} onClick={() => { void setSkin(s.id); setSwitcherOpen(false) }}>
            <Thumb id={s.id} />
            <b>{s.name}</b>
            <i>{s.tag.toUpperCase()}</i>
            <span>{s.blurb}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
