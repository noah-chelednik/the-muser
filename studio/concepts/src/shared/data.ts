import { RAW_VIBES, RAW_PRESET_NAMES } from './vibes'

export type MacroKey = 'energy' | 'vocals' | 'bass' | 'brightness' | 'space'
export type Macros = Record<MacroKey, number>
export type Family = 'four' | 'boom' | 'trap' | 'dnb' | 'amb' | 'rock' | 'latin'

export interface Vibe {
  id: string
  name: string
  desc: string
  bpm: number
  macros: Macros
  key: string
  minor: boolean
  family: Family
  index: number
}

export const VIBES: Vibe[] = (RAW_VIBES as unknown as Omit<Vibe, 'index'>[]).map((v, i) => ({ ...v, index: i }))
export const vibeById = (id: string | null) => VIBES.find((v) => v.id === id) ?? null

export const MACROS: { key: MacroKey; label: string; lo: string; hi: string; help: string; dyn: string }[] = [
  { key: 'energy', label: 'Energy', lo: 'Calm', hi: 'Hype', help: 'Drives drums, compression and grit.', dyn: 'Tempo, drum drive' },
  { key: 'vocals', label: 'Vocals', lo: 'Back', hi: 'Front', help: 'Pull the voice back or push it to the front.', dyn: 'Voice level' },
  { key: 'bass', label: 'Bass', lo: 'Light', hi: 'Heavy', help: 'Thin to heavy low end.', dyn: 'Sub weight' },
  { key: 'brightness', label: 'Brightness', lo: 'Warm', hi: 'Airy', help: 'Dark and warm to crisp and airy.', dyn: 'Tilt, top end' },
  { key: 'space', label: 'Space', lo: 'Dry', hi: 'Wide', help: 'Dry and close to big and wide.', dyn: 'Reverb, echo' },
]
export const NEUTRAL: Macros = { energy: 50, vocals: 50, bass: 50, brightness: 50, space: 50 }

export const FINISH = [
  { key: 'spotify', label: 'Spotify', lufs: -14, tp: -1, note: 'Streaming standard. Clean peaks, no clipping.' },
  { key: 'youtube', label: 'YouTube', lufs: -14, tp: -1, note: 'Louder uploads are turned down, so no gain in pushing.' },
  { key: 'soundcloud', label: 'SoundCloud', lufs: -10, tp: -1, note: 'Competitive master that survives transcoding.' },
  { key: 'club', label: 'Club / DJ', lufs: -8, tp: -0.5, note: 'Loud and dense for club systems and DJ sets.' },
] as const
export type FinishKey = (typeof FINISH)[number]['key']

export const TOOLS = [
  { key: 'split', label: 'Split stems', busy: 'Splitting stems', done: 'Split into 4 stems. Undo brings back the mix.' },
  { key: 'remove_vocals', label: 'Remove vocals', busy: 'Removing vocals', done: 'Vocals removed. Undo restores them.' },
  { key: 'denoise', label: 'Clean up noise', busy: 'Cleaning up noise', done: 'Noise floor lowered by 11 dB.' },
  { key: 'match', label: 'Match reference', busy: 'Matching reference', done: 'Matched tone and loudness to your reference.' },
  { key: 'midi', label: 'Turn into MIDI', busy: 'Transcribing to MIDI', done: 'MIDI ready, 73 notes.' },
] as const
export type ToolKey = (typeof TOOLS)[number]['key']

export type StemId = 'drums' | 'bass' | 'keys' | 'voice'
export const STEMS: { id: StemId; name: string; short: string; clef: string; chain: string[] }[] = [
  { id: 'drums', name: 'Drums', short: 'DRM', clef: 'perc', chain: ['Gate', 'Punch Comp', 'Tape Sat', 'Room'] },
  { id: 'bass', name: 'Bass', short: 'BAS', clef: 'bass', chain: ['EQ', 'Warm Comp', 'Sub Sat'] },
  { id: 'keys', name: 'Keys', short: 'KEY', clef: 'treble', chain: ['EQ', 'Chorus', 'Plate'] },
  { id: 'voice', name: 'Voice', short: 'VOX', clef: 'treble', chain: ['De-ess', 'EQ', 'Comp', 'Plate'] },
]

