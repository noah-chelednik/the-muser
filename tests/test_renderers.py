"""Tests for the rendering pipeline.

Tests are organized into tiers:

- **Unit tests** run without any external system tools.
- **System tests** (marked ``@pytest.mark.system``) require LilyPond,
  MuseScore, FluidSynth, and/or ffmpeg to be installed.  Each test
  checks for the required tool and skips gracefully if it is absent.
"""

import shutil
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_musicxml(tmp_path: Path) -> Path:
    """Create a minimal 4-bar C major piano piece as MusicXML.

    Returns:
        Path to the generated ``.musicxml`` file.
    """
    import music21

    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = "Piano"
    part.insert(0, music21.instrument.Piano())

    notes_per_bar = [
        ["C4", "E4", "G4", "C5"],
        ["D4", "F4", "A4", "D5"],
        ["E4", "G4", "B4", "E5"],
        ["C4", "E4", "G4", "C5"],
    ]

    for bar_notes in notes_per_bar:
        measure = music21.stream.Measure()
        for pitch in bar_notes:
            measure.append(music21.note.Note(pitch, quarterLength=1.0))
        part.append(measure)

    score.append(part)

    out = tmp_path / "test_score.musicxml"
    score.write("musicxml", fp=str(out))
    assert out.exists(), "music21 failed to write MusicXML"
    return out


@pytest.fixture()
def sample_midi(tmp_path: Path, sample_musicxml: Path) -> Path:
    """Convert the sample MusicXML fixture to MIDI.

    Returns:
        Path to the generated ``.mid`` file.
    """
    from src.notation.score_renderer import render_midi

    out = tmp_path / "test_score.mid"
    render_midi(str(sample_musicxml), str(out))
    assert out.exists(), "render_midi failed to produce MIDI"
    return out


@pytest.fixture()
def sample_wav(tmp_path: Path) -> Path:
    """Generate a short sine-wave WAV file for audio processing tests.

    This avoids needing FluidSynth or a soundfont just to get a WAV.

    Returns:
        Path to the generated ``.wav`` file.
    """
    import numpy as np
    import soundfile as sf

    sample_rate = 44100
    duration_s = 2.0
    freq_hz = 440.0

    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    signal = 0.5 * np.sin(2 * np.pi * freq_hz * t)

    out = tmp_path / "test_tone.wav"
    sf.write(str(out), signal, sample_rate)
    assert out.exists()
    return out


# ---------------------------------------------------------------------------
# Notation renderer tests
# ---------------------------------------------------------------------------


@pytest.mark.system
def test_lilypond_render_pdf(tmp_path: Path, sample_musicxml: Path) -> None:
    """Render a PDF via LilyPond and verify the output."""
    if not shutil.which("lilypond"):
        pytest.skip("lilypond not found on PATH")
    if not shutil.which("musicxml2ly"):
        pytest.skip("musicxml2ly not found on PATH")

    from src.notation.score_renderer import render_pdf_lilypond

    out = tmp_path / "output.pdf"
    result = render_pdf_lilypond(str(sample_musicxml), str(out))

    result_path = Path(result)
    assert result_path.is_file(), f"PDF not found at {result}"
    assert result_path.stat().st_size > 0, "PDF is empty"


@pytest.mark.system
def test_musescore_render_pdf(tmp_path: Path, sample_musicxml: Path) -> None:
    """Render a PDF via MuseScore and verify the output."""
    if not (shutil.which("musescore3") or shutil.which("musescore")):
        pytest.skip("musescore3/musescore not found on PATH")

    from src.notation.score_renderer import render_pdf_musescore

    out = tmp_path / "output.pdf"
    result = render_pdf_musescore(str(sample_musicxml), str(out))

    result_path = Path(result)
    assert result_path.is_file(), f"PDF not found at {result}"
    assert result_path.stat().st_size > 0, "PDF is empty"


