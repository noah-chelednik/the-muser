import { useState } from 'react'
import type { Status, Track } from '../types'
import { EnginesPanel } from './EnginesPanel'

export function SystemDrawer({ status, onClose, onRefresh, toast, initialTab = 'engines' }: { initialTab?: 'engines' | 'system'; status: Status | null; onClose: () => void; onRefresh: () => void; toast?: (t: string, k?: 'info' | 'error' | 'ok') => void }) {
  const [tab, setTab] = useState<'engines' | 'system'>(initialTab)
  return (
    <div className="overlay" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head">
          <h2>System</h2>
          <div>
            <button className="btn ghost small" onClick={onRefresh}>Re-check</button>
            <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
          </div>
        </div>
        <div className="tabs drawer-tabs">
          <button className={tab === 'engines' ? 'on' : ''} onClick={() => setTab('engines')}>Engines</button>
          <button className={tab === 'system' ? 'on' : ''} onClick={() => setTab('system')}>System</button>
        </div>
        {tab === 'engines' ? <EnginesPanel toast={toast} /> : !status ? (
          <p className="muted">Connecting to the Studio API...</p>
        ) : (
          <>
            <div className={`mode-card ${status.mode}`}>
              <span className={`mode-badge ${status.mode}`}>{status.mode.toUpperCase()}</span>
              <p>{status.mode_detail}</p>
              <p className="muted">Agent exposes {status.tool_count} tools.</p>
            </div>
            {Object.values(status.items).map((it) => (
              <div key={it.key} className={`sys-row ${it.available ? 'ok' : 'missing'}`}>
                <span className={`sys-led ${it.available ? 'ok' : 'warn'}`}><i /></span>
                <div>
                  <strong>{it.label}</strong>
                  <div className="sys-detail">{it.detail}</div>
                  {!it.available && it.hint && <div className="sys-hint">{it.hint}</div>}
                </div>
              </div>
            ))}
          </>
        )}
      </aside>
    </div>
  )
}

export function ExportDialog({ track, onClose, onExport }: {
  track: Track
  onClose: () => void
  onExport: (o: { formats: string[]; include_stems: boolean; normalize: boolean }) => Promise<Record<string, string> | null>
}) {
  const [formats, setFormats] = useState<string[]>(['wav', 'mp3'])
  const [stems, setStems] = useState(track.stems.length > 0)
  const [normalize, setNormalize] = useState(true)
  const [files, setFiles] = useState<Record<string, string> | null>(null)
  const [busy, setBusy] = useState(false)
  const toggle = (f: string) => setFormats((xs) => (xs.includes(f) ? xs.filter((x) => x !== f) : [...xs, f]))
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head">
          <h2>Export</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>
        <p className="muted">{track.title}</p>
        <div className="opt-row">
          {['wav', 'mp3', 'flac'].map((f) => (
            <button key={f} className={`led-btn wide ${formats.includes(f) ? 'on' : ''}`} onClick={() => toggle(f)}>{f.toUpperCase()}</button>
          ))}
        </div>
        <label className="check"><input type="checkbox" checked={normalize} onChange={(e) => setNormalize(e.target.checked)} /> Loudness normalize (-14 LUFS)</label>
        <label className="check"><input type="checkbox" checked={stems} disabled={!track.stems.length} onChange={(e) => setStems(e.target.checked)} /> Include stems (.zip)</label>
        <button
          className="btn pri full"
          disabled={busy || !formats.length}
          onClick={async () => {
            setBusy(true)
            setFiles(await onExport({ formats, include_stems: stems, normalize }))
            setBusy(false)
          }}
        >
          {busy ? 'Exporting...' : 'Export'}
        </button>
        {files && (
          <div className="downloads">
            {Object.entries(files).map(([k, url]) => (
              <a key={k} className="dl" href={url} download>⇣ {k.replace('_', ' ').toUpperCase()}</a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export type Toast = { id: number; text: string; kind: 'info' | 'error' | 'ok' }
export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>
      ))}
    </div>
  )
}
