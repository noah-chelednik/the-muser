"""Environment verification tests.

These tests verify that all required libraries and system tools
are properly installed and configured.
"""

import os
import shutil
import subprocess

import pytest


def test_music21_import():
    """music21 can be imported and can create a basic score."""
    import music21

    s = music21.stream.Score()
    p = music21.stream.Part()
    m = music21.stream.Measure()
    m.append(music21.note.Note("C4", quarterLength=4.0))
    p.append(m)
    s.append(p)
    assert len(s.parts) == 1


def test_music21_musicxml_roundtrip(tmp_path):
    """music21 can write and re-parse MusicXML."""
    import music21

    s = music21.stream.Score()
    p = music21.stream.Part()
    m = music21.stream.Measure()
    m.append(music21.note.Note("C4", quarterLength=4.0))
    p.append(m)
    s.append(p)

    out = tmp_path / "test.musicxml"
    s.write("musicxml", fp=str(out))
    assert out.exists()
    assert out.stat().st_size > 0

    parsed = music21.converter.parse(str(out))
    assert len(parsed.parts) >= 1


@pytest.mark.system
def test_lilypond_available():
    """LilyPond is installed and accessible."""
    from src.orchestrator.config import LILYPOND_PATH

    path = shutil.which("lilypond") or (LILYPOND_PATH if os.path.isfile(LILYPOND_PATH) else None)
    assert path is not None, "lilypond not found in PATH or config"
    result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0


@pytest.mark.system
def test_fluidsynth_available():
    """FluidSynth is installed and accessible."""
    from src.orchestrator.config import FLUIDSYNTH_PATH

    path = shutil.which("fluidsynth") or (
        FLUIDSYNTH_PATH if os.path.isfile(FLUIDSYNTH_PATH) else None
    )
    assert path is not None, "fluidsynth not found in PATH or config"
    result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
    # fluidsynth --version exits 1 on some versions but prints version
    assert "fluidsynth" in (result.stdout + result.stderr).lower()


@pytest.mark.system
def test_ffmpeg_available():
    """ffmpeg is installed and accessible."""
    path = shutil.which("ffmpeg")
    assert path is not None, "ffmpeg not found in PATH"
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0


@pytest.mark.system
def test_musescore_available():
    """MuseScore is installed and accessible (optional)."""
    path = shutil.which("musescore3") or shutil.which("musescore")
    if path is None:
        pytest.skip("MuseScore not installed (optional dependency)")


def test_llm_provider():
    """LLM provider module can be imported and configured."""
    from src.orchestrator.llm_provider import get_provider_chain

    chain = get_provider_chain()
    assert len(chain) > 0


@pytest.mark.gpu
def test_torch_cuda():
    """PyTorch is installed with CUDA support."""
    import torch

    assert torch.cuda.is_available(), "CUDA not available"
    device_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"GPU: {device_name}, VRAM: {vram_gb:.1f} GB")
    assert vram_gb >= 8, f"Insufficient VRAM: {vram_gb:.1f} GB (need >= 8 GB)"


def test_config_imports():
    """Config module can be imported and paths are valid."""
    from src.orchestrator.config import (
        PROJECT_ROOT,
        MODELS_DIR,
        VOICES_DIR,
        SOUNDFONTS_DIR,
        COMPOSITIONS_DIR,
    )

    assert PROJECT_ROOT.exists()
    assert MODELS_DIR.parent == PROJECT_ROOT
    assert VOICES_DIR.parent == PROJECT_ROOT
    assert SOUNDFONTS_DIR.parent == PROJECT_ROOT
    assert COMPOSITIONS_DIR.parent == PROJECT_ROOT
