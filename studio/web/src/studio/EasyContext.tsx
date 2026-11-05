import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, waitJob } from '../api'
import type { FinishTarget, MacroKey, Preset, Slider, Track } from '../types'
import { useStudio } from './StudioContext'
import { viz } from './viz'

export type Version = { track: Track; label: string; macros: Record<MacroKey, number> }
export type EasySession = { genreId: string | null; vibe: string; macros: Record<MacroKey, number>; versions: string[]; idx: number; labels: string[] }
export const NEUTRAL: Record<MacroKey, number> = { energy: 50, vocals: 50, bass: 50, brightness: 50, space: 50 }
export const ENDS: Record<MacroKey, [string, string]> = {
  energy: ['Calm', 'Hype'],
  vocals: ['Back', 'Front'],
  bass: ['Light', 'Heavy'],
  brightness: ['Warm', 'Airy'],
  space: ['Dry', 'Wide'],
}

export interface Easy {
  vibes: Preset[]
  all: Preset[]
  tiles: Preset[]
  sliders: Slider[]
  targets: Record<string, FinishTarget>
  showAll: boolean
  setShowAll: (v: boolean | ((x: boolean) => boolean)) => void
  genreId: string | null
  selectGenre: (p: Preset) => void
  vibe: string
  setVibe: (v: string) => void
  macros: Record<MacroKey, number>
  setMacro: (k: MacroKey, v: number) => void
  /** Call when a slider gesture ends: re-renders the mix. */
  commitMacros: () => void
  resetMacros: () => void
  versions: Version[]
  idx: number
  setIdx: (i: number | ((x: number) => number)) => void
  cur: Version | null
  track: Track | null
  busy: string
  files: Record<string, string> | null
  midi: string | null
  report: { lufs: number; true_peak_db: number; target: { key: string }; within_tolerance?: boolean } | undefined
  analysis: { lufs: number | null; true_peak_db: number } | null
  make: () => Promise<void>
  finish: (target: string) => Promise<void>
  doExport: () => Promise<void>
  tool: (name: string, label: string, extra?: Record<string, unknown>) => Promise<void>
  pickUpload: () => void
  pickReference: () => void
  openAdvanced: () => void
}

const Ctx = createContext<Easy | null>(null)
export const useEasy = () => {
  const s = useContext(Ctx)
  if (!s) throw new Error('EasyProvider missing')
  return s
}

