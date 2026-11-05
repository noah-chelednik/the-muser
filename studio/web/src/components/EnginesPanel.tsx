import { useCallback, useEffect, useState } from 'react'
import { api, waitJob } from '../api'
import type { EngineInfo, EnginePick, Hardware } from '../types'

const COMM: Record<string, [string, string]> = {
  yes: ['ok', 'Commercial OK'],
  conditional: ['warn', 'Commercial: conditions'],
  no: ['bad', 'Personal use only'],
}

const FIT: Record<string, string> = { cpu: 'ok', fits: 'ok', 'fits-reduced': 'ok', tight: 'warn', 'too-big': 'bad', 'no-gpu': 'bad' }

function vramText(min: number, full?: number, cpu?: boolean): string {
  if (!min) return cpu ? 'CPU OK' : 'GPU'
  return full && full > min ? `${min} to ${full} GB VRAM` : `${min} GB VRAM`
}

/** Engines and hardware: what is installed, what fits this machine, one-click installs. */
export function EnginesPanel({ toast }: { toast?: (t: string, k?: 'info' | 'error' | 'ok') => void }) {
  const [hw, setHw] = useState<Hardware | null>(null)
  const [engines, setEngines] = useState<EngineInfo[]>([])
  const [tasks, setTasks] = useState<Record<string, string>>({})
  const [picks, setPicks] = useState<Record<string, EnginePick>>({})
  const [installing, setInstalling] = useState<Record<string, string>>({})
  const [showAll, setShowAll] = useState(false)
  const [err, setErr] = useState('')

  const load = useCallback(async (refresh = false) => {
    try {
      const [h, e] = await Promise.all([api.hardware(refresh), api.engines()])
      setHw(h)
      setEngines(e.engines)
      setTasks(e.tasks)
      setPicks(e.selected)
      setErr('')
    } catch (x) {
      setErr((x as Error).message)
    }
  }, [])
  useEffect(() => void load(), [load])

  const install = async (e: EngineInfo) => {
    setInstalling((m) => ({ ...m, [e.key]: 'Starting...' }))
    try {
      const { job_id } = await api.installEngine(e.key)
      const r = await waitJob<{ installed: boolean }>(job_id, (m) => setInstalling((x) => ({ ...x, [e.key]: m })))
      toast?.(r.installed ? `${e.name} is installed.` : `${e.name} finished installing but did not pass its check yet. See the details below.`, r.installed ? 'ok' : 'info')
    } catch (x) {
      toast?.((x as Error).message, 'error')
    } finally {
      setInstalling((m) => {
        const n = { ...m }
        delete n[e.key]
        return n
      })
      void load(true)
    }
  }

  if (err) return <p className="sys-hint">Engines unavailable: {err}</p>
  if (!hw) return <p className="muted">Checking your hardware...</p>
  const visible = showAll ? engines : engines.filter((e) => e.tier !== 'heavy' || e.health.installed)

  return (
    <div className="engines">
      <div className="hw-card">
        <div><span className="muted">GPU</span><strong>{hw.hardware.gpu || 'None detected'}{hw.hardware.vram_gb ? ` · ${hw.hardware.vram_gb} GB` : ''}</strong></div>
        <div><span className="muted">RAM</span><strong>{hw.hardware.ram_gb} GB</strong></div>
        <div><span className="muted">CPU</span><strong>{hw.hardware.cpu_count} threads</strong></div>
        <div><span className="muted">Tier</span><strong className="hot-text">{hw.tier}</strong></div>
      </div>
      {hw.hardware.vram_gb > 0 && (
        <div className="fit-card">
          <h3 className="eng-h">On your {hw.hardware.vram_gb} GB card</h3>
          <div className="fit-list">
            {hw.recommendations.map((r) => (
              <div key={r.key} className={`fit-item ${FIT[r.status] ?? 'bad'}`} title={[r.reason, r.caveat].filter(Boolean).join(' ')}>
                <span className={`lic ${FIT[r.status] ?? 'bad'}`}>{r.status === 'fits' || r.status === 'fits-reduced' ? 'Fits' : r.status === 'tight' ? 'Tight' : r.status === 'cpu' ? 'CPU' : 'Not recommended'}</span>
                <strong>{r.name}</strong>
                <em className="muted">{vramText(r.min_vram_gb, r.vram_full_gb)}{r.profile && r.status === 'fits-reduced' ? ` · ${r.profile.label} settings` : ''}</em>
              </div>
            ))}
          </div>
          {hw.hardware.notes.length > 0 && <div className="sys-detail">{hw.hardware.notes.join(' ')}</div>}
        </div>
      )}
      <h3 className="eng-h">Picked for you</h3>
      <div className="picks">
        {Object.entries(picks).filter(([t]) => ['generate', 'separate', 'denoise', 'match', 'midi', 'master'].includes(t)).map(([t, p]) => (
          <div key={t} className="pick">
            <span className="muted">{tasks[t] ?? t}</span>
            <strong>{p.name ?? 'Not available'}</strong>
            {p.upgrades[0] && <em className="muted">Upgrade: {p.upgrades[0].name}</em>}
          </div>
        ))}
      </div>
      <h3 className="eng-h">
        Engines
        <button className="link" onClick={() => setShowAll((v) => !v)}>{showAll ? 'Hide heavy GPU models' : 'Show heavy GPU models'}</button>
      </h3>
      {visible.map((e) => {
        const [cls, label] = COMM[e.commercial] ?? COMM.conditional
        const busy = installing[e.key]
        return (
          <div key={e.key} className={`eng-row ${e.health.installed ? 'ok' : 'missing'}`}>
            <span className={`sys-led ${e.health.installed ? 'ok' : e.fits ? 'warn' : 'off'}`}><i /></span>
            <div className="eng-body">
              <div className="eng-title">
                <strong>{e.name}</strong>
                <span className={`lic ${cls}`} title={e.commercial_note}>{label}</span>
                {e.untested_here && <span className="lic warn" title="Adapter written against the official docs; not run on this build machine.">Untested here</span>}
                {e.verified === 'working' && <span className="lic ok">Verified</span>}
                {e.archived && <span className="lic">Archived</span>}
                {e.fit && e.tier === 'heavy' && <span className={`lic ${FIT[e.fit.status] ?? 'bad'}`} title={e.fit.reason}>{e.fit.label}</span>}
              </div>
              <div className="sys-detail">{e.summary}</div>
              <div className="eng-meta">
                {e.weights_license}{e.code_license && e.code_license !== e.weights_license ? ` (code ${e.code_license})` : ''} · {vramText(e.min_vram_gb, e.vram_full_gb, e.cpu_ok)} · {e.tasks.join(', ')}
                {e.install.download_gb ? ` · ${e.install.download_gb} GB download` : ''}
              </div>
              {!e.health.installed && <div className="sys-detail">{e.health.detail}</div>}
              {e.tier === 'heavy' && e.fit && (e.fit.status === 'fits-reduced' || e.fit.status === 'tight') && <div className="sys-detail">Your card: {e.fit.reason}</div>}
              {(!e.fits || e.fit?.status === 'too-big') && <div className="sys-hint">Not recommended for your card: {e.fit_reason}</div>}
              {e.tier === 'heavy' && e.fit?.caveat && <div className="sys-detail">{e.fit.caveat}</div>}
              {busy && <div className="sys-detail"><span className="spinner" /> {busy}</div>}
            </div>
            {!e.health.installed && e.install.kind !== 'builtin' && (
              <button className="btn ghost small" disabled={!!busy} onClick={() => void install(e)}>{busy ? 'Installing' : e.fit && !e.fit.recommended && e.tier === 'heavy' ? 'Install anyway' : 'Install'}</button>
            )}
          </div>
        )
      })}
    </div>
  )
}
