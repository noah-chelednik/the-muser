import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { audio, type Region } from '../../audio/engine'
import { PADS } from '../../audio/instruments'
import {
  detectBpm, detectTransients, equalSlices, fadeBuffer, normalizeBuffer, peakOf, reverseBuffer, sliceBuffer,
} from '../../audio/sampler'
import { auditionPad, deleteKit, kitZip, listKits, loadKit, padBank, saveKit, type PadSample } from '../../audio/samples'
import { bufferToWav, download, safeName } from '../../audio/wav'
import { useStudio } from '../../studio/StudioContext'
import { DEFAULT_STEM } from '../../types'
import { Field } from './Tabs'
import { RegionWave, type Grid } from './RegionWave'

type Change = { id: string; prev: AudioBuffer; next: AudioBuffer }
type Edit = { label: string; changes: Change[] }
const ALL = '__all__'

/** Sum of every channel buffer, for display and chopping when the whole track is the source. */
function sumBuffers(bufs: AudioBuffer[]): AudioBuffer | undefined {
  if (!bufs.length) return undefined
  if (bufs.length === 1) return bufs[0]
  const len = Math.max(...bufs.map((b) => b.length))
  const out = new AudioBuffer({ numberOfChannels: 2, length: len, sampleRate: bufs[0].sampleRate })
  for (let c = 0; c < 2; c++) {
    const d = out.getChannelData(c)
    for (const b of bufs) {
      const s = b.getChannelData(Math.min(c, b.numberOfChannels - 1))
      for (let i = 0; i < s.length; i++) d[i] += s[i]
    }
  }
  return out
}

