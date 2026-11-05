import { useEffect, useState } from 'react'
import { audio } from '../audio/engine'

/**
 * Shown only when playback was requested but the browser has not let the audio
 * context run (autoplay policy, a phone call, iOS interruption). One tap fixes it.
 */
export function AudioGate() {
  const [, force] = useState(0)
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])
  if (!audio.blocked) return null
  return (
    <button className="audio-gate" data-testid="audio-gate" onClick={() => { audio.unlock(); void audio.resume() }}>
      <b>Tap to enable sound</b>
      <span>Your browser is holding audio until you tap.</span>
    </button>
  )
}