export function EasyProvider({ children }: { children: ReactNode }) {
  const studio = useStudio()
  const { toast, addTrack, loadTrack, mode, setMode } = studio
  const [loaded, setLoaded] = useState(false)
  const [vibes, setVibes] = useState<Preset[]>([])
  const [all, setAll] = useState<Preset[]>([])
  const [sliders, setSliders] = useState<Slider[]>([])
  const [targets, setTargets] = useState<Record<string, FinishTarget>>({})
  const [showAll, setShowAll] = useState(false)
  const [genreId, setGenreId] = useState<string | null>(null)
  const [vibe, setVibe] = useState('')
  const [macros, setMacros] = useState<Record<MacroKey, number>>(NEUTRAL)
  const [versions, setVersions] = useState<Version[]>([])
  const [idx, setIdx] = useState(-1)
  const [busy, setBusy] = useState('')
  const [files, setFiles] = useState<Record<string, string> | null>(null)
  const [midi, setMidi] = useState<string | null>(null)
  const upload = useRef<HTMLInputElement>(null)
  const refUpload = useRef<HTMLInputElement>(null)
  const renderTimer = useRef<number | undefined>(undefined)
  const saveTimer = useRef<number | undefined>(undefined)
  const macrosRef = useRef(macros)
  macrosRef.current = macros

  const cur = idx >= 0 ? versions[idx] ?? null : null
  const track = cur?.track ?? null

  useEffect(() => {
    api.vibes().then((v) => {
      setVibes(v.vibes)
      setSliders(v.sliders)
      setTargets(v.finish)
    }).catch(() => toast('Could not load the vibe library. Is the Studio running?', 'error'))
    api.presets({ category: 'genre' }).then((r) => setAll(r.presets)).catch(() => undefined)
  }, [toast])

  // restore the last session, once
  useEffect(() => {
    let dead = false
    api.session().then(async (r) => {
      const s = (r.easy as EasySession) ?? null
      if (dead) return
      if (s) {
        setGenreId(s.genreId ?? null)
        setVibe(s.vibe ?? '')
        if (s.macros) setMacros(s.macros)
        if (s.versions?.length) {
          const ts = await Promise.all(s.versions.map((id) => api.track(id).catch(() => null)))
          const vs: Version[] = []
          ts.forEach((t, i) => t && vs.push({ track: t, label: s.labels?.[i] ?? 'Restored', macros: s.macros }))
          if (vs.length && !dead) {
            setVersions(vs)
            setIdx(Math.min(s.idx, vs.length - 1))
          }
        }
      }
    }).catch(() => undefined).finally(() => !dead && setLoaded(true))
    return () => {
      dead = true
    }
  }, [])

  // autosave (debounced), only after the restore finished
  useEffect(() => {
    if (!loaded) return
    window.clearTimeout(saveTimer.current)
    const s: EasySession = { genreId, vibe, macros, versions: versions.map((v) => v.track.id), idx, labels: versions.map((v) => v.label) }
    saveTimer.current = window.setTimeout(() => void api.saveSession({ easy: s }).catch(() => undefined), 600)
  }, [loaded, genreId, vibe, macros, versions, idx])

  // the engine always plays the Easy version you are looking at
  useEffect(() => {
    if (mode === 'easy' && track) loadTrack(track, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, track?.id])

  useEffect(() => {
    viz.energy = macros.energy
  }, [macros.energy])
  const working = busy || studio.busy
  useEffect(() => {
    viz.making = working ? 1 : 0
  }, [working])

  const push = useCallback((t: Track, label: string, m: Record<MacroKey, number>) => {
    setVersions((vs) => [...vs.slice(0, idx + 1), { track: t, label, macros: m }].slice(-40))
    setIdx((i) => Math.min(i + 1, 39))
    setFiles(null)
    addTrack(t)
  }, [idx, addTrack])

  const run = async <T,>(label: string, start: () => Promise<{ job_id: string }>): Promise<T | null> => {
    setBusy(label)
    try {
      const { job_id } = await start()
      return await waitJob<T>(job_id, (m) => setBusy(m))
    } catch (e) {
      toast((e as Error).message, 'error')
      return null
    } finally {
      setBusy('')
    }
  }

  const make = async () => {
    if (!genreId && !vibe.trim()) {
      toast('Pick a vibe tile or describe the vibe first.', 'info')
      return
    }
    const g = all.find((p) => p.id === genreId) ?? vibes.find((p) => p.id === genreId)
    const m = (g?.macros as Record<MacroKey, number>) ?? macros
    viz.hit(1)
    const res = await run<{ track: Track; genre_id: string; macros: Record<MacroKey, number> }>('Writing your track...', () =>
      api.easyMake({ genre_id: genreId, vibe }))
    if (res) {
      setGenreId(res.genre_id)
      setMacros(res.macros ?? m)
      push(res.track, 'Made it', res.macros ?? m)
      toast('Your track is ready. Shape it with the sliders, then finish it.', 'ok')
    }
  }

  const rerender = (m: Record<MacroKey, number>) => {
    if (!track) return
    window.clearTimeout(renderTimer.current)
    renderTimer.current = window.setTimeout(async () => {
      const res = await run<{ track: Track }>('Updating the mix...', () => api.easyRender({ track_id: track.id, genre_id: genreId, ...m }))
      if (res) push(res.track, 'Shaped', m)
    }, 350)
  }

  const finish = async (target: string) => {
    if (!track) return
    const res = await run<{ track: Track; report: { lufs: number; true_peak_db: number } }>(`Finishing for ${targets[target]?.label}...`, () =>
      api.finish({ track_id: track.id, target }))
    if (res) {
      push(res.track, `Finished for ${targets[target]?.label}`, macros)
      toast(`Finished: ${res.report.lufs.toFixed(1)} LUFS, ${res.report.true_peak_db.toFixed(1)} dBTP.`, 'ok')
    }
  }

  const doExport = async () => {
    if (!track) return
    const finished = !!track.meta?.finished
    const res = await run<{ files: Record<string, string> }>('Exporting...', () =>
      api.export({ track_id: track.id, formats: ['wav', 'mp3'], include_stems: false, normalize: !finished }))
    if (res) {
      setFiles(res.files)
      toast(finished ? 'Exported at your finished loudness.' : 'Exported. Tip: finish for a platform first for the best loudness.', 'ok')
    }
  }

  const tool = async (name: string, label: string, extra: Record<string, unknown> = {}) => {
    if (!track) return
    const res = await run<{ track?: Track; midi_url?: string; note?: string; notes?: number; engine?: string }>(label, () =>
      api.tool(name, { track_id: track.id, ...extra }))
    if (!res) return
    if (res.midi_url) {
      setMidi(res.midi_url)
      toast(`MIDI ready (${res.notes ?? 0} notes).`, 'ok')
    }
    if (res.track) {
      push(res.track, label.replace('...', ''), macros)
      toast(res.note || 'Done. Undo brings back the previous version.', 'ok')
    }
  }

  const onUpload = async (f: File) => {
    setBusy(`Importing ${f.name}...`)
    try {
      const { track: t } = await api.upload(f)
      push(t, 'Imported', NEUTRAL)
      setMacros(NEUTRAL)
      toast(`Imported ${f.name}. The sliders shape the full mix; split stems for finer control.`, 'ok')
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy('')
    }
  }

  const onReference = async (f: File) => {
    if (!track) return
    setBusy('Importing reference...')
    try {
      const { track: ref } = await api.upload(f)
      await tool('match', 'Matching your reference...', { reference_track_id: ref.id })
    } catch (e) {
      toast((e as Error).message, 'error')
      setBusy('')
    }
  }

  const tiles = useMemo(() => (showAll ? all : vibes), [showAll, all, vibes])
  const report = track?.meta?.master as Easy['report']
  const analysis = (track?.meta?.analysis ?? null) as Easy['analysis']

  const value: Easy = {
    vibes, all, tiles, sliders, targets, showAll, setShowAll, genreId,
    selectGenre: (p) => {
      setGenreId(p.id)
      if (p.macros) setMacros(p.macros as Record<MacroKey, number>)
      viz.hit(0.6)
    },
    vibe, setVibe, macros,
    setMacro: (k, v) => setMacros((m) => ({ ...m, [k]: v })),
    commitMacros: () => rerender(macrosRef.current),
    resetMacros: () => {
      setMacros(NEUTRAL)
      rerender(NEUTRAL)
    },
    versions, idx, setIdx, cur, track, busy: working, files, midi, report, analysis,
    make, finish, doExport, tool,
    pickUpload: () => upload.current?.click(),
    pickReference: () => refUpload.current?.click(),
    openAdvanced: () => {
      if (cur?.track) loadTrack(cur.track)
      setMode('advanced')
    },
  }
  return (
    <Ctx.Provider value={value}>
      {children}
      <input ref={upload} data-testid="easy-upload" type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void onUpload(f); e.target.value = '' }} />
      <input ref={refUpload} data-testid="easy-reference" type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void onReference(f); e.target.value = '' }} />
    </Ctx.Provider>
  )
}
