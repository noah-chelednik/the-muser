/**
 * Premium Sample Library Browser
 * Cyber-HUD / chromatic nihilism aesthetic. Searchable drive-scanned library
 * of samples and soundfonts. Assign directly to pads or audition.
 */
import { useCallback, useEffect, useState } from 'react'
import { padBank } from '../audio/samples'
import { validateAudioFile } from '../audio/upload'
import { PADS } from '../audio/instruments'

type LibItem = {
  path: string
  name: string
  type: 'sample' | 'soundfont'
  size: number
  mtime: number
  duration?: number | null
}

type Props = {
  onAssign?: (item: LibItem, padIndex: number) => void
}

export function SampleLibrary({ onAssign }: Props) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<'all' | 'sample' | 'soundfont'>('all')
  const [items, setItems] = useState<LibItem[]>([])
  const [stats, setStats] = useState({ total: 0, samples: 0, soundfonts: 0 })
  const [scanning, setScanning] = useState(false)
  const [scanPaths, setScanPaths] = useState('C:\\Users\\Public\\Music\\Samples')
  const [selected, setSelected] = useState<LibItem | null>(null)
  const [targetPad, setTargetPad] = useState(0)

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

  const [assignErr, setAssignErr] = useState('')
  const assign = async (item: LibItem) => {
    if (item.type !== 'sample') return
    setAssignErr('')
    try {
      // the server only serves files its scanner indexed; the bytes still go through the upload guard
      const r = await fetch(`/api/library/file?path=${encodeURIComponent(item.path)}`)
      if (!r.ok) throw new Error('The file is no longer in the library. Scan again.')
      const blob = await r.blob()
      const v = await validateAudioFile(new File([blob], item.path.split(/[\\/]/).pop() || 'sample.wav', { type: blob.type || '' }))
      padBank.set(targetPad, { name: v.name, buffer: v.buffer, pitch: 0, rate: 1, gain: 1, source: { kind: 'upload' } })
      onAssign?.(item, targetPad)
    } catch (e) {
      setAssignErr((e as Error).message)
    }
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
            onClick={() => setSelected(it)}
          >
            <span className={`src-dot src-${it.type}`} />
            <div className="lib-body">
              <div className="lib-title">{it.name}</div>
              <div className="lib-sub">{it.type} · {(it.size / 1024 / 1024).toFixed(1)} MB</div>
            </div>
          </div>
        ))}
      </div>

      {selected && selected.type === 'sample' && (
        <div className="lib-assign">
          <label>
            Assign to pad
            <select value={targetPad} onChange={(e) => setTargetPad(+e.target.value)}>
              {PADS.map((p, i) => <option key={i} value={i}>{i + 1} {p.name}</option>)}
            </select>
          </label>
          <button className="btn pri" onClick={() => void assign(selected)}>Load onto pad</button>
          {assignErr && <p className="nd-err" role="alert">{assignErr}</p>}
        </div>
      )}
    </section>
  )
}
