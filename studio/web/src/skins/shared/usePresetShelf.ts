import { useCallback, useEffect, useRef, useState } from 'react'
import { api, waitJob } from '../../api'
import { tapAudioElement } from '../../studio/viz'
import { useRack } from '../../studio/RackContext'
import { useStudio } from '../../studio/StudioContext'
import type { Preset } from '../../types'

export const PRESET_CATS = ['', 'genre', 'mix', 'vocal', 'fx', 'master'] as const

/** One data path for every skin's quick preset shelf. The full browser lives in the Presets tab. */
export function usePresetShelf() {
  const { current: track, toast } = useStudio()
  const rack = useRack()
  const [q, setQ] = useState('')
  const [cat, setCat] = useState<string>('')
  const [items, setItems] = useState<Preset[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [pick, setPick] = useState<string | null>(null)
  const [hearing, setHearing] = useState('')
  const aud = useRef<HTMLAudioElement | null>(null)

  const load = useCallback(async () => {
    try {
      const r = await api.presets({ category: cat || undefined, q: q || undefined })
      setItems(r.presets)
      setCounts(r.counts)
      setLabels(r.categories)
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }, [cat, q, toast])
  useEffect(() => {
    const t = window.setTimeout(() => void load(), 150)
    return () => window.clearTimeout(t)
  }, [load])
  useEffect(() => () => aud.current?.pause(), [])

  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const cur = items.find((p) => p.id === pick) ?? items[0]
  const target = rack.sel === '__master__' ? 'MASTER' : (track?.stems.find((s) => s.id === rack.sel)?.name ?? 'MASTER').toUpperCase()

  const hear = async (p: Preset) => {
    if (hearing === p.id && aud.current) {
      aud.current.pause()
      setHearing('')
      return
    }
    try {
      setHearing(p.id)
      const { job_id } = await api.previewPreset({ preset_id: p.id, track_id: track?.id, stem_id: rack.sel === '__master__' ? undefined : rack.sel })
      const r = await waitJob<{ url: string }>(job_id)
      aud.current?.pause()
      const a = new Audio(r.url)
      aud.current = a
      a.onended = () => setHearing('')
      tapAudioElement(a)
      await a.play()
    } catch (e) {
      setHearing('')
      toast((e as Error).message, 'error')
    }
  }
  const fav = async (p: Preset) => {
    await api.favoritePreset(p.id)
    void load()
  }
  const apply = async (p: Preset) => {
    await rack.applyPreset(p)
    rack.setTab('Chains')
  }
  return { q, setQ, cat, setCat, items, counts, labels, total, cur, setPick, hearing, hear, fav, apply, target }
}