export const PRESET_CATS = ['genre', 'mix', 'vocal', 'fx', 'master'] as const
export type PresetCat = (typeof PRESET_CATS)[number]
export interface PresetItem { id: string; name: string; cat: PresetCat; tags: string[]; blurb: string }
const BLURB: Record<string, string> = {
  genre: 'Starter for a whole track', mix: 'Stem chain', vocal: 'Vocal chain', fx: 'Effect on a stem', master: 'Master target chain',
}
export const PRESETS: PresetItem[] = PRESET_CATS.flatMap((cat) =>
  (RAW_PRESET_NAMES[cat] ?? []).map((name) => ({
    id: `${cat}/${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
    name,
    cat,
    tags: [],
    blurb: cat === 'genre' ? (VIBES.find((v) => v.name === name)?.desc ?? BLURB[cat]) : BLURB[cat],
  })),
)

export interface Engine {
  key: string; name: string; role: string; vram: string; status: 'fits' | 'tight' | 'no' | 'cpu'; note?: string; installed: boolean; tier: 'light' | 'heavy'
}
export const ENGINES: Engine[] = [
  { key: 'demo', name: 'Demo synth', role: 'Built-in generator', vram: 'CPU', status: 'cpu', installed: true, tier: 'light' },
  { key: 'resemble', name: 'Resemble Enhance', role: 'Denoise and enhance', vram: '4 GB', status: 'fits', installed: true, tier: 'light' },
  { key: 'ace', name: 'ACE-Step 1.5', role: 'Song generation', vram: '6 to 20 GB', status: 'fits', note: '8 GB card settings', installed: false, tier: 'heavy' },
  { key: 'applio', name: 'Applio (RVC)', role: 'Voice conversion', vram: '4 GB', status: 'fits', installed: false, tier: 'light' },
  { key: 'seedvc', name: 'Seed-VC', role: 'Voice conversion', vram: '4 to 6 GB', status: 'fits', installed: false, tier: 'light' },
  { key: 'sao', name: 'Stable Audio Open', role: 'Text to audio', vram: '6 GB', status: 'fits', installed: false, tier: 'heavy' },
  { key: 'musicgen', name: 'MusicGen (Meta AudioCraft)', role: 'Text to music', vram: '4 to 16 GB', status: 'fits', note: 'Small settings', installed: false, tier: 'heavy' },
  { key: 'audioldm', name: 'AudioLDM 2', role: 'Text to audio', vram: '6 GB', status: 'fits', installed: false, tier: 'heavy' },
  { key: 'audiosr', name: 'AudioSR', role: 'Super resolution', vram: '6 to 8 GB', status: 'tight', installed: false, tier: 'heavy' },
  { key: 'diffrhythm', name: 'DiffRhythm', role: 'Full song', vram: '8 to 12 GB', status: 'tight', installed: false, tier: 'heavy' },
  { key: 'full', name: 'Full pipeline (24 GB)', role: 'End to end', vram: '20 to 24 GB', status: 'no', installed: false, tier: 'heavy' },
  { key: 'yue', name: 'YuE', role: 'Lyrics to song', vram: '24 GB', status: 'no', installed: false, tier: 'heavy' },
  { key: 'levo', name: 'SongGeneration / LeVo (Tencent)', role: 'Song generation', vram: '10 to 16 GB', status: 'no', installed: false, tier: 'heavy' },
]
export const FIT_LABEL: Record<Engine['status'], string> = { fits: 'Fits', tight: 'Tight', no: 'Not recommended', cpu: 'CPU' }

export const SHORTCUTS: [string, string][] = [
  ['Space', 'Play / pause'],
  ['Enter', 'Make It'],
  ['[  ]', 'Previous / next vibe'],
  ['1 to 5', 'Select a macro'],
  ['← →', 'Nudge macro (Shift = x10)'],
  ['F', 'Cycle finish target'],
  ['X', 'Export'],
  ['E', 'Easy / Advanced'],
  ['Z', 'Undo (Shift+Z redo)'],
  ['/', 'Focus prompt or search'],
  ['G', 'Engines'],
  ['?', 'This sheet'],
]

export const dynFor = (v: number) => (v < 12 ? 'ppp' : v < 25 ? 'pp' : v < 40 ? 'p' : v < 52 ? 'mp' : v < 66 ? 'mf' : v < 80 ? 'f' : v < 92 ? 'ff' : 'fff')
export const tempoWord = (bpm: number) =>
  bpm < 66 ? 'Largo' : bpm < 76 ? 'Adagio' : bpm < 92 ? 'Andante' : bpm < 108 ? 'Moderato' : bpm < 120 ? 'Allegretto' : bpm < 156 ? 'Allegro' : 'Presto'
export const fmtTime = (s: number) => {
  const m = Math.floor(s / 60)
  const r = s - m * 60
  return `${String(m).padStart(2, '0')}:${r.toFixed(2).padStart(5, '0')}`
}
