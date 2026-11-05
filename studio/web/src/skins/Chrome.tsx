import { useEffect, useMemo, useRef, useState } from 'react'
import { isBrowserDemo } from '../api'
import { audio } from '../audio/engine'
import { ExportDialog, SystemDrawer, Toasts } from '../components/Dialogs'
import { BRAND, UPSTREAM, UPSTREAM_URL } from '../brand'
import { useEasy } from '../studio/EasyContext'
import { isTyping, useStudio } from '../studio/StudioContext'
import { MACRO_KEYS, MACRO_META, SHORTCUTS, TOOLS } from '../studio/vibe'
import { SKINS } from './registry'
import { useSkin } from './SkinProvider'
import { SkinPopover } from './shared/SkinSwitcher'

/** Global behaviour that must survive a skin swap: shortcuts, overlays, palette, help. */
export function Chrome() {
  const studio = useStudio()
  const easy = useEasy()
  const sk = useSkin()
  const commit = useRef<number | undefined>(undefined)
  const live = useRef({ studio, easy, sk })
  live.current = { studio, easy, sk }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const { studio: st, easy: ez, sk: s } = live.current
      const mod = e.ctrlKey || e.metaKey
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        s.setPaletteOpen((v) => !v)
        return
      }
      if (e.key === 'Escape') {
        if (s.paletteOpen) s.setPaletteOpen(false)
        else if (s.nodawOpen) s.setNodawOpen(false)
        else if (s.helpOpen) s.setHelpOpen(false)
        else if (s.switcherOpen) s.setSwitcherOpen(false)
        else if (st.showExport) st.setShowExport(false)
        else if (st.showSystem) st.setShowSystem(false)
        else (e.target as HTMLElement | null)?.blur?.()
        return
      }
      if (e.altKey && !mod) {
        if (e.code === 'KeyS') { e.preventDefault(); s.cycleSkin(e.shiftKey ? -1 : 1) }
        else if (e.code === 'KeyE') { e.preventDefault(); st.setMode(st.mode === 'easy' ? 'advanced' : 'easy') }
        else if (e.code === 'KeyG') { e.preventDefault(); s.setDrawerTab('engines'); st.setShowSystem(!st.showSystem) }
        return
      }
      const t = e.target as HTMLElement
      if (isTyping()) {
        if (e.key === 'Enter' && st.mode === 'easy' && t.getAttribute?.('data-prompt') !== null) {
          e.preventDefault()
          void ez.make()
        }
        return
      }
      if (mod || e.altKey || s.paletteOpen) return
      if (e.key === '?') { s.setHelpOpen((v) => !v); return }
      if (e.key === '/') {
        const f = document.querySelector('[data-focus-target]') as HTMLElement | null
        if (f) { e.preventDefault(); f.focus() }
        return
      }
      // Single-letter keys belong to the pads and keys in Advanced, so these are Easy only.
      if (st.mode !== 'easy' || st.showSystem || st.showExport) return
      const k = e.key
      const low = k.toLowerCase()
      const nudge = (d: number) => {
        e.preventDefault()
        const key = s.selMacro
        ez.setMacro(key, Math.max(0, Math.min(100, ez.macros[key] + d)))
        window.clearTimeout(commit.current)
        commit.current = window.setTimeout(() => ez.commitMacros(), 450)
      }
      if (k === 'Enter') { e.preventDefault(); void ez.make() }
      else if (k === '[' || k === ']') {
        const list = ez.tiles
        if (!list.length) return
        const i = Math.max(0, list.findIndex((v) => v.id === ez.genreId))
        ez.selectGenre(list[(i + (k === ']' ? 1 : -1) + list.length) % list.length])
      } else if (/^[1-5]$/.test(k)) s.setSelMacro(MACRO_KEYS[Number(k) - 1])
      else if (k === 'ArrowLeft' || k === 'ArrowDown') nudge(e.shiftKey ? -10 : -1)
      else if (k === 'ArrowRight' || k === 'ArrowUp') nudge(e.shiftKey ? 10 : 1)
      else if (low === 'f') {
        const keys = Object.keys(ez.targets)
        if (keys.length) {
          const cur = ez.report?.target?.key
          void ez.finish(keys[(Math.max(-1, keys.indexOf(cur ?? '')) + 1) % keys.length])
        }
      } else if (low === 'x') void ez.doExport()
      else if (low === 't') s.cycleSkin(e.shiftKey ? -1 : 1)
      else if (low === 'z') ez.setIdx((i) => Math.max(0, Math.min(ez.versions.length - 1, i + (e.shiftKey ? 1 : -1))))
      else if (low === 'e') st.setMode('advanced')
      else if (low === 'g') { s.setDrawerTab('engines'); st.setShowSystem(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <SkinPopover />
      {sk.paletteOpen && <CommandPalette />}
      {sk.helpOpen && <HelpSheet />}
      {sk.nodawOpen && <NoDawPanel />}
      {studio.apiDown && (
        <div className="api-down" role="alert">
          Studio API unreachable. Start it with <code>start_studio.bat</code> (Windows) or <code>python -m studio.server</code>.
        </div>
      )}
      {studio.showSystem && (
        <SystemDrawer key={sk.drawerTab} initialTab={sk.drawerTab} status={studio.status} onClose={() => studio.setShowSystem(false)} onRefresh={() => void studio.refreshStatus(true)} toast={studio.toast} />
      )}
      {studio.showExport && studio.current && <ExportDialog track={studio.current} onClose={() => studio.setShowExport(false)} onExport={studio.onExport} />}
      <Toasts toasts={studio.toasts} />
    </>
  )
}

