import { useEffect, useState } from 'react'
import { audio, isTouchDevice } from '../audio/engine'

const needsFirstTap = () =>
  typeof window !== 'undefined' && (isTouchDevice() || window.innerWidth <= 820) && !/[?&]nogate=1/.test(location.search)

/**
 * Sound gate.
 * - Phones and narrow screens: a first-run "Tap to enable sound" sheet. The tap creates and resumes
 *   the AudioContext inside the gesture, plays a short chime and only hides once the output analyser
 *   (or the media fallback) actually carries signal.
 * - Everywhere: shown again when playback is requested but the browser holds audio (autoplay policy,
 *   a phone call, an iOS interruption).
 */
export function AudioGate() {
  const [, force] = useState(0)
  const [first, setFirst] = useState(needsFirstTap)
  const [phase, setPhase] = useState<'idle' | 'checking' | 'silent'>('idle')
  useEffect(() => audio.subscribe(() => force((x) => x + 1)), [])

  const enable = async () => {
    setPhase('checking')
    const r = await audio.verify()
    if (r.rms > 0.0005) {
      setFirst(false)
      setPhase('idle')
      if (audio.playing && audio.path === 'webaudio') void audio.resume()
    } else setPhase('silent')
  }

  if (first) {
    return (
      <div className="sound-gate" role="dialog" aria-modal="true" aria-label="Enable sound" data-testid="sound-gate-sheet">
        <button className="sound-gate-btn" data-testid="sound-gate" onClick={() => void enable()} disabled={phase === 'checking'}>
          <span className="sg-icon" aria-hidden>
            <svg viewBox="0 0 48 48" width="44" height="44"><path d="M8 18h8l10-8v28l-10-8H8z" fill="currentColor" /><path d="M32 16c3 2 5 5 5 8s-2 6-5 8M36 10c5 3.5 8 8.5 8 14s-3 10.5-8 14" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>
          </span>
          <b>{phase === 'checking' ? 'Checking sound' : phase === 'silent' ? 'Tap again' : 'Tap to enable sound'}</b>
          <span>
            {phase === 'silent'
              ? 'No signal reached the speakers. Turn the volume up, check Bluetooth, then tap again.'
              : 'Phones keep audio off until you tap. You will hear a short chime.'}
          </span>
        </button>
        <p className="sg-tip">On iPhone, sound plays even with the silent switch on. Keep this tab in front while you play.</p>
        <button className="sg-skip" onClick={() => setFirst(false)}>Continue without sound</button>
      </div>
    )
  }
  if (!audio.blocked) return null
  return (
    <button className="audio-gate" data-testid="audio-gate" onClick={() => { audio.unlock(); if (!audio.playing && audio.ids().length) audio.play(); else void audio.resume() }}>
      <b>Tap to enable sound</b>
      <span>Your browser is holding audio until you tap.</span>
    </button>
  )
}
