import { useRef, useState } from 'react'
import type { Track } from '../types'

type Props = {
  tracks: Track[]
  currentId: string | null
  onSelect: (t: Track) => void
  onDelete: (t: Track) => void
  onUpload: (f: File) => void
}

export function Library({ tracks, currentId, onSelect, onDelete, onUpload }: Props) {
  const file = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  return (
    <section
      className={`panel library ${drag ? 'drag' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDrag(false)
        const f = e.dataTransfer.files?.[0]
        if (f) onUpload(f)
      }}
    >
      <div className="panel-head">
        <h2>Library</h2>
        <button className="btn ghost small" onClick={() => file.current?.click()}>+ Import audio</button>
        <input ref={file} type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = '' }} />
      </div>
      <div className="lib-list">
        {tracks.length === 0 && <div className="muted pad-s">No tracks yet. Drop an audio file here or ask the composer.</div>}
        {tracks.map((t) => (
          <div key={t.id} className={`lib-item ${t.id === currentId ? 'on' : ''}`} onClick={() => onSelect(t)}>
            <span className={`src-dot src-${t.source}`} />
            <div className="lib-body">
              <div className="lib-title">{t.title}</div>
              <div className="lib-sub">
                {t.source} · {t.duration_s.toFixed(0)}s{t.stems.length ? ` · ${t.stems.length} stems` : ''}
              </div>
            </div>
            <button className="icon-btn" title="Delete" onClick={(e) => { e.stopPropagation(); onDelete(t) }}>×</button>
          </div>
        ))}
      </div>
    </section>
  )
}
