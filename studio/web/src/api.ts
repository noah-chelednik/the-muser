import type { Analysis, EngineInfo, EnginePick, FinishTarget, Hardware, Job, PluginSpec, Preset, Slider, Status, Track } from './types'

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const put = (url: string, body: unknown) =>
  fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const get = <T,>(url: string) => fetch(url).then((r) => j<T>(r))
type JobRef = { job_id: string }
const enc = encodeURIComponent

const remote = {
  status: (refresh = false) => fetch(`/api/status${refresh ? '?refresh=true' : ''}`).then((r) => j<Status>(r)),
  tracks: () => fetch('/api/tracks').then((r) => j<Track[]>(r)),
  deleteTrack: (id: string) => fetch(`/api/tracks/${id}`, { method: 'DELETE' }).then((r) => j(r)),
  generate: (body: { prompt: string; duration_s: number; bpm?: number | null; key?: string; force_demo?: boolean }) =>
    post('/api/generate', body).then((r) => j<{ job_id: string }>(r)),
  split: (id: string, mode: '4stem' | '2stem') =>
    post(`/api/tracks/${id}/split`, { mode }).then((r) => j<{ job_id: string }>(r)),
  mix: (body: unknown) => post('/api/mix', body).then((r) => j<{ job_id: string }>(r)),
  export: (body: unknown) => post('/api/export', body).then((r) => j<{ job_id: string }>(r)),
  job: <T>(id: string) => fetch(`/api/jobs/${id}`).then((r) => j<Job<T>>(r)),
  upload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/upload', { method: 'POST', body: fd }).then((r) => j<{ track: Track }>(r))
  },
  track: (id: string) => get<Track>(`/api/tracks/${id}`),

  // ---- v2: engines, presets, Easy, tools, Advanced
  hardware: (refresh = false) => get<Hardware>(`/api/hardware${refresh ? '?refresh=true' : ''}`),
  engines: (commercialOnly = true) =>
    get<{ engines: EngineInfo[]; tasks: Record<string, string>; selected: Record<string, EnginePick> }>(`/api/engines?commercial_only=${commercialOnly}`),
  installEngine: (key: string) => post(`/api/engines/${key}/install`, {}).then((r) => j<JobRef>(r)),
  plugins: () => get<{ plugins: Record<string, PluginSpec> }>('/api/fx/plugins'),
  targets: () => get<{ targets: Record<string, FinishTarget> }>('/api/mastering/targets'),
  presets: (o: { category?: string; q?: string; favorites?: boolean } = {}) => {
    const qs = new URLSearchParams()
    if (o.category) qs.set('category', o.category)
    if (o.q) qs.set('q', o.q)
    if (o.favorites) qs.set('favorites', 'true')
    return get<{ presets: Preset[]; counts: Record<string, number>; categories: Record<string, string> }>(`/api/presets?${qs}`)
  },
  preset: (id: string) => get<Preset>(`/api/presets/${enc(id)}/item`),
  savePreset: (preset: Partial<Preset>) => post('/api/presets', { preset }).then((r) => j<{ preset: Preset }>(r)),
  deletePreset: (id: string) => fetch(`/api/presets/${enc(id)}/item`, { method: 'DELETE' }).then((r) => j(r)),
  favoritePreset: (id: string) => post(`/api/presets/${enc(id)}/favorite`, {}).then((r) => j<{ favorite: boolean }>(r)),
  importPresets: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/presets/import', { method: 'POST', body: fd }).then((r) => j<{ imported: string[] }>(r))
  },
  exportPresetsUrl: (ids: string[] = []) => `/api/presets/export${ids.length ? `?ids=${enc(ids.join(','))}` : ''}`,
  previewPreset: (body: { preset_id?: string; chain?: unknown; track_id?: string; stem_id?: string }) =>
    post('/api/presets/preview', body).then((r) => j<JobRef>(r)),
  vibes: () => get<{ vibes: Preset[]; sliders: Slider[]; finish: Record<string, FinishTarget> }>('/api/vibes'),
  easyMake: (body: Record<string, unknown>) => post('/api/easy/make', body).then((r) => j<JobRef>(r)),
  easyRender: (body: Record<string, unknown>) => post('/api/easy/render', body).then((r) => j<JobRef>(r)),
  finish: (body: Record<string, unknown>) => post('/api/finish', body).then((r) => j<JobRef>(r)),
  tool: (name: string, body: Record<string, unknown>) => post(`/api/tools/${name}`, body).then((r) => j<JobRef>(r)),
  advancedRender: (body: unknown) => post('/api/advanced/render', body).then((r) => j<JobRef>(r)),
  advancedGenerate: (body: unknown) => post('/api/advanced/generate', body).then((r) => j<JobRef>(r)),
  sepModels: () => get<{ models: { file: string; label: string; stems: number; gpu: boolean }[]; default: Record<string, string> }>('/api/separation/models'),
  analysis: (id: string) => get<{ analysis: Analysis; meta: Record<string, unknown> }>(`/api/tracks/${id}/analysis`),
  session: () => get<Record<string, unknown>>('/api/session'),
  saveSession: (body: unknown) => put('/api/session', body).then((r) => j(r)),
}

export type Api = typeof remote

let demo: Api | null = null
/** True when the Studio is running its in-browser demo backend (no Python server reachable). */
export const isBrowserDemo = () => demo !== null

/** Calls go to the Python server, or to the in-browser demo backend when no server answers. */
export const api: Api = new Proxy(remote, {
  get: (t, k) => (demo ? (demo as never)[k] : (t as never)[k]),
})

/**
 * Probe the server once at startup. A network error, a timeout, or a non-JSON reply (a static
 * host rewriting /api/* to index.html) switches to the browser demo. Set ?demo=1 to force it.
 */
export async function initApi(): Promise<void> {
  const force = new URLSearchParams(location.search).get('demo') === '1'
  let ok = false
  if (!force) {
    try {
      const ctl = new AbortController()
      const timer = setTimeout(() => ctl.abort(), 3500)
      const res = await fetch('/api/status', { signal: ctl.signal })
      clearTimeout(timer)
      const body = res.ok && (res.headers.get('content-type') ?? '').includes('json') ? await res.json() : null
      ok = !!body && typeof body === 'object' && 'items' in body
    } catch {
      ok = false
    }
  }
  if (!ok) demo = (await import('./demo/backend')).createDemoApi()
}

/** Poll a job until it finishes. */
export async function waitJob<T>(id: string, onMsg?: (m: string) => void): Promise<T> {
  for (;;) {
    const job = await api.job<T>(id)
    if (job.message && onMsg) onMsg(job.message)
    if (job.status === 'done') return job.result as T
    if (job.status === 'error') throw new Error(job.error || 'Job failed')
    await new Promise((r) => setTimeout(r, 400))
  }
}

export type ChatEvent = { event: string; data: any } // eslint-disable-line @typescript-eslint/no-explicit-any

/** POST + read a Server-Sent-Events stream. */
export async function streamChat(
  body: { message: string; session_id?: string | null; model?: string | null },
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (demo) return (await import('./demo/backend')).demoChat(body, onEvent, signal)
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`Chat failed: ${res.status}`)
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!data) continue
      try {
        onEvent({ event, data: JSON.parse(data) })
      } catch {
        onEvent({ event, data })
      }
    }
  }
}
