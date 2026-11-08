/**
 * Sample Library Browser
 * Searchable drive-scanned library of samples and soundfonts.
 * Assign samples to pads or load soundfonts onto the keyboard.
 */
import { useCallback, useEffect, useState } from 'react'
import { PADS } from '../audio/instruments'
import { loadPadBuffer, padBank } from '../audio/samples'
import * as soundfont from '../audio/soundfont'
import { validateAudioFile } from '../audio/upload'
import './SampleLibrary.css'

type LibItem = {
  path: string
  name: string
  type: 'sample' | 'soundfont'
  size: number
  mtime: number
  duration?: number | null
  sample_rate?: number | null
}

type Props = {
  onAssign?: (item: LibItem, padIndex: number) => void
}

const fileUrl = (path: string) => `/api/library/file?path=${encodeURIComponent(path)}`

export function SampleLibrary({ onAssign }: Props) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<'all' | 'sample' | 'soundfont'>('all')
  const [items, setItems] = useState<LibItem[]>([])
  const [stats, setStats] = useState({ total: 0, samples: 0, soundfonts: 0 })
  const [scanning, setScanning] = useState(false)
  const [scanPaths, setScanPaths] = useState('C:\\Users\\Public\\Music\\Samples')
  const [selected, setSelected] = useState<LibItem | null>(null)
  const [targetPad, setTargetPad] = useState(0)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [preview, setPreview] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const s = await fetch('/api/library/stats').then((r) => r.json())
      setStats(s)
      const qs = new URLSearchParams()
      if (query) qs.set('q', query)
      if (kind !== 'all') qs.set('kind', kind)
      const list = await fetch(`/api/library/search?${qs}`).then((r) => r.json())
      setItems(list)
    } catch {
      setItems([])
    }
  }, [query, kind])

  useEffect(() => { void refresh() }, [refresh])

  const scan = async () => {
    const paths = scanPaths.split(/[;\n]/).map((s) => s.trim()).filter(Boolean)
    if (!paths.length) return
    setScanning(true)
    setMsg('')
    try {
      await fetch('/api/library/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths }),
      })
      await refresh()
    } finally {
      setScanning(false)
    }
  }

  const assign = async (item: LibItem) => {
    setBusy(true)
    setMsg('')
    try {
      if (item.type === 'soundfont') {
        await soundfont.loadFromLibrary(item.path)
        setMsg(`Loaded ${item.name} on the keyboard`)
        onAssign?.(item, -1)
        return
      }
      const res = await fetch(fileUrl(item.path))
      if (!res.ok) throw new Error(res.status === 403 ? 'File is not in the scanned library.' : 'Could not load file')
      // the server only serves files its scanner indexed; the bytes still go through the upload checks
      const blob = await res.blob()
      const v = await validateAudioFile(new File([blob], item.path.split(/[\\/]/).pop() || 'sample.wav', { type: blob.type || '' }))
      await loadPadBuffer(targetPad, v.name, v.buffer, { kind: 'upload' })
      setMsg(`Loaded onto pad ${targetPad + 1}`)
      onAssign?.(item, targetPad)
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Load failed')
    } finally {
      setBusy(false)
    }
  }

  const pick = (item: LibItem) => {
    setSelected(item)
    setPreview(item.type === 'sample' ? fileUrl(item.path) : null)
  }

  const detail = (it: LibItem) => {
    const parts = [it.type, `${(it.size / 1024 / 1024).toFixed(1)} MB`]
    if (it.duration) parts.push(`${it.duration.toFixed(1)}s`)
    if (it.sample_rate) parts.push(`${Math.round(it.sample_rate / 1000)} kHz`)
    return parts.join(' · ')
  }

  return (
    <section className="sample-lib panel" data-testid="sample-library">
      <div className="panel-head">
        <h2>Sample Library</h2>
        <span className="muted">{stats.samples} samples · {stats.soundfonts} soundfonts</span>
      </div>

      <div className="lib-scan">
        <input
          className="num wide"
          placeholder="D:\\Samples; C:\\Music\\Kits"
          value={scanPaths}
          onChange={(e) => setScanPaths(e.target.value)}
        />
        <button className="btn pri" disabled={scanning} onClick={scan}>
          {scanning ? 'Scanning…' : 'Scan drives'}
        </button>
      </div>

      <div className="lib-search">
        <input
          className="num wide"
          placeholder="Search name or path…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select className="select" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="all">All</option>
          <option value="sample">Samples</option>
          <option value="soundfont">SoundFonts</option>
        </select>
      </div>

      <div className="lib-list premium">
        {items.length === 0 && <div className="muted pad-s">No matches. Scan a folder above.</div>}
        {items.map((it) => (
          <div
            key={it.path}
            className={`lib-item ${selected?.path === it.path ? 'on' : ''} ${it.type}`}
            onClick={() => pick(it)}
          >
            <span className={`src-dot src-${it.type}`} />
            <div className="lib-body">
              <div className="lib-title">{it.name}</div>
              <div className="lib-sub">{detail(it)}</div>
            </div>
          </div>
        ))}
      </div>

      {selected && selected.type === 'sample' && (
        <div className="lib-assign">
          <label>
            Assign to pad
            <select value={targetPad} onChange={(e) => setTargetPad(+e.target.value)}>
              {PADS.map((p, i) => <option key={i} value={i}>{i + 1} {padBank.get(i)?.name ?? p.name}</option>)}
            </select>
          </label>
          <button className="btn pri" disabled={busy} onClick={() => void assign(selected)}>
            {busy ? 'Loading…' : 'Load onto pad'}
          </button>
        </div>
      )}

      {selected && selected.type === 'soundfont' && (
        <div className="lib-assign">
          <button className="btn pri" disabled={busy} onClick={() => void assign(selected)}>
            {busy ? 'Loading…' : 'Load onto keyboard'}
          </button>
        </div>
      )}

      {preview && (
        <audio className="lib-preview" src={preview} controls preload="none" />
      )}
      {msg && <div className="muted pad-s">{msg}</div>}
      {soundfont.hasFont() && <div className="muted pad-s">Keyboard: {soundfont.fontName()}</div>}
    </section>
  )
}
