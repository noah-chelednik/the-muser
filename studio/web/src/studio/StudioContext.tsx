import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, waitJob } from '../api'
import { audio, MASTER_ID } from '../audio/engine'
import { useHistory, type History } from '../state/history'
import { DEFAULT_STEM, SERVER_STEM_KEYS, type Mode, type Project, type Status, type StemParams, type Track } from '../types'
import { viz } from './viz'

export type Toast = { id: number; text: string; kind: 'info' | 'error' | 'ok' }
export type Channel = { id: string; name: string; color: string; url: string; role: string }
/** Pseudo channel so the master FX use the same knobs, undo and bindings as a stem. */
export const MASTER_CH: Channel = { id: MASTER_ID, name: 'Master', color: '#ffffff', url: '', role: 'master' }
export type ToastFn = (text: string, kind?: Toast['kind']) => void

export const INITIAL: Project = {
  mixer: {},
  master: { gain_db: 0, normalize: true },
  synth: { wave: 'sawtooth', cutoff: 0.65, reso: 0.15, attack: 0.01, release: 0.4, detune: 8, volume: 0.7, octave: 0 },
  pads: { volume: 0.8, pitch: 0, tone: 0.5 },
  pattern: (() => {
    const p = Array.from({ length: 16 }, () => Array(16).fill(false) as boolean[])
    ;[0, 6, 10].forEach((s) => (p[0][s] = true))
    ;[4, 12].forEach((s) => (p[1][s] = true))
    for (let s = 0; s < 16; s += 2) p[4][s] = true
    return p
  })(),
  bpm: 92,
}

export const isTyping = () => {
  const el = document.activeElement as HTMLElement | null
  return !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)
}

export function roleOf(name: string): string {
  const n = name.toLowerCase()
  if (/vocal|vox|voice/.test(n)) return 'vocals'
  if (/drum|kick|snare|perc/.test(n)) return 'drums'
  if (/bass|808|sub/.test(n)) return 'bass'
  if (/guitar/.test(n)) return 'guitar'
  if (/lead|melody|synth/.test(n)) return 'lead'
  if (/chord|key|piano|pad|other|instrumental/.test(n)) return 'keys'
  return 'other'
}

export const METHOD_LABEL: Record<string, string> = {
  'demo-synth': 'DEMO STEMS',
  'band-split': 'BAND SPLIT (fallback)',
  'demucs-4stem': 'DEMUCS 4-STEM',
  'demucs-2stem': 'DEMUCS 2-STEM',
}

export interface Studio {
  history: History<Project>
  status: Status | null
  apiDown: boolean
  tracks: Track[]
  current: Track | null
  channels: Channel[]
  buffersVersion: number
  busy: string
  generating: boolean
  toasts: Toast[]
  toast: ToastFn
  mixer: Project['mixer']
  master: Project['master']
  mode: Mode
  setMode: (m: Mode) => void
  showSystem: boolean
  setShowSystem: (v: boolean) => void
  showExport: boolean
  setShowExport: (v: boolean) => void
  loadTrack: (t: Track, keepPosition?: boolean) => void
  addTrack: (t: Track) => void
  refreshStatus: (force?: boolean) => Promise<void>
  deleteTrack: (t: Track) => Promise<void>
  uploadFile: (f: File) => Promise<void>
  onGenerate: (args: { prompt: string; duration_s: number; bpm: number | null; key: string }) => Promise<void>
  onSplit: (mode: '4stem' | '2stem') => Promise<void>
  onRender: () => Promise<void>
  onExport: (o: { formats: string[]; include_stems: boolean; normalize: boolean }) => Promise<Record<string, string> | null>
  setStem: (id: string, name: string, key: keyof StemParams, v: number | boolean, label?: string) => void
  /** Props that wire a Knob or slider to one stem parameter with grouped undo. */
  bindStem: (ch: Channel, key: keyof StemParams, label: string) => {
    value: number
    onBegin: () => void
    onChange: (v: number) => void
    onEnd: () => void
    onCommit: (v: number) => void
  }
  bindMaster: () => { value: number; onBegin: () => void; onChange: (v: number) => void; onEnd: () => void; onCommit: (v: number) => void }
}

