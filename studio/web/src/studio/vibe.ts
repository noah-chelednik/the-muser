import type { MacroKey, Preset } from '../types'

export type Family = 'four' | 'boom' | 'trap' | 'dnb' | 'amb' | 'rock' | 'latin'

/** Rough family for a genre preset, used only to pick cartridge art and spectral colour. */
export function familyOf(p: Pick<Preset, 'id' | 'name' | 'description'>): Family {
  const t = `${p.id} ${p.name} ${p.description ?? ''}`.toLowerCase()
  if (/techno|house|trance|edm|disco|garage|electro|four/.test(t)) return 'four'
  if (/trap|drill|grime|phonk/.test(t)) return 'trap'
  if (/dnb|drum ?& ?bass|drum and bass|jungle|breakbeat|hardcore/.test(t)) return 'dnb'
  if (/ambient|chill|cinematic|drone|new age|downtempo|sleep|score/.test(t)) return 'amb'
  if (/rock|metal|punk|grunge|indie|emo|blues/.test(t)) return 'rock'
  if (/latin|reggaeton|salsa|bossa|samba|afro|dancehall|reggae|cumbia/.test(t)) return 'latin'
  return 'boom'
}

export function barcode(id: string, n = 18): number[] {
  let h = 2166136261
  for (const c of id) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  const out: number[] = []
  for (let i = 0; i < n; i++) {
    h = Math.imul(h ^ (h >>> 13), 1274126177)
    out.push(1 + ((h >>> 8) & 3))
  }
  return out
}

export const tempoWord = (bpm: number) =>
  bpm < 70 ? 'Largo' : bpm < 90 ? 'Andante' : bpm < 108 ? 'Moderato' : bpm < 128 ? 'Allegro' : bpm < 150 ? 'Vivace' : 'Presto'

export const dynFor = (v: number) => (v < 12 ? 'ppp' : v < 25 ? 'pp' : v < 40 ? 'p' : v < 52 ? 'mp' : v < 66 ? 'mf' : v < 80 ? 'f' : v < 92 ? 'ff' : 'fff')

export const fmtTime = (s: number) => {
  const m = Math.floor(s / 60)
  return `${String(m).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}
export const fmtClock = (s: number) => `${fmtTime(s)}.${String(Math.floor((s % 1) * 100)).padStart(2, '0')}`

export const MACRO_META = [
  { key: 'energy', label: 'Energy', help: 'Drives drums, compression and grit.', dyn: 'Tempo, drum drive' },
  { key: 'vocals', label: 'Vocals', help: 'Pull the voice back or push it to the front.', dyn: 'Voice level' },
  { key: 'bass', label: 'Bass', help: 'Thin to heavy low end.', dyn: 'Sub weight' },
  { key: 'brightness', label: 'Brightness', help: 'Dark and warm to crisp and airy.', dyn: 'Tilt, top end' },
  { key: 'space', label: 'Space', help: 'Dry and close to big and wide.', dyn: 'Reverb, echo' },
] as const

export const TOOLS = [
  { name: 'split', label: 'Split stems', extra: { mode: '4stem' } },
  { name: 'remove_vocals', label: 'Remove vocals' },
  { name: 'denoise', label: 'Clean up noise' },
  { name: 'match', label: 'Match reference', reference: true },
  { name: 'midi', label: 'Turn into MIDI' },
] as const

export const SHORTCUTS: [string, string][] = [
  ['Space', 'Play / pause'],
  ['Ctrl K', 'Command palette'],
  ['Alt S', 'Next skin (T in Easy)'],
  ['Alt E', 'Easy / Advanced'],
  ['Alt G', 'Engines drawer'],
  ['Ctrl Z / Y', 'Undo / redo'],
  ['Enter', 'Make It (Easy)'],
  ['[  ]', 'Previous / next vibe (Easy)'],
  ['1 to 5', 'Select a macro (Easy)'],
  ['← →', 'Nudge macro, Shift x10 (Easy)'],
  ['F', 'Cycle finish target (Easy)'],
  ['X', 'Export (Easy)'],
  ['/', 'Focus the prompt or search'],
  ['?', 'This sheet'],
]

export const MACRO_KEYS = MACRO_META.map((m) => m.key) as MacroKey[]
