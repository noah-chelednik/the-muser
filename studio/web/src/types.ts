export type CapabilityItem = {
  key: string
  label: string
  available: boolean
  detail: string
  hint: string
}

export type Status = {
  mode: 'demo' | 'hybrid' | 'full'
  mode_detail: string
  demo_forced: boolean
  items: Record<string, CapabilityItem>
  ollama_models: string[]
  llm_models: string[]
  tool_count: number
  /** True when served by the in-browser demo backend (no Python server). */
  browser_demo?: boolean
}

export type StemInfo = { id: string; name: string; path: string; url: string; color: string }

export type Track = {
  id: string
  title: string
  source: string
  url: string
  created: number
  prompt: string
  bpm: number | null
  key: string
  duration_s: number
  stems: StemInfo[]
  stem_method: string
  notes: string
  parent_id: string
  meta?: Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
}

export type Job<T = unknown> = {
  job_id: string
  kind: string
  status: 'queued' | 'running' | 'done' | 'error'
  message: string
  result: T | null
  error: string
  detail?: string
}

export type StemParams = {
  gain_db: number
  pan: number
  mute: boolean
  solo: boolean
  eq_low_db: number
  eq_mid_db: number
  eq_high_db: number
  comp: number
  reverb: number
  room: number
  // ---- live Web Audio chain (browser only, also used by the offline bounce)
  /** Parametric band: centre Hz, gain dB, Q. */
  peq_freq: number
  peq_gain: number
  peq_q: number
  /** Saturation amount 0..1 (WaveShaper, parallel). */
  sat: number
  delay_mix: number
  delay_time: number
  delay_fb: number
  /** Stereo width 0 (mono) .. 1 (as is) .. 2 (wide). */
  width: number
  /** Filter sweep -1 (low-pass closing) .. 0 (open) .. +1 (high-pass rising). */
  filter: number
  filter_q: number
  /** Bypass the whole FX chain (level, pan, mute and solo stay live). */
  bypass: boolean
  byp_eq: boolean
  byp_comp: boolean
  byp_sat: boolean
  byp_delay: boolean
  byp_verb: boolean
  byp_filter: boolean
  byp_width: boolean
}

/** The fields the server mix endpoint understands. */
export const SERVER_STEM_KEYS = ['gain_db', 'pan', 'mute', 'solo', 'eq_low_db', 'eq_mid_db', 'eq_high_db', 'comp', 'reverb', 'room'] as const

export const DEFAULT_STEM: StemParams = {
  gain_db: 0,
  pan: 0,
  mute: false,
  solo: false,
  eq_low_db: 0,
  eq_mid_db: 0,
  eq_high_db: 0,
  comp: 0,
  reverb: 0,
  room: 0.5,
  peq_freq: 2500,
  peq_gain: 0,
  peq_q: 1.2,
  sat: 0,
  delay_mix: 0,
  delay_time: 0.375,
  delay_fb: 0.35,
  width: 1,
  filter: 0,
  filter_q: 0.8,
  bypass: false,
  byp_eq: false,
  byp_comp: false,
  byp_sat: false,
  byp_delay: false,
  byp_verb: false,
  byp_filter: false,
  byp_width: false,
}

export type SynthParams = {
  wave: OscillatorType
  cutoff: number // 0..1
  reso: number // 0..1
  attack: number // seconds
  release: number // seconds
  detune: number // cents
  volume: number // 0..1
  octave: number // -2..2
}

export type PadParams = { volume: number; pitch: number; tone: number }

export type Project = {
  mixer: Record<string, StemParams> // key: stem id (or "<trackId>:mix")
  master: { gain_db: number; normalize: boolean; limiter?: boolean }
  synth: SynthParams
  pads: PadParams
  pattern: boolean[][] // 16 pads x 16 steps
  bpm: number
}

export type ChatItem =
  | { kind: 'user'; text: string }
  | { kind: 'assistant'; text: string; streaming?: boolean }
  | { kind: 'tool'; name: string; status: 'running' | 'success' | 'error'; detail?: string }
  | { kind: 'track'; track: Track }
  | { kind: 'error'; text: string }

// ---------------------------------------------------------------- v2 (all-in-one)

export type Mode = 'easy' | 'advanced'

export type FxItem = { type: string; params: Record<string, number>; bypass?: boolean }
export type PluginParam = { min: number; max: number; default: number; unit?: string; label?: string; step?: number }
export type PluginSpec = { label: string; group?: string; params: Record<string, PluginParam> }

export type Preset = {
  id: string
  name: string
  category: 'genre' | 'mix' | 'master' | 'vocal' | 'fx'
  subcategory?: string
  tags: string[]
  description: string
  factory?: boolean
  favorite?: boolean
  user?: boolean
  role?: string
  easy?: boolean
  icon?: string
  chain?: FxItem[]
  master?: { target: string; chain: FxItem[]; release_ms?: number } | string | null
  generate?: { prompt: string; bpm: number; duration_s: number; lyrics: string }
  stems?: Record<string, string | FxItem[]>
  macros?: Record<MacroKey, number>
}

export type MacroKey = 'energy' | 'vocals' | 'bass' | 'brightness' | 'space'
export type Slider = { key: MacroKey; label: string; help: string; low?: string; high?: string }
export type FinishTarget = { label: string; lufs: number; true_peak_db: number; easy: boolean; note: string }

export type EngineInfo = {
  key: string
  name: string
  tasks: string[]
  summary: string
  homepage: string
  code_license: string
  weights_license: string
  commercial: 'yes' | 'conditional' | 'no'
  commercial_note: string
  tier: 'builtin' | 'core' | 'optional' | 'heavy'
  min_vram_gb: number
  cpu_ok: boolean
  windows: string
  verified: 'working' | 'adapter'
  untested_here: boolean
  gpl_note?: string
  archived?: boolean
  install: { kind: string; download_gb?: number }
  health: { installed: boolean; detail: string; [k: string]: unknown }
  fits: boolean
  fit_reason: string
  vram_full_gb?: number
  vram_caveat?: string
  fit?: EngineFit
}

export type FitStatus = 'cpu' | 'fits' | 'fits-reduced' | 'tight' | 'too-big' | 'no-gpu'
export type EngineFit = { status: FitStatus; label: string; reason: string; recommended: boolean; caveat: string; profile: { id: string; label: string; vram_gb: number; how: string } | null }

export type EnginePick = { engine: string | null; name: string | null; reasons: string[]; alternatives: { key: string; name: string }[]; upgrades: { key: string; name: string; detail: string }[] }

export type Hardware = {
  hardware: { os: string; cpu_count: number; ram_gb: number; gpu: string; vram_gb: number; cuda: boolean; notes: string[]; compute_cap?: string; bf16?: boolean }
  tier: string
  recommendations: { key: string; name: string; can_run: boolean; status: FitStatus; label: string; reason: string; commercial: string; min_vram_gb: number; vram_full_gb: number; caveat: string; profile: EngineFit['profile'] }[]
}

export type Analysis = { lufs: number | null; true_peak_db: number; peak_db: number; rms_db: number; duration_s: number; sample_rate: number; channels: number }
