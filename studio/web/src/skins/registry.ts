import type { ComponentType } from 'react'

export type SkinId = 'cathode' | 'terrain' | 'score'
export interface SkinDef {
  id: SkinId
  name: string
  tag: string
  blurb: string
  load: () => Promise<{ default: ComponentType }>
}

/** Order matters: it is the order of the switcher and the T / Alt+S cycle. */
export const SKINS: SkinDef[] = [
  { id: 'cathode', name: 'Cathode', tag: 'Phosphor', blurb: 'Black glass, one lime phosphor, a live scope. Faders and cartridges.', load: () => import('./cathode') },
  { id: 'terrain', name: 'Terrain', tag: 'Spectral', blurb: 'Your sound as a landscape. Orbit it, steer it, read it.', load: () => import('./terrain') },
  { id: 'score', name: 'Score', tag: 'Engraved', blurb: 'Paper, ink and one red mark. Dynamics and dials, engraved.', load: () => import('./score') },
]
export const DEFAULT_SKIN: SkinId = 'cathode'
export const skinDef = (id: SkinId) => SKINS.find((s) => s.id === id) ?? SKINS[0]
export const isSkinId = (v: unknown): v is SkinId => SKINS.some((s) => s.id === v)

export function initialSkin(): SkinId {
  try {
    const v = localStorage.getItem('muser.skin')
    if (isSkinId(v)) return v
  } catch {
    /* storage blocked: fall back to default */
  }
  return DEFAULT_SKIN
}
