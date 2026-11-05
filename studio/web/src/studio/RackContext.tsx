import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, waitJob } from '../api'
import { roleFor } from '../components/pro/Tabs'
import type { EngineInfo, FinishTarget, FxItem, PluginSpec, Preset, Track } from '../types'
import { useStudio } from './StudioContext'

export type StemState = { chain: FxItem[]; gain_db: number; pan: number; mute: boolean; solo: boolean }
export type ChainsState = { stems: Record<string, StemState>; master: FxItem[] }
export const EMPTY: StemState = { chain: [], gain_db: 0, pan: 0, mute: false, solo: false }
export const MASTER = '__master__'
export const TABS = ['Live FX', 'Split', 'Sampler', 'Chains', 'Generate', 'Separate', 'Master', 'Presets', 'A/B'] as const
export type Tab = (typeof TABS)[number]

/** Small snapshot undo stack for the chain editor (Ctrl+Z still drives the live mixer). */
function useSnap<T>(initial: T) {
  const [state, setState] = useState(initial)
  const past = useRef<T[]>([])
  const future = useRef<T[]>([])
  const [, tick] = useState(0)
  const set = useCallback((next: T) => {
    setState((cur) => {
      past.current = [...past.current.slice(-99), cur]
      future.current = []
      return next
    })
    tick((x) => x + 1)
  }, [])
  const undo = () => {
    const p = past.current.pop()
    if (p === undefined) return
    future.current.push(state)
    setState(p)
    tick((x) => x + 1)
  }
  const redo = () => {
    const f = future.current.pop()
    if (f === undefined) return
    past.current.push(state)
    setState(f)
    tick((x) => x + 1)
  }
  const reset = (v: T) => {
    past.current = []
    future.current = []
    setState(v)
  }
  return { state, set, undo, redo, reset, canUndo: past.current.length > 0, canRedo: future.current.length > 0 }
}

export interface Rack {
  tab: Tab
  setTab: (t: Tab) => void
  plugins: Record<string, PluginSpec>
  targets: Record<string, FinishTarget>
  engines: EngineInfo[]
  models: { file: string; label: string; stems: number; gpu: boolean }[]
  busy: string
  sel: string
  setSel: (s: string) => void
  chains: ChainsState
  selChain: FxItem[]
  setSelChain: (c: FxItem[]) => void
  setStemState: (id: string, patch: Partial<StemState>) => void
  snap: { undo: () => void; redo: () => void; canUndo: boolean; canRedo: boolean }
  applyPreset: (p: Preset) => Promise<void>
  render: () => Promise<void>
  run: <T>(label: string, start: () => Promise<{ job_id: string }>) => Promise<T | null>
}

const Ctx = createContext<Rack | null>(null)
export const useRack = () => {
  const s = useContext(Ctx)
  if (!s) throw new Error('RackProvider missing')
  return s
}

export function RackProvider({ children }: { children: ReactNode }) {
  const { current: track, toast, loadTrack } = useStudio()
  const [tab, setTab] = useState<Tab>('Live FX')
  const [plugins, setPlugins] = useState<Record<string, PluginSpec>>({})
  const [targets, setTargets] = useState<Record<string, FinishTarget>>({})
  const [engines, setEngines] = useState<EngineInfo[]>([])
  const [models, setModels] = useState<Rack['models']>([])
  const [busy, setBusy] = useState('')
  const [sel, setSel] = useState<string>(MASTER)
  const snap = useSnap<ChainsState>({ stems: {}, master: [] })

  useEffect(() => {
    api.plugins().then((r) => setPlugins(r.plugins)).catch(() => undefined)
    api.targets().then((r) => setTargets(r.targets)).catch(() => undefined)
    api.engines().then((r) => setEngines(r.engines)).catch(() => undefined)
    api.sepModels().then((r) => setModels(r.models)).catch(() => undefined)
  }, [])

  const stemKey = track?.stems.map((s) => s.id).join('|') ?? ''
  useEffect(() => {
    snap.reset({ stems: Object.fromEntries((track?.stems ?? []).map((s) => [s.id, { ...EMPTY }])), master: [] })
    setSel(track?.stems[0]?.id ?? MASTER)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track?.id, stemKey])

  const run: Rack['run'] = async <T,>(label: string, start: () => Promise<{ job_id: string }>) => {
    setBusy(label)
    try {
      const { job_id } = await start()
      return await waitJob<T>(job_id, setBusy)
    } catch (e) {
      toast((e as Error).message, 'error')
      return null
    } finally {
      setBusy('')
    }
  }

  const chains = snap.state
  const selChain = sel === MASTER ? chains.master : chains.stems[sel]?.chain ?? []
  const setSelChain = (c: FxItem[]) =>
    snap.set(sel === MASTER ? { ...chains, master: c } : { ...chains, stems: { ...chains.stems, [sel]: { ...(chains.stems[sel] ?? EMPTY), chain: c } } })
  const setStemState = (id: string, patch: Partial<StemState>) => snap.set({ ...chains, stems: { ...chains.stems, [id]: { ...(chains.stems[id] ?? EMPTY), ...patch } } })

  const applyPreset = async (p: Preset) => {
    try {
      const full = await api.preset(p.id)
      if (full.category === 'master' && typeof full.master === 'object' && full.master) {
        snap.set({ ...chains, master: full.master.chain })
        setSel(MASTER)
        toast(`Loaded ${full.name} on the master bus.`, 'ok')
      } else if (full.category === 'genre') {
        const next: ChainsState = { stems: { ...chains.stems }, master: chains.master }
        for (const s of track?.stems ?? []) {
          const role = roleFor(s.name)
          const ref = full.stems?.[role] ?? (role === 'other' ? full.stems?.keys : undefined)
          if (typeof ref === 'string') next.stems[s.id] = { ...(next.stems[s.id] ?? EMPTY), chain: (await api.preset(ref)).chain ?? [] }
        }
        if (typeof full.master === 'string') {
          const m = await api.preset(full.master)
          if (typeof m.master === 'object' && m.master) next.master = m.master.chain
        }
        snap.set(next)
        toast(`Loaded the ${full.name} starter onto every stem.`, 'ok')
      } else {
        setSelChain(full.chain ?? [])
        toast(`Loaded ${full.name}.`, 'ok')
      }
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }

  const render = async () => {
    if (!track) return
    const res = await run<{ track: Track }>('Rendering...', () => api.advancedRender({
      track_id: track.id,
      stems: track.stems.map((s) => ({ stem_id: s.id, ...(chains.stems[s.id] ?? EMPTY) })),
      master_chain: chains.master,
    }))
    if (res) {
      loadTrack(res.track)
      toast(`Rendered ${res.track.title}. The original is untouched.`, 'ok')
    }
  }

  const value: Rack = {
    tab, setTab, plugins, targets, engines, models, busy, sel, setSel, chains, selChain, setSelChain, setStemState,
    snap: { undo: snap.undo, redo: snap.redo, canUndo: snap.canUndo, canRedo: snap.canRedo },
    applyPreset, render, run,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
