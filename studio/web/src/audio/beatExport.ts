/** Offline bounce of the pattern playlist to a WAV file. */
import type { Project } from '../types'
import { arrangementSeconds, ensureBeat, hitsAt } from './arrange'
import { buildChain } from './fx'
import { PADS } from './instruments'
import { bufferToWav, download, safeName } from './wav'

export type BeatExportOpts = { bitDepth?: 16 | 24; normalize?: boolean }

function normalizeBuffer(buf: AudioBuffer) {
  let peak = 0
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const data = buf.getChannelData(c)
    for (let i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i]))
  }
  if (peak < 1e-6 || peak <= 1) return
  const gain = 0.99 / peak
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const data = buf.getChannelData(c)
    for (let i = 0; i < data.length; i++) data[i] *= gain
  }
}

export async function exportArrangement(project: Project, opts: BeatExportOpts = {}): Promise<Blob> {
  const beat = ensureBeat(project)
  const arr = beat.arrangement!
  const bpm = Math.max(1, beat.bpm)
  const sr = 44100
  const ctx = new OfflineAudioContext(2, Math.ceil(arrangementSeconds(bpm, arr.bars) * sr), sr)
  const master = buildChain(ctx)
  master.output.connect(ctx.destination)
  master.apply(arr.masterFx)
  const tracks = arr.tracks.map((track) => {
    const chain = buildChain(ctx)
    chain.output.connect(master.input)
    chain.apply(track.fx)
    return chain
  })
  const stepSec = 60 / bpm / 4
  for (let bar = 0; bar < arr.bars; bar++) {
    for (let step = 0; step < 16; step++) {
      const when = (bar * 16 + step) * stepSec
      for (const hit of hitsAt(arr, beat.patterns!, bar, step)) {
        PADS[hit.pad]?.play(when, beat.pads, tracks[hit.track]?.input ?? master.input)
      }
    }
  }
  const rendered = await ctx.startRendering()
  if (opts.normalize) normalizeBuffer(rendered)
  return bufferToWav(rendered, opts.bitDepth ?? 16)
}

export async function downloadArrangement(project: Project, opts: BeatExportOpts = {}) {
  const blob = await exportArrangement(project, opts)
  const bits = opts.bitDepth ?? 16
  download(blob, `${safeName('arrangement')}_${Math.round(project.bpm)}bpm_${bits}bit.wav`)
}
