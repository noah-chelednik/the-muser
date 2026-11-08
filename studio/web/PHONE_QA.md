# Phone audio + six-layout QA

## Automated checks

From `studio/web`:

- `npx tsc -b --pretty false`
- `npm run build`
- `npm run test:phone-audio`

The last command executes the real engine against deterministic browser/audio
API doubles. It checks the running-but-muted-context branch, stale Safari stream
preferences, persistent element priming, media-first Android playback, direct
desktop playback, bounce caching/replacement, stop cancellation, permission
retry, broken mix URL fallback, mixer refresh, and generation auto-start wiring.
These are regression checks, **not proof that a physical speaker is audible**.

## Physical-device acceptance (not performed in this environment)

1. On an iPhone in Safari, start a fresh session at 390px-ish width. Enable sound
   and hear the chime. Repeat with the hardware silent switch enabled. Also test
   an iPad reporting a Macintosh user agent. Disable Bluetooth for speaker tests.
2. Wait at least ten seconds after the chime. Choose a vibe, tap Make and wait
   through generation. The track should start automatically without another tap.
   `window.__muser.audio.path` should be `media`, even if `ctx.state` is `running`.
   The audible source is an unmuted, gesture-primed HTMLAudioElement using
   `Track.url`, not a Web Audio MediaStream. The same element is retained.
3. Pause, interact with unrelated controls, and confirm it stays paused. Tap Play,
   seek, loop, and select a region. Confirm stop cancels a pending offline bounce.
4. Import an audio file. It should auto-play after decoding on a phone. With no
   usable full-mix URL, or after mixer/FX edits, it should play an offline-rendered
   WAV through the same element. Check mute/solo, master gain, FX and export.
5. Repeat in Android Chrome. Loaded tracks use normal file media playback; the
   live AudioContext/direct graph remains available for pads/keys. Repeat on
   desktop: tracks should still use direct Web Audio and exports should render.
6. Test a browser autoplay denial and tap the sound-retry banner. It now retries
   the loaded track, not just `AudioContext.resume()`. Lock/unlock the phone and
   switch apps; if the OS revokes playback permission, a fresh tap may be needed.

## Layout acceptance

- At 390px and 1280px, cycle Cathode → Terrain → Score → Horology → Metro → Vend.
- The skin trigger is a separate pinned header cell. Swipe/keyboard-scroll the
  adjacent toolbar to reach modes, readouts, demo badge, NoDAW, system, engines
  and help. Safe-area padding keeps it clear of notches.
- At phone widths the picker is a fixed, full-width bottom sheet, with all six
  unique SVG thumbnails, names, tags and descriptions in two columns. Scroll to
  the last card. Escape / close / backdrop dismiss it; focus returns to trigger.
- Horology: radial macro complications and crown transport; advanced control
  room remains a circular atelier, with existing DAW panes beneath.
- Metro: stations on coloured transit lines, boarding pass, DEPART action,
  parallel stem routes and a playhead train.
- Vend: lit product windows and selection codes, LED readout, dispense action,
  animated audio collection tray; advanced tools inside a service hatch.
- Test Easy/Advanced, prompt, make, play, shaping, finishing/export, and advanced
  Mix / Pads-Keys-Arranger / Library / Compose in all new layouts.
- Check keyboard focus, picker focus cycling and reduced-motion preference.

## Known trade-offs

- Phone mixer/FX changes regenerate a cached offline WAV (debounced 180ms), not
  live per-sample processing. Long tracks can take time/memory to re-render.
- While phone tracks use media playback, live Web Audio analyser meters are not
  evidence of speaker audibility and do not mirror the offline file's spectrum.
- An OS interruption or stricter iOS autoplay policy can still require a new tap;
  failure remains visible/retryable instead of silently claiming playback.
- Live iOS pads/keys still depend on the direct AudioContext/audio-session route;
  this change addresses generated/imported track output, not a media-based
  low-latency instrument engine.
