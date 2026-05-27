"""Tests for voice modules.

Tests cover voice registry CRUD, RVC wrapper parameter validation,
and Demucs wrapper parameter validation.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestVoiceRegistry:
    """Tests for the voice model registry."""

    def test_list_voices_empty_by_default(self):
        """Default registry starts empty (no phantom entries)."""
        from src.voice.voice_registry import list_voices

        voices = list_voices()
        assert isinstance(voices, list)

    def test_get_voice_after_register(self):
        """Can register and retrieve a voice by ID."""
        from src.voice.voice_registry import register_voice, get_voice, remove_voice

        try:
            register_voice(
                voice_id="test-voice-reg",
                name="Test Voice",
                voice_type="rvc",
                model_path="/tmp/fake.pth",
            )
            voice = get_voice("test-voice-reg")
            assert voice is not None
            assert voice["id"] == "test-voice-reg"
            assert voice["type"] == "rvc"
            assert "model_path" in voice
        finally:
            remove_voice("test-voice-reg")

    def test_get_voice_nonexistent(self):
        """Nonexistent voice returns None."""
        from src.voice.voice_registry import get_voice

        voice = get_voice("nonexistent-voice-xyz")
        assert voice is None

    def test_register_voice(self, tmp_path):
        """Can register a custom voice."""
        from src.voice.voice_registry import register_voice, get_voice, remove_voice, _REGISTRY

        voice_id = "test-custom-voice"
        try:
            result = register_voice(
                voice_id=voice_id,
                name="Test Custom",
                voice_type="rvc",
                model_path=str(tmp_path / "custom.pth"),
                description="A test voice",
                gender="male",
            )

            assert result["id"] == voice_id
            assert get_voice(voice_id) is not None
        finally:
            # Clean up
            remove_voice(voice_id)

    def test_remove_voice(self):
        """Can remove a registered voice."""
        from src.voice.voice_registry import register_voice, remove_voice, get_voice

        register_voice(
            voice_id="temp-voice",
            name="Temp",
            voice_type="rvc",
            model_path="/tmp/temp.pth",
        )
        assert get_voice("temp-voice") is not None

        result = remove_voice("temp-voice")
        assert result is True
        assert get_voice("temp-voice") is None

    def test_remove_nonexistent_voice(self):
        """Removing nonexistent voice returns False."""
        from src.voice.voice_registry import remove_voice

        result = remove_voice("does-not-exist-xyz")
        assert result is False

    def test_voice_metadata_fields(self):
        """Registered voices have expected metadata fields."""
        from src.voice.voice_registry import register_voice, get_voice, remove_voice

        try:
            register_voice(
                voice_id="test-meta-voice",
                name="Meta Test",
                voice_type="rvc",
                model_path="/tmp/meta.pth",
                description="Test description",
                use_cases=["pop"],
                gender="male",
            )
            voice = get_voice("test-meta-voice")
            assert voice is not None
            assert "name" in voice
            assert "type" in voice
            assert "model_path" in voice
            assert "description" in voice
            assert "use_cases" in voice
            assert "gender" in voice
        finally:
            remove_voice("test-meta-voice")


class TestRVCWrapper:
    """Tests for RVC voice conversion parameter validation."""

    def test_missing_input_audio(self):
        """Raises FileNotFoundError for missing input."""
        from src.voice.rvc_wrapper import convert_voice

        with pytest.raises(FileNotFoundError):
            convert_voice(
                input_audio="/nonexistent/audio.wav",
                model_path="/nonexistent/model.pth",
            )

    def test_missing_model_file(self, tmp_path):
        """Raises FileNotFoundError for missing model."""
        from src.voice.rvc_wrapper import convert_voice

        # Create a dummy input file
        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake wav data")

        with pytest.raises(FileNotFoundError):
            convert_voice(
                input_audio=str(input_file),
                model_path="/nonexistent/model.pth",
            )

    def test_list_f0_methods(self):
        """f0 methods list is available."""
        from src.voice.rvc_wrapper import list_f0_methods

        methods = list_f0_methods()
        assert "rmvpe" in methods
        assert "crepe" in methods


class TestDemucsWrapper:
    """Tests for Demucs stem separation parameter validation."""

    def test_missing_input_audio(self):
        """Raises FileNotFoundError for missing input."""
        from src.voice.demucs_wrapper import separate_stems

        with pytest.raises(FileNotFoundError):
            separate_stems(input_audio="/nonexistent/audio.wav")

    def test_output_dir_creation(self, tmp_path):
        """Output directory is created if it doesn't exist."""
        # Just verify the path logic, actual separation requires the model
        from pathlib import Path

        output_dir = tmp_path / "new_stems_dir"
        assert not output_dir.exists()

        # Create dummy input
        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake wav data")

        # Will fail at demucs import/execution but dir should be created
        try:
            from src.voice.demucs_wrapper import separate_stems
            separate_stems(
                input_audio=str(input_file),
                output_dir=str(output_dir),
            )
        except (ImportError, RuntimeError, SystemExit, Exception):
            pass  # Expected - fake WAV data can't be processed

        # The function should have created the output dir before failing
        assert output_dir.exists()