export function SamplerTab() {
  const { channels, current, buffersVersion, toast, mixer, master } = useStudio()
  const [src, setSrc] = useState<string>(ALL)
  const [region, setRegion] = useState<Region | null>(null)
  const [markers, setMarkers] = useState<number[]>([])
  const [grid, setGrid] = useState<Grid>({ bpm: 120, offset: 0, division: 1, snap: true, show: true })
  const [conf, setConf] = useState<number | null>(null)
  const [fadeIn, setFadeIn] = useState(0.02)
  const [fadeOut, setFadeOut] = useState(0.05)
  const [chop, setChop] = useState<'markers' | 'transients' | 'equal'>('transients')
  const [slices, setSlices] = useState(8)
  const [sens, setSens] = useState(0.5)
  const [padStart, setPadStart] = useState(0)
  const [selPad, setSelPad] = useState(0)
  const [looping, setLooping] = useState(false)
  const [kitName, setKitName] = useState('My kit')
  const [kits, setKits] = useState<{ name: string; created: number; pads: number }[]>([])
  const [kitPick, setKitPick] = useState('')
  const [busy, setBusy] = useState('')
  const undo = useRef<Edit[]>([])
  const redo = useRef<Edit[]>([])
  const [, tick] = useState(0)
  const bump = () => tick((x) => x + 1)
  const bank = useSyncExternalStore(padBank.subscribe, padBank.version)

  const ids = useMemo(() => channels.map((c) => c.id), [channels])
  const single = ids.length < 2
  const srcId = single ? ids[0] : src
  const targets = srcId === ALL ? ids : srcId ? [srcId] : []

  // new track: drop the edit history, the region and the markers
  useEffect(() => { undo.current = []; redo.current = []; setRegion(null); setMarkers([]); setLooping(false); audio.setRegion(null); bump() }, [current?.id])
  useEffect(() => { void listKits().then(setKits).catch(() => undefined) }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const display = useMemo(() => (srcId === ALL ? sumBuffers(ids.map((i) => audio.buffer(i)).filter(Boolean) as AudioBuffer[]) : srcId ? audio.buffer(srcId) : undefined), [srcId, ids, buffersVersion])
  const dur = display?.duration ?? 0

  const applyEdit = useCallback((label: string, fn: (b: AudioBuffer, id: string) => AudioBuffer, ts = targets) => {
    const changes: Change[] = []
    for (const id of ts) {
      const prev = audio.buffer(id)
      if (!prev) continue
      const next = fn(prev, id)
      if (next !== prev) changes.push({ id, prev, next })
    }
    if (!changes.length) return
    changes.forEach((c) => audio.setBuffer(c.id, c.next))
    undo.current.push({ label, changes })
    redo.current = []
    bump()
  }, [targets])

  const doUndo = useCallback(() => {
    const e = undo.current.pop()
    if (!e) return false
    e.changes.forEach((c) => audio.setBuffer(c.id, c.prev))
    redo.current.push(e)
    bump()
    return true
  }, [])
  const doRedo = useCallback(() => {
    const e = redo.current.pop()
    if (!e) return false
    e.changes.forEach((c) => audio.setBuffer(c.id, c.next))
    undo.current.push(e)
    bump()
    return true
  }, [])

  // While this tab is open, Ctrl/Cmd+Z walks the sampler edits first, then the mixer history.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey
      const k = e.key.toLowerCase()
      const t = e.target as HTMLElement | null
      if (!mod || (k !== 'z' && k !== 'y') || (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && (t as HTMLInputElement).type !== 'range')) return
      const did = k === 'y' || e.shiftKey ? doRedo() : doUndo()
      if (did) { e.preventDefault(); e.stopImmediatePropagation() }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [doUndo, doRedo])

  const r = region && region.end - region.start > 0.005 ? region : null
  const needRegion = (what: string) => { if (!r) { toast(`Select a region first to ${what}.`, 'info'); return false } return true }

  const crop = () => {
    if (!needRegion('crop')) return
    const reg = r!
    applyEdit('Crop', (b) => sliceBuffer(b, reg.start, reg.end), ids)
    setGrid((g) => { const beat = 60 / g.bpm; return { ...g, offset: (((g.offset - reg.start) % beat) + beat) % beat } })
    setRegion(null); setMarkers([]); audio.setRegion(null); setLooping(false)
    audio.seek(0)
  }
  const fades = () => { if (needRegion('fade')) applyEdit('Fades', (b) => fadeBuffer(b, r, fadeIn, fadeOut)) }
  const normalize = () => {
    const peak = Math.max(0, ...targets.map((id) => peakOf(audio.buffer(id)!, r)))
    applyEdit('Normalize', (b) => normalizeBuffer(b, r, -0.3, peak))
  }
  const reverse = () => applyEdit('Reverse', (b) => reverseBuffer(b, r))
  const resetAll = () => { applyEdit('Revert to original', (_b, id) => audio.original(id)!, ids); setRegion(null); setMarkers([]) }

  const toggleLoop = () => {
    if (!r) { toast('Select a region to loop.', 'info'); return }
    if (looping) { audio.setRegion(null); setLooping(false); return }
    audio.setRegion(r); audio.setLoop(true); audio.seek(r.start); audio.play(); setLooping(true)
  }
  useEffect(() => { if (looping) audio.setRegion(r) }, [r?.start, r?.end]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { audio.setRegion(null) }, [])

  const detect = () => {
    if (!display) return
    setBusy('Detecting tempo...')
    window.setTimeout(() => {
      const d = detectBpm(r ? sliceBuffer(display, r.start, r.end) : display)
      const off = r ? (((d.offset + r.start) % (60 / d.bpm)) + 60 / d.bpm) % (60 / d.bpm) : d.offset
      setGrid((g) => ({ ...g, bpm: d.bpm, offset: off }))
      setConf(d.confidence)
      setBusy('')
      toast(`Detected ${d.bpm} BPM`, 'ok')
    }, 20)
  }

  // ---- sample source for pads and exports
  const sampleOf = async (a: number, b: number, fx: boolean): Promise<AudioBuffer | null> => {
    if (fx && (srcId === ALL || single)) return audio.bounce({ mixer: { ...mixer, [ids[0]]: mixer[ids[0]] ?? DEFAULT_STEM }, masterGainDb: master.gain_db, limiter: master.limiter !== false, range: { start: a, end: b }, tail: 0 })
    return display ? sliceBuffer(display, a, b) : null
  }
  const boundaries = (): [number, number][] => {
    if (!display) return []
    const a = r?.start ?? 0, b = r?.end ?? dur
    let pts: number[]
    if (chop === 'equal') pts = equalSlices(a, b, slices)
    else if (chop === 'transients') pts = [a, ...detectTransients(sliceBuffer(display, a, b), sens).map((t) => t + a).filter((t) => t > a + 0.03)]
    else pts = [a, ...markers.filter((m) => m > a && m < b).sort((x, y) => x - y)]
    pts = pts.slice(0, 16 - padStart)
    return pts.map((p, i) => [p, i + 1 < pts.length ? pts[i + 1] : b] as [number, number]).filter(([x, y]) => y - x > 0.01)
  }

  const putPad = (i: number, buf: AudioBuffer, name: string) => {
    const click = fadeBuffer(buf, null, 0.002, 0.008)
    const prev = padBank.get(i)
    padBank.set(i, { name, buffer: click, pitch: prev?.pitch ?? 0, rate: prev?.rate ?? 1, gain: prev?.gain ?? 1 })
  }
  const sendRegion = async () => {
    if (!needRegion('send to a pad')) return
    setBusy('Sending to pad...')
    try {
      const b = await sampleOf(r!.start, r!.end, true)
      if (b) { putPad(selPad, b, `${PADS[selPad].name} ${r!.start.toFixed(1)}s`); toast(`Region on pad ${selPad + 1}`, 'ok'); auditionPad(selPad) }
    } finally { setBusy('') }
  }
  const doChop = async () => {
    const bs = boundaries()
    if (!bs.length) { toast(chop === 'markers' ? 'Add markers inside the region first.' : 'No slices found. Raise the sensitivity or pick equal slices.', 'info'); return }
    setBusy('Chopping...')
    try {
      for (let i = 0; i < bs.length; i++) {
        const b = await sampleOf(bs[i][0], bs[i][1], true)
        if (b) putPad(padStart + i, b, `Slice ${i + 1}`)
      }
      setMarkers(bs.map((x) => x[0]).slice(1))
      setSelPad(padStart)
      toast(`${bs.length} slices on pads ${padStart + 1} to ${padStart + bs.length}`, 'ok')
    } finally { setBusy('') }
  }
  const addMarker = () => {
    const t = audio.currentTime()
    const g = grid
    setMarkers((m) => [...m, g.snap ? Math.max(0, Math.round((t - g.offset) / (60 / g.bpm / g.division)) * (60 / g.bpm / g.division) + g.offset) : t].sort((a, b) => a - b))
  }

  const pad = bank && padBank.get(selPad)
  const upd = (patch: Partial<PadSample>) => padBank.update(selPad, patch)

  const exportRegion = async () => {
    const a = r?.start ?? 0, b = r?.end ?? dur
    const buf = await sampleOf(a, b, false)
    if (buf) download(bufferToWav(buf, 24), `${safeName(current?.title ?? 'sample')}_${a.toFixed(2)}-${b.toFixed(2)}.wav`)
  }

  const refreshKits = () => void listKits().then(setKits)
  const save = async () => {
    try { const n = await saveKit(kitName.trim() || 'My kit'); toast(`Saved kit with ${n} sample${n === 1 ? '' : 's'}`, 'ok'); refreshKits() } catch (e) { toast(`Could not save: ${(e as Error).message}`, 'error') }
  }

  if (!channels.length) return <p className="muted pad-s">Load, generate or import a track first. The sampler cuts regions out of it and puts them on the pads.</p>

  return (
    <div className="pro-form sampler" data-testid="sampler">
      <div className="field-row">
        {!single && (
          <Field label="Source">
            <select className="select" value={srcId} onChange={(e) => { setSrc(e.target.value); setRegion(null); setMarkers([]) }} data-testid="sampler-src">
              <option value={ALL}>Whole track (all stems)</option>
              {channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        )}
        <div className="field"><span>History</span>
          <div className="btn-row">
            <button className="btn small" disabled={!undo.current.length} onClick={doUndo} data-testid="sampler-undo">Undo{undo.current.length ? ` (${undo.current[undo.current.length - 1].label})` : ''}</button>
            <button className="btn small" disabled={!redo.current.length} onClick={doRedo}>Redo</button>
            <button className="btn small ghost" disabled={!undo.current.length} onClick={resetAll}>Revert all</button>
          </div>
        </div>
        {busy && <span className="busy"><span className="spinner" /> {busy}</span>}
      </div>

      <RegionWave buffer={display} region={r} onRegion={setRegion} markers={markers} grid={grid} height={150} onSeek={(t) => audio.seek(t)} />

      <fieldset className="sp-group"><legend>Edit region</legend>
        <div className="btn-row">
          <button className="btn small" disabled={!r} onClick={crop} data-testid="crop">Crop to region</button>
          <button className="btn small" disabled={!r} onClick={fades} data-testid="fades">Apply fades</button>
          <button className="btn small" onClick={normalize} data-testid="normalize">Normalize</button>
          <button className="btn small" onClick={reverse} data-testid="reverse">Reverse</button>
          <button className={`btn small ${looping ? 'pri' : ''}`} disabled={!r} onClick={toggleLoop} data-testid="loop-region">{looping ? 'Looping' : 'Loop region'}</button>
        </div>
        <div className="field-row">
          <label className="sp-range">Fade in <input type="range" min={0} max={2} step={0.005} value={fadeIn} onChange={(e) => setFadeIn(+e.target.value)} /><em>{Math.round(fadeIn * 1000)} ms</em></label>
          <label className="sp-range">Fade out <input type="range" min={0} max={2} step={0.005} value={fadeOut} onChange={(e) => setFadeOut(+e.target.value)} /><em>{Math.round(fadeOut * 1000)} ms</em></label>
        </div>
        {srcId !== ALL && !single ? <p className="muted sp-note">Crop always cuts every stem so they stay in sync. Other edits touch only {channels.find((c) => c.id === srcId)?.name}.</p> : null}
      </fieldset>

      <fieldset className="sp-group"><legend>Tempo and grid</legend>
        <div className="field-row">
          <Field label="BPM"><input className="num" type="number" min={40} max={240} step={0.1} value={grid.bpm} onChange={(e) => setGrid({ ...grid, bpm: Math.max(40, Number(e.target.value) || 120) })} data-testid="bpm" /></Field>
          <button className="btn small" onClick={detect} data-testid="detect-bpm">Detect BPM</button>
          {conf !== null && <span className="muted">confidence {Math.round(conf * 100)}%</span>}
          <Field label="Grid"><select className="select" value={grid.division} onChange={(e) => setGrid({ ...grid, division: Number(e.target.value) })}><option value={0.25}>1 bar</option><option value={1}>1/4</option><option value={2}>1/8</option><option value={4}>1/16</option></select></Field>
          <label className="sp-check"><input type="checkbox" checked={grid.snap} onChange={(e) => setGrid({ ...grid, snap: e.target.checked })} /> Snap</label>
          <label className="sp-check"><input type="checkbox" checked={grid.show} onChange={(e) => setGrid({ ...grid, show: e.target.checked })} /> Show</label>
          <button className="btn small ghost" onClick={() => setGrid({ ...grid, offset: audio.currentTime() })}>Grid starts at playhead</button>
        </div>
      </fieldset>

      <fieldset className="sp-group"><legend>Send to pads</legend>
        <div className="sp-pads" role="group" aria-label="Pad targets">
          {PADS.map((p, i) => {
            const s = padBank.get(i)
            return (
              <button key={p.name} className={`sp-pad ${selPad === i ? 'sel' : ''} ${s ? 'has' : ''}`} onClick={() => { setSelPad(i); if (s) auditionPad(i) }} data-testid={`sp-pad-${i}`} aria-label={`Pad ${i + 1}: ${s?.name ?? p.name}`}>
                <b>{i + 1}</b><span>{s ? s.name : p.name}</span>
              </button>
            )
          })}
        </div>
        <div className="btn-row">
          <button className="btn small pri" disabled={!r} onClick={() => void sendRegion()} data-testid="send-region">Send region to pad {selPad + 1}</button>
          <button className="btn small" onClick={addMarker}>Add marker at playhead</button>
          <button className="btn small ghost" disabled={!markers.length} onClick={() => setMarkers([])}>Clear markers ({markers.length})</button>
        </div>
        <div className="field-row">
          <Field label="Chop mode">
            <select className="select" value={chop} onChange={(e) => setChop(e.target.value as typeof chop)} data-testid="chop-mode">
              <option value="transients">Auto: by transients</option>
              <option value="equal">Equal slices</option>
              <option value="markers">Manual: at my markers</option>
            </select>
          </Field>
          {chop === 'equal' && <Field label="Slices"><select className="select" value={slices} onChange={(e) => setSlices(+e.target.value)}>{[2, 4, 8, 16].map((n) => <option key={n}>{n}</option>)}</select></Field>}
          {chop === 'transients' && <label className="sp-range">Sensitivity <input type="range" min={0} max={1} step={0.05} value={sens} onChange={(e) => setSens(+e.target.value)} /><em>{Math.round(sens * 100)}%</em></label>}
          <Field label="Start at pad"><select className="select" value={padStart} onChange={(e) => setPadStart(+e.target.value)}>{PADS.map((_, i) => <option key={i} value={i}>{i + 1}</option>)}</select></Field>
          <button className="btn small pri" onClick={() => void doChop()} data-testid="chop">Chop onto pads</button>
        </div>
      </fieldset>

      <fieldset className="sp-group"><legend>Pad {selPad + 1}{pad ? `: ${pad.name}` : ' (synth drum)'}</legend>
        {pad ? (
          <>
            <div className="field-row">
              <label className="sp-range">Pitch <input type="range" min={-12} max={12} step={1} value={pad.pitch} onChange={(e) => upd({ pitch: +e.target.value })} data-testid="pad-pitch" /><em>{pad.pitch > 0 ? '+' : ''}{pad.pitch} st</em></label>
              <label className="sp-range">Rate <input type="range" min={0.25} max={2} step={0.01} value={pad.rate} onChange={(e) => upd({ rate: +e.target.value })} data-testid="pad-rate" /><em>{pad.rate.toFixed(2)}x</em></label>
              <label className="sp-range">Level <input type="range" min={0} max={1.5} step={0.01} value={pad.gain} onChange={(e) => upd({ gain: +e.target.value })} /><em>{Math.round(pad.gain * 100)}%</em></label>
            </div>
            <p className="muted sp-note">Pitch and rate both repitch like a tape sampler (no time stretch), so they multiply.</p>
            <div className="btn-row">
              <button className="btn small" onClick={() => auditionPad(selPad)}>Play pad</button>
              <button className="btn small" onClick={() => download(bufferToWav(pad.buffer, 24), `pad${selPad + 1}_${safeName(pad.name)}.wav`)}>Export pad WAV</button>
              <button className="btn small ghost" onClick={() => padBank.set(selPad, null)}>Clear pad</button>
            </div>
          </>
        ) : <p className="muted sp-note">Select a region and press Send, or chop. This pad plays its synthesized drum until then.</p>}
      </fieldset>

      <fieldset className="sp-group"><legend>Kits and export</legend>
        <div className="field-row">
          <Field label="Kit name"><input className="num wide" value={kitName} onChange={(e) => setKitName(e.target.value)} /></Field>
          <button className="btn small" onClick={() => void save()} data-testid="save-kit">Save kit</button>
          <button className="btn small" onClick={() => void kitZip(kitName).then((b) => download(b, `${safeName(kitName)}_kit.zip`))}>Export kit (zip of WAVs)</button>
        </div>
        <div className="field-row">
          <Field label="Saved kits">
            <select className="select" value={kitPick} onChange={(e) => setKitPick(e.target.value)} data-testid="kit-pick">
              <option value="">{kits.length ? 'Choose a kit' : 'No saved kits yet'}</option>
              {kits.map((k) => <option key={k.name} value={k.name}>{k.name} ({k.pads})</option>)}
            </select>
          </Field>
          <button className="btn small" disabled={!kitPick} onClick={() => void loadKit(kitPick).then((n) => toast(`Loaded ${n} samples`, 'ok'))}>Load</button>
          <button className="btn small ghost" disabled={!kitPick} onClick={() => void deleteKit(kitPick).then(() => { setKitPick(''); refreshKits() })}>Delete</button>
          <button className="btn small" onClick={() => void exportRegion()} data-testid="export-region">Export {r ? 'region' : 'whole source'} as WAV</button>
        </div>
      </fieldset>
    </div>
  )
}
