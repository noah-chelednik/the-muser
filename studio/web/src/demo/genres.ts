// Genre recipes for the browser demo synthesizer: tempo, swing, drum lanes, bass, chords, lead and mix.
// This is a hand-written rule set, not a model. The UI says so wherever it plays.
import type { BassKind, KickP, SnareP } from './voices'

export type Mode = 'minor' | 'major' | 'dorian' | 'phrygian' | 'mixolydian'
export const MODES: Record<Mode, number[]> = {
  minor: [0, 2, 3, 5, 7, 8, 10], major: [0, 2, 4, 5, 7, 9, 11], dorian: [0, 2, 3, 5, 7, 9, 10],
  phrygian: [0, 1, 3, 5, 7, 8, 10], mixolydian: [0, 2, 4, 5, 7, 9, 10],
}
export type Structure = 'groove' | 'edm' | 'band' | 'ambient' | 'cinematic'
export type LaneRole = 'kick' | 'back' | 'hat' | 'perc'
export type Lane = { voice: string; role: LaneRole; pat: string[]; gain?: number; rolls?: { at: number[]; sub: number; prob: number; steps?: number } }
export type ChordVoice = 'rhodes' | 'piano' | 'organ' | 'supersaw' | 'pad' | 'strings' | 'brass' | 'choir' | 'harmonium' | 'guitar' | 'distPalm' | 'dist' | 'bell' | 'pluck' | 'stab' | 'square'
export type ChordLayer = {
  voice: ChordVoice; pat: string[]; style: 'block' | 'arp' | 'strum' | 'power'; center: number; gain?: number
  ext?: 3 | 4 | 5; hold?: number; strumMs?: number; octave?: number; filterStart?: boolean
}
export type LeadSpec = { voice: ChordVoice; rhythms: string[]; base: number; len?: number; prob?: number; gain?: number; pent?: boolean; oct2?: boolean }
export type BassSpec = { kind: BassKind; pat: string[]; lo: number; glide?: number; lfo?: number; drive?: number; decay?: number; hold?: number; walk?: boolean }
export type MixSpec = {
  gains: { drums: number; bass: number; chords: number; lead: number }
  pump?: number; drumsLp?: number; drumsSat?: number; chordsLp?: number; chordsRev?: number; leadRev?: number
  leadDelay?: [number, number, number]; vinyl?: number; crush?: number; width?: number; chordsChorus?: number; bassSat?: number; leadSat?: number
}
export type Profile = {
  id: string; name: string; aliases: string[]; bpm: number; swing: number; swingGrid?: 8 | 16
  root: number; mode: Mode; progs: number[][]; structure: Structure; human?: number
  drums: { lanes: Lane[]; fill?: 'snare' | 'tom' | 'none' }
  bass: BassSpec | null; chords: ChordLayer[]; lead: LeadSpec | null; mix: MixSpec
}

export const KICKS: Record<string, KickP> = {
  boom: { f0: 130, f1: 52, sweep: 38, decay: 8, drive: 1.6, click: 0.12, len: 0.4 },
  lofi: { f0: 110, f1: 50, sweep: 30, decay: 9, drive: 1.4, click: 0.05, len: 0.4 },
  trap: { f0: 170, f1: 48, sweep: 55, decay: 5.5, drive: 2.2, click: 0.2, len: 0.6 },
  house: { f0: 155, f1: 50, sweep: 42, decay: 7, drive: 1.7, click: 0.15, len: 0.42 },
  techno: { f0: 180, f1: 48, sweep: 50, decay: 5, drive: 3, click: 0.25, len: 0.5 },
  rock: { f0: 120, f1: 62, sweep: 48, decay: 10, drive: 1.4, click: 0.5, len: 0.32 },
  metal: { f0: 140, f1: 60, sweep: 60, decay: 11, drive: 2, click: 0.8, len: 0.22 },
  soft: { f0: 105, f1: 55, sweep: 30, decay: 12, drive: 1.2, click: 0.05, len: 0.3 },
  dnb: { f0: 160, f1: 52, sweep: 50, decay: 10, drive: 2, click: 0.2, len: 0.3 },
  dub: { f0: 150, f1: 48, sweep: 45, decay: 6, drive: 2.4, click: 0.15, len: 0.5 },
  edm: { f0: 170, f1: 50, sweep: 48, decay: 6.5, drive: 2, click: 0.22, len: 0.4 },
  pop: { f0: 140, f1: 52, sweep: 40, decay: 8, drive: 1.6, click: 0.12, len: 0.38 },
  jazz: { f0: 95, f1: 60, sweep: 25, decay: 14, drive: 1.1, click: 0.03, len: 0.3 },
}
export const SNARES: Record<string, SnareP> = {
  boom: { tone: 190, toneDecay: 28, toneLevel: 0.6, noiseDecay: 20, noiseLevel: 0.7, hp: 1200, len: 0.25 },
  lofi: { tone: 175, toneDecay: 30, toneLevel: 0.5, noiseDecay: 24, noiseLevel: 0.45, hp: 900, lpf: 6500, len: 0.22 },
  trap: { tone: 210, toneDecay: 30, toneLevel: 0.35, noiseDecay: 16, noiseLevel: 0.75, hp: 1800, len: 0.3 },
  rock: { tone: 200, toneDecay: 22, toneLevel: 0.7, noiseDecay: 13, noiseLevel: 0.85, hp: 1000, len: 0.3 },
  metal: { tone: 230, toneDecay: 26, toneLevel: 0.65, noiseDecay: 12, noiseLevel: 0.9, hp: 1400, len: 0.28 },
  dnb: { tone: 240, toneDecay: 30, toneLevel: 0.5, noiseDecay: 17, noiseLevel: 0.8, hp: 1500, len: 0.22 },
  dub: { tone: 200, toneDecay: 20, toneLevel: 0.7, noiseDecay: 11, noiseLevel: 0.9, hp: 900, len: 0.35 },
  gate: { tone: 185, toneDecay: 20, toneLevel: 0.6, noiseDecay: 9, noiseLevel: 0.85, hp: 1000, len: 0.3 },
  pop: { tone: 195, toneDecay: 26, toneLevel: 0.5, noiseDecay: 18, noiseLevel: 0.7, hp: 1300, len: 0.24 },
}


const P = (...s: string[]) => s

