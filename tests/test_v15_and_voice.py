"""Tests for ACE-Step v1.5 features, voice pipeline, and new tools.

Covers v1.5 wrapper dispatch, validators for new Pydantic models,
repaint/cover/extend tool handlers, voice preprocessing, and
LoRA training tool.
"""

import os
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# v1.5 Validator Tests
# ---------------------------------------------------------------------------


class TestV15Validators:
    """Tests for v1.5-specific Pydantic validators."""

    def test_v15_validator_valid(self):
        """Valid v1.5 arguments pass validation."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "generate_audio_acestep_v15",
            {
                "tags": "A warm jazz piano trio with walking bass",
                "lyrics": "[instrumental]",
                "duration_s": 120,
                "num_candidates": 4,
                "bpm": 120,
                "key_scale": "C major",
                "time_signature": "4/4",
            },
        )
        assert isinstance(result, dict)
        assert result["tags"] == "A warm jazz piano trio with walking bass"
        assert result["duration_s"] == 120
        assert result["num_candidates"] == 4
        assert result["bpm"] == 120

    def test_v15_validator_defaults(self):
        """v1.5 validator applies correct defaults."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "generate_audio_acestep_v15",
            {
                "tags": "pop track",
            },
        )
        assert isinstance(result, dict)
        assert result["duration_s"] == 120
        assert result["num_candidates"] == 1
        assert result["bpm"] is None
        assert result["key_scale"] == ""

    def test_v15_validator_extended_duration(self):
        """v1.5 supports longer duration (up to 600s)."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "generate_audio_acestep_v15",
            {
                "tags": "epic orchestral piece",
                "duration_s": 500,
            },
        )
        assert isinstance(result, dict)
        assert result["duration_s"] == 500

    def test_v15_validator_rejects_too_long(self):
        """v1.5 rejects duration > 600s."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "generate_audio_acestep_v15",
            {
                "tags": "test",
                "duration_s": 700,
            },
        )
        assert isinstance(result, str)
        assert "Invalid" in result

    def test_v15_validator_batch_size(self):
        """v1.5 supports up to 8 candidates."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "generate_audio_acestep_v15",
            {
                "tags": "test",
                "num_candidates": 8,
            },
        )
        assert isinstance(result, dict)
        assert result["num_candidates"] == 8

    def test_repaint_validator_valid(self):
        """Valid repaint arguments pass validation."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "repaint_audio_acestep",
            {
                "src_audio": "/tmp/test.wav",
                "tags": "jazz piano",
                "start_s": 10.0,
                "end_s": 30.0,
            },
        )
        assert isinstance(result, dict)
        assert result["start_s"] == 10.0
        assert result["end_s"] == 30.0

    def test_repaint_validator_rejects_missing_src(self):
        """Repaint requires src_audio."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "repaint_audio_acestep",
            {
                "tags": "jazz",
                "start_s": 0.0,
                "end_s": 10.0,
            },
        )
        assert isinstance(result, str)
        assert "Invalid" in result

    def test_cover_validator_valid(self):
        """Valid cover arguments pass validation."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "cover_audio_acestep",
            {
                "src_audio": "/tmp/test.wav",
                "tags": "rock guitar cover",
                "cover_strength": 0.7,
            },
        )
        assert isinstance(result, dict)
        assert result["cover_strength"] == 0.7

    def test_cover_validator_default_strength(self):
        """Cover defaults to 0.5 strength."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "cover_audio_acestep",
            {
                "src_audio": "/tmp/test.wav",
                "tags": "jazz version",
            },
        )
        assert isinstance(result, dict)
        assert result["cover_strength"] == 0.5

    def test_cover_validator_rejects_bad_strength(self):
        """Cover rejects strength > 1.0."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "cover_audio_acestep",
            {
                "src_audio": "/tmp/test.wav",
                "tags": "test",
                "cover_strength": 1.5,
            },
        )
        assert isinstance(result, str)
        assert "Invalid" in result

    def test_extend_validator_valid(self):
        """Valid extend arguments pass validation."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "extend_audio_acestep",
            {
                "src_audio": "/tmp/test.wav",
                "tags": "continue the melody",
                "extend_s": 60.0,
            },
        )
        assert isinstance(result, dict)
        assert result["extend_s"] == 60.0

    def test_extend_validator_default_duration(self):
        """Extend defaults to 30s."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "extend_audio_acestep",
            {
                "src_audio": "/tmp/test.wav",
                "tags": "more",
            },
        )
        assert isinstance(result, dict)
        assert result["extend_s"] == 30.0


# ---------------------------------------------------------------------------
# v1.5 Tool Definitions Tests
# ---------------------------------------------------------------------------


