import type { Arrangement } from '../types'
import { audio } from './engine'
import { buildChain, type Chain } from './fx'

let tracks: Chain[] = []
let master: Chain | null = null

function dispose() {
  tracks.forEach((chain) => chain.dispose())
  master?.dispose()
  tracks = []
  master = null
}

export function syncArrangeGraph(arrangement: Arrangement) {
  const ctx = audio.ensure()
  if (!master || tracks.length !== arrangement.tracks.length) {
    dispose()
    master = buildChain(ctx)
    master.output.connect(audio.instBus)
    tracks = arrangement.tracks.map(() => {
      const chain = buildChain(ctx)
      chain.output.connect(master!.input)
      return chain
    })
  }
  tracks.forEach((chain, i) => chain.apply(arrangement.tracks[i].fx, { live: true }))
  master.apply(arrangement.masterFx, { live: true })
}

export function trackInput(index: number) {
  return tracks[index]?.input ?? audio.instBus
}

export function disposeArrangeGraph() {
  dispose()
}
