"""Tests for all new tools added in the open-source release."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestToolRegistration:
    """Verify all new tools are properly registered."""

    def test_tool_count_at_least_46(self):
        from src.orchestrator.tool_definitions import get_all_tools
        assert len(get_all_tools()) >= 46

    def test_all_tools_have_validators(self):
        from src.orchestrator.tool_definitions import get_tool_names
        from src.orchestrator.tool_validators import TOOL_VALIDATORS
        for name in get_tool_names():
            assert name in TOOL_VALIDATORS, f"Missing validator for {name}"

    def test_all_tools_have_handlers(self):
        from src.orchestrator.tool_definitions import get_tool_names
        from src.orchestrator.tool_executor import _HANDLERS
        for name in get_tool_names():
            assert name in _HANDLERS, f"Missing handler for {name}"


class TestPlayAudioTool:

    def test_validator_valid(self):
        from src.orchestrator.tool_validators import PlayAudio
        v = PlayAudio(wav_path="/tmp/test.wav")
        assert v.wav_path == "/tmp/test.wav"
        assert v.start_s == 0.0

    def test_validator_rejects_empty_path(self):
        from src.orchestrator.tool_validators import PlayAudio
        with pytest.raises(Exception):
            PlayAudio(wav_path="")

    def test_handler_missing_file(self):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("play_audio", {"wav_path": "/nonexistent/file.wav"})
        assert result["status"] == "error"

    @patch("src.audio.player.shutil.which", return_value=None)
    def test_handler_no_player(self, mock_which, tone_wav):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("play_audio", {"wav_path": tone_wav})
        assert result["status"] == "error"
        assert "No audio player" in result["error"]


class TestScoreAudioQuality:

    def test_validator_valid(self):
        from src.orchestrator.tool_validators import ScoreAudioQuality
        v = ScoreAudioQuality(wav_path="/tmp/test.wav")
        assert v.tags == ""

    def test_handler_returns_grade(self, tone_wav):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("score_audio_quality", {"wav_path": tone_wav})
        assert result["status"] == "success"
        assert result["grade"] in ("A", "B", "C", "D", "F")
        assert 0.0 <= result["composite_score"] <= 1.0
        assert "metrics" in result
        assert "recommendation" in result

    def test_handler_missing_file(self):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("score_audio_quality", {"wav_path": "/nonexistent.wav"})
        assert result["status"] == "error"


class TestEffectsTools:

    def test_eq_validator(self):
        from src.orchestrator.tool_validators import ApplyEq
        v = ApplyEq(wav_path="/tmp/t.wav", frequency_hz=1000, gain_db=3.0)
        assert v.q == 1.0

    def test_eq_validator_rejects_out_of_range(self):
        from src.orchestrator.tool_validators import ApplyEq
        with pytest.raises(Exception):
            ApplyEq(wav_path="/tmp/t.wav", frequency_hz=30000, gain_db=3.0)

    def test_reverb_validator_defaults(self):
        from src.orchestrator.tool_validators import ApplyReverb
        v = ApplyReverb(wav_path="/tmp/t.wav")
        assert v.room_size == 0.5
        assert v.decay == 0.4
        assert v.mix == 0.3

    def test_compression_validator(self):
        from src.orchestrator.tool_validators import ApplyCompression
        v = ApplyCompression(wav_path="/tmp/t.wav", threshold_db=-15.0, ratio=6.0)
        assert v.attack_ms == 10.0

    def test_volume_validator(self):
        from src.orchestrator.tool_validators import AdjustVolume
        v = AdjustVolume(wav_path="/tmp/t.wav", gain_db=-6.0)
        assert v.gain_db == -6.0

    @pytest.mark.system
    def test_eq_handler(self, tone_wav, tmp_path):
        from src.orchestrator.tool_executor import execute_tool
        out = str(tmp_path / "eq_out.wav")
        result = execute_tool("apply_eq", {
            "wav_path": tone_wav, "frequency_hz": 1000,
            "gain_db": 3.0, "output_path": out,
        })
        assert result["status"] == "success"
        assert Path(result["output_path"]).exists()

    @pytest.mark.system
    def test_volume_handler(self, tone_wav, tmp_path):
        from src.orchestrator.tool_executor import execute_tool
        out = str(tmp_path / "vol_out.wav")
        result = execute_tool("adjust_volume", {
            "wav_path": tone_wav, "gain_db": -6.0, "output_path": out,
        })
        assert result["status"] == "success"


class TestMixTracksTool:

    def test_validator_requires_min_2_tracks(self):
        from src.orchestrator.tool_validators import MixTracks, MixTrackEntry
        with pytest.raises(Exception):
            MixTracks(tracks=[MixTrackEntry(path="/tmp/a.wav")])

    def test_validator_valid(self):
        from src.orchestrator.tool_validators import MixTracks, MixTrackEntry
        v = MixTracks(tracks=[
            MixTrackEntry(path="/tmp/a.wav"),
            MixTrackEntry(path="/tmp/b.wav", volume_db=-3.0, pan=0.5),
        ])
        assert len(v.tracks) == 2
        assert v.normalize is True

    @pytest.mark.system
    def test_handler(self, tone_wav, silent_wav, tmp_path):
        from src.orchestrator.tool_executor import execute_tool
        out = str(tmp_path / "mix.wav")
        result = execute_tool("mix_tracks", {
            "tracks": [
                {"path": tone_wav, "volume_db": 0},
                {"path": silent_wav, "volume_db": -6},
            ],
            "output_path": out,
        })
        assert result["status"] == "success"


class TestExtractMidiTool:

    def test_validator_valid(self):
        from src.orchestrator.tool_validators import ExtractMidiFromAudio
        v = ExtractMidiFromAudio(audio_path="/tmp/test.wav")
        assert v.onset_threshold == 0.5

    def test_handler_missing_file(self):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("extract_midi_from_audio", {"audio_path": "/nonexistent.wav"})
        assert result["status"] == "error"

    def test_handler_extracts_midi(self, tone_wav, tmp_path):
        from src.orchestrator.tool_executor import execute_tool
        out = str(tmp_path / "extracted.mid")
        result = execute_tool("extract_midi_from_audio", {
            "audio_path": tone_wav, "output_path": out,
        })
        assert result["status"] == "success"
        assert result["note_count"] >= 0
        assert result["method"] in ("basic_pitch", "librosa_piptrack")


class TestCheckTrainingStatus:

    def test_validator_defaults(self):
        from src.orchestrator.tool_validators import CheckTrainingStatus
        v = CheckTrainingStatus()
        assert v.pid == 0
        assert v.voice_name == ""

    def test_handler_list_empty(self):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("check_training_status", {"pid": 0})
        assert result["status"] == "success"
        assert "jobs" in result

    def test_handler_unknown_pid(self):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("check_training_status", {"pid": 99999})
        assert result["status"] == "error"


class TestAnalyzeAudioDimensions:

    def test_validator(self):
        from src.orchestrator.tool_validators import AnalyzeAudioDimensions
        v = AnalyzeAudioDimensions(wav_path="/tmp/test.wav")
        assert v.genre == "pop"

    def test_handler(self, tone_wav):
        from src.orchestrator.tool_executor import execute_tool
        result = execute_tool("analyze_audio_dimensions", {"wav_path": tone_wav, "genre": "pop"})
        assert result["status"] == "success"
        assert "composite_score" in result
        assert "dimensions" in result
        assert isinstance(result["hard_gates_passed"], bool)


class TestBestOfN:

    def test_select_best_single(self, tone_wav):
        from src.orchestrator.tool_executor import _select_best_candidate
        result = _select_best_candidate([tone_wav], 1)
        assert result["status"] == "success"
        assert len(result["wav_paths"]) == 1

    def test_select_best_multiple(self, tone_wav, silent_wav):
        from src.orchestrator.tool_executor import _select_best_candidate
        result = _select_best_candidate([tone_wav, silent_wav], 2)
        assert result["status"] == "success"
        assert result["best_grade"] in ("A", "B", "C", "D", "F")
        assert result["wav_paths"][0] == tone_wav
