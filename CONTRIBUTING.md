# Contributing to The Muser

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/noahchelednik/the-muser.git
cd the-muser
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

System dependencies: `ffmpeg`, `fluidsynth` (for audio rendering tests).

## Running Tests

```bash
pytest tests/ -v -m "not gpu"               # CPU tests (default)
pytest tests/ -v -m "not gpu and not system" # Skip system dep tests
pytest tests/ -v --cov=src                   # With coverage
```

## Code Style

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting:
- Line length: 100
- Target: Python 3.10+
- Run `ruff check .` and `ruff format .` before committing

Install pre-commit hooks: `pre-commit install`

## Adding a New Tool

The Muser uses a three-file pattern for every tool:

1. **`src/orchestrator/tool_definitions.py`** — Add the tool schema (Anthropic format with `input_schema`)
2. **`src/orchestrator/tool_validators.py`** — Add a Pydantic `BaseModel` class, register in `TOOL_VALIDATORS`
3. **`src/orchestrator/tool_executor.py`** — Add a `_handle_<tool_name>()` function, register in `_HANDLERS`
4. **`tests/test_new_tools.py`** (or a new test file) — Add validator and handler tests

Every handler returns `{"status": "success", ...}` or `{"status": "error", "error": "..."}`.

## GPL Isolation Rule

LilyPond and MuseScore are **GPL-licensed**. They must ONLY be invoked via `subprocess` — never imported as Python libraries. This maintains MIT license isolation for The Muser. The same applies to `parselmouth` (GPL v3) — it must be behind the `MUSER_FEMINIZE_BACKEND` opt-in flag.

## Pull Request Process

1. Fork the repo and create a feature branch
2. Write tests for new functionality
3. Ensure `pytest tests/ -v -m "not gpu"` passes
4. Ensure `ruff check .` and `ruff format --check .` pass
5. Open a PR with a clear description of changes

## Architecture Overview

See [docs/architecture.md](docs/architecture.md) for the full system design. Key packages:

- `src/orchestrator/` — LLM agent loop, tool system, composition state
- `src/generation/` — AI model wrappers (NotaGen, ACE-Step, DiffSinger)
- `src/audio/` — Rendering, validation, effects, mixing, export
- `src/notation/` — Format conversion, theory validation, score rendering
- `src/voice/` — Voice conversion (RVC, Seed-VC), stem separation (Demucs)
- `src/curation/` — 12-dimension quality analysis and batch curation
- `src/web/` — Gradio web interface
