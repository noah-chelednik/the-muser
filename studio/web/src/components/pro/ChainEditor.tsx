import { useState } from 'react'
import type { FxItem, PluginSpec } from '../../types'

type Props = {
  chain: FxItem[]
  plugins: Record<string, PluginSpec>
  onChange: (chain: FxItem[], label: string) => void
  title?: string
}

const fmt = (v: number, step?: number) => (Math.abs(v) >= 100 || step === 1 ? v.toFixed(0) : v.toFixed(2))

export function defaults(plugins: Record<string, PluginSpec>, type: string): FxItem {
  const p = plugins[type]
  return { type, params: Object.fromEntries(Object.entries(p?.params ?? {}).map(([k, v]) => [k, v.default])), bypass: false }
}

/** Every parameter of every plugin, exposed. Dense on purpose: this is Advanced mode. */
export function ChainEditor({ chain, plugins, onChange, title }: Props) {
  const [add, setAdd] = useState('compressor')
  const set = (i: number, item: FxItem, label: string) => onChange(chain.map((c, j) => (j === i ? item : c)), label)
  const move = (i: number, d: number) => {
    const j = i + d
    if (j < 0 || j >= chain.length) return
    const next = [...chain]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next, 'Reorder')
  }
  return (
    <div className="chain">
      <div className="chain-head">
        {title && <strong>{title}</strong>}
        <span className="muted">{chain.length} plugin{chain.length === 1 ? '' : 's'}</span>
        <div className="chain-add">
          <select className="select" value={add} onChange={(e) => setAdd(e.target.value)} aria-label="Plugin to add">
            {Object.entries(plugins).map(([k, p]) => (
              <option key={k} value={k}>{p.label}</option>
            ))}
          </select>
          <button className="btn ghost small" onClick={() => onChange([...chain, defaults(plugins, add)], `Add ${plugins[add]?.label}`)}>Add</button>
          {chain.length > 0 && <button className="btn ghost small" onClick={() => onChange([], 'Clear chain')}>Clear</button>}
        </div>
      </div>
      {chain.length === 0 && <div className="muted pad-s">Empty chain: the signal passes through untouched.</div>}
      {chain.map((item, i) => {
        const spec = plugins[item.type]
        return (
          <div key={i} className={`fx ${item.bypass ? 'bypassed' : ''}`}>
            <div className="fx-head">
              <button className={`led-btn ${item.bypass ? '' : 'on'}`} onClick={() => set(i, { ...item, bypass: !item.bypass }, `${item.bypass ? 'Enable' : 'Bypass'} ${spec?.label}`)} title="Bypass">
                {item.bypass ? 'OFF' : 'ON'}
              </button>
              <strong>{spec?.label ?? item.type}</strong>
              <span className="fx-group">{spec?.group}</span>
              <div className="fx-actions">
                <button className="icon-btn" onClick={() => move(i, -1)} aria-label="Move up">↑</button>
                <button className="icon-btn" onClick={() => move(i, 1)} aria-label="Move down">↓</button>
                <button className="icon-btn" onClick={() => set(i, defaults(plugins, item.type), 'Reset plugin')} aria-label="Reset" title="Reset to defaults">⟲</button>
                <button className="icon-btn" onClick={() => onChange(chain.filter((_, j) => j !== i), `Remove ${spec?.label}`)} aria-label="Remove">×</button>
              </div>
            </div>
            <div className="fx-params">
              {Object.entries(spec?.params ?? {}).map(([k, p]) => {
                const v = item.params[k] ?? p.default
                const step = p.step ?? (p.max - p.min > 100 ? 1 : (p.max - p.min) / 200)
                return (
                  <label key={k} className="fx-param">
                    <span>{p.label ?? k}</span>
                    <input type="range" min={p.min} max={p.max} step={step} value={v} aria-label={`${spec?.label} ${p.label ?? k}`}
                      onChange={(e) => set(i, { ...item, params: { ...item.params, [k]: Number(e.target.value) } }, `${spec?.label} ${p.label ?? k}`)} />
                    <input className="num" type="number" min={p.min} max={p.max} step={step} value={Number(fmt(v, p.step))}
                      onChange={(e) => {
                        const n = Math.min(p.max, Math.max(p.min, Number(e.target.value)))
                        if (Number.isFinite(n)) set(i, { ...item, params: { ...item.params, [k]: n } }, `${spec?.label} ${p.label ?? k}`)
                      }} />
                    <em>{p.unit ?? ''}</em>
                  </label>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
