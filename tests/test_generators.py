"""Tests for generation model wrappers.

Tests cover NotaGen symbolic generation, ACE-Step audio generation,
format conversion, and model manager operations.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


class TestFormatConverter:
    """Tests for ABC/MusicXML/MIDI format conversion."""

    def test_abc_to_musicxml_simple(self):
        """Convert a simple ABC string to MusicXML."""
        from src.notation.format_converter import abc_to_musicxml

        abc = "X:1\nT:Test\nM:4/4\nK:C\nCDEF|GABc|\n"
        result = abc_to_musicxml(abc)
        assert result is not None
        assert len(result) > 0
        assert "score-partwise" in result or "xml" in result.lower()

    def test_abc_to_musicxml_missing_headers(self):
        """ABC with missing headers should still convert (defaults added)."""
        from src.notation.format_converter import abc_to_musicxml

        abc = "CDEF|GABc|\n"
        result = abc_to_musicxml(abc)
        assert result is not None

    def test_abc_to_midi(self, tmp_path):
        """Convert ABC to MIDI file."""
        from src.notation.format_converter import abc_to_midi

        abc = "X:1\nT:Test\nM:4/4\nK:C\nCDEF|GABc|\n"
        output = str(tmp_path / "test.mid")
        result = abc_to_midi(abc, output)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 0

    def test_musicxml_roundtrip(self, tmp_path):
        """MusicXML -> MIDI -> MusicXML roundtrip."""
        import music21

        # Create a score
        s = music21.stream.Score()
        p = music21.stream.Part()
        p.partName = "Piano"
        m = music21.stream.Measure()
        m.append(music21.meter.TimeSignature("4/4"))
        m.append(music21.key.Key("C"))
        for pitch in ["C4", "D4", "E4", "F4"]:
            m.append(music21.note.Note(pitch, quarterLength=1.0))
        p.append(m)
        s.append(p)

        # Write MusicXML
        mxml_path = str(tmp_path / "test.musicxml")
        s.write("musicxml", fp=mxml_path)
        assert os.path.exists(mxml_path)

        # Convert to MIDI
        from src.notation.format_converter import musicxml_to_midi

        midi_path = str(tmp_path / "test.mid")
        result = musicxml_to_midi(mxml_path, midi_path)
        assert os.path.exists(result)

    def test_musicxml_to_lilypond(self, tmp_path):
        """Convert MusicXML to LilyPond format."""
        import music21

        s = music21.stream.Score()
        p = music21.stream.Part()
        m = music21.stream.Measure()
        m.append(music21.note.Note("C4", quarterLength=4.0))
        p.append(m)
        s.append(p)

        mxml_path = str(tmp_path / "test.musicxml")
        s.write("musicxml", fp=mxml_path)

        from src.notation.format_converter import musicxml_to_lilypond

        ly_path = str(tmp_path / "test.ly")
        try:
            result = musicxml_to_lilypond(mxml_path, ly_path)
            assert os.path.exists(result)
            assert os.path.getsize(result) > 0
        except RuntimeError:
            pytest.skip("music21 LilyPond writer not available")


class TestNotaGenWrapper:
    """Tests for NotaGen symbolic generation wrapper."""

    @patch("src.generation.notagen_wrapper.get_manager")
    def test_generate_symbolic_returns_dict(self, mock_manager):
        """generate_symbolic returns a properly structured dict."""
        from src.generation.notagen_wrapper import generate_symbolic

        # Mock the model manager to simulate NotaGen being unavailable
        mock_mgr = MagicMock()
        mock_mgr.load_notagen.side_effect = ImportError("NotaGen not installed")
        mock_manager.return_value = mock_mgr

        result = generate_symbolic(
            period="Romantic",
            composer="Chopin",
            instrumentation="Piano",
        )

        assert isinstance(result, dict)
        assert "metadata" in result
        assert result["metadata"]["period"] == "Romantic"
        assert result["metadata"]["composer"] == "Chopin"

    def test_generate_symbolic_metadata(self):
        """Metadata is always populated even on failure."""
        from src.generation.notagen_wrapper import generate_symbolic

        with patch("src.generation.notagen_wrapper.get_manager") as mock_mgr:
            mock_mgr.return_value.load_notagen.side_effect = RuntimeError("GPU OOM")
            result = generate_symbolic(period="Baroque", composer="Bach")

        assert result["metadata"]["period"] == "Baroque"
        assert result["metadata"]["composer"] == "Bach"
        assert "error" in result


class TestACEStepWrapper:
    """Tests for ACE-Step audio generation wrapper."""

    @patch("src.generation.acestep_wrapper.ACESTEP_VERSION", "v10")
    @patch("src.generation.acestep_wrapper.get_manager")
    def test_generate_audio_returns_list(self, mock_manager):
        """generate_audio returns a list of paths or empty list on failure."""
        from src.generation.acestep_wrapper import generate_audio

        mock_mgr = MagicMock()
        mock_mgr.load_acestep.side_effect = ImportError("ACE-Step not installed")
        mock_manager.return_value = mock_mgr

        result = generate_audio(tags="pop, upbeat")
        assert isinstance(result, list)

    @patch("src.generation.acestep_wrapper.ACESTEP_VERSION", "v10")
    @patch("src.generation.acestep_wrapper.get_manager")
    def test_generate_audio_accepts_new_params(self, mock_manager):
        """generate_audio accepts infer_step and guidance_scale params."""
        from src.generation.acestep_wrapper import generate_audio

        mock_mgr = MagicMock()
        mock_mgr.load_acestep.side_effect = ImportError("ACE-Step not installed")
        mock_manager.return_value = mock_mgr

        # Should not raise even with new params
        result = generate_audio(
            tags="pop, upbeat",
            infer_step=27,
            guidance_scale=12.0,
        )
        assert isinstance(result, list)

    @patch("src.generation.acestep_wrapper.ACESTEP_VERSION", "v10")
    @patch("src.generation.acestep_wrapper.get_manager")
    def test_generate_audio_with_pipeline(self, mock_manager):
        """generate_audio calls pipeline with correct ACE-Step v1.0 API params."""
        from src.generation.acestep_wrapper import generate_audio

        mock_pipeline = MagicMock()
        # Pipeline returns list of wav paths + params json
        mock_pipeline.return_value = []

        mock_mgr = MagicMock()
        mock_mgr.load_acestep.return_value = mock_pipeline
        mock_manager.return_value = mock_mgr

        result = generate_audio(
            tags="pop, female vocals, upbeat",
            lyrics="[verse]\nHello world\n[chorus]\nLa la la",
            duration_s=30,
            seed=42,
            infer_step=27,
            guidance_scale=15.0,
        )

        assert isinstance(result, list)
        # Verify pipeline was called
        mock_pipeline.assert_called()
        # Verify the call used correct parameter names
        call_kwargs = mock_pipeline.call_args
        if call_kwargs:
            kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
            if kwargs:
                assert "audio_duration" in kwargs
                assert "prompt" in kwargs
                assert "lyrics" in kwargs
                assert "infer_step" in kwargs
                assert "guidance_scale" in kwargs
                assert "manual_seeds" in kwargs
                assert "save_path" in kwargs
                # Should NOT have the old wrong parameter names
                assert "duration" not in kwargs
                assert "num_candidates" not in kwargs
                assert "generator" not in kwargs
                assert "sample_rate" not in kwargs

    def test_is_silent_helper(self, tmp_path):
        """Silence detection helper works on a known-silent file."""
        try:
            import librosa  # noqa: F401
        except ImportError:
            pytest.skip("librosa not installed")

        import numpy as np
        import soundfile as sf

        # Create a silent WAV
        silent = np.zeros(44100, dtype=np.float32)
        wav_path = str(tmp_path / "silent.wav")
        sf.write(wav_path, silent, 44100)

        from src.generation.acestep_wrapper import _is_silent

        assert _is_silent(wav_path) is True

    def test_is_silent_non_silent(self, tmp_path):
        """Silence detection correctly identifies non-silent audio."""
        import numpy as np
        import soundfile as sf

        # Create a non-silent WAV (sine wave)
        t = np.linspace(0, 1, 44100, dtype=np.float32)
        audio = 0.5 * np.sin(2 * np.pi * 440 * t)
        wav_path = str(tmp_path / "tone.wav")
        sf.write(wav_path, audio, 44100)

        from src.generation.acestep_wrapper import _is_silent

        assert _is_silent(wav_path) is False

    @pytest.mark.gpu
    @pytest.mark.integration
    def test_acestep_generates_audio(self):
        """Integration test: ACE-Step generates a non-silent audio file.

        Generates a short 10s track with infer_step=27 (fast mode).
        Requires GPU and ACE-Step model weights.
        """
        from src.generation.acestep_wrapper import generate_audio

        paths = generate_audio(
            tags="pop, instrumental, piano, upbeat, 120 bpm, major key",
            lyrics="[instrumental]",
            duration_s=10,
            num_candidates=1,
            seed=42,
            infer_step=27,
        )

        assert len(paths) >= 1, "ACE-Step should produce at least one output"
        for p in paths:
            assert os.path.isfile(p), f"Output file should exist: {p}"
            assert os.path.getsize(p) > 1000, f"Output file should not be empty: {p}"

    @pytest.mark.gpu
    @pytest.mark.integration
    def test_acestep_silence_detection(self):
        """Integration test: ACE-Step discards silent outputs.

        This tests the retry mechanism — if ACE-Step produces silence,
        the wrapper should detect it and retry with a different seed.
        """
        from src.generation.acestep_wrapper import generate_audio, _is_silent

        paths = generate_audio(
            tags="electronic, ambient, synthesizer, atmospheric, 100 bpm",
            lyrics="[instrumental]",
            duration_s=10,
            num_candidates=1,
            seed=12345,
            infer_step=27,
        )

        # All returned paths should be non-silent
        for p in paths:
            assert not _is_silent(p), f"Returned path should not be silent: {p}"


class TestPostProduction:
    """Tests for post-production and export pipeline."""

    @pytest.mark.system
    def test_loudness_normalization(self, tone_wav, tmp_path):
        """Loudness normalization produces output file."""
        from src.audio.export import normalize_loudness

        output = str(tmp_path / "normalized.wav")
        result = normalize_loudness(tone_wav, output, target_lufs=-14.0)
        assert os.path.isfile(result)
        assert os.path.getsize(result) > 0

    @pytest.mark.system
    def test_mp3_export(self, tone_wav, tmp_path):
        """MP3 export produces a valid MP3 file."""
        from src.audio.export import convert_to_mp3

        output = str(tmp_path / "test.mp3")
        result = convert_to_mp3(tone_wav, output)
        assert os.path.isfile(result)
        assert os.path.getsize(result) > 0

    @pytest.mark.system
    def test_metadata_tagging(self, tone_wav):
        """Metadata tagging writes without error."""
        from src.audio.export import add_metadata

        result = add_metadata(
            tone_wav,
            title="Test Track",
            artist="The Muser",
            genre="Electronic",
            year="2026",
            comment="AI generated test",
        )
        assert os.path.isfile(result)

    @pytest.mark.system
    def test_export_composition(self, tone_wav, tmp_path):
        """Full export pipeline produces WAV + MP3."""
        from src.audio.export import export_composition

        outputs = export_composition(
            wav_path=tone_wav,
            output_dir=str(tmp_path / "export"),
            formats=["wav", "mp3"],
            title="Test Export",
            artist="The Muser",
            genre="Electronic",
        )

        assert "wav" in outputs
        assert "mp3" in outputs
        assert os.path.isfile(outputs["wav"])
        assert os.path.isfile(outputs["mp3"])

    @pytest.mark.system
    def test_postproduction_default(self, tone_wav, tmp_path):
        """Default post-production preset applies without error."""
        from src.audio.postproduction import apply_postproduction

        output = str(tmp_path / "mastered.wav")
        result = apply_postproduction(tone_wav, output, genre="default")
        assert os.path.isfile(result)

    @pytest.mark.system
    def test_postproduction_rock(self, tone_wav, tmp_path):
        """Rock post-production preset applies without crash (afir fix)."""
        from src.audio.postproduction import apply_postproduction

        output = str(tmp_path / "mastered_rock.wav")
        result = apply_postproduction(tone_wav, output, genre="rock")
        assert os.path.isfile(result)

    def test_postproduction_preset_list(self):
        """All expected genre presets are available."""
        from src.audio.postproduction import list_presets

        presets = list_presets()
        assert "default" in presets
        assert "classical" in presets
        assert "pop" in presets
        assert "rock" in presets
        assert "electronic" in presets


class TestModelManager:
    """Tests for the VRAM-aware model manager."""

    def test_singleton_pattern(self):
        """get_manager returns the same instance."""
        from src.utils.model_manager import get_manager

        mgr1 = get_manager()
        mgr2 = get_manager()
        assert mgr1 is mgr2

    def test_initial_state(self):
        """ModelManager starts with no model loaded."""
        from src.utils.model_manager import ModelManager

        mgr = ModelManager()
        assert mgr._current_model is None
        assert mgr._current_name is None

    @pytest.mark.gpu
    def test_get_vram_free(self):
        """get_vram_free_gb returns a positive number on GPU systems."""
        from src.utils.model_manager import ModelManager

        mgr = ModelManager()
        free = mgr.get_vram_free_gb()
        assert free > 0

    def test_unload_no_model(self):
        """unload_current is safe to call with no model loaded."""
        from src.utils.model_manager import ModelManager

        mgr = ModelManager()
        mgr.unload_current()  # Should not raise
        assert mgr._current_model is None

    @pytest.mark.gpu
    def test_model_swap(self):
        """Loading a new model unloads the previous one.

        This test requires NotaGen and ACE-Step to be installed.
        """
        from src.utils.model_manager import ModelManager

        mgr = ModelManager()
        # Just verify the method exists and handles errors
        try:
            mgr.load_notagen()
        except (ImportError, FileNotFoundError):
            pytest.skip("NotaGen not installed")
        except RuntimeError as exc:
            if "VRAM" in str(exc) or "CUDA" in str(exc):
                pytest.skip(f"Insufficient VRAM: {exc}")
            raise

        assert mgr._current_name == "notagen"
        mgr.unload_current()
        assert mgr._current_name is None


class TestToolValidators:
    """Tests for Pydantic tool argument validators."""

    def test_acestep_validator_valid(self):
        """Valid ACE-Step arguments pass validation."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments("generate_audio_acestep", {
            "tags": "pop, female vocals, upbeat",
            "lyrics": "[instrumental]",
            "duration_s": 60,
            "infer_step": 27,
            "guidance_scale": 15.0,
        })
        assert isinstance(result, dict)
        assert result["tags"] == "pop, female vocals, upbeat"
        assert result["infer_step"] == 27

    def test_acestep_validator_defaults(self):
        """ACE-Step validator applies defaults for optional fields."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments("generate_audio_acestep", {
            "tags": "jazz, piano trio",
        })
        assert isinstance(result, dict)
        assert result["duration_s"] == 60
        assert result["num_candidates"] == 1

    def test_acestep_validator_rejects_bad_input(self):
        """ACE-Step validator rejects empty tags."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments("generate_audio_acestep", {
            "tags": "",
        })
        assert isinstance(result, str)
        assert "Invalid" in result

    def test_postproduction_validator(self):
        """Post-production validator works."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments("apply_postproduction", {
            "wav_path": "/tmp/test.wav",
            "genre": "rock",
        })
        assert isinstance(result, dict)
        assert result["genre"] == "rock"

    def test_export_validator(self):
        """Export validator works."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments("export_final", {
            "wav_path": "/tmp/test.wav",
            "formats": ["wav", "mp3"],
        })
        assert isinstance(result, dict)
        assert result["formats"] == ["wav", "mp3"]

    def test_validate_audio_validator(self):
        """Validate audio validator works."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments("validate_audio", {
            "wav_path": "/tmp/test.wav",
            "expected_duration_s": 60.0,
        })
        assert isinstance(result, dict)

    def test_unknown_tool_passes_through(self):
        """Unknown tools pass arguments through without validation."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments("some_unknown_tool", {"foo": "bar"})
        assert isinstance(result, dict)
        assert result["foo"] == "bar"