const Ctx = createContext<Studio | null>(null)
export const useStudio = () => {
  const s = useContext(Ctx)
  if (!s) throw new Error('StudioProvider missing')
  return s
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const history = useHistory<Project>(INITIAL)
  const [status, setStatus] = useState<Status | null>(null)
  const [apiDown, setApiDown] = useState(false)
  const [tracks, setTracks] = useState<Track[]>([])
  const [current, setCurrent] = useState<Track | null>(null)
  const [buffersVersion, setBuffersVersion] = useState(0)
  const [busy, setBusy] = useState('')
  const [generating, setGenerating] = useState(false)
  const [showSystem, setShowSystem] = useState(false)
  const [showExport, setShowExport] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastId = useRef(0)
  const [mode, setModeState] = useState<Mode>(() => (localStorage.getItem('muser.mode') === 'advanced' ? 'advanced' : 'easy'))
  const setMode = useCallback((m: Mode) => {
    localStorage.setItem('muser.mode', m)
    setModeState(m)
  }, [])

  const toast = useCallback<ToastFn>((text, kind = 'info') => {
    const id = ++toastId.current
    setToasts((t) => [...t, { id, text, kind }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5200)
  }, [])

  const refreshStatus = useCallback(async (force = false) => {
    try {
      setStatus(await api.status(force))
      setApiDown(false)
    } catch {
      setApiDown(true)
    }
  }, [])
  const refreshTracks = useCallback(async () => {
    try {
      setTracks(await api.tracks())
    } catch {
      /* status banner covers this */
    }
  }, [])

  useEffect(() => {
    void refreshStatus(true)
    void refreshTracks()
    const t = window.setInterval(() => void refreshStatus(), 15000)
    return () => window.clearInterval(t)
  }, [refreshStatus, refreshTracks])

  const channels: Channel[] = useMemo(() => {
    if (!current) return []
    if (current.stems.length) return current.stems.map((s) => ({ id: s.id, name: s.name, color: s.color || '#ffffff', url: s.url, role: roleOf(s.name) }))
    return [{ id: `${current.id}:mix`, name: 'Full mix', color: '#ffffff', url: current.url, role: 'mix' }]
  }, [current])

  const keepPos = useRef(false)
  const channelKey = channels.map((c) => c.id).join('|')
  useEffect(() => {
    if (!channels.length) return
    let cancelled = false
    history.reset((s) => {
      const mixer = { ...s.mixer }
      channels.forEach((c) => (mixer[c.id] ??= { ...DEFAULT_STEM }))
      mixer[MASTER_ID] ??= { ...DEFAULT_STEM }
      return mixer === s.mixer ? s : { ...s, mixer, bpm: current?.bpm ?? s.bpm }
    })
    if (current?.bpm) viz.bpm = current.bpm
    const keepPosition = keepPos.current
    keepPos.current = false
    audio
      .load(channels.map((c) => ({ id: c.id, url: c.url })), { keepPosition })
      .then(() => !cancelled && setBuffersVersion((v) => v + 1))
      .catch((e) => toast(`Audio load failed: ${e.message}`, 'error'))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelKey])

  useEffect(() => {
    let rev = audio.bufferRev
    return audio.subscribe(() => { if (audio.bufferRev !== rev) { rev = audio.bufferRev; setBuffersVersion((v) => v + 1) } })
  }, [])

  const { mixer, master } = history.state
  useEffect(() => {
    const anySolo = channels.some((c) => mixer[c.id]?.solo)
    channels.forEach((c) => audio.applyParams(c.id, mixer[c.id] ?? DEFAULT_STEM, anySolo))
  }, [mixer, channels, buffersVersion])
  const masterFx = mixer[MASTER_ID] ?? DEFAULT_STEM
  useEffect(() => audio.applyMaster(masterFx, master.gain_db, master.limiter !== false), [masterFx, master.gain_db, master.limiter, buffersVersion])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey
      if (mod && e.key.toLowerCase() === 'z') {
        if (isTyping()) return
        e.preventDefault()
        if (e.shiftKey) history.redo()
        else history.undo()
      } else if (mod && e.key.toLowerCase() === 'y') {
        if (isTyping()) return
        e.preventDefault()
        history.redo()
      } else if (e.code === 'Space' && !isTyping() && !(document.activeElement instanceof HTMLButtonElement) && !(document.activeElement instanceof HTMLAnchorElement)) {
        e.preventDefault()
        if (audio.playing) audio.pause()
        else audio.play()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [history])

  const addTrack = useCallback((t: Track) => setTracks((xs) => (xs.some((x) => x.id === t.id) ? xs : [t, ...xs])), [])
  const loadTrack = useCallback((t: Track, keep = false) => {
    audio.ensure()
    // a re-render of the same sound keeps the playhead where the listener is
    keepPos.current = keep
    setCurrent(t)
    setTracks((xs) => (xs.some((x) => x.id === t.id) ? xs.map((x) => (x.id === t.id ? t : x)) : [t, ...xs]))
  }, [])

  const deleteTrack = useCallback(
    async (t: Track) => {
      await api.deleteTrack(t.id)
      if (current?.id === t.id) {
        audio.stop()
        setCurrent(null)
      }
      void refreshTracks()
    },
    [current, refreshTracks],
  )

  const uploadFile = useCallback(
    async (f: File) => {
      setBusy(`Importing ${f.name}...`)
      try {
        const { track } = await api.upload(f)
        loadTrack(track)
        toast(`Imported ${f.name}`, 'ok')
      } catch (e) {
        toast(String((e as Error).message), 'error')
      } finally {
        setBusy('')
      }
    },
    [loadTrack, toast],
  )

  const onGenerate: Studio['onGenerate'] = async (args) => {
    setGenerating(true)
    setBusy('Generating...')
    try {
      const { job_id } = await api.generate(args)
      const res = await waitJob<{ track: Track; engine: string; reason?: string }>(job_id, setBusy)
      loadTrack(res.track)
      toast(res.engine === 'demo-synth' ? `Demo synth sketch ready (${res.reason})` : 'ACE-Step generation complete', 'ok')
    } catch (e) {
      toast(String((e as Error).message), 'error')
    } finally {
      setGenerating(false)
      setBusy('')
    }
  }

  const onSplit: Studio['onSplit'] = async (m) => {
    if (!current) return
    setBusy(m === '4stem' ? 'Splitting into stems...' : 'Separating vocals / instrumental...')
    try {
      const { job_id } = await api.split(current.id, m)
      const res = await waitJob<{ track: Track; method: string; note: string }>(job_id, setBusy)
      loadTrack(res.track)
      toast(res.note, res.method === 'band-split' ? 'info' : 'ok')
    } catch (e) {
      toast(String((e as Error).message), 'error')
    } finally {
      setBusy('')
    }
  }

  const onRender: Studio['onRender'] = async () => {
    if (!current) return
    setBusy('Rendering mix on the server...')
    try {
      const stems = channels.map((c) => {
        const p = (mixer[c.id] ?? DEFAULT_STEM) as unknown as Record<string, unknown>
        return { stem_id: c.id, ...Object.fromEntries(SERVER_STEM_KEYS.map((k) => [k, p[k]])) }
      })
      const { job_id } = await api.mix({ track_id: current.id, stems, master_gain_db: master.gain_db, normalize: master.normalize })
      const res = await waitJob<{ track: Track }>(job_id, setBusy)
      setTracks((xs) => [res.track, ...xs])
      toast(`Mixdown rendered: ${res.track.title}`, 'ok')
    } catch (e) {
      toast(String((e as Error).message), 'error')
    } finally {
      setBusy('')
    }
  }

  const onExport: Studio['onExport'] = async (o) => {
    if (!current) return null
    try {
      const { job_id } = await api.export({ track_id: current.id, ...o })
      const res = await waitJob<{ files: Record<string, string> }>(job_id)
      toast('Export ready', 'ok')
      return res.files
    } catch (e) {
      toast(String((e as Error).message), 'error')
      return null
    }
  }

  const setStem = useCallback(
    (id: string, name: string, key: keyof StemParams, v: number | boolean, label?: string) =>
      history.commit(label ?? `${name} ${String(key)}`, (s) => ({ ...s, mixer: { ...s.mixer, [id]: { ...(s.mixer[id] ?? DEFAULT_STEM), [key]: v } } })),
    [history],
  )

  const bindStem: Studio['bindStem'] = (ch, key, label) => {
    const upd = (v: number) => (s: Project): Project => ({ ...s, mixer: { ...s.mixer, [ch.id]: { ...(s.mixer[ch.id] ?? DEFAULT_STEM), [key]: v } } })
    return {
      value: (mixer[ch.id] ?? DEFAULT_STEM)[key] as number,
      onBegin: () => history.begin(`${ch.name} ${label}`),
      onChange: (v) => history.preview(upd(v)),
      onEnd: () => history.end(),
      onCommit: (v) => history.commit(`${ch.name} ${label}`, upd(v)),
    }
  }
  const bindMaster: Studio['bindMaster'] = () => {
    const upd = (v: number) => (s: Project): Project => ({ ...s, master: { ...s.master, gain_db: v } })
    return {
      value: master.gain_db,
      onBegin: () => history.begin('Master gain'),
      onChange: (v) => history.preview(upd(v)),
      onEnd: () => history.end(),
      onCommit: (v) => history.commit('Master gain', upd(v)),
    }
  }

  const value: Studio = {
    history, status, apiDown, tracks, current, channels, buffersVersion, busy, generating, toasts, toast, mixer, master,
    mode, setMode, showSystem, setShowSystem, showExport, setShowExport,
    loadTrack, addTrack, refreshStatus, deleteTrack, uploadFile, onGenerate, onSplit, onRender, onExport, setStem, bindStem, bindMaster,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
