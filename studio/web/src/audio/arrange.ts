/** Pattern playlist helpers: named patterns placed on a timeline, FL-style. */
import { DEFAULT_STEM, type Arrangement, type ArrangeTrack, type BeatPattern, type Project } from '../types'

export type Hit = { pad: number; track: number }

export const uid = (p = 'id') => `${p}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`

export const blankSteps = (): boolean[][] => Array.from({ length: 16 }, () => Array(16).fill(false) as boolean[])

export const cloneSteps = (steps: boolean[][]) => steps.map((row) => row.slice())

export function makePattern(name: string, steps?: boolean[][], id?: string): BeatPattern {
  return { id: id ?? uid('pat'), name, steps: steps ? cloneSteps(steps) : blankSteps() }
}

export function defaultTracks(): ArrangeTrack[] {
  return [1, 2, 3, 4].map((n) => ({ name: `Track ${n}`, fx: { ...DEFAULT_STEM } }))
}

export function defaultArrangement(firstPatternId?: string): Arrangement {
  return {
    bars: 8,
    clips: firstPatternId
      ? [{ id: 'clip-1', patternId: firstPatternId, track: 0, startBar: 0, lengthBars: 1 }]
      : [],
    tracks: defaultTracks(),
    masterFx: { ...DEFAULT_STEM },
  }
}

export function ensureBeat(project: Project): Project {
  const seeded = project.patterns?.length
    ? project.patterns
    : [makePattern('Pattern 1', project.pattern, 'pat-1')]
  const patterns = seeded
  const activePatternId = patterns.some((item) => item.id === project.activePatternId)
    ? project.activePatternId!
    : patterns[0].id
  const raw = project.arrangement ?? defaultArrangement(patterns[0].id)
  const tracks = raw.tracks.length >= 4
    ? raw.tracks
    : [...raw.tracks, ...defaultTracks().slice(raw.tracks.length)]
  return {
    ...project,
    patterns,
    activePatternId,
    arrangement: { ...raw, tracks, bars: Math.max(1, raw.bars), clips: raw.clips ?? [] },
  }
}

export function syncActivePattern(project: Project, steps: boolean[][]): Project {
  const next = ensureBeat(project)
  return {
    ...next,
    pattern: cloneSteps(steps),
    patterns: next.patterns!.map((item) => (item.id === next.activePatternId ? { ...item, steps: cloneSteps(steps) } : item)),
  }
}

export function hitsAt(arrangement: Arrangement, patterns: BeatPattern[], bar: number, step: number): Hit[] {
  const byId = new Map(patterns.map((item) => [item.id, item]))
  const seen = new Set<string>()
  const hits: Hit[] = []
  for (const clip of arrangement.clips) {
    const span = Math.max(1, clip.lengthBars)
    if (bar < clip.startBar || bar >= clip.startBar + span) continue
    const pat = byId.get(clip.patternId)
    if (!pat) continue
    const localStep = ((bar - clip.startBar) * 16 + step) % 16
    pat.steps.forEach((row, pad) => {
      if (!row[localStep]) return
      const key = `${clip.track}:${pad}`
      if (seen.has(key)) return
      seen.add(key)
      hits.push({ pad, track: clip.track })
    })
  }
  return hits
}

export function arrangementSeconds(bpm: number, bars: number, tail = 1.5): number {
  const stepSec = 60 / Math.max(1, bpm) / 4
  return Math.max(1, bars) * 16 * stepSec + tail
}

export function clipAt(arrangement: Arrangement, track: number, bar: number) {
  return arrangement.clips.find((clip) => (
    clip.track === track && bar >= clip.startBar && bar < clip.startBar + Math.max(1, clip.lengthBars)
  ))
}