def test_render_midi(tmp_path: Path, sample_musicxml: Path) -> None:
    """Render MIDI from MusicXML and validate the output."""
    from src.notation.score_renderer import render_midi

    out = tmp_path / "output.mid"
    result = render_midi(str(sample_musicxml), str(out))

    result_path = Path(result)
    assert result_path.is_file(), f"MIDI not found at {result}"
    assert result_path.stat().st_size > 0, "MIDI file is empty"

    # Validate that the file is recognizable as MIDI.
    with open(result, "rb") as f:
        header = f.read(4)
    assert header == b"MThd", f"Not a valid MIDI file (header: {header!r})"


# ---------------------------------------------------------------------------
# FluidSynth renderer tests
# ---------------------------------------------------------------------------


@pytest.mark.system
def test_fluidsynth_render(tmp_path: Path, sample_midi: Path) -> None:
    """Render WAV via FluidSynth and verify the output."""
    if not shutil.which("fluidsynth"):
        pytest.skip("fluidsynth not found on PATH")

    from src.audio.fluidsynth_renderer import render_fluidsynth, list_soundfonts

    available = list_soundfonts()
    if not available:
        pytest.skip("No soundfont files found on disk")

    # Use the first available soundfont preset.
    sf_name = next(iter(available))
    out = tmp_path / "output.wav"
    result = render_fluidsynth(str(sample_midi), str(out), soundfont=sf_name)

    result_path = Path(result)
    assert result_path.is_file(), f"WAV not found at {result}"
    assert result_path.stat().st_size > 0, "WAV is empty"


# ---------------------------------------------------------------------------
# Audio export tests
# ---------------------------------------------------------------------------


@pytest.mark.system
def test_convert_to_mp3(tmp_path: Path, sample_wav: Path) -> None:
    """Convert WAV to MP3 and verify the output."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not found on PATH")

    from src.audio.export import convert_to_mp3

    out = tmp_path / "output.mp3"
    result = convert_to_mp3(str(sample_wav), str(out))

    result_path = Path(result)
    assert result_path.is_file(), f"MP3 not found at {result}"
    assert result_path.stat().st_size > 0, "MP3 is empty"


@pytest.mark.system
def test_convert_to_flac(tmp_path: Path, sample_wav: Path) -> None:
    """Convert WAV to FLAC and verify the output."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not found on PATH")

    from src.audio.export import convert_to_flac

    out = tmp_path / "output.flac"
    result = convert_to_flac(str(sample_wav), str(out))

    result_path = Path(result)
    assert result_path.is_file(), f"FLAC not found at {result}"
    assert result_path.stat().st_size > 0, "FLAC is empty"


@pytest.mark.system
def test_normalize_loudness(tmp_path: Path, sample_wav: Path) -> None:
    """Normalize audio loudness and verify the output."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not found on PATH")

    from src.audio.export import normalize_loudness

    out = tmp_path / "output_normalized.wav"
    result = normalize_loudness(str(sample_wav), str(out))

    result_path = Path(result)
    assert result_path.is_file(), f"Normalized WAV not found at {result}"
    assert result_path.stat().st_size > 0, "Normalized WAV is empty"


# ---------------------------------------------------------------------------
# Post-production tests
# ---------------------------------------------------------------------------


def test_postproduction_presets() -> None:
    """Verify all preset names are valid and the list is non-empty."""
    from src.audio.postproduction import GENRE_PRESETS, list_presets

    presets = list_presets()
    assert len(presets) > 0, "No presets defined"
    assert "default" in presets, "'default' preset missing"

    # Every preset should have the required keys.
    for name in presets:
        preset = GENRE_PRESETS[name]
        assert "filters" in preset, f"Preset '{name}' missing 'filters'"
        assert "target_lufs" in preset, f"Preset '{name}' missing 'target_lufs'"
        assert isinstance(preset["filters"], list), f"Preset '{name}' filters not a list"
        assert isinstance(preset["target_lufs"], (int, float)), (
            f"Preset '{name}' target_lufs not numeric"
        )


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


def test_list_soundfonts() -> None:
    """Verify list_soundfonts returns a dict."""
    from src.audio.fluidsynth_renderer import list_soundfonts

    result = list_soundfonts()
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"

    # Values (if any) should be path strings.
    for name, path_str in result.items():
        assert isinstance(name, str)
        assert isinstance(path_str, str)
        assert Path(path_str).is_file(), f"Soundfont path does not exist: {path_str}"
