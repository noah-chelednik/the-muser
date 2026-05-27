# The Muser

**The open-source alternative to Suno and ElevenLabs Music.**
Run locally. Own everything. No subscriptions, no ToS, no limits.

Describe what you want to hear in natural language, and The Muser orchestrates
AI models to produce scores, audio, and vocal performances — entirely on your
hardware.

## Quick Start

```bash
pip install -e "."
ollama pull qwen3:30b-a3b
bash scripts/setup_models.sh
muser
```

> **You:** Compose a 2-minute lo-fi hip hop beat with jazzy piano and vinyl crackle
>
> The Muser generates candidates, selects the best, and exports production-ready audio.

## What It Does

```
User ──► LLM Agent (46 tools) ──► AI Models ──► Your Music
              │                        │
         Plans, validates,        NotaGen (notation)
         iterates, mixes         ACE-Step (audio)
                                 DiffSinger (vocals)
                                 RVC (voice cloning)
```

- **Natural language composition** — describe music in plain English, get professional output
- **46-tool vocabulary** — generation, validation, rendering, voice, effects, mixing, curation
- **Multiple AI models** — NotaGen for classical notation, ACE-Step for modern audio, DiffSinger for singing
- **Full voice pipeline** — RVC voice conversion, Demucs stem separation, feminization presets
- **Quality scoring** — 9-metric analysis with letter grades, best-of-N candidate selection
- **Audio-to-MIDI bridge** — extract sheet music from generated audio
- **Individual effects** — EQ, reverb, compression, volume, mixing — all controllable by the LLM
- **12-dimension curation** — hard gates + soft scores for batch quality control
- **Web UI** — Gradio interface with chat, audio player, and composition status
- **Streaming** — token-by-token LLM responses, no more staring at spinners

## Output Ownership

Every default generation path produces commercially-safe output:

| Path | License | Commercial Use |
|---|---|---|
| ACE-Step audio | Apache 2.0 | **YES** |
| NotaGen notation | MIT | **YES** |
| DiffSinger + Griffin-Lim (default) | Apache 2.0 | **YES** |
| RVC voice conversion | MIT | **YES** |
| FluidSynth/sfizz rendering | LGPL/BSD | **YES** |

See [docs/legal.md](docs/legal.md) for the full breakdown including optional components.

## Installation

### Prerequisites

- Python 3.10+
- NVIDIA GPU with 24GB VRAM (for full pipeline) or CPU-only (LLM orchestration)
- [Ollama](https://ollama.com) for local LLM inference
- ffmpeg, FluidSynth (for audio rendering)

### Full Install

```bash
git clone https://github.com/noah-chelednik/the-muser.git
cd the-muser
python -m venv .venv && source .venv/bin/activate
pip install -e ".[gpu,voice]"       # GPU + voice pipeline
bash scripts/setup_environment.sh   # System tools + Ollama
bash scripts/setup_models.sh        # AI model weights
cp .env.example .env                # Edit as needed
```

### Docker

```bash
docker-compose up muser-gpu    # GPU mode (requires NVIDIA Container Toolkit)
docker-compose up muser-cpu    # CPU-only mode
docker-compose up muser-web    # Web UI at http://localhost:7860
```

## Usage

### CLI

```bash
muser                           # Interactive session
muser -c my-piece               # Resume a composition
muser --stream                  # Streaming responses (default)
muser -m groq/llama-3.3-70b    # Use a specific LLM provider
```

### Web UI

```bash
muser-web                       # Launch at http://localhost:7860
```

### LLM Providers

No paid API key required. The Muser routes to the best available provider:

| Provider | Speed | Cost | Setup |
|---|---|---|---|
| Groq | 300+ tok/s | Free tier | Set `GROQ_API_KEY` |
| Cerebras | 1000+ tok/s | Free tier | Set `CEREBRAS_API_KEY` |
| Gemini | Fast | Free tier | Set `GOOGLE_API_KEY` |
| Ollama (local) | 12-28 tok/s | Free forever | `ollama pull qwen3:30b-a3b` |

## Architecture

```
src/
  orchestrator/    LLM agent loop, 46 tools, composition state
  generation/      AI model wrappers (NotaGen, ACE-Step, DiffSinger)
  audio/           Rendering, validation, effects, mixing, export
  notation/        Format conversion, theory validation, score rendering
  voice/           Voice conversion (RVC, Seed-VC), stem separation
  curation/        12-dimension quality analysis, batch curation
  web/             Gradio web interface
```

See [docs/architecture.md](docs/architecture.md) for the full system design.

## Testing

```bash
pytest tests/ -v -m "not gpu"   # 258+ tests, ~6 seconds
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style,
and the tool-adding guide.

## License

[MIT](LICENSE) — The Muser framework and all original code.

See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for component licenses
and [docs/legal.md](docs/legal.md) for output ownership details.
