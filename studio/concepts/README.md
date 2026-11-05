# The Muser: front end concepts

Three high-fidelity, interactive prototypes of the Studio UI. Each one is a full layout rethink with no colored spheres and no gold. They share one audio engine, one store and one data set, so only the layout, the skin and the motion differ.

| | Concept | Idea |
|---|---|---|
| A | Spectral Terrain | A live WebGL landscape of your sound with the studio drawn as a monochrome HUD over it. |
| B | Engraved Score | Your track as a printed score on paper. Dynamics marks are the macros, vermilion is the playhead. |
| C | Cathode | A graphite rack with a phosphor oscilloscope as the hero and a shelf of cartridges for vibes and presets. |

## Run

```
cd studio/concepts
npm install
npm run dev        # http://127.0.0.1:5173
```

Routes (hash based):

- `#/` index
- `#/a/easy`, `#/a/advanced`
- `#/b/easy`, `#/b/advanced`
- `#/c/easy`, `#/c/advanced`

Demo states go in the query string before the hash, for example `/?s=made,fin#/c/easy`:

- `made`: a finished track is loaded
- `fin`: a finish target has been measured and exported
- `split`: stems are separated
- `eng`: the Engines drawer is open

## What is real

- Web Audio: a built-in demo tone and beat generator, a live analyser feeding every visual, per-stem gain, pan, EQ, compressor and reverb.
- 24 vibes, 5 macros, 105 presets, 8 engines with 8 GB fit badges, undo, redo and revision history.
- Keyboard: press `?` in any concept.
- Generate, Separate, Master and A/B actions are simulated. They update the UI state and the audio, but call no backend.

## Screenshots

```
npm run dev &
npm run shoot            # all concepts
node scripts/shoot.mjs http://127.0.0.1:5173 c   # one concept
```

Output goes to `../../screenshots/concepts/`. Headless Chrome uses SwiftShader for WebGL, so the visuals run on a synthetic signal there.
