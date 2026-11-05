import { useCallback, useEffect, useRef, useState } from 'react'
import { api, waitJob } from '../../api'
import type { FxItem, Preset } from '../../types'

type Props = {
  trackId?: string
  stemId?: string
  onApply: (p: Preset) => void
  applyLabel: string
  toast: (t: string, k?: 'info' | 'error' | 'ok') => void
  currentChain?: FxItem[]
  saveCategory?: 'mix' | 'vocal' | 'fx'
}

const CAT_ORDER = ['genre', 'mix', 'vocal', 'fx', 'master']

/** Browse, search, favorite, preview, save, import and export presets. */
export function PresetBrowser({ trackId, stemId, onApply, applyLabel, toast, currentChain, saveCategory = 'mix' }: Props) {
  const [q, setQ] = useState('')
  const [cat, setCat] = useState<string>('')
  const [favOnly, setFavOnly] = useState(false)
  const [items, setItems] = useState<Preset[]>([])
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<{ id: string; url: string; dry: string } | null>(null)
  const [previewing, setPreviewing] = useState('')
  const [wet, setWet] = useState(true)
  const [saveName, setSaveName] = useState('')
  const file = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const r = await api.presets({ category: cat || undefined, q: q || undefined, favorites: favOnly })
      setItems(r.presets)
      setCounts(r.counts)
      setLabels(r.categories)
    } catch (e) {
      toast((e as Error).message, 'error')
    }
  }, [cat, q, favOnly, toast])
  useEffect(() => {
    const t = window.setTimeout(() => void load(), 150)
    return () => window.clearTimeout(t)
  }, [load])

  const total = Object.values(counts).reduce((a, b) => a + b, 0)

  const doPreview = async (p: Preset) => {
    setPreviewing(p.id)
    try {
      const { job_id } = await api.previewPreset({ preset_id: p.id, track_id: trackId, stem_id: stemId })
      const r = await waitJob<{ url: string; dry_url: string }>(job_id)
      setPreview({ id: p.id, url: r.url, dry: r.dry_url })
      setWet(true)
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setPreviewing('')
    }
  }

  return (
    <div className="presets">
      <div className="preset-bar">
        <input className="search" placeholder={`Search ${total} presets: warm, 808, vocal, club...`} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search presets" />
        <button className={`led-btn ${favOnly ? 'on' : ''}`} onClick={() => setFavOnly((v) => !v)} title="Favorites only">★</button>
        <button className="btn ghost small" onClick={() => file.current?.click()}>Import</button>
        <a className="btn ghost small" href={api.exportPresetsUrl()} download="muser-presets.json">Export mine</a>
        <input ref={file} type="file" accept="application/json,.json" hidden onChange={async (e) => {
          const f = e.target.files?.[0]
          e.target.value = ''
          if (!f) return
          try {
            const r = await api.importPresets(f)
            toast(`Imported ${r.imported.length} preset(s).`, 'ok')
            void load()
          } catch (err) {
            toast((err as Error).message, 'error')
          }
        }} />
      </div>
      <div className="tabs preset-cats">
        <button className={!cat ? 'on' : ''} onClick={() => setCat('')}>All <small>{total}</small></button>
        {CAT_ORDER.map((c) => (
          <button key={c} className={cat === c ? 'on' : ''} onClick={() => setCat(c)}>{labels[c] ?? c} <small>{counts[c] ?? 0}</small></button>
        ))}
      </div>
      {preview && (
        <div className="preview-bar">
          <span className="muted">Preview of {items.find((p) => p.id === preview.id)?.name ?? preview.id} (level matched)</span>
          <button className={`led-btn ${wet ? 'on' : ''}`} onClick={() => setWet((w) => !w)}>{wet ? 'WITH PRESET' : 'ORIGINAL'}</button>
          <audio key={wet ? preview.url : preview.dry} src={wet ? preview.url : preview.dry} controls autoPlay />
        </div>
      )}
      <div className="preset-list">
        {items.length === 0 && <div className="muted pad-s">No presets match.</div>}
        {items.map((p) => (
          <div key={p.id} className="preset-row">
            <button className={`star ${p.favorite ? 'on' : ''}`} aria-label={p.favorite ? 'Unfavorite' : 'Favorite'} onClick={async () => { await api.favoritePreset(p.id); void load() }}>★</button>
            <div className="preset-body">
              <div className="preset-name">{p.name} {p.user && <span className="tag user">mine</span>}</div>
              <div className="preset-sub">{p.category}{p.subcategory ? ` · ${p.subcategory}` : ''}{p.role ? ` · ${p.role}` : ''} · {p.description}</div>
              <div className="preset-tags">{p.tags.slice(0, 5).map((t) => <span key={t} className="tag">{t}</span>)}</div>
            </div>
            <div className="preset-actions">
              <button className="btn ghost small" disabled={previewing === p.id} onClick={() => void doPreview(p)}>{previewing === p.id ? '...' : 'Preview'}</button>
              <button className="btn pri small" onClick={() => onApply(p)}>{applyLabel}</button>
              {p.user && <button className="icon-btn" aria-label="Delete preset" onClick={async () => { await api.deletePreset(p.id); void load() }}>×</button>}
            </div>
          </div>
        ))}
      </div>
      {currentChain && (
        <div className="preset-save">
          <input placeholder="Save the current chain as..." value={saveName} onChange={(e) => setSaveName(e.target.value)} aria-label="Preset name" />
          <button className="btn ghost small" disabled={!saveName.trim()} onClick={async () => {
            try {
              const r = await api.savePreset({ name: saveName, category: saveCategory, chain: currentChain, tags: ['mine'], description: 'Saved from Advanced mode.' })
              toast(`Saved preset ${r.preset.name}.`, 'ok')
              setSaveName('')
              void load()
            } catch (e) {
              toast((e as Error).message, 'error')
            }
          }}>Save preset</button>
        </div>
      )}
    </div>
  )
}
