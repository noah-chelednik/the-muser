import { Suspense, lazy, useMemo } from 'react'
import { useSkin } from './SkinProvider'
import { skinDef } from './registry'

/** Lazy per-skin chunk (layout, CSS, fonts, WebGL). Providers above this keep state across swaps. */
export function SkinHost() {
  const { skin } = useSkin()
  const Skin = useMemo(() => lazy(skinDef(skin).load), [skin])
  return (
    <Suspense fallback={<div className="fallback-boot">Loading {skinDef(skin).name}</div>}>
      <Skin />
    </Suspense>
  )
}
