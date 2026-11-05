// FX chain renderer for the browser demo. Same plugin names and parameters as the server.
import type { FxItem, PluginSpec } from '../types'
import plugins from './fixtures/plugins.json'
import * as D from './dsp'

const specs = plugins as unknown as Record<string, PluginSpec>

/** Fill defaults and clamp to range, like the server's normalize_chain. */
export function normalizeChain(chain: FxItem[] | null | undefined): FxItem[] {
  const out: FxItem[] = []
  for (const it of chain ?? []) {
    const spec = specs[it.type]
    if (!spec) continue
    const params: Record<string, number> = {}
    for (const [k, p] of Object.entries(spec.params)) {
      const v = Number(it.params?.[k] ?? p.default)
      params[k] = Math.min(Math.max(Number.isFinite(v) ? v : p.default, p.min), p.max)
    }
    out.push({ type: it.type, params, bypass: !!it.bypass })
  }
  return out
}

export function applyItem(a: D.Audio, it: FxItem): D.Audio {
  const p = it.params
  switch (it.type) {
    case 'gain': return D.scale(a, D.db2lin(p.gain_db))
    case 'highpass': return D.biquad(D.biquad(a, 'highpass', p.cutoff_hz), 'highpass', p.cutoff_hz)
    case 'lowpass': return D.biquad(D.biquad(a, 'lowpass', p.cutoff_hz), 'lowpass', p.cutoff_hz)
    case 'lowshelf': return D.biquad(a, 'lowshelf', p.cutoff_hz, p.q, p.gain_db)
    case 'highshelf': return D.biquad(a, 'highshelf', p.cutoff_hz, p.q, p.gain_db)
    case 'peak': return D.biquad(a, 'peak', p.freq_hz, p.q, p.gain_db)
    case 'compressor': return D.compress(a, p.threshold_db, p.ratio, p.attack_ms, p.release_ms, p.makeup_db)
    case 'gate': return D.gate(a, p.threshold_db, p.ratio, p.attack_ms, p.release_ms)
    case 'deesser': return D.deess(a, p.frequency_hz, p.threshold_db, p.ratio)
    case 'saturation': return D.saturate(a, p.drive_db, p.mix)
    case 'bitcrush': return D.bitcrush(a, p.bit_depth, p.mix)
    case 'chorus': return D.chorus(a, p.rate_hz, p.depth, p.centre_delay_ms, p.feedback, p.mix)
    case 'phaser': return D.phaser(a, p.rate_hz, p.depth, p.centre_frequency_hz, p.feedback, p.mix)
    case 'delay': return D.delayFx(a, p.time_ms, p.feedback, p.mix)
    case 'reverb': return D.reverb(a, p.room_size, p.damping, p.width, p.mix)
    case 'width': return D.widen(a, p.width)
    case 'limiter': return D.limit(a, p.ceiling_db, p.release_ms)
    default: return a
  }
}

/** Renders a chain on a copy of the audio. */
export function renderChain(src: D.Audio, chain: FxItem[] | null | undefined): D.Audio {
  let a = D.clone(src)
  for (const it of normalizeChain(chain)) if (!it.bypass) a = applyItem(a, it)
  return a
}
