"""Shared pytest fixtures for The Muser tests.

Provides reusable fixtures for sample scores, mock Claude responses,
temporary directories, and test markers.
"""

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "gpu: requires CUDA GPU")
    config.addinivalue_line("markers", "system: requires system packages")
    config.addinivalue_line("markers", "integration: end-to-end integration tests")


# ---------------------------------------------------------------------------
# Sample MusicXML fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_score():
    """Create a simple 4-bar piano score using music21."""
    import music21

    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = "Piano"
    part.insert(0, music21.instrument.Piano())

    # 4 bars of C major
    for bar_num in range(4):
        measure = music21.stream.Measure(number=bar_num + 1)
        if bar_num == 0:
            measure.append(music21.meter.TimeSignature("4/4"))
            measure.append(music21.key.Key("C"))

        pitches = [
            ["C4", "E4", "G4", "C5"],
            ["D4", "F4", "A4", "D5"],
            ["E4", "G4", "B4", "E5"],
            ["C4", "E4", "G4", "C5"],
        ][bar_num]

        for pitch in pitches:
            measure.append(music21.note.Note(pitch, quarterLength=1.0))

        part.append(measure)

    score.append(part)
    return score


@pytest.fixture
def sample_musicxml_path(tmp_path, sample_score):
    """Write sample score to a MusicXML file and return the path."""
    path = str(tmp_path / "sample.musicxml")
    sample_score.write("musicxml", fp=path)
    return path


@pytest.fixture
def sample_midi_path(tmp_path, sample_score):
    """Write sample score to a MIDI file and return the path."""
    path = str(tmp_path / "sample.mid")
    sample_score.write("midi", fp=path)
    return path


@pytest.fixture
def sample_abc():
    """Return a simple ABC notation string."""
    return "X:1\nT:Test Piece\nM:4/4\nL:1/4\nK:C\nCDEF|GABc|cBAG|FEDC|\n"


@pytest.fixture
def bad_score_rhythm():
    """Create a score with rhythm errors (measure doesn't sum to time sig)."""
    import music21

    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = "Piano"
    measure = music21.stream.Measure(number=1)
    measure.append(music21.meter.TimeSignature("4/4"))
    # Only 3 quarter notes in a 4/4 bar
    for pitch in ["C4", "D4", "E4"]:
        measure.append(music21.note.Note(pitch, quarterLength=1.0))
    part.append(measure)
    score.append(part)
    return score


@pytest.fixture
def bad_score_range():
    """Create a score with out-of-range notes for violin."""
    import music21

    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = "Violin"
    part.insert(0, music21.instrument.Violin())
    measure = music21.stream.Measure(number=1)
    measure.append(music21.meter.TimeSignature("4/4"))
    # C2 is way below violin range (G3)
    measure.append(music21.note.Note("C2", quarterLength=4.0))
    part.append(measure)
    score.append(part)
    return score


@pytest.fixture
def empty_score():
    """Create a score with no notes (only rests)."""
    import music21

    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = "Piano"
    measure = music21.stream.Measure(number=1)
    measure.append(music21.meter.TimeSignature("4/4"))
    measure.append(music21.note.Rest(quarterLength=4.0))
    part.append(measure)
    score.append(part)
    return score


# ---------------------------------------------------------------------------
# Mock Claude API fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_claude_text_response():
    """Create a mock Claude API response with just text."""
    mock_text = MagicMock()
    mock_text.type = "text"
    mock_text.text = "I'll compose a 4-bar piano piece in C major."

    mock_response = MagicMock()
    mock_response.content = [mock_text]
    mock_response.stop_reason = "end_turn"
    return mock_response


@pytest.fixture
def mock_claude_tool_response():
    """Create a mock Claude API response with a tool call."""
    mock_tool = MagicMock()
    mock_tool.type = "tool_use"
    mock_tool.id = "toolu_test123"
    mock_tool.name = "create_composition_plan"
    mock_tool.input = {
        "title": "Test Sonata",
        "genre": "classical",
        "instrumentation": ["Piano"],
        "form": "sonata",
        "key": "C major",
        "tempo": 120,
    }

    mock_response = MagicMock()
    mock_response.content = [mock_tool]
    mock_response.stop_reason = "tool_use"
    return mock_response


@pytest.fixture
def composition_state(tmp_path):
    """Create a fresh CompositionState with a temp directory."""
    from src.orchestrator.composition_state import CompositionState

    state = CompositionState()
    state.project_dir = str(tmp_path / "test_composition")
    return state


