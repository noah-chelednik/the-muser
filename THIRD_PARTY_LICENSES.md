# Third-Party Licenses

The Muser incorporates or interfaces with the following third-party components.
See [NOTICE](NOTICE) for full attribution text.

## Core Framework (MIT)

The Muser itself is MIT-licensed. All code in `src/` is original work by
The Muser Contributors.

## AI Models

| Model | License | Usage | Commercial Output |
|---|---|---|---|
| ACE-Step v1.0 | Apache 2.0 | Audio generation | YES |
| ACE-Step v1.5 | MIT | Audio generation | YES |
| NotaGen | MIT | Symbolic notation | YES |
| Applio / RVC | MIT | Voice conversion | YES |
| Demucs | MIT | Stem separation | YES |
| Seed-VC | MIT | Zero-shot voice conversion | YES |

## Vocoders (Critical for DiffSinger)

| Vocoder | License | Default? | Commercial Output |
|---|---|---|---|
| Griffin-Lim | N/A (algorithm) | **YES (default)** | YES |
| fish-hifigan | Apache 2.0 | Recommended upgrade | YES |
| NSF-HiFiGAN (OpenVPI) | **CC-BY-NC-SA 4.0** | Opt-in only | **NO** |

## Subprocess Tools (GPL — Isolated)

These are invoked as external processes only. GPL does not affect The Muser's
MIT license or restrict the output files.

| Tool | License | Usage |
|---|---|---|
| LilyPond | GPL v3 | PDF score rendering |
| MuseScore | GPL v3 | PDF/PNG rendering |
| Praat | GPL v2 | Formant analysis (CLI mode) |

## Optional GPL Components (User Opt-In)

These are **never required** and **never installed by default**. Users who
choose to install them accept the GPL implications.

| Component | License | What It Does | Safe Alternative |
|---|---|---|---|
| parselmouth | GPL v3 | Python Praat bindings for formant shifting | Praat CLI (default) |
| phonemizer | GPL v3 | Grapheme-to-phoneme conversion | g2p_en (Apache 2.0, default) |

## Python Libraries

| Library | License |
|---|---|
| LiteLLM | MIT |
| Pydantic | MIT |
| music21 | BSD |
| librosa | ISC |
| PyTorch | BSD |
| soundfile | BSD |
| numpy / scipy | BSD |
| Click | BSD |
| Rich | MIT |
| GitPython | BSD |
| pretty-midi | MIT |
| lxml | BSD |
| pyfluidsynth | LGPL 2.1 |
| Gradio | Apache 2.0 |
| basic-pitch | Apache 2.0 |

## Soundfonts

| Soundfont | License |
|---|---|
| FluidR3_GM | MIT |
| VSCO 2 Community Edition | CC0 (Public Domain) |
| Sonatina Symphonic Orchestra | CC Sampling Plus 1.0 |

## LLM Providers

| Provider | License |
|---|---|
| Qwen3 (via Ollama) | Apache 2.0 |
| Llama 3.3 (via Groq/Cerebras) | Llama 3.3 Community |
| Gemini (via Google) | Google API ToS |
| Claude (via Anthropic) | Anthropic API ToS |

LLM providers generate orchestration instructions only — they do not generate
the music itself. The LLM's license does not affect ownership of your compositions.