type Cmd = { id: string; group: string; label: string; hint?: string; run: () => void }

function CommandPalette() {
  const studio = useStudio()
  const easy = useEasy()
  const sk = useSkin()
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => ref.current?.focus(), [])
  const close = () => sk.setPaletteOpen(false)

  const cmds = useMemo<Cmd[]>(() => {
    const c: Cmd[] = []
    SKINS.forEach((s, i) => c.push({ id: `skin-${s.id}`, group: 'Skin', label: `Skin: ${s.name} (${s.tag})`, hint: sk.skin === s.id ? 'on' : String(i + 1), run: () => void sk.setSkin(s.id) }))
    c.push({ id: 'skin-next', group: 'Skin', label: 'Next skin', hint: 'Alt S', run: () => sk.cycleSkin() })
    c.push({ id: 'mode-easy', group: 'Mode', label: 'Easy mode', run: () => studio.setMode('easy') })
    c.push({ id: 'mode-adv', group: 'Mode', label: 'Advanced mode', hint: 'Alt E', run: () => studio.setMode('advanced') })
    c.push({ id: 'make', group: 'Make', label: 'Make It', hint: 'Enter', run: () => void easy.make() })
    c.push({ id: 'play', group: 'Play', label: audio.playing ? 'Pause' : 'Play', hint: 'Space', run: () => (audio.playing ? audio.pause() : audio.play()) })
    c.push({ id: 'stop', group: 'Play', label: 'Stop', run: () => audio.stop() })
    c.push({ id: 'undo', group: 'Edit', label: 'Undo', hint: 'Ctrl Z', run: () => studio.history.undo() })
    c.push({ id: 'redo', group: 'Edit', label: 'Redo', hint: 'Ctrl Y', run: () => studio.history.redo() })
    c.push({ id: 'engines', group: 'Open', label: 'Engines and 8 GB fit', hint: 'Alt G', run: () => { sk.setDrawerTab('engines'); studio.setShowSystem(true) } })
    c.push({ id: 'system', group: 'Open', label: 'System status', run: () => { sk.setDrawerTab('system'); studio.setShowSystem(true) } })
    c.push({ id: 'export', group: 'Open', label: studio.mode === 'easy' ? (isBrowserDemo() ? 'Export WAV and stems' : 'Export WAV and MP3') : 'Export dialog', hint: 'X', run: () => (studio.mode === 'easy' ? void easy.doExport() : studio.setShowExport(true)) })
    c.push({ id: 'nodaw', group: 'Open', label: 'NoDAW mode: v2 coming soon', hint: 'v2', run: () => sk.setNodawOpen(true) })
    c.push({ id: 'help', group: 'Open', label: 'Keyboard shortcuts', hint: '?', run: () => sk.setHelpOpen(true) })
    TOOLS.forEach((t) =>
      c.push({
        id: `tool-${t.name}`,
        group: 'Tool',
        label: t.label,
        run: () => ('reference' in t && t.reference ? easy.pickReference() : void easy.tool(t.name, t.label, 'extra' in t ? (t.extra as Record<string, unknown>) : undefined)),
      }),
    )
    Object.entries(easy.targets).forEach(([k, v]) => c.push({ id: `fin-${k}`, group: 'Finish', label: `Finish for ${v.label}`, hint: `${v.lufs} LUFS`, run: () => void easy.finish(k) }))
    MACRO_META.forEach((m, i) => c.push({ id: `macro-${m.key}`, group: 'Macro', label: `Select macro: ${m.label}`, hint: String(i + 1), run: () => sk.setSelMacro(m.key) }))
    easy.all.forEach((v) => c.push({ id: `vibe-${v.id}`, group: 'Vibe', label: v.name, run: () => easy.selectGenre(v) }))
    return c
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sk.skin, studio.mode, easy.all, easy.targets, studio.history])

  const shown = useMemo(() => {
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean)
    const list = terms.length ? cmds.filter((x) => terms.every((t) => `${x.group} ${x.label}`.toLowerCase().includes(t))) : cmds.filter((x) => x.group !== 'Vibe' && x.group !== 'Macro')
    return list.slice(0, 40)
  }, [cmds, q])
  useEffect(() => setSel(0), [q])
  useEffect(() => {
    document.querySelector('.pal li.on')?.scrollIntoView?.({ block: 'nearest' })
  }, [sel])

  const run = (c?: Cmd) => {
    if (!c) return
    close()
    window.setTimeout(c.run, 0)
  }
  return (
    <div className="pal-wrap" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="pal" role="dialog" aria-label="Command palette" data-testid="palette">
        <input
          ref={ref}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Type a command, a skin, a tool or a vibe"
          aria-label="Command palette"
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(shown.length - 1, s + 1)) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(0, s - 1)) }
            else if (e.key === 'Enter') { e.preventDefault(); run(shown[sel]) }
          }}
        />
        {shown.length ? (
          <ul role="listbox">
            {shown.map((c, i) => (
              <li key={c.id} className={i === sel ? 'on' : ''} role="option" aria-selected={i === sel}>
                <button onMouseEnter={() => setSel(i)} onClick={() => run(c)}>
                  <i>{c.group}</i>
                  <span>{c.label}</span>
                  {c.hint && <kbd>{c.hint}</kbd>}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p>No match.</p>
        )}
      </div>
    </div>
  )
}

const V2_ITEMS: [string, string][] = [
  ['Sound library', 'Kits, packs, one-shots, FX and instruments you can browse, audition and drop in.'],
  ['Pattern builder', 'Start from scratch or from templates and build patterns step by step.'],
  ['Full beat arrangement', 'Lay patterns out on a timeline and arrange a complete beat.'],
  ['Export', 'Bounce your arrangement to MP3, WAV or FLAC.'],
  ['Project import', 'Bring FL Studio .flp and REAPER .rpp projects into the NoDAW workshop.'],
]

/** Teaser only. NoDAW mode (v2) is not built yet; this panel says what is coming. */
function NoDawPanel() {
  const { setNodawOpen } = useSkin()
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => ref.current?.focus(), [])
  return (
    <div className="help-wrap" onMouseDown={(e) => e.target === e.currentTarget && setNodawOpen(false)}>
      <div className="help nodaw" role="dialog" aria-label="NoDAW mode v2 coming soon" data-testid="nodaw-panel">
        <p className="nodaw-tag">V2 · COMING SOON</p>
        <h2>NoDAW mode</h2>
        <p className="nodaw-lead">A beat workshop inside {BRAND}. It is not available yet. Here is what it will do.</p>
        <ul className="nodaw-list">
          {V2_ITEMS.map(([t, d]) => (
            <li key={t}><b>{t}</b><span>{d}</span></li>
          ))}
        </ul>
        <p className="help-foot">Nothing to install or enable. It will appear here when it ships.</p>
        <div className="nodaw-actions"><button ref={ref} className="btn pri" onClick={() => setNodawOpen(false)}>Got it</button></div>
      </div>
    </div>
  )
}

function HelpSheet() {
  const { setHelpOpen, setNodawOpen } = useSkin()
  return (
    <div className="help-wrap" onMouseDown={(e) => e.target === e.currentTarget && setHelpOpen(false)}>
      <div className="help" role="dialog" aria-label="Keyboard shortcuts" data-testid="help">
        <h2>Keyboard</h2>
        <dl>
          {SHORTCUTS.map(([k, d]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{d}</dd>
            </div>
          ))}
        </dl>
        <p className="help-about">
          <b>{BRAND}</b> is a browser studio for making, splitting, shaping and sampling music. Built on{' '}
          <a href={UPSTREAM_URL} target="_blank" rel="noreferrer">{UPSTREAM}</a> (MIT). Upstream licence and notices are unchanged.
        </p>
        <p className="help-about"><button className="btn small" onClick={() => { setHelpOpen(false); setNodawOpen(true) }}>NoDAW mode: v2 coming soon</button></p>
        <p className="help-foot">{BRAND} · built on {UPSTREAM} (MIT)</p>
      </div>
    </div>
  )
}