# ---------------------------------------------------------------------------
# Audio fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def silent_wav(tmp_path):
    """Create a silent WAV file."""
    import numpy as np
    import soundfile as sf

    audio = np.zeros(44100 * 2, dtype=np.float32)  # 2 seconds silence
    path = str(tmp_path / "silent.wav")
    sf.write(path, audio, 44100)
    return path


@pytest.fixture
def tone_wav(tmp_path):
    """Create a WAV file with a 440Hz tone."""
    import numpy as np
    import soundfile as sf

    t = np.linspace(0, 2, 44100 * 2, dtype=np.float32)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    path = str(tmp_path / "tone.wav")
    sf.write(path, audio, 44100)
    return path


# ---------------------------------------------------------------------------
# Voice pipeline fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def voice_test_audio(tmp_path):
    """Generate a short sine wave WAV suitable for voice pipeline tests.

    Creates a 1-second, 44100 Hz mono WAV with a 220 Hz tone (A3),
    a reasonable fundamental frequency for voice processing tests.
    No GPU required.
    """
    import numpy as np
    import soundfile as sf

    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    # 220 Hz fundamental with a harmonic to mimic a rough vocal timbre
    audio = 0.4 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 440 * t)
    path = str(tmp_path / "voice_test.wav")
    sf.write(path, audio, sample_rate)
    return path


@pytest.fixture
def voice_registry_with_test_model(tmp_path):
    """Provide a temporary voice registry with a placeholder test model entry.

    Registers a fake voice model and cleans it up after the test.
    Returns the voice metadata dict.
    """
    from src.voice.voice_registry import register_voice, remove_voice

    # Create placeholder model files
    model_file = tmp_path / "test_model.pth"
    model_file.write_bytes(b"fake model data")
    index_file = tmp_path / "test_model.index"
    index_file.write_bytes(b"fake index data")

    voice_id = "_test_fixture_voice"
    voice = register_voice(
        voice_id=voice_id,
        name="Test Fixture Voice",
        voice_type="rvc",
        model_path=str(model_file),
        description="Temporary voice for testing",
        index_path=str(index_file),
        gender="male",
        range="baritone",
        use_cases=["testing"],
    )

    yield voice

    # Cleanup
    remove_voice(voice_id)


@pytest.fixture
def tmp_voice_dir(tmp_path):
    """Provide a temporary directory for voice test outputs."""
    voice_dir = tmp_path / "voice_outputs"
    voice_dir.mkdir()
    return str(voice_dir)


# ---------------------------------------------------------------------------
# Curation and quality fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_wav_samples():
    """440Hz sine tone as numpy array — passes all quality gates."""
    import numpy as np

    sr = 44100
    t = np.linspace(0, 3, sr * 3, dtype=np.float32)
    return 0.5 * np.sin(2 * np.pi * 440 * t), sr


@pytest.fixture
def clipped_wav_samples():
    """Audio samples with clipping (values at ±0.999+)."""
    import numpy as np

    sr = 44100
    t = np.linspace(0, 2, sr * 2, dtype=np.float32)
    audio = 2.0 * np.sin(2 * np.pi * 440 * t)
    return np.clip(audio, -1.0, 1.0).astype(np.float32), sr


@pytest.fixture
def silent_wav_samples():
    """Mostly silent audio with a brief gap."""
    import numpy as np

    sr = 44100
    return np.zeros(sr * 3, dtype=np.float32), sr


@pytest.fixture
def stereo_samples():
    """Stereo audio (2-channel) for phase/stereo tests."""
    import numpy as np

    sr = 44100
    t = np.linspace(0, 2, sr * 2, dtype=np.float32)
    left = 0.5 * np.sin(2 * np.pi * 440 * t)
    right = 0.5 * np.sin(2 * np.pi * 440 * t + 0.3)
    return np.stack([left, right]).astype(np.float32), sr


@pytest.fixture
def default_pipeline_config():
    """PipelineConfig with defaults."""
    from src.curation.models import PipelineConfig

    return PipelineConfig()


@pytest.fixture
def sample_musicxml_with_vocals(tmp_path):
    """MusicXML with a vocal part and lyrics for DiffSinger tests."""
    import music21

    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = "Vocals"

    measure = music21.stream.Measure(number=1)
    measure.append(music21.meter.TimeSignature("4/4"))
    measure.append(music21.tempo.MetronomeMark(number=120))

    notes_lyrics = [("C4", "hel"), ("D4", "lo"), ("E4", "world"), ("C4", "now")]
    for pitch, lyric in notes_lyrics:
        n = music21.note.Note(pitch, quarterLength=1.0)
        n.lyric = lyric
        measure.append(n)

    part.append(measure)
    score.append(part)

    path = str(tmp_path / "vocal_score.musicxml")
    score.write("musicxml", fp=path)
    return path
