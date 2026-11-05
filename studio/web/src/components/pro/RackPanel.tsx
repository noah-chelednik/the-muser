import { useStudio } from '../../studio/StudioContext'
import { MASTER, TABS, useRack, EMPTY, type Tab } from '../../studio/RackContext'
import { ChainEditor } from './ChainEditor'
import { PresetBrowser } from './PresetBrowser'
import { isBrowserDemo } from '../../api'
import { LiveFxTab } from './LiveFxTab'
import { SamplerTab } from './SamplerTab'
import { SplitTab } from './SplitTab'
import { ABTab, GenerateTab, MasterTab, SeparateTab } from './Tabs'

/**
 * The advanced rack: Live FX, Split, Sampler, Chains, Generate, Separate, Master, Presets, A/B.
 * One implementation, styled by whichever skin hosts it. `only` lets a skin
 * render a subset and place the tab strip itself.
 */
export function RackTabs({ only }: { only?: readonly Tab[] }) {
  const { tab, setTab, busy } = useRack()
  const list = (only ?? TABS).filter((t) => !(t === 'Separate' && isBrowserDemo()))
  return (
    <div className="tabs rack-tabs" role="tablist" aria-label="Pro rack">
      {list.map((t) => (
        <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
          {t}
          {t === 'Chains' && busy ? <i className="tab-dot" /> : null}
        </button>
      ))}
    </div>
  )
}

export function RackBody({ only }: { only?: readonly Tab[] }) {
  const { current: track, tracks, toast, loadTrack } = useStudio()
  const r = useRack()
  const { chains, sel, setSel, selChain, setSelChain, setStemState, snap, busy } = r
  const tab = only && !only.includes(r.tab) ? only[0] : r.tab === 'Separate' && isBrowserDemo() ? 'Split' : r.tab
  const common = { run: r.run, onTrack: (t: typeof track & object) => loadTrack(t), toast }

  return (
    <div className="rack-body" data-tab={tab}>
      {busy && (
        <span className="busy">
          <span className="spinner" /> {busy}
        </span>
      )}
      {tab === 'Chains' && (
        <div className="pro-chains">
          <div className="pro-side">
            {(track?.stems ?? []).map((s, i) => {
              const st = chains.stems[s.id] ?? EMPTY
              return (
                <div key={s.id} className={`pro-stem ${sel === s.id ? 'on' : ''}`} onClick={() => setSel(s.id)} style={{ ['--i' as string]: i }}>
                  <span className="lane-dot" />
                  <strong>{s.name}</strong>
                  <span className="muted">{st.chain.length} fx</span>
                  <div className="pro-stem-ctl" onClick={(e) => e.stopPropagation()}>
                    <label>Gain <input className="num" type="number" step={0.5} min={-60} max={12} value={st.gain_db} onChange={(e) => setStemState(s.id, { gain_db: Number(e.target.value) })} /></label>
                    <label>Pan <input className="num" type="number" step={0.05} min={-1} max={1} value={st.pan} onChange={(e) => setStemState(s.id, { pan: Number(e.target.value) })} /></label>
                    <button className={`led-btn ${st.mute ? 'on red' : ''}`} onClick={() => setStemState(s.id, { mute: !st.mute })}>M</button>
                    <button className={`led-btn ${st.solo ? 'on' : ''}`} onClick={() => setStemState(s.id, { solo: !st.solo })}>S</button>
                  </div>
                </div>
              )
            })}
            <div className={`pro-stem master ${sel === MASTER ? 'on' : ''}`} onClick={() => setSel(MASTER)}>
              <span className="lane-dot" />
              <strong>Master bus</strong>
              <span className="muted">{chains.master.length} fx</span>
            </div>
            {!track?.stems.length && <p className="muted pad-s">No stems yet. Split the track to get per-stem chains; the master bus works on the full mix.</p>}
            <div className="pro-actions">
              <button className="btn ghost small" disabled={!snap.canUndo} onClick={snap.undo}>Undo chain</button>
              <button className="btn ghost small" disabled={!snap.canRedo} onClick={snap.redo}>Redo chain</button>
              <button className="btn pri" disabled={!track || !!busy} onClick={() => void r.render()}>Render pro mix</button>
            </div>
          </div>
          <div className="pro-main">
            <ChainEditor
              chain={selChain}
              plugins={r.plugins}
              title={sel === MASTER ? 'Master bus chain' : `${track?.stems.find((s) => s.id === sel)?.name ?? ''} chain`}
              onChange={(c) => setSelChain(c)}
            />
          </div>
        </div>
      )}
      {tab === 'Live FX' && <LiveFxTab />}
      {tab === 'Split' && <SplitTab />}
      {tab === 'Sampler' && <SamplerTab />}
      {tab === 'Generate' && <GenerateTab engines={r.engines} {...common} />}
      {tab === 'Separate' && <SeparateTab track={track} engines={r.engines} models={r.models} {...common} />}
      {tab === 'Master' && <MasterTab track={track} targets={r.targets} plugins={r.plugins} {...common} />}
      {tab === 'Presets' && (
        <PresetBrowser
          trackId={track?.id}
          stemId={sel === MASTER ? undefined : sel}
          onApply={(p) => void r.applyPreset(p)}
          applyLabel={sel === MASTER ? 'Load' : 'Load on stem'}
          toast={toast}
          currentChain={selChain}
        />
      )}
      {tab === 'A/B' && <ABTab track={track} tracks={tracks} />}
    </div>
  )
}
