import { useEffect, useRef, useState } from 'react'
import { streamChat } from '../api'
import type { ChatItem, Status, Track } from '../types'
import { Knob } from './Knob'

type Props = {
  status: Status | null
  onTrack: (t: Track, autoload: boolean) => void
  onGenerate: (args: { prompt: string; duration_s: number; bpm: number | null; key: string }) => Promise<void>
  generating: boolean
}

const QUICK = ['lo-fi hip hop, jazzy keys', 'dark trap 140 bpm', 'deep house groove', 'cinematic ambient in D minor', 'synthwave night drive']
const KEYS = ['', 'C major', 'A minor', 'D minor', 'F minor', 'G major', 'E minor', 'Bb major', 'F# minor']

function fmt(text: string) {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br/>')
}

export function Composer({ status, onTrack, onGenerate, generating }: Props) {
  const [items, setItems] = useState<ChatItem[]>([
    {
      kind: 'assistant',
      text:
        'Welcome to **NoDAW Studio PRO**. Describe the music you want - genre, mood, tempo, key, instruments - and I will compose it. ' +
        'Every result lands in the stem mixer where you can split, sculpt and export it.',
    },
  ])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [session, setSession] = useState<string | null>(null)
  const [model, setModel] = useState<string>('')
  const [duration, setDuration] = useState(20)
  const [bpm, setBpm] = useState(0)
  const [key, setKey] = useState('')
  const list = useRef<HTMLDivElement>(null)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' })
  }, [items])

  useEffect(() => {
    if (status && !model && status.llm_models.length) setModel(status.llm_models[0])
  }, [status, model])

  const send = async (text: string) => {
    const msg = text.trim()
    if (!msg || streaming) return
    setInput('')
    setStreaming(true)
    setItems((xs) => [...xs, { kind: 'user', text: msg }, { kind: 'assistant', text: '', streaming: true }])
    const ac = new AbortController()
    abort.current = ac
    const appendToken = (tok: string) =>
      setItems((xs) => {
        const out = [...xs]
        for (let i = out.length - 1; i >= 0; i--) {
          const it = out[i]
          if (it.kind === 'assistant' && it.streaming) {
            out[i] = { ...it, text: it.text + tok }
            return out
          }
        }
        return [...out, { kind: 'assistant', text: tok, streaming: true }]
      })
    try {
      await streamChat(
        { message: msg, session_id: session, model: model || null },
        ({ event, data }) => {
          if (event === 'session') setSession(data.session_id)
          else if (event === 'token') appendToken(data.text)
          else if (event === 'tool_start')
            setItems((xs) => [...xs, { kind: 'tool', name: data.name, status: 'running' }])
          else if (event === 'tool_end')
            setItems((xs) => {
              const out = [...xs]
              for (let i = out.length - 1; i >= 0; i--) {
                const it = out[i]
                if (it.kind === 'tool' && it.name === data.name && it.status === 'running') {
                  out[i] = {
                    ...it,
                    status: data.status === 'success' ? 'success' : 'error',
                    detail: data.status === 'success' ? undefined : JSON.stringify(data.result).slice(0, 220),
                  }
                  break
                }
              }
              // new assistant bubble for tokens after the tool runs
              return [...out.map((x) => (x.kind === 'assistant' ? { ...x, streaming: false } : x)), { kind: 'assistant', text: '', streaming: true }]
            })
          else if (event === 'track') {
            setItems((xs) => [...xs, { kind: 'track', track: data.track }])
            onTrack(data.track, true)
          } else if (event === 'final') {
            setItems((xs) => {
              const has = xs.some((x) => x.kind === 'assistant' && x.streaming && x.text)
              if (has || !data.text) return xs
              return [...xs, { kind: 'assistant', text: data.text }]
            })
          } else if (event === 'error') setItems((xs) => [...xs, { kind: 'error', text: data.message }])
        },
        ac.signal,
      )
    } catch (e) {
      if (!ac.signal.aborted) setItems((xs) => [...xs, { kind: 'error', text: String(e) }])
    } finally {
      setItems((xs) =>
        xs
          .map((x) => (x.kind === 'assistant' ? { ...x, streaming: false } : x))
          .filter((x) => !(x.kind === 'assistant' && !x.text)),
      )
      setStreaming(false)
    }
  }

  const mode = status?.mode ?? 'demo'
  return (
    <section className="panel composer">
      <div className="panel-head">
        <h2>Composer</h2>
        <div className="composer-meta">
          <span className={`mode-badge ${mode}`}>{mode.toUpperCase()}</span>
          {status && mode !== 'demo' && status.llm_models.length > 0 && (
            <select className="select" value={model} onChange={(e) => setModel(e.target.value)} aria-label="LLM model">
              {status.llm_models.map((m) => (
                <option key={m} value={m}>{m.replace('ollama_chat/', 'ollama · ')}</option>
              ))}
            </select>
          )}
        </div>
      </div>
      <div className="chat" ref={list}>
        {items.map((it, i) => {
          if (it.kind === 'user') return <div key={i} className="msg user">{it.text}</div>
          if (it.kind === 'assistant')
            return (
              <div key={i} className={`msg bot ${it.streaming ? 'streaming' : ''}`}>
                <span dangerouslySetInnerHTML={{ __html: fmt(it.text) }} />
                {it.streaming && <span className="caret" />}
              </div>
            )
          if (it.kind === 'tool')
            return (
              <div key={i} className={`tool-chip ${it.status}`}>
                <span className="tool-led" /> <code>{it.name}</code>
                <span className="tool-status">{it.status === 'running' ? 'running...' : it.status}</span>
                {it.detail && <div className="tool-detail">{it.detail}</div>}
              </div>
            )
          if (it.kind === 'track')
            return (
              <button key={i} className="track-card" onClick={() => onTrack(it.track, true)}>
                <span className="tc-play">▶</span>
                <span className="tc-body">
                  <strong>{it.track.title}</strong>
                  <small>{it.track.source} · {it.track.duration_s.toFixed(0)}s {it.track.key ? `· ${it.track.key}` : ''}</small>
                </span>
              </button>
            )
          return <div key={i} className="msg err">{it.text}</div>
        })}
      </div>
      <div className="quick">
        {QUICK.map((q) => (
          <button key={q} className="chip-btn" onClick={() => setInput(q)}>{q}</button>
        ))}
      </div>
      <form
        className="prompt"
        onSubmit={(e) => {
          e.preventDefault()
          void send(input)
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Compose a 2-minute lo-fi beat with jazzy piano and vinyl crackle..."
          rows={2}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send(input)
            }
          }}
          aria-label="Prompt"
        />
        {streaming ? (
          <button type="button" className="btn send" onClick={() => abort.current?.abort()}>Stop</button>
        ) : (
          <button type="submit" className="btn pri send" disabled={!input.trim()}>Send</button>
        )}
      </form>
      <div className="direct">
        <div className="direct-title">Direct generate <span className="muted">· skips the agent</span></div>
        <div className="direct-row">
          <Knob label="Length" value={duration} min={4} max={120} step={1} defaultValue={20} size={44} format={(v) => `${v.toFixed(0)}s`} onChange={setDuration} />
          <Knob label="BPM" value={bpm} min={0} max={180} step={1} defaultValue={0} size={44} format={(v) => (v < 40 ? 'auto' : v.toFixed(0))} onChange={setBpm} />
          <select className="select" value={key} onChange={(e) => setKey(e.target.value)} aria-label="Key">
            {KEYS.map((k) => <option key={k} value={k}>{k || 'Key: auto'}</option>)}
          </select>
          <button
            className="btn pri"
            disabled={generating || !input.trim()}
            onClick={() => onGenerate({ prompt: input.trim(), duration_s: duration, bpm: bpm >= 40 ? bpm : null, key })}
            title={mode === 'full' ? 'Generate with ACE-Step' : 'ACE-Step unavailable: renders a demo-synth sketch'}
          >
            {generating ? 'Generating...' : mode === 'full' ? 'Generate (ACE-Step)' : 'Generate (demo synth)'}
          </button>
        </div>
      </div>
    </section>
  )
}
