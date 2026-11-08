import { useEffect, useRef } from 'react'
import { SKINS, type SkinId } from '../registry'
import { useSkin } from '../SkinProvider'

/** Tiny inline previews: real colours and shapes of each skin, no images to load. */
export function Thumb({ id }: { id: SkinId }) {
  switch (id) {
  case 'cathode':
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
  case 'terrain':
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
  case 'score': return (
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
  case 'horology': return <svg viewBox="0 0 160 96" role="img" aria-label="Horology preview"><rect width="160" height="96" fill="#f5f1e7" /><circle cx="80" cy="48" r="41" fill="#fffaf0" stroke="#b99a5b" strokeWidth="3" />{[34, 28, 22].map((r) => <circle key={r} cx="80" cy="48" r={r} fill="none" stroke="#b99a5b" strokeWidth=".7" />)}<path d="M80 48 L82 16 L78 48 L101 61" stroke="#244f78" fill="#244f78" /><circle cx="80" cy="48" r="3" fill="#b99a5b" /><rect x="66" y="61" width="28" height="9" fill="#e9e5d4" /><text x="70" y="68" fontSize="6" fill="#244f78">00:00</text><rect x="122" y="44" width="9" height="12" rx="3" fill="#b99a5b" /></svg>
  case 'metro': return <svg viewBox="0 0 160 96" role="img" aria-label="Metro preview"><rect width="160" height="96" fill="#fafaf5" /><rect width="160" height="14" fill="#141414" /><text x="7" y="10" fontFamily="Arial" fontWeight="900" fontSize="9" fill="#fff">METRO ↗</text><path d="M10 32 H118 Q134 32 134 48 V82" stroke="#e52a2e" strokeWidth="6" fill="none" /><path d="M10 58 H94 L119 82 H150" stroke="#0075be" strokeWidth="6" fill="none" /><path d="M36 22 V83" stroke="#f6b900" strokeWidth="6" />{[20, 60, 100].map((x) => <g key={x}><circle cx={x} cy="32" r="4" fill="#fff" stroke="#e52a2e" strokeWidth="2" /><circle cx={x} cy="58" r="4" fill="#fff" stroke="#0075be" strokeWidth="2" /></g>)}<circle cx="36" cy="58" r="6" fill="#fff" stroke="#141414" strokeWidth="2" /></svg>
  case 'vend': return <svg viewBox="0 0 160 96" role="img" aria-label="Vend preview"><rect width="160" height="96" fill="#bdc5d1" /><rect x="17" y="3" width="126" height="90" rx="6" fill="#d9dfe8" stroke="#808c9f" /><rect x="23" y="8" width="114" height="15" rx="3" fill="#fbf4e5" /><text x="28" y="19" fontFamily="Arial" fontStyle="italic" fontWeight="900" fontSize="12" fill="#e91e60">VEND!</text><rect x="23" y="28" width="78" height="47" fill="#141a24" />{['#ff5699','#6de3ff','#f6d753','#b1fa76','#ab9bff','#ff874a'].map((c, i) => <rect key={c} x={28 + (i % 3) * 24} y={32 + Math.floor(i / 3) * 22} width="15" height="17" rx="3" fill={c} />)}<rect x="107" y="28" width="28" height="18" fill="#111c24" /><text x="109" y="39" fill="#97fcad" fontSize="6">READY</text><rect x="107" y="53" width="28" height="10" rx="3" fill="#e91e60" /><rect x="27" y="80" width="105" height="9" rx="3" fill="#111c24" /></svg>
  }
  const unreachable: never = id
  throw new Error(`Unknown skin preview: ${unreachable}`)
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
    const previous = document.activeElement as HTMLElement | null
    ref.current?.querySelector<HTMLElement>('button')?.focus()
    const esc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSwitcherOpen(false)
      if (e.key !== 'Tab') return
      const items = ref.current?.querySelectorAll<HTMLElement>('button')
      if (!items?.length) return
      const first = items[0], last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('mousedown', off)
    window.addEventListener('keydown', esc)
    return () => {
      window.removeEventListener('mousedown', off)
      window.removeEventListener('keydown', esc)
      if (previous?.isConnected) previous.focus()
    }
  }, [switcherOpen, setSwitcherOpen])
  if (!switcherOpen) return null
  return (
    <div className="sw-backdrop" onClick={(e) => { if (e.target === e.currentTarget) setSwitcherOpen(false) }}><div className="sw-pop" ref={ref} role="dialog" aria-modal="true" aria-label="Choose a skin" data-testid="skin-popover">
      <h3>
        <span>Skins</span>
        <span>
          <button className="sw-close" onClick={() => setSwitcherOpen(false)} aria-label="Close skin picker">✕</button>
          <kbd>Alt S</kbd>
          <kbd>Ctrl K</kbd>
        </span>
      </h3>
      <div className="sw-grid" role="radiogroup">
        {SKINS.map((s) => (
          <button key={s.id} role="radio" aria-checked={skin === s.id} className="sw-card" data-skin-option={s.id} onClick={() => { void setSkin(s.id).then(() => document.querySelector<HTMLButtonElement>('[data-testid=skin-button]')?.focus()); setSwitcherOpen(false) }}>
            <Thumb id={s.id} />
            <b>{s.name}</b>
            <i>{s.tag.toUpperCase()}</i>
            <span>{s.blurb}</span>
          </button>
        ))}
      </div>
    </div></div>
  )
}
