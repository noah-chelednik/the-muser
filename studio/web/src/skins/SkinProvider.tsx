import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import type { MacroKey } from '../types'
import { prefersReducedMotion } from '../studio/viz'
import { SKINS, initialSkin, skinDef, type SkinId } from './registry'

export type DrawerTab = 'engines' | 'system'
export interface SkinCtx {
  skin: SkinId
  /** Preloads the skin chunk, then swaps with a view transition when allowed. State above the host is untouched. */
  setSkin: (id: SkinId) => Promise<void>
  cycleSkin: (dir?: 1 | -1) => void
  preload: (id: SkinId) => void
  switcherOpen: boolean
  setSwitcherOpen: (v: boolean | ((x: boolean) => boolean)) => void
  paletteOpen: boolean
  setPaletteOpen: (v: boolean | ((x: boolean) => boolean)) => void
  nodawOpen: boolean
  setNodawOpen: (v: boolean | ((x: boolean) => boolean)) => void
  helpOpen: boolean
  setHelpOpen: (v: boolean | ((x: boolean) => boolean)) => void
  drawerTab: DrawerTab
  setDrawerTab: (t: DrawerTab) => void
  selMacro: MacroKey
  setSelMacro: (k: MacroKey) => void
}

const Ctx = createContext<SkinCtx | null>(null)
export const useSkin = () => {
  const c = useContext(Ctx)
  if (!c) throw new Error('SkinProvider missing')
  return c
}

export function applySkinAttr(id: SkinId) {
  document.documentElement.dataset.skin = id
  const m = document.querySelector('meta[name=theme-color]')
  if (m) m.setAttribute('content', id === 'score' ? '#ECE9E2' : id === 'terrain' ? '#000000' : '#0D0E0F')
}

export function SkinProvider({ children }: { children: ReactNode }) {
  const [skin, setSkinState] = useState<SkinId>(initialSkin)
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [nodawOpen, setNodawOpen] = useState(false)
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('engines')
  const [selMacro, setSelMacro] = useState<MacroKey>('energy')
  const cur = useRef(skin)
  cur.current = skin

  useEffect(() => applySkinAttr(skin), [skin])

  const preload = useCallback((id: SkinId) => void skinDef(id).load().catch(() => undefined), [])

  const setSkin = useCallback(async (id: SkinId) => {
    if (id === cur.current) return
    try {
      await skinDef(id).load()
    } catch {
      return
    }
    const swap = () => {
      flushSync(() => setSkinState(id))
      applySkinAttr(id)
    }
    try {
      localStorage.setItem('muser.skin', id)
    } catch {
      /* ignore */
    }
    const d = document as Document & { startViewTransition?: (cb: () => void) => unknown }
    if (d.startViewTransition && !prefersReducedMotion()) d.startViewTransition(swap)
    else swap()
  }, [])

  const cycleSkin = useCallback(
    (dir: 1 | -1 = 1) => {
      const i = SKINS.findIndex((s) => s.id === cur.current)
      void setSkin(SKINS[(i + dir + SKINS.length) % SKINS.length].id)
    },
    [setSkin],
  )

  const v = useMemo<SkinCtx>(
    () => ({ skin, setSkin, cycleSkin, preload, switcherOpen, setSwitcherOpen, paletteOpen, setPaletteOpen, nodawOpen, setNodawOpen, helpOpen, setHelpOpen, drawerTab, setDrawerTab, selMacro, setSelMacro }),
    [skin, setSkin, cycleSkin, preload, switcherOpen, paletteOpen, nodawOpen, helpOpen, drawerTab, selMacro],
  )
  return <Ctx.Provider value={v}>{children}</Ctx.Provider>
}