class TestV15ToolDefinitions:
    """Tests for v1.5 tool definition schemas."""

    def test_v15_tools_present(self):
        """v1.5 tools are included in all tools."""
        from src.orchestrator.tool_definitions import get_tool_names

        names = get_tool_names()
        assert "generate_audio_acestep_v15" in names
        assert "repaint_audio_acestep" in names
        assert "cover_audio_acestep" in names
        assert "extend_audio_acestep" in names

    def test_lora_training_tool_present(self):
        """LoRA training tool is included."""
        from src.orchestrator.tool_definitions import get_tool_names

        names = get_tool_names()
        assert "train_voice_lora" in names

    def test_v15_tool_schemas_valid(self):
        """v1.5 tool schemas have required fields."""
        from src.orchestrator.tool_definitions import get_all_tools

        v15_names = {
            "generate_audio_acestep_v15",
            "repaint_audio_acestep",
            "cover_audio_acestep",
            "extend_audio_acestep",
            "train_voice_lora",
        }
        tools = get_all_tools()
        v15_tools = [t for t in tools if t["name"] in v15_names]

        assert len(v15_tools) == 5, f"Expected 5 v1.5/voice tools, found {len(v15_tools)}"

        for tool in v15_tools:
            schema = tool["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema


# ---------------------------------------------------------------------------
# v1.5 Tool Executor Tests
# ---------------------------------------------------------------------------


class TestV15ToolExecutor:
    """Tests for v1.5 tool handler dispatch."""

    @patch("src.generation.acestep_wrapper.generate_audio")
    def test_generate_v15_handler(self, mock_gen, tmp_path):
        """generate_audio_acestep_v15 handler dispatches correctly."""
        from src.orchestrator.tool_executor import execute_tool

        mock_gen.return_value = ["/tmp/test.wav"]

        result = execute_tool(
            "generate_audio_acestep_v15",
            {
                "tags": "jazz piano",
                "duration_s": 60,
                "num_candidates": 2,
                "bpm": 120,
            },
        )

        assert result["status"] == "success"
        assert "wav_paths" in result

    @patch("src.generation.acestep_wrapper.generate_audio")
    def test_generate_v15_empty_result(self, mock_gen):
        """v1.5 handler returns error on empty output."""
        from src.orchestrator.tool_executor import execute_tool

        mock_gen.return_value = []

        result = execute_tool(
            "generate_audio_acestep_v15",
            {
                "tags": "test",
            },
        )

        assert result["status"] == "error"

    @patch("src.generation.acestep_wrapper.repaint_audio")
    def test_repaint_handler(self, mock_repaint):
        """repaint_audio_acestep handler dispatches correctly."""
        from src.orchestrator.tool_executor import execute_tool

        mock_repaint.return_value = ["/tmp/repainted.wav"]

        result = execute_tool(
            "repaint_audio_acestep",
            {
                "src_audio": "/tmp/source.wav",
                "tags": "jazz",
                "start_s": 10.0,
                "end_s": 20.0,
            },
        )

        assert result["status"] == "success"

    @patch("src.generation.acestep_wrapper.cover_audio")
    def test_cover_handler(self, mock_cover):
        """cover_audio_acestep handler dispatches correctly."""
        from src.orchestrator.tool_executor import execute_tool

        mock_cover.return_value = ["/tmp/covered.wav"]

        result = execute_tool(
            "cover_audio_acestep",
            {
                "src_audio": "/tmp/source.wav",
                "tags": "rock version",
                "cover_strength": 0.6,
            },
        )

        assert result["status"] == "success"

    @patch("src.generation.acestep_wrapper.extend_audio")
    def test_extend_handler(self, mock_extend):
        """extend_audio_acestep handler dispatches correctly."""
        from src.orchestrator.tool_executor import execute_tool

        mock_extend.return_value = ["/tmp/extended.wav"]

        result = execute_tool(
            "extend_audio_acestep",
            {
                "src_audio": "/tmp/source.wav",
                "tags": "continue",
                "extend_s": 30.0,
            },
        )

        assert result["status"] == "success"

    @patch("src.generation.acestep_wrapper.repaint_audio")
    def test_repaint_empty_result(self, mock_repaint):
        """Repaint handler returns error on empty output."""
        from src.orchestrator.tool_executor import execute_tool

        mock_repaint.return_value = []

        result = execute_tool(
            "repaint_audio_acestep",
            {
                "src_audio": "/tmp/source.wav",
                "tags": "jazz",
                "start_s": 0.0,
                "end_s": 10.0,
            },
        )

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# v1.5 Wrapper Dispatch Tests
# ---------------------------------------------------------------------------


class TestACEStepV15Wrapper:
    """Tests for the dual v1.0/v1.5 wrapper dispatch logic."""

    @patch("src.generation.acestep_wrapper.ACESTEP_VERSION", "v10")
    @patch("src.generation.acestep_wrapper.get_manager")
    def test_v10_dispatch(self, mock_manager):
        """generate_audio dispatches to v1.0 when ACESTEP_VERSION=v10."""
        from src.generation.acestep_wrapper import generate_audio

        mock_pipeline = MagicMock()
        mock_pipeline.return_value = []
        mock_mgr = MagicMock()
        mock_mgr.load_acestep.return_value = mock_pipeline
        mock_manager.return_value = mock_mgr

        result = generate_audio(tags="pop, upbeat")
        assert isinstance(result, list)
        mock_mgr.load_acestep.assert_called()

    @patch("src.generation.acestep_wrapper.ACESTEP_VERSION", "v15")
    @patch("src.generation.acestep_wrapper.ACESTEP_V15_API_URL", "")
    @patch("src.generation.acestep_wrapper.get_manager")
    def test_v15_dispatch_calls_load_v15(self, mock_manager):
        """generate_audio dispatches to v1.5 when ACESTEP_VERSION=v15."""
        from src.generation.acestep_wrapper import generate_audio

        mock_mgr = MagicMock()
        mock_mgr.load_acestep_v15.side_effect = RuntimeError("v1.5 not installed")
        mock_manager.return_value = mock_mgr

        # v1.5 dispatch should attempt to load v1.5 handler
        result = generate_audio(tags="pop, upbeat")
        assert isinstance(result, list)
        mock_mgr.load_acestep_v15.assert_called()

    @patch("src.generation.acestep_wrapper.get_manager")
    def test_repaint_audio_calls_v15(self, mock_manager):
        """repaint_audio attempts to load v1.5 model."""
        from src.generation.acestep_wrapper import repaint_audio

        mock_mgr = MagicMock()
        mock_mgr.load_acestep_v15.side_effect = RuntimeError("v1.5 not installed")
        mock_manager.return_value = mock_mgr

        result = repaint_audio(
            src_audio="/tmp/test.wav",
            tags="jazz",
            start_s=0.0,
            end_s=10.0,
        )
        assert isinstance(result, list)
        mock_mgr.load_acestep_v15.assert_called()

    @patch("src.generation.acestep_wrapper.get_manager")
    def test_cover_audio_calls_v15(self, mock_manager):
        """cover_audio attempts to load v1.5 model."""
        from src.generation.acestep_wrapper import cover_audio

        mock_mgr = MagicMock()
        mock_mgr.load_acestep_v15.side_effect = RuntimeError("v1.5 not installed")
        mock_manager.return_value = mock_mgr

        result = cover_audio(
            src_audio="/tmp/test.wav",
            tags="rock version",
        )
        assert isinstance(result, list)
        mock_mgr.load_acestep_v15.assert_called()

    @patch("src.generation.acestep_wrapper.get_manager")
    def test_extend_audio_calls_v15(self, mock_manager):
        """extend_audio attempts to load v1.5 model."""
        from src.generation.acestep_wrapper import extend_audio

        mock_mgr = MagicMock()
        mock_mgr.load_acestep_v15.side_effect = RuntimeError("v1.5 not installed")
        mock_manager.return_value = mock_mgr

        result = extend_audio(
            src_audio="/tmp/test.wav",
            tags="continue",
        )
        assert isinstance(result, list)
        mock_mgr.load_acestep_v15.assert_called()


# ---------------------------------------------------------------------------
# LoRA Training Tool Tests
# ---------------------------------------------------------------------------


class TestTrainVoiceLora:
    """Tests for the LoRA training orchestrator tool."""

    def test_lora_validator_valid(self):
        """Valid LoRA training arguments pass validation."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "train_voice_lora",
            {
                "voice_name": "noah",
                "training_data_dir": "/tmp/training",
                "epochs": 500,
                "lora_rank": 32,
            },
        )
        assert isinstance(result, dict)
        assert result["voice_name"] == "noah"
        assert result["epochs"] == 500

    def test_lora_validator_defaults(self):
        """LoRA validator applies defaults for optional fields."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "train_voice_lora",
            {
                "voice_name": "noah",
                "training_data_dir": "/tmp/training",
            },
        )
        assert isinstance(result, dict)
        assert result["epochs"] == 500
        assert result["lora_rank"] == 32
        assert result["learning_rate"] == 0.0001

    def test_lora_validator_rejects_bad_name(self):
        """LoRA validator rejects names with special characters."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "train_voice_lora",
            {
                "voice_name": "noah's voice",
                "training_data_dir": "/tmp/training",
            },
        )
        assert isinstance(result, str)
        assert "Invalid" in result

    def test_lora_validator_rejects_too_many_epochs(self):
        """LoRA validator rejects epochs > 5000."""
        from src.orchestrator.tool_validators import validate_arguments

        result = validate_arguments(
            "train_voice_lora",
            {
                "voice_name": "test",
                "training_data_dir": "/tmp/training",
                "epochs": 10000,
            },
        )
        assert isinstance(result, str)
        assert "Invalid" in result

    def test_lora_handler_missing_dir(self):
        """LoRA handler returns error for missing training data dir."""
        from src.orchestrator.tool_executor import execute_tool

        result = execute_tool(
            "train_voice_lora",
            {
                "voice_name": "test",
                "training_data_dir": "/nonexistent/path/training",
            },
        )

        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_lora_handler_missing_script(self, tmp_path):
        """LoRA handler returns error when training script missing."""
        from src.orchestrator.tool_executor import execute_tool

        # Create a valid training dir but with non-default script path
        train_dir = str(tmp_path / "training")
        os.makedirs(train_dir)

        with patch("src.orchestrator.config.PROJECT_ROOT", tmp_path):
            result = execute_tool(
                "train_voice_lora",
                {
                    "voice_name": "test",
                    "training_data_dir": train_dir,
                },
            )

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Model Manager v1.5 Tests
# ---------------------------------------------------------------------------


class TestModelManagerV15:
    """Tests for v1.5 model manager additions."""

    def test_unload_tuple_model(self):
        """unload_current handles tuple models (dit + llm handlers)."""
        from src.utils.model_manager import ModelManager

        mgr = ModelManager()
        mock_dit = MagicMock()
        mock_llm = MagicMock()
        mgr._current_model = (mock_dit, mock_llm)
        mgr._current_name = "acestep_v15"

        mgr.unload_current()

        assert mgr._current_model is None
        assert mgr._current_name is None

    def test_load_v15_when_already_loaded(self):
        """load_acestep_v15 returns cached when already loaded."""
        from src.utils.model_manager import ModelManager

        mgr = ModelManager()
        mock_handlers = (MagicMock(), MagicMock())
        mgr._current_model = mock_handlers
        mgr._current_name = "acestep_v15"

        result = mgr.load_acestep_v15()
        assert result is mock_handlers


# ---------------------------------------------------------------------------
# sfizz + VSCO 2 CE Tests
# ---------------------------------------------------------------------------


class TestSfizzVSCO:
    """Tests for sfizz renderer VSCO 2 CE integration."""

    def test_list_sfz_instruments_returns_list(self):
        """list_sfz_instruments returns a list even with no libraries."""
        from src.audio.sfizz_renderer import list_sfz_instruments

        instruments = list_sfz_instruments()
        assert isinstance(instruments, list)

    @patch("src.audio.sfizz_renderer.VSCO_CE_DIR")
    @patch("src.audio.sfizz_renderer.SONATINA_SSO_DIR")
    def test_find_default_sfz_no_libraries(self, mock_sonatina, mock_vsco):
        """_find_default_sfz raises when no libraries found."""
        from src.audio.sfizz_renderer import _find_default_sfz

        mock_vsco.is_dir.return_value = False
        mock_sonatina.is_dir.return_value = False

        with pytest.raises(FileNotFoundError):
            _find_default_sfz()


# ---------------------------------------------------------------------------
# AutoGen Loop Tests
# ---------------------------------------------------------------------------


class TestAutoGenLoop:
    """Tests for the AutoGen continuous generation loop."""

    def test_leaderboard_sorting(self):
        """Leaderboard sorts candidates by score descending."""
        import sys

        sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "scripts")))
        from autogen_loop import Leaderboard, Candidate

        lb = Leaderboard()
        lb.add(Candidate(path="/a.wav", score=0.5, seed=1, round_idx=0, generation_time_s=1.0))
        lb.add(Candidate(path="/b.wav", score=0.9, seed=2, round_idx=0, generation_time_s=1.0))
        lb.add(Candidate(path="/c.wav", score=0.7, seed=3, round_idx=1, generation_time_s=1.0))

        assert lb.best.score == 0.9
        assert lb.best.path == "/b.wav"
        assert lb.count == 3

        top2 = lb.top(2)
        assert top2[0].score == 0.9
        assert top2[1].score == 0.7

    def test_leaderboard_empty(self):
        """Leaderboard handles empty state."""
        import sys

        sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "scripts")))
        from autogen_loop import Leaderboard

        lb = Leaderboard()
        assert lb.best is None
        assert lb.count == 0
        assert lb.top(5) == []

    def test_leaderboard_to_list(self):
        """Leaderboard serializes to list of dicts."""
        import sys

        sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..", "scripts")))
        from autogen_loop import Leaderboard, Candidate

        lb = Leaderboard()
        lb.add(Candidate(path="/a.wav", score=0.5, seed=1, round_idx=0, generation_time_s=1.0))

        data = lb.to_list()
        assert len(data) == 1
        assert data[0]["path"] == "/a.wav"
        assert data[0]["score"] == 0.5
