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

## Important Caveats

### Training Data Provenance

The AI models used by The Muser (ACE-Step, NotaGen, etc.) were trained on
datasets that may include copyrighted music. This is the same legal gray area
that every AI music company (Suno, ElevenLabs, etc.) operates in. Your legal
exposure is no greater than using any commercial AI music service — and
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
