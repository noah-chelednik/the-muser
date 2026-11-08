import { useEffect, useMemo, useRef, useState } from 'react'
import { audio } from '../../audio/engine'
import { PADS } from '../../audio/instruments'
import { keySampler } from '../../audio/keys'
import {
  assignLibrarySound, assignUserSound, deleteUserSound, filterSounds, importUserSound, LIB_BASE, LIB_TYPES,
  librarySoundBuffer, listUserSounds, loadCatalog, soundUrl, userSoundBuffer, type LibSound, type UserSound,
} from '../../audio/library'
import { padBank } from '../../audio/samples'
import { ACCEPT } from '../../audio/upload'

type Props = {
  pad: number
  setPad: (i: number) => void
  onAssigned: (pad: number) => void
  onKeys: () => void
}

const TYPE_LABEL: Record<string, string> = { kick: 'Kick', snare: 'Snare', clap: 'Clap', hat: 'Hat', 'open-hat': 'Open hat', perc: 'Perc', '808': '808', cymbal: 'Cymbal', tom: 'Tom' }
const titleCase = (g: string) => g.split('-').map((w) => (w.length <= 2 && w !== 'lo' ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1))).join(' ').replace('R B', 'R&B')

/** CC0 drum library and the user's uploads. Preview with an <audio> element, load onto any pad. */
export function SoundBrowser({ pad, setPad, onAssigned, onKeys }: Props) {
  const [all, setAll] = useState<LibSound[]>([])
  const [err, setErr] = useState('')
  const [src, setSrc] = useState<'library' | 'mine'>('library')
  const [type, setType] = useState('')
  const [genre, setGenre] = useState('')
  const [q, setQ] = useState('')
  const [mine, setMine] = useState<UserSound[]>([])
  const [playing, setPlaying] = useState('')
  const [loading, setLoading] = useState('')
  const [upErr, setUpErr] = useState('')
  const [upBusy, setUpBusy] = useState(false)
  const el = useRef<HTMLAudioElement | null>(null)
  const file = useRef<HTMLInputElement>(null)

  useEffect(() => { loadCatalog().then(setAll).catch(() => setErr('The sound library could not load. Check your connection and reopen this tab.')) }, [])
  useEffect(() => { void listUserSounds().then(setMine) }, [])
  useEffect(() => () => { el.current?.pause() }, [])

  const genres = useMemo(() => [...new Set(all.flatMap((s) => s.genres))].sort(), [all])
  const list = useMemo(() => filterSounds(all, { type, genre, q }), [all, type, genre, q])

  const preview = (id: string, url: string) => {
    audio.unlock()
    if (!el.current) {
      const a = new Audio()
      a.setAttribute('playsinline', '')
      a.preload = 'auto'
      a.onended = () => setPlaying('')
      el.current = a
    }
    const a = el.current
    if (playing === id) { a.pause(); setPlaying(''); return }
    a.src = url
    a.currentTime = 0
    setPlaying(id)
    void a.play().catch(() => setPlaying((p) => (p === id ? '' : p)))
  }
  const previewUser = (u: UserSound) => {
    // user sounds live as decoded planes: audition through Web Audio
    audio.unlock()
    const ctx = audio.ensure()
    const s = ctx.createBufferSource()
    s.buffer = userSoundBuffer(u)
    s.connect(audio.instBus)
    s.start()
  }

  const load = async (s: LibSound) => {
    audio.unlock()
    setLoading(s.id)
    try {
      await assignLibrarySound(pad, s)
      onAssigned(pad)
    } catch { setErr(`Could not load ${s.title}.`) } finally { setLoading('') }
  }
  const toKeys = async (s: LibSound) => {
    audio.unlock()
    keySampler.library = await librarySoundBuffer(s)
    keySampler.libraryName = s.title
    onKeys()
  }
  const upload = async (f: File | undefined) => {
    if (!f) return
    setUpErr(''); setUpBusy(true)
    try {
      const { sound } = await importUserSound(f)
      setMine((m) => [sound, ...m.filter((x) => x.id !== sound.id)])
      setSrc('mine')
    } catch (e) { setUpErr((e as Error).message) } finally { setUpBusy(false) }
  }

  return (
    <div className="nd-browser" data-testid="sound-browser">
      <div className="nd-br-top">
        <div className="nd-seg" role="tablist" aria-label="Sound source">
          <button role="tab" aria-selected={src === 'library'} className={src === 'library' ? 'on' : ''} onClick={() => setSrc('library')} data-testid="src-library">Library <sup>{all.length}</sup></button>
          <button role="tab" aria-selected={src === 'mine'} className={src === 'mine' ? 'on' : ''} onClick={() => setSrc('mine')} data-testid="src-mine">My uploads <sup>{mine.length}</sup></button>
        </div>
        <label className="nd-target">
          <span>Load into</span>
          <select value={pad} onChange={(e) => setPad(+e.target.value)} data-testid="target-pad">
            {PADS.map((p, i) => <option key={i} value={i}>Pad {i + 1}: {padBank.get(i)?.name ?? p.name}</option>)}
          </select>
        </label>
      </div>

      {src === 'library' ? (
        <>
          <div className="nd-chips" role="group" aria-label="Type">
            <button className={`nd-chip ${type === '' ? 'on' : ''}`} onClick={() => setType('')}>All</button>
            {LIB_TYPES.map((t) => <button key={t} className={`nd-chip ${type === t ? 'on' : ''}`} onClick={() => setType(type === t ? '' : t)} data-testid={`type-${t}`}>{TYPE_LABEL[t]}</button>)}
          </div>
          <div className="nd-br-filters">
            <select value={genre} onChange={(e) => setGenre(e.target.value)} aria-label="Genre" data-testid="genre">
              <option value="">Any genre</option>
              {genres.map((g) => <option key={g} value={g}>{titleCase(g)}</option>)}
            </select>
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search kick, rimshot, dusty" aria-label="Search sounds" data-testid="lib-search" />
          </div>
          {err && <p className="nd-err" role="alert">{err}</p>}
          <ul className="nd-list" data-testid="lib-list">
            {list.slice(0, 160).map((s) => (
              <li key={s.id} className={`nd-row ${playing === s.id ? 'playing' : ''}`}>
                <button className="nd-icon play" aria-label={`Preview ${s.title}`} onClick={() => preview(s.id, soundUrl(s))} data-testid="lib-preview">{playing === s.id ? '■' : '▶'}</button>
                <span className="nd-row-t">
                  <b>{s.title}</b>
                  <i>{TYPE_LABEL[s.type] ?? s.type} · {(s.duration_ms / 1000).toFixed(2)}s · {s.license === 'CC0-1.0' ? 'CC0' : s.license}</i>
                </span>
                <button className="nd-btn small" onClick={() => void toKeys(s)} aria-label={`Play ${s.title} on the keys`}>Keys</button>
                <button className="nd-btn small pri" onClick={() => void load(s)} disabled={loading === s.id} data-testid="lib-load">{loading === s.id ? '...' : `Pad ${pad + 1}`}</button>
              </li>
            ))}
            {!list.length && all.length > 0 && <li className="nd-muted">No sounds match. Clear a filter.</li>}
          </ul>
          <p className="nd-foot">{list.length} of {all.length} sounds. All are CC0 (public domain): free in commercial beats and apps, no credit required. <a href={`${LIB_BASE}ATTRIBUTIONS.md`} target="_blank" rel="noreferrer">Sources and credits</a></p>
        </>
      ) : (
        <>
          <div className="nd-upload">
            <button className="nd-btn pri" onClick={() => file.current?.click()} disabled={upBusy} data-testid="mine-upload-btn">{upBusy ? 'Checking file' : 'Upload a sound'}</button>
            <input ref={file} type="file" accept={ACCEPT} hidden data-testid="mine-upload" onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = '' }} />
            <span className="nd-muted">WAV, MP3, FLAC, OGG, AIFF, M4A or WebM, up to 40 MB. Files are checked and decoded in this browser and never leave it.</span>
          </div>
          {upErr && <p className="nd-err" role="alert" data-testid="upload-error">{upErr}</p>}
          <ul className="nd-list">
            {mine.map((u) => (
              <li key={u.id} className="nd-row">
                <button className="nd-icon play" aria-label={`Preview ${u.name}`} onClick={() => previewUser(u)}>▶</button>
                <span className="nd-row-t"><b>{u.name}</b><i>{u.duration.toFixed(2)}s · your upload</i></span>
                <button className="nd-icon" aria-label={`Delete ${u.name}`} onClick={() => { void deleteUserSound(u.id); setMine((m) => m.filter((x) => x.id !== u.id)) }}>✕</button>
                <button className="nd-btn small pri" onClick={() => { audio.unlock(); assignUserSound(pad, u); onAssigned(pad) }} data-testid="mine-load">Pad {pad + 1}</button>
              </li>
            ))}
            {!mine.length && <li className="nd-muted">Nothing uploaded yet.</li>}
          </ul>
        </>
      )}
    </div>
  )
}
