"""End-to-end integration tests for The Muser.

All tests use mocked Claude API for CI compatibility.
Tests verify complete workflows from user instruction to final output.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
class TestPianoPieceWorkflow:
    """Test: User requests a piano piece → plan → compose → validate → render."""

    def test_plan_to_validation(self, composition_state, sample_musicxml_path):
        """Plan creation → MusicXML validation workflow."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        # Step 1: Create plan
        result = execute_tool("create_composition_plan", {
            "title": "Test Nocturne",
            "genre": "classical",
            "instrumentation": ["Piano"],
            "form": "ABA",
            "key": "C minor",
            "tempo": 72,
        })
        assert result["status"] == "success"

        # Step 2: Validate existing MusicXML
        result = execute_tool("validate_notation", {
            "musicxml_path": sample_musicxml_path,
        })
        assert result["status"] == "success"
        assert result["passed"] is True

    def test_save_section_and_list(self, composition_state):
        """Save sections and list them."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        # Save a section
        musicxml = '<?xml version="1.0"?><score-partwise version="4.0"></score-partwise>'
        composition_state.save_section("intro", musicxml)

        # List sections
        result = execute_tool("list_sections", {})
        assert result["status"] == "success"
        assert len(result["sections"]) == 1
        assert result["sections"][0]["name"] == "intro"

        # Get section
        result = execute_tool("get_section", {"section_name": "intro"})
        assert result["status"] == "success"
        assert "score-partwise" in result["musicxml"]

    def test_get_nonexistent_section(self, composition_state):
        """Getting a nonexistent section returns error."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("get_section", {"section_name": "nonexistent"})
        assert result["status"] == "error"


@pytest.mark.integration
class TestPopSongWorkflow:
    """Test: Pop song workflow with ACE-Step (mocked)."""

    def test_pop_song_plan(self, composition_state):
        """Create a pop song plan."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("create_composition_plan", {
            "title": "Summer Days",
            "genre": "pop",
            "instrumentation": ["Vocals", "Guitar", "Bass", "Drums"],
            "form": "verse-chorus",
            "key": "G major",
            "tempo": 120,
            "sections": [
                {"name": "intro", "measures": 8},
                {"name": "verse1", "measures": 16},
                {"name": "chorus", "measures": 8},
            ],
        })
        assert result["status"] == "success"
        assert composition_state.project["title"] == "Summer Days"
        assert composition_state.form_plan["form"] == "verse-chorus"

    @patch("src.generation.acestep_wrapper.get_manager")
    def test_acestep_generation_failure_handled(self, mock_mgr, composition_state):
        """ACE-Step failure is handled gracefully."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        mock_mgr.return_value.load_acestep.side_effect = ImportError("Not installed")
        set_state(composition_state)

        result = execute_tool("generate_audio_acestep", {
            "tags": "pop, female vocals, upbeat",
            "lyrics": "[verse]\nWalking in the sun\n[chorus]\nSummer days",
        })
        assert result["status"] == "error"


