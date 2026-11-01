# Output Ownership & Legal Guide

## TL;DR

Audio you generate with The Muser is yours. Every default generation path uses
permissively-licensed models (Apache 2.0 or MIT). You can sell, distribute, and
commercially use your compositions without restriction.

## Output Ownership by Generation Path

| Generation Path | Model License | Commercial Use | Notes |
|---|---|---|---|
| ACE-Step v1.0/v1.5 → audio | Apache 2.0 | **YES** | Primary audio generation |
| NotaGen → notation → FluidSynth → audio | MIT + LGPL 2.1 | **YES** | Classical/symbolic path |
| DiffSinger + Griffin-Lim (default) | Apache 2.0 | **YES** | Safe default vocoder |
| DiffSinger + fish-hifigan | Apache 2.0 | **YES** | Recommended upgrade |
| DiffSinger + NSF-HiFiGAN (opt-in) | CC-BY-NC-SA 4.0 | **NO** | Requires `MUSER_VOCODER_NC_ACK=true` |
| RVC voice conversion | MIT | **YES** | Respect source voice IP |
| Demucs stem separation | MIT | **YES** | |
| LilyPond PDF rendering | GPL (subprocess) | **YES** | GPL does not restrict output |
| sfizz + VSCO 2 CE rendering | BSD + CC0 | **YES** | |

## Studio tools (all-in-one fork)

The Studio's auto-selector is commercial-safe by default: it only picks tools marked "Yes" or
"Conditions" below, and it never picks a personal-use tool on its own.

| Tool | License | Commercial output | Notes |
|---|---|---|---|
| Built-in sketch synth, band split, DSP, pitch tracker | MIT | **YES** | Part of this repo |
| Spotify Pedalboard | GPL-3.0 | **YES** | Library use; GPL covers code, not your audio |
| Matchering 2 | GPL-3.0 | **YES** | Same as Pedalboard |
| pyloudnorm, noisereduce | MIT | **YES** | |
| Basic Pitch | Apache 2.0 | **YES** | |
| Demucs v4 | MIT | **YES** | |
| DeepFilterNet 3 | MIT or Apache 2.0 | **YES** | |
| Audio Separator (UVR models) | MIT, varies per model | **CONDITIONS** | Check each model's card |
| Karaoke and denoise Roformer weights (aufr33, viperx) | Not stated | **CONDITIONS** | Opt-in, labelled "licence unstated", never auto-picked. The anvuew de-reverb weights are GPL-3.0 and are deliberately not offered. |
| stemsep, TramEFX stem-separator, nussl | MIT | n/a | Ideas only, no code shipped. nussl is only the inspiration for a dev benchmark script |
| ACE-Step 1.5 | MIT | **YES** | Default generator, runs on 8 GB cards |
| DiffRhythm | Apache 2.0 | **YES** | |
| AudioSR, Resemble Enhance | MIT | **YES** | |
| Stable Audio Open | Stability AI Community License | **CONDITIONS** | Free under 1M USD yearly revenue |
| YuE | CC BY-NC 4.0 weights per model card, code Apache 2.0 | **CONDITIONS** | Individuals: attribution; companies need a license |
| Applio (RVC), Seed-VC | MIT / GPL-3.0 | **CONDITIONS** | Get consent for any voice you clone |
| MusicGen | CC BY-NC 4.0 weights | **NO** | Personal use only |
| AudioLDM 2 | CC BY-NC-SA 4.0 weights | **NO** | Personal use only |
| SongGeneration / LeVo | Tencent custom, research only | **NO** | Personal use only |

### GPL tools used as libraries

Pedalboard and Matchering are GPL-3.0 Python libraries. Running them on your own machine and selling
the audio they process is fine: the GPL applies to the software, not to your output. If you
redistribute a modified copy of the Studio, publish its source under the GPL as well.

## Important Caveats

### Training Data Provenance

The AI models used by The Muser (ACE-Step, NotaGen, etc.) were trained on
datasets that may include copyrighted music. This is the same legal gray area
that every AI music company (Suno, ElevenLabs, etc.) operates in. Your legal
exposure is no greater than using any commercial AI music service, and
potentially less, since there is no platform ToS complicating your ownership.

### Voice Cloning Ethics

If you train a voice model (RVC LoRA) using someone else's voice, you are
responsible for obtaining appropriate consent. The Muser provides the tools;
you are responsible for how you use them.

### GPL-Licensed Components

The following components are GPL-licensed and require special handling:

- **LilyPond** (GPL v3): Invoked only as external subprocess. GPL does not
  restrict the license of output files (PDFs, PNGs).
- **MuseScore** (GPL v3): Same subprocess isolation as LilyPond.
- **parselmouth** (GPL v3): Optional. Only used if `MUSER_FEMINIZE_BACKEND=parselmouth`.
  Default is `praat_cli` (subprocess-isolated).
- **phonemizer** (GPL v3): Optional. Never required. The Muser uses `g2p_en`
  (Apache 2.0) by default for grapheme-to-phoneme conversion.

### AI Disclosure

Some jurisdictions and platforms (e.g., DistroKid, Spotify) require disclosure
that content was created with AI assistance. The Muser adds a `LICENSE_INFO.txt`
alongside exported compositions listing the models used.

## Component License Summary

See [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md) for full license texts.
See [NOTICE](../NOTICE) for attribution requirements.