export const PROFILES: Profile[] = [
  {
    id: 'lo-fi-chill', name: 'Lo-fi Chill', aliases: ['lo-fi', 'lofi', 'lo fi', 'chillhop', 'study beat'],
    bpm: 78, swing: 0.2, root: 9, mode: 'minor', progs: [[0, 5, 3, 4], [0, 3, 5, 4], [5, 3, 0, 4]], structure: 'groove', human: 9,
    drums: {
      lanes: [
        { voice: 'kick:lofi', role: 'kick', pat: P('x.....x...x.....', 'x.....x....x..o.', 'x.......x.x.....', 'x.....x...x...o.') },
        { voice: 'snare:lofi', role: 'back', pat: P('....x.......x...', '....x.......x..g') },
        { voice: 'hat', role: 'hat', pat: P('x.o.x.o.x.o.x.ox', 'x.o.x.ox.o.x.o.x'), gain: 0.55 },
        { voice: 'shaker', role: 'perc', pat: P('..o...o...o...o.'), gain: 0.4 },
      ],
    },
    bass: { kind: 'sub', pat: P('x.....x...x.....', 'x.....x....5..o.', 'x.......x.x.....'), lo: 33, hold: 5 },
    chords: [{ voice: 'rhodes', pat: P('x.......x..x....', 'x.....x.....x...', 'x.......x.......'), style: 'block', center: 62, ext: 5, strumMs: 22, hold: 7 }],
    lead: { voice: 'rhodes', rhythms: P('x...x.x.....x...', '..x.....x.x.....', 'x.....x...x.....'), base: 76, len: 3, prob: 0.8, gain: 0.55, pent: true },
    mix: { gains: { drums: 0.9, bass: 0.9, chords: 0.8, lead: 0.5 }, drumsLp: 6800, drumsSat: 5, chordsLp: 3400, chordsRev: 0.22, leadRev: 0.3, vinyl: 0.012, chordsChorus: 0.25, leadDelay: [0.375, 0.35, 0.22] },
  },
  {
    id: 'hip-hop', name: 'Hip Hop', aliases: ['hip hop', 'hip-hop', 'hiphop', 'boom bap', 'boombap', 'rap beat'],
    bpm: 90, swing: 0.14, root: 5, mode: 'minor', progs: [[0, 5, 3, 4], [0, 6, 5, 6], [0, 3, 0, 4]], structure: 'groove', human: 6,
    drums: {
      lanes: [
        { voice: 'kick:boom', role: 'kick', pat: P('x.....x..x......', 'x.....x..xx.....', 'x..x..x...x.....', 'x.....x..x...x..') },
        { voice: 'snare:boom', role: 'back', pat: P('....X.......X...', '....X.......X..g') },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.xo', 'x.xox.x.x.xox.x.'), gain: 0.65 },
        { voice: 'rim', role: 'perc', pat: P('..............g.', '...........g....'), gain: 0.5 },
      ],
    },
    bass: { kind: 'electric', pat: P('x.....x..x......', 'x.....x..5..o...', 'x..x..x...x.....'), lo: 31, hold: 5, drive: 1.4 },
    chords: [{ voice: 'piano', pat: P('x.....x...x.x...', 'x.......x..x....', 'x..x....x.......'), style: 'block', center: 60, ext: 4, strumMs: 12, hold: 4 }],
    lead: { voice: 'bell', rhythms: P('x...x...x.x.....', '..x...x.....x...', 'x.....x...x...x.'), base: 72, len: 2, prob: 0.65, gain: 0.4, pent: true },
    mix: { gains: { drums: 1, bass: 0.85, chords: 0.7, lead: 0.4 }, drumsSat: 4, chordsLp: 4500, chordsRev: 0.12, vinyl: 0.006, leadRev: 0.2 },
  },
  {
    id: 'trap', name: 'Trap', aliases: ['trap', 'atlanta', '808 trap'],
    bpm: 140, swing: 0, root: 6, mode: 'minor', progs: [[0, 0, 5, 6], [0, 5, 2, 6], [0, 1, 0, 6]], structure: 'groove', human: 3,
    drums: {
      lanes: [
        { voice: 'kick:trap', role: 'kick', pat: P('x.......x..x.x..', 'x....x..x.......', 'x..x....x..x....', 'x.......x...x.x.') },
        { voice: 'clap', role: 'back', pat: P('........x.......', '........x......g'), gain: 0.9 },
        { voice: 'snare:trap', role: 'back', pat: P('........x.......'), gain: 0.55 },
        { voice: 'hat:trap', role: 'hat', pat: P('x.x.x.x.x.x.x.x.', 'x.xxx.x.x.x.xx.x', 'xoxox.x.x.xox.x.'), gain: 0.6, rolls: { at: [6, 14], sub: 3, prob: 0.8 } },
        { voice: 'ohat', role: 'perc', pat: P('..............x.', '......x.........'), gain: 0.5 },
      ],
    },
    bass: { kind: 'sub808', pat: P('x.......x..x.x..', 'x....x..x.......', 'x..x....5..x....'), lo: 28, glide: 0.07, hold: 8, drive: 2.2 },
    chords: [{ voice: 'pad', pat: P('x...............'), style: 'block', center: 60, ext: 4, hold: 16, gain: 0.55 }],
    lead: { voice: 'bell', rhythms: P('x...x...x.x.....', '..x...x...x...x.', 'x.x...x.........'), base: 79, len: 3, prob: 0.9, gain: 0.45, pent: true },
    mix: { gains: { drums: 0.95, bass: 1, chords: 0.45, lead: 0.5 }, drumsSat: 3, chordsLp: 2600, chordsRev: 0.3, leadRev: 0.35, leadDelay: [0.75, 0.3, 0.2], bassSat: 3 },
  },
  {
    id: 'uk-drill', name: 'UK Drill', aliases: ['uk drill', 'drill', 'ny drill', 'chicago drill'],
    bpm: 142, swing: 0, root: 7, mode: 'minor', progs: [[0, 0, 5, 4], [0, 1, 0, 6], [0, 5, 6, 0]], structure: 'groove', human: 3,
    drums: {
      lanes: [
        { voice: 'kick:trap', role: 'kick', pat: P('x.....x....x....', 'x..x.......x.x..', 'x.....x..x......', 'x.......x...x...') },
        { voice: 'snare:trap', role: 'back', pat: P('..........x.....', '........x...x...'), gain: 0.95 },
        { voice: 'rim', role: 'perc', pat: P('........x.......'), gain: 0.4 },
        { voice: 'hat:trap', role: 'hat', pat: P('x.x.x.x.x.x.x.x.', 'x.xxx.x.xx.xx.x.'), gain: 0.55, rolls: { at: [3, 7, 11, 15], sub: 3, prob: 0.9 } },
      ],
    },
    bass: { kind: 'sub808', pat: P('x.....x....x....', 'x..x.......x.x..', 'x.....x..5......'), lo: 28, glide: 0.11, hold: 10, drive: 2.4 },
    chords: [{ voice: 'strings', pat: P('x...............'), style: 'block', center: 60, ext: 3, hold: 16, gain: 0.4 }],
    lead: { voice: 'piano', rhythms: P('x..x..x...x..x..', '..x..x..x.......', 'x.....x...x.x...'), base: 72, len: 2, prob: 0.9, gain: 0.55, pent: true },
    mix: { gains: { drums: 0.95, bass: 1, chords: 0.4, lead: 0.6 }, drumsSat: 3, chordsLp: 2400, chordsRev: 0.28, leadRev: 0.25, bassSat: 3 },
  },
  {
    id: 'phonk', name: 'Phonk', aliases: ['phonk', 'memphis', 'drift phonk', 'memphis trap'],
    bpm: 130, swing: 0.04, root: 2, mode: 'phrygian', progs: [[0, 0, 1, 0], [0, 5, 0, 1], [0, 6, 5, 0]], structure: 'groove', human: 5,
    drums: {
      lanes: [
        { voice: 'kick:trap', role: 'kick', pat: P('x.......x.x.....', 'x..x....x.......', 'x.......x..x.x..') },
        { voice: 'clap', role: 'back', pat: P('....x.......x...', '........x.......'), gain: 0.9 },
        { voice: 'hat:trap', role: 'hat', pat: P('x.x.x.x.x.x.x.x.', 'xxx.x.x.xxx.x.xx'), gain: 0.55, rolls: { at: [7, 15], sub: 4, prob: 0.6 } },
        { voice: 'cowbell', role: 'perc', pat: P('x..x..x.........', 'x..x..x...x.....'), gain: 0.55 },
      ],
    },
    bass: { kind: 'sub808', pat: P('x.......x.x.....', 'x..x....x.......'), lo: 27, glide: 0.06, hold: 8, drive: 3.4 },
    chords: [{ voice: 'choir', pat: P('x.......x.......', 'x.......x..x....'), style: 'block', center: 62, ext: 3, hold: 5, gain: 0.5 }],
    lead: { voice: 'bell', rhythms: P('x..x..x.x..x....', 'x.x...x.x.x.....'), base: 74, len: 2, prob: 1, gain: 0.5, pent: true },
    mix: { gains: { drums: 0.95, bass: 1, chords: 0.5, lead: 0.55 }, drumsSat: 6, chordsLp: 3000, chordsRev: 0.3, leadRev: 0.28, crush: 9, bassSat: 5 },
  },
  {
    id: 'techno', name: 'Techno', aliases: ['techno', 'warehouse', 'minimal techno', 'industrial'],
    bpm: 130, swing: 0, root: 9, mode: 'minor', progs: [[0, 0, 0, 5], [0, 0, 6, 0], [0, 5, 0, 6]], structure: 'edm', human: 1,
    drums: {
      lanes: [
        { voice: 'kick:techno', role: 'kick', pat: P('x...x...x...x...') },
        { voice: 'clap', role: 'back', pat: P('....x.......x...'), gain: 0.7 },
        { voice: 'ohat', role: 'hat', pat: P('..x...x...x...x.'), gain: 0.55 },
        { voice: 'hat', role: 'hat', pat: P('xoxoxoxoxoxoxoxo', 'xoxoxoxoxoxoxoox'), gain: 0.38 },
        { voice: 'rim', role: 'perc', pat: P('.......x.....x..', '....g...x...g...'), gain: 0.35 },
      ],
    },
    bass: { kind: 'saw', pat: P('.xxx.xxx.xxx.xxx', '.xx..xxx.xx.xxx.'), lo: 33, hold: 1, decay: 12 },
    chords: [{ voice: 'stab', pat: P('x..x..x...x.x...', 'x..x....x..x..x.', 'x.x...x...x.....'), style: 'block', center: 60, ext: 3, hold: 1, gain: 0.7 }],
    lead: { voice: 'pluck', rhythms: P('xxxxxxxxxxxxxxxx', 'x.xx.xx.x.xx.xx.'), base: 69, len: 1, prob: 1, gain: 0.35, pent: true },
    mix: { gains: { drums: 1, bass: 0.8, chords: 0.5, lead: 0.3 }, pump: 0.45, chordsRev: 0.25, leadRev: 0.2, leadDelay: [0.75, 0.45, 0.3], drumsSat: 4 },
  },
  {
    id: 'house', name: 'House', aliases: ['house', 'deep house', 'tech house', 'club house'],
    bpm: 124, swing: 0.1, root: 9, mode: 'minor', progs: [[0, 5, 3, 6], [0, 3, 5, 4], [1, 4, 0, 5]], structure: 'edm', human: 4,
    drums: {
      lanes: [
        { voice: 'kick:house', role: 'kick', pat: P('x...x...x...x...') },
        { voice: 'clap', role: 'back', pat: P('....x.......x...'), gain: 0.8 },
        { voice: 'ohat', role: 'hat', pat: P('..x...x...x...x.'), gain: 0.6 },
        { voice: 'hat', role: 'hat', pat: P('xoxoxoxoxoxoxoxo', 'x.xoxoxox.xoxoxo'), gain: 0.4 },
        { voice: 'shaker', role: 'perc', pat: P('.o.o.o.o.o.o.o.o'), gain: 0.4 },
        { voice: 'conga:hi', role: 'perc', pat: P('...x......x.....', '......x....x...x'), gain: 0.35 },
      ],
    },
    bass: { kind: 'pluck', pat: P('..x...x...x...x.', '..x..x....x..x..'), lo: 33, hold: 2, decay: 6 },
    chords: [{ voice: 'rhodes', pat: P('x..x..x.x..x..x.', 'x..x....x..x..x.', 'x..x..x...x.x...'), style: 'block', center: 62, ext: 5, strumMs: 10, hold: 2, gain: 0.8 },
      { voice: 'pad', pat: P('x...............'), style: 'block', center: 60, ext: 3, hold: 16, gain: 0.3 }],
    lead: { voice: 'pluck', rhythms: P('..x...x...x...x.', 'x.x...x.x.......'), base: 76, len: 2, prob: 0.9, gain: 0.4, pent: true },
    mix: { gains: { drums: 0.95, bass: 0.9, chords: 0.7, lead: 0.4 }, pump: 0.5, chordsRev: 0.2, leadRev: 0.25, leadDelay: [0.75, 0.4, 0.25], drumsSat: 3 },
  },
  {
    id: 'edm-anthem', name: 'EDM Anthem', aliases: ['edm', 'anthem', 'festival', 'big room', 'trance', 'progressive house'],
    bpm: 128, swing: 0, root: 0, mode: 'major', progs: [[5, 3, 0, 4], [0, 4, 5, 3], [5, 3, 0, 4]], structure: 'edm', human: 2,
    drums: {
      lanes: [
        { voice: 'kick:edm', role: 'kick', pat: P('x...x...x...x...') },
        { voice: 'clap', role: 'back', pat: P('....x.......x...'), gain: 0.85 },
        { voice: 'ohat', role: 'hat', pat: P('..x...x...x...x.'), gain: 0.55 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.'), gain: 0.35 },
        { voice: 'shaker', role: 'perc', pat: P('xoxoxoxoxoxoxoxo'), gain: 0.3 },
      ],
    },
    bass: { kind: 'saw', pat: P('.xxx.xxx.xxx.xxx', '.x.x.x.x.x.x.x.x'), lo: 33, hold: 1, decay: 9 },
    chords: [{ voice: 'supersaw', pat: P('x.......x.......', 'x...............'), style: 'block', center: 64, ext: 3, hold: 8, gain: 0.8 },
      { voice: 'pluck', pat: P('x.x.x.x.x.x.x.x.'), style: 'arp', center: 70, ext: 3, hold: 1, gain: 0.35 }],
    lead: { voice: 'supersaw', rhythms: P('x..x..x.x.......', 'x.x.x...x..x....', 'x..x..x.x..x.x..'), base: 76, len: 2, prob: 1, gain: 0.7, pent: false },
    mix: { gains: { drums: 0.95, bass: 0.85, chords: 0.75, lead: 0.7 }, pump: 0.7, chordsRev: 0.28, leadRev: 0.3, leadDelay: [0.75, 0.35, 0.22], width: 1.3, drumsSat: 3 },
  },
  {
    id: 'synthwave', name: 'Synthwave', aliases: ['synthwave', 'retrowave', 'outrun', '80s', 'neon', 'darksynth'],
    bpm: 105, swing: 0, root: 9, mode: 'minor', progs: [[0, 5, 2, 6], [0, 6, 5, 6], [0, 3, 5, 6]], structure: 'band', human: 3,
    drums: {
      lanes: [
        { voice: 'kick:pop', role: 'kick', pat: P('x.......x.x.....', 'x...x...x...x...') },
        { voice: 'snare:gate', role: 'back', pat: P('....x.......x...'), gain: 0.95 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.xx'), gain: 0.45 },
        { voice: 'tom:mid', role: 'perc', pat: P('..............g.', '............x.x.'), gain: 0.5 },
      ],
      fill: 'tom',
    },
    bass: { kind: 'saw', pat: P('xxxxxxxxxxxxxxxx'), lo: 33, hold: 1, decay: 6 },
    chords: [{ voice: 'pad', pat: P('x...............'), style: 'block', center: 62, ext: 4, hold: 16, gain: 0.65 },
      { voice: 'pluck', pat: P('x.x.x.x.x.x.x.x.'), style: 'arp', center: 69, ext: 3, hold: 1, gain: 0.25 }],
    lead: { voice: 'square', rhythms: P('x..x..x.x.......', 'x.....x.x.x.x...', 'x..x..x.x..x....'), base: 76, len: 3, prob: 1, gain: 0.55, pent: false },
    mix: { gains: { drums: 0.9, bass: 0.8, chords: 0.7, lead: 0.55 }, pump: 0.2, chordsRev: 0.3, leadRev: 0.3, leadDelay: [0.75, 0.4, 0.28], chordsChorus: 0.35, width: 1.2, drumsSat: 2 },
  },
  {
    id: 'chillwave', name: 'Chillwave', aliases: ['chillwave', 'dream pop', 'vaporwave', 'hazy', 'summer'],
    bpm: 95, swing: 0.08, root: 4, mode: 'major', progs: [[0, 4, 5, 3], [0, 5, 3, 4], [3, 0, 4, 5]], structure: 'groove', human: 6,
    drums: {
      lanes: [
        { voice: 'kick:soft', role: 'kick', pat: P('x.......x.x.....', 'x......x..x.....') },
        { voice: 'snare:lofi', role: 'back', pat: P('....x.......x...'), gain: 0.8 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.'), gain: 0.4 },
        { voice: 'shaker', role: 'perc', pat: P('.o.o.o.o.o.o.o.o'), gain: 0.35 },
      ],
    },
    bass: { kind: 'sub', pat: P('x.......x.x.....', 'x.......x..5....'), lo: 33, hold: 6 },
    chords: [{ voice: 'pad', pat: P('x...............', 'x.......x.......'), style: 'block', center: 64, ext: 4, hold: 12, gain: 0.7 },
      { voice: 'rhodes', pat: P('x.....x.........', '..x.....x.x.....'), style: 'arp', center: 70, ext: 4, hold: 3, gain: 0.4 }],
    lead: { voice: 'pluck', rhythms: P('x...x...x.......', '..x.....x.x.x...'), base: 76, len: 3, prob: 0.8, gain: 0.45, pent: true },
    mix: { gains: { drums: 0.8, bass: 0.85, chords: 0.8, lead: 0.5 }, drumsLp: 7500, chordsRev: 0.35, leadRev: 0.4, leadDelay: [0.75, 0.45, 0.35], chordsChorus: 0.5, width: 1.3, vinyl: 0.004, pump: 0.15 },
  },
  {
    id: 'ambient', name: 'Ambient', aliases: ['ambient', 'soundscape', 'drone', 'meditation', 'new age', 'atmosphere'],
    bpm: 70, swing: 0, root: 2, mode: 'major', progs: [[0, 4, 5, 3], [0, 5, 3, 4]], structure: 'ambient', human: 12,
    drums: { lanes: [{ voice: 'shaker', role: 'perc', pat: P('................', 'x...............'), gain: 0.15 }] },
    bass: { kind: 'drone', pat: P('x...............'), lo: 31, hold: 16 },
    chords: [{ voice: 'pad', pat: P('x...............'), style: 'block', center: 62, ext: 5, hold: 16, gain: 0.8 },
      { voice: 'strings', pat: P('x...............'), style: 'block', center: 69, ext: 3, hold: 16, gain: 0.35 }],
    lead: { voice: 'piano', rhythms: P('x.......x.......', '....x...........', 'x...........x...'), base: 76, len: 8, prob: 0.55, gain: 0.5, pent: true },
    mix: { gains: { drums: 0.3, bass: 0.7, chords: 0.9, lead: 0.55 }, chordsRev: 0.55, leadRev: 0.6, leadDelay: [0.75, 0.5, 0.4], chordsChorus: 0.5, width: 1.5 },
  },
  {
    id: 'cinematic', name: 'Cinematic', aliases: ['cinematic', 'orchestral', 'film score', 'epic', 'trailer', 'score'],
    bpm: 90, swing: 0, root: 2, mode: 'minor', progs: [[0, 5, 2, 6], [0, 3, 5, 4], [0, 6, 5, 6]], structure: 'cinematic', human: 8,
    drums: {
      lanes: [
        { voice: 'tom:lo', role: 'kick', pat: P('x.......x.......', 'x...........x...', 'x.x.....x.......'), gain: 1 },
        { voice: 'tom:mid', role: 'back', pat: P('........x.......', '....x.......x.x.'), gain: 0.65 },
        { voice: 'shaker', role: 'perc', pat: P('x.x.x.x.x.x.x.x.'), gain: 0.2 },
      ],
      fill: 'tom',
    },
    bass: { kind: 'drone', pat: P('x...............'), lo: 29, hold: 16 },
    chords: [{ voice: 'strings', pat: P('x...............'), style: 'block', center: 62, ext: 4, hold: 16, gain: 0.8 },
      { voice: 'brass', pat: P('x.......x.......', 'x...............'), style: 'block', center: 55, ext: 3, hold: 8, gain: 0.55 }],
    lead: { voice: 'strings', rhythms: P('x.......x.......', 'x...x.......x...', 'x.......x...x...'), base: 74, len: 6, prob: 0.9, gain: 0.55, pent: false },
    mix: { gains: { drums: 0.85, bass: 0.8, chords: 0.9, lead: 0.6 }, chordsRev: 0.45, leadRev: 0.45, width: 1.4, drumsSat: 2 },
  },
  {
    id: 'jazz-lounge', name: 'Jazz Lounge', aliases: ['jazz', 'lounge', 'bossa', 'swing', 'bebop', 'piano trio'],
    bpm: 96, swing: 0.33, swingGrid: 8, root: 10, mode: 'major', progs: [[1, 4, 0, 5], [0, 5, 1, 4], [1, 4, 0, 0]], structure: 'groove', human: 11,
    drums: {
      lanes: [
        { voice: 'ride', role: 'hat', pat: P('x...x.x.x...x.x.'), gain: 0.5 },
        { voice: 'hat:pedal', role: 'hat', pat: P('....x.......x...'), gain: 0.45 },
        { voice: 'brush', role: 'back', pat: P('..........g.....', '......g...g...g.', '..g.....g...g...'), gain: 0.6 },
        { voice: 'kick:jazz', role: 'kick', pat: P('x...............', 'x.........g.....', '..........g.....'), gain: 0.6 },
      ],
    },
    bass: { kind: 'walk', pat: P('x...x...x...x...'), lo: 34, hold: 4, walk: true },
    chords: [{ voice: 'piano', pat: P('x.....x.......x.', '..x.......x.....', 'x.........x.....'), style: 'block', center: 62, ext: 5, strumMs: 14, hold: 3, gain: 0.8 }],
    lead: { voice: 'rhodes', rhythms: P('x..x..x.x.......', '..x.x.x...x.x...', 'x.....x.x..x....'), base: 74, len: 2, prob: 0.85, gain: 0.5, pent: false },
    mix: { gains: { drums: 0.8, bass: 0.9, chords: 0.75, lead: 0.5 }, chordsRev: 0.22, leadRev: 0.25, chordsLp: 6500 },
  },
  {
    id: 'r-b-slow-jam', name: 'R&B Slow Jam', aliases: ['r&b', 'rnb', 'r b', 'slow jam', 'neo soul', 'soul'],
    bpm: 72, swing: 0.1, root: 3, mode: 'major', progs: [[1, 4, 0, 5], [0, 5, 3, 4], [3, 2, 1, 4]], structure: 'groove', human: 8,
    drums: {
      lanes: [
        { voice: 'kick:soft', role: 'kick', pat: P('x.....x...x.....', 'x.......x..x....', 'x..x....x...x...') },
        { voice: 'snap', role: 'back', pat: P('........x.......', '........x......g'), gain: 0.9 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.xx', 'x.xox.x.x.xox.x.'), gain: 0.4 },
        { voice: 'rim', role: 'perc', pat: P('............g...'), gain: 0.4 },
      ],
    },
    bass: { kind: 'sub', pat: P('x.....x...x.....', 'x.......x..5..o.'), lo: 32, hold: 6 },
    chords: [{ voice: 'rhodes', pat: P('x.....x.....x...', 'x.......x.......', 'x...x.....x.....'), style: 'block', center: 62, ext: 5, strumMs: 20, hold: 5, gain: 0.8 },
      { voice: 'pad', pat: P('x...............'), style: 'block', center: 64, ext: 4, hold: 16, gain: 0.35 }],
    lead: { voice: 'rhodes', rhythms: P('x..x....x..x....', '..x...x..x.x....', 'x.....x.x...x...'), base: 76, len: 3, prob: 0.85, gain: 0.5, pent: false },
    mix: { gains: { drums: 0.8, bass: 0.9, chords: 0.8, lead: 0.5 }, chordsRev: 0.28, leadRev: 0.3, leadDelay: [0.75, 0.3, 0.2], chordsChorus: 0.3 },
  },
  {
    id: 'pop', name: 'Pop', aliases: ['pop', 'dance pop', 'electropop', 'top 40', 'radio'],
    bpm: 115, swing: 0, root: 7, mode: 'major', progs: [[0, 4, 5, 3], [5, 3, 0, 4], [0, 5, 3, 4]], structure: 'band', human: 3,
    drums: {
      lanes: [
        { voice: 'kick:pop', role: 'kick', pat: P('x...x...x...x...', 'x......xx...x...') },
        { voice: 'clap', role: 'back', pat: P('....x.......x...'), gain: 0.8 },
        { voice: 'snap', role: 'perc', pat: P('....o.......o...'), gain: 0.4 },
        { voice: 'hat', role: 'hat', pat: P('..x...x...x...x.', 'x.x.x.x.x.x.x.xx'), gain: 0.5 },
        { voice: 'ohat', role: 'hat', pat: P('..x.......x.....'), gain: 0.4 },
      ],
    },
    bass: { kind: 'pluck', pat: P('x.x.x.x.x.x.x.x.', 'x..x..x.x..x..x.'), lo: 33, hold: 2, decay: 4 },
    chords: [{ voice: 'piano', pat: P('x...x...x...x...', 'x..x..x.x..x..x.'), style: 'block', center: 62, ext: 3, hold: 3, gain: 0.7 },
      { voice: 'supersaw', pat: P('x...............', 'x.......x.......'), style: 'block', center: 62, ext: 3, hold: 8, gain: 0.35 }],
    lead: { voice: 'pluck', rhythms: P('x..x..x.x..x....', 'x.x.x...x.x.x...', 'x..x..x.x...x.x.'), base: 79, len: 2, prob: 1, gain: 0.6, pent: false },
    mix: { gains: { drums: 0.95, bass: 0.85, chords: 0.7, lead: 0.6 }, pump: 0.3, chordsRev: 0.2, leadRev: 0.25, leadDelay: [0.75, 0.3, 0.2], width: 1.2 },
  },
  {
    id: 'rock', name: 'Rock', aliases: ['rock', 'alt rock', 'garage rock', 'hard rock', 'guitar band', 'punk'],
    bpm: 120, swing: 0.02, root: 4, mode: 'minor', progs: [[0, 6, 5, 6], [0, 5, 6, 0], [0, 3, 6, 0]], structure: 'band', human: 7,
    drums: {
      lanes: [
        { voice: 'kick:rock', role: 'kick', pat: P('x.......x.x.....', 'x.......x.x...x.', 'x..x....x.x.....') },
        { voice: 'snare:rock', role: 'back', pat: P('....x.......x...', '....x.......x..g') },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.', 'x.x.x.x.x.x.x.xo'), gain: 0.65 },
      ],
    },
    bass: { kind: 'electric', pat: P('x.x.x.x.x.x.x.x.', 'x.x.x.x.x.x.5.5.'), lo: 28, hold: 2, drive: 1.8 },
    chords: [{ voice: 'dist', pat: P('x.x.x.x.x.x.x.x.', 'x.x.x.xxx.x.x.x.', 'x...x...x...x...'), style: 'power', center: 52, hold: 2, gain: 0.7 }],
    lead: { voice: 'guitar', rhythms: P('x..x..x.x..x....', 'x.x...x.x.x.....', 'x.....x.x..x.x..'), base: 71, len: 3, prob: 0.9, gain: 0.55, pent: true },
    mix: { gains: { drums: 1, bass: 0.8, chords: 0.7, lead: 0.5 }, chordsRev: 0.14, leadRev: 0.2, drumsSat: 3, width: 1.1 },
  },
  {
    id: 'metal', name: 'Metal', aliases: ['metal', 'heavy metal', 'thrash', 'djent', 'hardcore'],
    bpm: 150, swing: 0, root: 2, mode: 'phrygian', progs: [[0, 0, 1, 0], [0, 5, 0, 1], [0, 0, 6, 5]], structure: 'band', human: 3,
    drums: {
      lanes: [
        { voice: 'kick:metal', role: 'kick', pat: P('xxxxxxxxxxxxxxxx', 'x.x.xxx.x.x.xxx.', 'xxx.xxx.xxx.xxxx') },
        { voice: 'snare:metal', role: 'back', pat: P('....x.......x...', '....x.......x.xx') },
        { voice: 'ride', role: 'hat', pat: P('x...x...x...x...'), gain: 0.4 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.'), gain: 0.4 },
      ],
      fill: 'snare',
    },
    bass: { kind: 'electric', pat: P('xxxxxxxxxxxxxxxx'), lo: 26, hold: 1, drive: 3 },
    chords: [{ voice: 'distPalm', pat: P('xxxxxxxxxxxxxxxx', 'xxx.xxx.xxx.xxx.', 'xxxxxx..xxxxxx..'), style: 'power', center: 50, hold: 1, gain: 0.75 }],
    lead: { voice: 'dist', rhythms: P('x.x.x.x.x.x.x...', 'x..x..x.x..x.x..', 'x.......x...x.x.'), base: 74, len: 3, prob: 0.8, gain: 0.5, pent: false },
    mix: { gains: { drums: 1, bass: 0.7, chords: 0.7, lead: 0.5 }, chordsRev: 0.1, leadRev: 0.2, drumsSat: 4, width: 1.2 },
  },
  {
    id: 'afrobeats', name: 'Afrobeats', aliases: ['afrobeats', 'afrobeat', 'afro', 'amapiano', 'afropop'],
    bpm: 108, swing: 0.07, root: 5, mode: 'major', progs: [[0, 3, 4, 3], [0, 5, 3, 4], [5, 3, 0, 4]], structure: 'groove', human: 6,
    drums: {
      lanes: [
        { voice: 'kick:pop', role: 'kick', pat: P('x.....x...x.....', 'x..x..x...x..x..', 'x.....x...x.x...') },
        { voice: 'clap', role: 'back', pat: P('....x.......x...', '....x......xx...'), gain: 0.7 },
        { voice: 'rim', role: 'perc', pat: P('..x..x..x..x..x.', '..x..x..x.x.....'), gain: 0.5 },
        { voice: 'shaker', role: 'hat', pat: P('xoxoxoxoxoxoxoxo'), gain: 0.5 },
        { voice: 'conga:hi', role: 'perc', pat: P('...x..x...x..x..', '.x...x..x..x....'), gain: 0.5 },
        { voice: 'hat', role: 'hat', pat: P('..x...x...x...x.'), gain: 0.35 },
      ],
    },
    bass: { kind: 'logdrum', pat: P('x..x..x...x..x..', 'x.....x.x..x....', 'x..x..5...x.o...'), lo: 33, hold: 3 },
    chords: [{ voice: 'guitar', pat: P('x.x..x.x.x..x.x.', 'x..x.x..x.x..x..'), style: 'arp', center: 66, ext: 4, hold: 2, gain: 0.8 },
      { voice: 'rhodes', pat: P('x.......x.......', 'x...........x...'), style: 'block', center: 62, ext: 4, hold: 6, gain: 0.5 }],
    lead: { voice: 'pluck', rhythms: P('x..x..x...x..x..', '..x..x.x....x...', 'x.x..x..x.......'), base: 76, len: 2, prob: 0.9, gain: 0.5, pent: true },
    mix: { gains: { drums: 0.9, bass: 0.9, chords: 0.7, lead: 0.5 }, chordsRev: 0.2, leadRev: 0.25, leadDelay: [0.375, 0.3, 0.2], pump: 0.1 },
  },
  {
    id: 'reggaeton', name: 'Reggaeton', aliases: ['reggaeton', 'dembow', 'latin', 'perreo', 'moombahton'],
    bpm: 95, swing: 0, root: 9, mode: 'minor', progs: [[0, 5, 2, 6], [0, 6, 5, 6], [0, 3, 5, 4]], structure: 'groove', human: 4,
    drums: {
      lanes: [
        { voice: 'kick:pop', role: 'kick', pat: P('x...x...x...x...') },
        { voice: 'snare:pop', role: 'back', pat: P('...x..x....x..x.', '...x..x....x..xx'), gain: 0.85 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.'), gain: 0.5 },
        { voice: 'conga:lo', role: 'perc', pat: P('.......x.....x..'), gain: 0.4 },
        { voice: 'shaker', role: 'perc', pat: P('.o.o.o.o.o.o.o.o'), gain: 0.3 },
      ],
    },
    bass: { kind: 'sub808', pat: P('x..x..x.x..x..x.', 'x..x..x.x..x.5..', 'x.....x.x..x..x.'), lo: 30, glide: 0.04, hold: 3, drive: 2 },
    chords: [{ voice: 'pluck', pat: P('x..x..x.x..x..x.', 'x..x..x...x.x...'), style: 'block', center: 64, ext: 3, hold: 2, gain: 0.6 },
      { voice: 'pad', pat: P('x...............'), style: 'block', center: 62, ext: 3, hold: 16, gain: 0.25 }],
    lead: { voice: 'square', rhythms: P('x..x..x.x..x....', 'x.x...x.x...x...', 'x..x..x...x.x.x.'), base: 76, len: 2, prob: 0.95, gain: 0.5, pent: true },
    mix: { gains: { drums: 0.95, bass: 1, chords: 0.6, lead: 0.5 }, pump: 0.2, chordsRev: 0.2, leadRev: 0.2, leadDelay: [0.75, 0.3, 0.2], bassSat: 2 },
  },
  {
    id: 'drum-and-bass', name: 'Drum and Bass', aliases: ['drum and bass', 'drum & bass', 'dnb', 'd&b', 'jungle', 'liquid', 'breakbeat'],
    bpm: 174, swing: 0.02, root: 5, mode: 'minor', progs: [[0, 5, 2, 6], [0, 3, 5, 6], [0, 2, 5, 4]], structure: 'edm', human: 3,
    drums: {
      lanes: [
        { voice: 'kick:dnb', role: 'kick', pat: P('x.........x.....', 'x.........x...x.', 'x....x....x.....') },
        { voice: 'snare:dnb', role: 'back', pat: P('....x.......x...', '....x..g....x..x') },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.', 'x.xxx.x.x.xxx.x.'), gain: 0.5 },
        { voice: 'ride', role: 'perc', pat: P('..x.......x.....'), gain: 0.25 },
      ],
      fill: 'snare',
    },
    bass: { kind: 'reese', pat: P('x.......x.......', 'x.......x..x....', 'x.....x.x.......'), lo: 31, hold: 8 },
    chords: [{ voice: 'rhodes', pat: P('x.......x.......', 'x.....x.....x...'), style: 'block', center: 62, ext: 5, strumMs: 12, hold: 6, gain: 0.7 },
      { voice: 'pad', pat: P('x...............'), style: 'block', center: 62, ext: 4, hold: 16, gain: 0.4 }],
    lead: { voice: 'pluck', rhythms: P('x..x..x...x..x..', '..x...x.x.......', 'x.x..x..x...x...'), base: 76, len: 2, prob: 0.8, gain: 0.4, pent: true },
    mix: { gains: { drums: 0.95, bass: 0.9, chords: 0.65, lead: 0.4 }, pump: 0.3, chordsRev: 0.28, leadRev: 0.28, leadDelay: [0.75, 0.35, 0.22], drumsSat: 3 },
  },
  {
    id: 'dubstep', name: 'Dubstep', aliases: ['dubstep', 'brostep', 'riddim', 'bass music', 'wobble'],
    bpm: 140, swing: 0, root: 5, mode: 'minor', progs: [[0, 0, 5, 6], [0, 5, 0, 6], [0, 1, 0, 5]], structure: 'edm', human: 2,
    drums: {
      lanes: [
        { voice: 'kick:dub', role: 'kick', pat: P('x.........x.....', 'x.......x.x.....', 'x...............') },
        { voice: 'snare:dub', role: 'back', pat: P('........x.......'), gain: 1 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.', 'x.x.xxx.x.x.xxx.'), gain: 0.45 },
        { voice: 'ohat', role: 'perc', pat: P('............x...'), gain: 0.4 },
      ],
      fill: 'snare',
    },
    bass: { kind: 'wobble', pat: P('x...............', 'x.......x.......', 'x.......x.x.....'), lo: 31, lfo: 4.67, hold: 8, drive: 2 },
    chords: [{ voice: 'pad', pat: P('x...............'), style: 'block', center: 60, ext: 4, hold: 16, gain: 0.55 },
      { voice: 'stab', pat: P('x.......x.......', 'x...x...x.......'), style: 'block', center: 62, ext: 3, hold: 1, gain: 0.35 }],
    lead: { voice: 'supersaw', rhythms: P('x...x...x.......', 'x.......x...x...'), base: 74, len: 3, prob: 0.7, gain: 0.45, pent: true },
    mix: { gains: { drums: 1, bass: 0.9, chords: 0.5, lead: 0.4 }, pump: 0.5, chordsRev: 0.3, leadRev: 0.3, drumsSat: 4, bassSat: 3, width: 1.1 },
  },
  {
    id: 'country-pop', name: 'Country Pop', aliases: ['country', 'country pop', 'nashville', 'americana', 'twang'],
    bpm: 104, swing: 0.05, root: 7, mode: 'major', progs: [[0, 3, 4, 3], [0, 4, 5, 3], [0, 3, 0, 4]], structure: 'band', human: 8,
    drums: {
      lanes: [
        { voice: 'kick:rock', role: 'kick', pat: P('x.......x.......', 'x.......x.x.....') },
        { voice: 'snare:pop', role: 'back', pat: P('....x.......x...', '....x.......x..g') },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.'), gain: 0.5 },
        { voice: 'shaker', role: 'perc', pat: P('.o.o.o.o.o.o.o.o'), gain: 0.35 },
      ],
    },
    bass: { kind: 'electric', pat: P('x.......5.......', 'x...x...5...5...'), lo: 31, hold: 4 },
    chords: [{ voice: 'guitar', pat: P('x..xo.x.x..xo.x.', 'x..x..x.x..xo.x.'), style: 'strum', center: 58, ext: 3, hold: 3, strumMs: 16, gain: 0.8 },
      { voice: 'piano', pat: P('x...............', 'x.......x.......'), style: 'block', center: 60, ext: 3, hold: 8, gain: 0.3 }],
    lead: { voice: 'guitar', rhythms: P('x..x..x.x..x....', 'x.x...x.x.x.....', 'x.....x.x..x.x..'), base: 76, len: 2, prob: 0.9, gain: 0.6, pent: true },
    mix: { gains: { drums: 0.85, bass: 0.85, chords: 0.8, lead: 0.55 }, chordsRev: 0.18, leadRev: 0.25, leadDelay: [0.375, 0.25, 0.15] },
  },
  {
    id: 'indie-folk', name: 'Indie Folk', aliases: ['indie', 'folk', 'indie folk', 'acoustic', 'singer songwriter', 'bedroom'],
    bpm: 100, swing: 0.06, root: 2, mode: 'major', progs: [[0, 4, 5, 3], [0, 3, 0, 4], [5, 3, 0, 4]], structure: 'band', human: 10,
    drums: {
      lanes: [
        { voice: 'kick:soft', role: 'kick', pat: P('x.......x.x.....', 'x.......x.......') },
        { voice: 'brush', role: 'back', pat: P('....x.......x...', '....x......gx...'), gain: 0.8 },
        { voice: 'shaker', role: 'hat', pat: P('x.o.x.o.x.o.x.o.'), gain: 0.5 },
        { voice: 'rim', role: 'perc', pat: P('..............g.'), gain: 0.35 },
      ],
    },
    bass: { kind: 'walk', pat: P('x.......5.......', 'x.....x.5.....o.'), lo: 33, hold: 5 },
    chords: [{ voice: 'guitar', pat: P('x.x.x.x.x.x.x.x.'), style: 'arp', center: 58, ext: 4, hold: 2, gain: 0.85 },
      { voice: 'harmonium', pat: P('x...............', 'x.......x.......'), style: 'block', center: 60, ext: 3, hold: 12, gain: 0.35 }],
    lead: { voice: 'piano', rhythms: P('x...x...x.x.....', 'x.....x...x...x.', '..x...x...x.....'), base: 76, len: 4, prob: 0.8, gain: 0.5, pent: true },
    mix: { gains: { drums: 0.7, bass: 0.85, chords: 0.9, lead: 0.5 }, chordsRev: 0.25, leadRev: 0.3, width: 1.2 },
  },
  {
    id: 'gospel-soul', name: 'Gospel Soul', aliases: ['gospel', 'gospel soul', 'church', 'choir', 'praise', 'spiritual'],
    bpm: 88, swing: 0.3, swingGrid: 8, root: 8, mode: 'major', progs: [[0, 5, 3, 4], [0, 3, 0, 4], [3, 4, 5, 0]], structure: 'band', human: 9,
    drums: {
      lanes: [
        { voice: 'kick:soft', role: 'kick', pat: P('x.....x...x.....', 'x.......x.x.....') },
        { voice: 'clap', role: 'back', pat: P('....x.......x...'), gain: 0.7 },
        { voice: 'snare:lofi', role: 'back', pat: P('....x.......x..g'), gain: 0.5 },
        { voice: 'hat', role: 'hat', pat: P('x.x.x.x.x.x.x.x.'), gain: 0.4 },
        { voice: 'shaker', role: 'perc', pat: P('x.o.x.o.x.o.x.o.'), gain: 0.3 },
      ],
    },
    bass: { kind: 'electric', pat: P('x...x...5.....o.', 'x.....x.5...x...'), lo: 31, hold: 4 },
    chords: [{ voice: 'organ', pat: P('x...............', 'x.......x.......'), style: 'block', center: 58, ext: 4, hold: 14, gain: 0.65 },
      { voice: 'piano', pat: P('x..x..x.x..x..x.', 'x.x...x.x.x...x.'), style: 'block', center: 64, ext: 5, strumMs: 10, hold: 2, gain: 0.7 },
      { voice: 'choir', pat: P('x...............', 'x.......x.......'), style: 'block', center: 66, ext: 3, hold: 14, gain: 0.45 }],
    lead: { voice: 'choir', rhythms: P('x..x..x.x.......', 'x.....x.x..x....', 'x.x...x.x.......'), base: 74, len: 4, prob: 0.9, gain: 0.5, pent: true },
    mix: { gains: { drums: 0.75, bass: 0.85, chords: 0.85, lead: 0.5 }, chordsRev: 0.3, leadRev: 0.35, width: 1.3 },
  },
]

export const PROFILE_BY_ID: Record<string, Profile> = Object.fromEntries(PROFILES.map((p) => [p.id, p]))
export const DEFAULT_PROFILE = 'lo-fi-chill'

/** Pick the best profile for free text. Longer, more specific aliases win. */
export function matchProfile(text: string): Profile | null {
  const t = ` ${text.toLowerCase().replace(/[^a-z0-9&]+/g, ' ')} `
  let best: Profile | null = null, bs = 0
  for (const p of PROFILES) {
    for (const a of [p.name.toLowerCase(), ...p.aliases]) {
      const k = ` ${a.replace(/[^a-z0-9&]+/g, ' ')} `
      if (t.includes(k) && a.length + 2 > bs) { bs = a.length + 2; best = p }
    }
  }
  return best
}
export function profileFor(id: string | null | undefined): Profile | null {
  if (!id) return null
  const slug = id.replace(/^genre\//, '')
  return PROFILE_BY_ID[slug] ?? null
}