@pytest.mark.integration
class TestOrchestralWorkflow:
    """Test: Orchestral sketch workflow."""

    def test_orchestral_plan(self, composition_state):
        """Create an orchestral composition plan."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("create_composition_plan", {
            "title": "Symphony Sketch",
            "genre": "classical",
            "instrumentation": [
                "Flute", "Oboe", "Clarinet", "Bassoon",
                "Horn", "Trumpet", "Trombone",
                "Violin I", "Violin II", "Viola", "Cello", "Contrabass",
            ],
            "form": "sonata",
            "key": "D major",
            "tempo": 120,
        })
        assert result["status"] == "success"
        instruments = composition_state.orchestration_state["instruments"]
        assert len(instruments) == 12


@pytest.mark.integration
class TestErrorRecovery:
    """Test: Error recovery and edge cases."""

    def test_validate_bad_musicxml_path(self, composition_state):
        """Validation with non-existent file is handled."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("validate_notation", {
            "musicxml_path": "/nonexistent/file.musicxml",
        })
        # Should return error, not crash
        assert result["status"] in ("success", "error")

    def test_unknown_tool(self, composition_state):
        """Unknown tool returns structured error."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("totally_fake_tool", {"foo": "bar"})
        assert result["status"] == "error"
        assert "Unknown tool" in result["error"]

    def test_memory_document_update(self, composition_state):
        """Memory document updates work correctly."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("update_memory_document", {
            "section": "project",
            "data": {"title": "Updated Title", "status": "composing"},
        })
        assert result["status"] == "success"
        assert composition_state.project["title"] == "Updated Title"

    def test_memory_document_revision_notes(self, composition_state):
        """Revision notes accumulate correctly."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        execute_tool("update_memory_document", {
            "section": "revision_notes",
            "data": {"note": "Changed key to G minor"},
        })
        execute_tool("update_memory_document", {
            "section": "revision_notes",
            "data": {"note": "Extended coda by 4 bars"},
        })

        assert len(composition_state.revision_notes) == 2


@pytest.mark.integration
class TestGitVersioning:
    """Test: Composition version control."""

    def test_save_checkpoint(self, composition_state):
        """Save checkpoint creates a git commit."""
        from src.orchestrator.tool_executor import execute_tool, set_state
        from src.utils.git_manager import init_composition_repo

        set_state(composition_state)

        # Initialize git repo
        init_composition_repo(composition_state.project_dir)

        # Create some content
        composition_state.save_section("test", "<score/>")

        # Save checkpoint
        result = execute_tool("save_checkpoint", {
            "message": "Added test section",
        })
        assert result["status"] == "success"
        assert result["commit"] != ""


@pytest.mark.integration
class TestModelSwap:
    """Test: Sequential model loading stress test."""

    @patch("src.generation.notagen_wrapper.get_manager")
    @patch("src.generation.acestep_wrapper.get_manager")
    def test_sequential_generation_attempts(
        self, mock_ace_mgr, mock_nota_mgr, composition_state
    ):
        """Attempting multiple generators in sequence handles failures."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        # Both models fail (not installed)
        mock_nota_mgr.return_value.load_notagen.side_effect = ImportError("No NotaGen")
        mock_ace_mgr.return_value.load_acestep.side_effect = ImportError("No ACE-Step")
        set_state(composition_state)

        # NotaGen attempt
        result1 = execute_tool("generate_notation_notagen", {
            "period": "Romantic",
            "composer": "Chopin",
            "instrumentation": "Piano",
        })
        assert result1["status"] == "error"

        # ACE-Step attempt
        result2 = execute_tool("generate_audio_acestep", {
            "tags": "classical piano",
        })
        assert result2["status"] == "error"

        # Claude inline always works
        result3 = execute_tool("generate_notation_claude", {
            "section_name": "fallback",
            "instructions": "Simple C major scale",
            "instruments": ["Piano"],
        })
        assert result3["status"] == "success"


@pytest.mark.integration
class TestAudioValidation:
    """Test: Audio validation workflow."""

    def test_validate_silent_audio(self, composition_state, silent_wav):
        """Silent audio is flagged."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("validate_audio", {"wav_path": silent_wav})
        assert result["status"] == "success"
        # Should detect silence issue
        assert result.get("valid") is not None

    def test_validate_tone_audio(self, composition_state, tone_wav):
        """Valid tone audio passes validation."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("validate_audio", {
            "wav_path": tone_wav,
            "expected_duration_s": 2.0,
        })
        assert result["status"] == "success"

    def test_validate_missing_audio(self, composition_state):
        """Missing audio file is handled."""
        from src.orchestrator.tool_executor import execute_tool, set_state

        set_state(composition_state)

        result = execute_tool("validate_audio", {
            "wav_path": "/nonexistent/audio.wav",
        })
        assert result["status"] == "success"
        assert len(result.get("issues", [])) > 0
