import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { audio } from '../../audio/engine'
import { download, encodeWav, safeName } from '../../audio/wav'
import { zipFiles } from '../../demo/zip'
import { BrowserSeparator, MODELS, MODEL_ORDER, detectSepCaps, formatBytes, isModelCached, toStereo44k, type ModelDef, type SepCaps, type SepProgress } from '../../sep/client'
import { useStudio } from '../../studio/StudioContext'
import type { Track } from '../../types'
import { Field } from './Tabs'

const COLORS: Record<string, string> = { drums: '#ff7a59', bass: '#7c5cff', vocals: '#ffd166', other: '#4cc9f0', instrumental: '#4cc9f0' }
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const fmtTime = (ms: number) => { const s = Math.round(ms / 1000); return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s` }

type Clip = { name: string; buffer: AudioBuffer; url: string; fromUpload: boolean }
type Done = { backend: string; ms: number; threads: string; seconds: number; model: string; files: { name: string; blob: Blob }[] }

/**
 * Real stem separation in the browser: onnxruntime-web in a Worker, WebGPU when the GPU supports it and
 * WASM otherwise. Nothing is uploaded; the weights come from a CDN once and stay in this browser.
 */
export function SplitTab() {
  const { current, loadTrack, toast } = useStudio()
  const [caps, setCaps] = useState<SepCaps | null>(null)
  const [model, setModel] = useState('')
  const [device, setDevice] = useState<'auto' | 'wasm' | 'webgpu'>('auto')
  const [cached, setCached] = useState<Record<string, boolean>>({})
  const [clip, setClip] = useState<Clip | null>(null)
  const [start, setStart] = useState(0)
  const [useRegion, setUseRegion] = useState(true)
  const [ack, setAck] = useState<string>('')
  const [phase, setPhase] = useState<'idle' | 'decoding' | 'download' | 'init' | 'separate'>('idle')
  const [prog, setProg] = useState<SepProgress | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState<Done | null>(null)
  const sepRef = useRef<BrowserSeparator | null>(null)
  const cancelled = useRef(false)

  useEffect(() => {
    void detectSepCaps().then((c) => { setCaps(c); setModel((m) => m || c.recommended) })
    void Promise.all(MODEL_ORDER.map(async (id) => [id, await isModelCached(MODELS[id as keyof typeof MODELS]).catch(() => false)] as const)).then((r) => setCached(Object.fromEntries(r)))
    return () => { sepRef.current?.terminate() }
  }, [])

  const def = (model ? (MODELS as unknown as Record<string, ModelDef>)[model] : undefined) ?? null
  const busy = phase !== 'idle'
  const srcName = clip?.name ?? current?.title ?? ''
  const hasSource = !!clip || !!current
  const sourceDur = clip?.buffer.duration ?? current?.duration_s ?? 0
  const rgn = useSyncExternalStore((fn) => audio.subscribe(fn), () => audio.region)
  const region = useRegion ? rgn : null
  const maxSec = caps?.maxSeconds ?? 120
  const from = region ? region.start : Math.min(start, Math.max(0, sourceDur - 1))
  const wanted = region ? region.end - region.start : Math.max(0, sourceDur - from)
  const length = Math.min(wanted, maxSec)
  const clipped = wanted > maxSec + 0.5
  const needsDownload = !!def && !cached[def.id]
  const lowMemWarn = !!(caps && def && def.minMemoryGB && caps.lowMemory)

  const pick = async (f: File | undefined) => {
    if (!f) return
    setError(''); setDone(null); setPhase('decoding')
    try {
      const ab = await f.arrayBuffer()
      const url = URL.createObjectURL(new Blob([ab.slice(0)], { type: f.type || 'audio/mpeg' }))
      const buffer = await audio.decodeBytes(ab)
      setClip({ name: f.name.replace(/\.[^.]+$/, ''), buffer, url, fromUpload: true })
      setStart(0)
    } catch {
      setError(`This browser could not decode ${f.name}. Try an mp3, wav or m4a; some phones cannot read FLAC or OGG.`)
    } finally { setPhase('idle') }
  }

  const run = async () => {
    if (!def || !hasSource) return
    if (needsDownload && ack !== def.id) { setAck(def.id); return }
    setError(''); setDone(null); setNotice(''); cancelled.current = false
    try {
      setPhase('decoding')
      const buf = clip?.buffer ?? (await audio.decode(current!.url))
      const { left, right } = await toStereo44k(buf, from, Math.min(buf.duration, from + length))
      const sep = (sepRef.current ??= new BrowserSeparator())
      setPhase('download')
      await sep.load(def.id, device, (p) => {
        setProg(p)
        if (p.phase === 'init') setPhase('init')
        if (p.phase === 'fallback') setNotice('GPU not available for this model, switching to the CPU.')
      })
      setCached((c) => ({ ...c, [def.id]: true }))
      setPhase('separate')
      // the worker takes ownership of these buffers, so keep a copy of the mix first
      const mixBlob = encodeWav([left.slice(0), right.slice(0)], 44100, 16)
      const res = await sep.separate(left, right, (p) => { setProg(p); if (p.notice) setNotice(p.notice) })
      const files = Object.entries(res.stems).map(([name, [l, r]]) => ({ name, blob: encodeWav([l, r], res.sampleRate, 16) }))
      const id = `split-${Date.now().toString(36)}`
      const track: Track = {
        id,
        title: `${srcName} (stems)`,
        source: 'browser-split',
        url: URL.createObjectURL(mixBlob),
        created: Date.now() / 1000,
        prompt: '',
        bpm: current?.bpm ?? null,
        key: current?.key ?? '',
        duration_s: length,
        stems: files.map((f, i) => ({ id: `${id}:${f.name}`, name: cap(f.name), path: `local://${id}/${f.name}`, url: URL.createObjectURL(f.blob), color: COLORS[f.name] ?? ['#ff7a59', '#7c5cff', '#ffd166', '#4cc9f0'][i % 4] })),
        stem_method: `onnx:${def.id}`,
        notes: `Split in your browser with ${def.label} on ${res.backend}.`,
        parent_id: current?.id ?? '',
      }
      setDone({ backend: res.backend, ms: res.ms, threads: res.threads, seconds: length, model: def.label, files })
      loadTrack(track)
      toast(`Split into ${files.length} stems in ${fmtTime(res.ms)} on ${res.backend.toUpperCase()}`, 'ok')
    } catch (e) {
      const err = e as Error & { cancelled?: boolean }
      if (err.cancelled || cancelled.current) setNotice('Cancelled.')
      else {
        const m = String(err.message || err)
        setError(/memory|alloc|OOM|out of/i.test(m)
          ? `The browser ran out of memory loading ${def.label}. ${caps?.mobile ? 'Phones usually cannot hold this model. ' : ''}Pick the Light preview, split a shorter region, or close other tabs.`
          : /fetch|network|Failed to|download/i.test(m)
            ? `The model download failed (${m}). Check your connection and try again; it resumes where it stopped.`
            : m)
        sepRef.current?.terminate(); sepRef.current = null
      }
    } finally { setPhase('idle'); setProg(null); setAck('') }
  }

  const cancel = () => { cancelled.current = true; sepRef.current?.cancel(); if (phase === 'download') { sepRef.current?.terminate(); sepRef.current = null; setPhase('idle'); setNotice('Cancelled. The partial download is kept and resumes next time.') } }

  const pct = prog?.phase === 'download' && prog.total ? (prog.loaded ?? 0) / prog.total : prog?.phase === 'separate' && prog.total ? (prog.done ?? 0) / prog.total : null

  return (
    <div className="pro-form split" data-testid="split-tab">
      <p className="muted sp-note">
        Real AI stem separation that runs on this device. Your audio is never uploaded. The model downloads once from Hugging Face and is kept in this browser.
      </p>

      <div className="field-row">
        <Field label="Source">
          <div className="btn-row">
            <label className="btn small" data-testid="split-pick">
              Choose a file
              <input className="sr-file" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac,.ogg" onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = '' }} data-testid="split-file" />
            </label>
            {clip && <button className="btn small ghost" onClick={() => { setClip(null); setDone(null) }}>Use the loaded track</button>}
          </div>
        </Field>
        <div className="field"><span>Splitting</span><strong className="sp-src">{hasSource ? `${srcName} (${sourceDur ? fmtTime(sourceDur * 1000) : '?'})` : 'Nothing loaded: choose a file or load a track'}</strong></div>
      </div>

      <div className="split-models" role="radiogroup" aria-label="Model">
        {MODEL_ORDER.map((id) => {
          const m = (MODELS as unknown as Record<string, ModelDef>)[id]
          const rec = caps?.recommended === id
          return (
            <button key={id} role="radio" aria-checked={model === id} className={`split-model ${model === id ? 'on' : ''}`} onClick={() => { setModel(id); setAck('') }} disabled={busy} data-testid={`model-${id}`}>
              <b>{m.label}{rec ? ' (recommended here)' : ''}</b>
              <span>{m.short}</span>
              <em>{formatBytes(m.sizeBytes)}{cached[id] ? ' · downloaded' : ''} · {m.license.spdx.split(' ')[0]}</em>
            </button>
          )
        })}
      </div>
      {def && <p className="muted sp-note">{def.description} {def.ramHint} <a href={def.license.url} target="_blank" rel="noreferrer">Licence</a>{def.license.caveat ? `: ${def.license.caveat}` : ''}.</p>}

      <div className="field-row">
        <Field label="Compute">
          <select className="select" value={device} onChange={(e) => setDevice(e.target.value as typeof device)} disabled={busy} data-testid="split-device">
            <option value="auto">Auto ({caps ? (caps.webgpu ? 'WebGPU' : 'CPU / WASM') : '...'})</option>
            <option value="wasm">CPU (WASM{caps?.isolated ? ', multi-thread' : ', 1 thread'})</option>
            <option value="webgpu" disabled={!caps?.webgpu}>WebGPU{caps?.webgpu ? '' : ' (not available)'}</option>
          </select>
        </Field>
        {!rgn && <Field label="Start at (s)"><input className="num" type="number" min={0} step={1} value={start} onChange={(e) => setStart(Math.max(0, Number(e.target.value) || 0))} disabled={busy} /></Field>}
        {rgn && (
          <label className="sp-check"><input type="checkbox" checked={useRegion} onChange={(e) => setUseRegion(e.target.checked)} /> Only the selected region ({(rgn.end - rgn.start).toFixed(1)}s)</label>
        )}
      </div>

      {caps && (
        <p className="muted sp-note" data-testid="split-caps">
          {caps.webgpu ? 'WebGPU is available.' : caps.gpuReason} {caps.isolated ? `CPU threads: ${Math.min(caps.cores, 8)}.` : 'Multi-threading is off on this page, so the CPU path uses one thread.'}
          {' '}Up to {fmtTime(caps.maxSeconds * 1000)} per run on this device{caps.memoryGB ? ` (about ${caps.memoryGB} GB memory)` : ''}.
        </p>
      )}
      {clipped && <p className="sp-warn">Only {fmtTime(length * 1000)} of the {fmtTime(wanted * 1000)} will be split on this device. Select a region or move the start to choose which part.</p>}
      {lowMemWarn && model === 'htdemucs' && <p className="sp-warn">This looks like a low-memory device. The 4-stem Demucs model may crash the tab; the Light preview is safer.</p>}
      {def?.warning && model !== 'htdemucs' && <p className="muted sp-note">{def.warning}</p>}
      {needsDownload && ack === def?.id && !busy && (
        <p className="sp-warn" role="alert" data-testid="download-warning">
          First use downloads {formatBytes(def!.sizeBytes)} to this browser (once). On mobile data that can cost real money. Press the button again to go ahead.
        </p>
      )}

      <div className="btn-row">
        <button className="btn pri" disabled={busy || !hasSource || !def} onClick={() => void run()} data-testid="split-go">
          {busy ? 'Working...' : needsDownload ? (ack === def?.id ? `Download ${formatBytes(def!.sizeBytes)} and split` : `Split (needs a ${formatBytes(def?.sizeBytes ?? 0)} download)`) : `Split ${length ? fmtTime(length * 1000) : ''}`}
        </button>
        {busy && phase !== 'decoding' && <button className="btn" onClick={cancel} data-testid="split-cancel">Cancel</button>}
      </div>

      {busy && (
        <div className="split-prog" data-testid="split-progress" aria-live="polite">
          <div className="bar"><i style={{ width: `${pct === null ? 100 : Math.round(pct * 100)}%`, opacity: pct === null ? 0.35 : 1 }} /></div>
          <span className="muted">
            {phase === 'decoding' && 'Reading audio...'}
            {phase === 'download' && (prog?.verifying ? 'Verifying download...' : `Downloading model ${formatBytes(prog?.loaded ?? 0)} of ${formatBytes(prog?.total ?? def?.sizeBytes ?? 0)}${prog?.fromCache ? ' (from cache)' : ''}`)}
            {phase === 'init' && 'Starting the model (this can take a few seconds)...'}
            {phase === 'separate' && `Separating: chunk ${prog?.done ?? 0} of ${prog?.total ?? '?'}${prog?.etaMs ? `, about ${fmtTime(prog.etaMs)} left` : ''}`}
          </span>
        </div>
      )}
      {notice && <p className="muted sp-note" data-testid="split-notice">{notice}</p>}
      {error && <p className="sp-err" role="alert" data-testid="split-error">{error}</p>}

      {done && (
        <div className="split-done" data-testid="split-done">
          <div className="report">
            <div><strong>{done.files.length}</strong>stems</div>
            <div><strong>{fmtTime(done.ms)}</strong>{(done.ms / 1000 / done.seconds).toFixed(2)}x of clip length</div>
            <div><strong>{done.backend.toUpperCase()}</strong>{done.threads === 'single' ? '1 thread' : done.threads}</div>
            <div><strong>{done.model}</strong>model</div>
          </div>
          <p className="muted sp-note">The stems are loaded in the mixer. Use the Live FX and Sampler tabs on them. They live in this tab only, so download them to keep them.</p>
          <div className="btn-row">
            <button className="btn small" onClick={() => void zipFiles(done.files.map((f) => ({ name: `${safeName(srcName)}_${f.name}.wav`, blob: f.blob }))).then((z) => download(z, `${safeName(srcName)}_stems.zip`))}>Download stems (zip)</button>
            {done.files.map((f) => <button key={f.name} className="btn small ghost" onClick={() => download(f.blob, `${safeName(srcName)}_${f.name}.wav`)}>{cap(f.name)} WAV</button>)}
          </div>
        </div>
      )}
    </div>
  )
}
