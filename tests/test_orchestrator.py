"""Tests for the Claude orchestration layer.

Tests cover tool schema validation, tool executor routing,
composition state CRUD, and mocked Claude API integration.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


class TestToolDefinitions:
    """Tests for tool schema validity."""

    def test_all_tools_have_required_fields(self):
        """Every tool has name, description, and input_schema."""
        from src.orchestrator.tool_definitions import get_all_tools

        tools = get_all_tools()
        assert len(tools) > 0

        for tool in tools:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool['name']} missing 'description'"
            assert "input_schema" in tool, f"Tool {tool['name']} missing 'input_schema'"

    def test_all_tool_names_unique(self):
        """No duplicate tool names."""
        from src.orchestrator.tool_definitions import get_all_tools

        tools = get_all_tools()
        names = [t["name"] for t in tools]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_get_tool_names(self):
        """get_tool_names returns a list of strings."""
        from src.orchestrator.tool_definitions import get_tool_names

        names = get_tool_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)
        assert "create_composition_plan" in names
        assert "generate_audio_acestep" in names
        assert "validate_notation" in names

    def test_input_schemas_are_valid_json_schema(self):
        """Input schemas have required JSON Schema fields."""
        from src.orchestrator.tool_definitions import get_all_tools

        for tool in get_all_tools():
            schema = tool["input_schema"]
            assert schema.get("type") == "object", (
                f"Tool {tool['name']}: input_schema type must be 'object'"
            )
            assert "properties" in schema, (
                f"Tool {tool['name']}: input_schema must have 'properties'"
            )

    def test_expected_tool_count(self):
        """Verify we have all expected tools."""
        from src.orchestrator.tool_definitions import get_all_tools

        tools = get_all_tools()
        # Should have at least 20 tools across all categories
        assert len(tools) >= 20, f"Only {len(tools)} tools defined"


class TestToolExecutor:
    """Tests for tool dispatch and execution."""

    def test_unknown_tool_returns_error(self):
        """Unknown tool names return an error dict."""
        from src.orchestrator.tool_executor import execute_tool

        result = execute_tool("nonexistent_tool", {})
        assert result["status"] == "error"
        assert "Unknown tool" in result["error"]

    def test_create_composition_plan(self, tmp_path):
        """create_composition_plan tool works."""
        from src.orchestrator.composition_state import CompositionState
        from src.orchestrator.tool_executor import execute_tool, set_state

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")
        set_state(state)

        result = execute_tool("create_composition_plan", {
            "title": "Test Piece",
            "genre": "classical",
            "instrumentation": ["Piano"],
        })

        assert result["status"] == "success"
        assert state.project["title"] == "Test Piece"

    def test_update_composition_plan(self, tmp_path):
        """update_composition_plan tool works."""
        from src.orchestrator.composition_state import CompositionState
        from src.orchestrator.tool_executor import execute_tool, set_state

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")
        state.project["title"] = "Test"
        set_state(state)

        result = execute_tool("update_composition_plan", {
            "updates": {"project": {"title": "Updated Test"}},
            "reason": "Testing update",
        })

        assert result["status"] == "success"
        assert state.project["title"] == "Updated Test"

    def test_list_sections_empty(self, tmp_path):
        """list_sections returns empty list for new composition."""
        from src.orchestrator.composition_state import CompositionState
        from src.orchestrator.tool_executor import execute_tool, set_state

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")
        set_state(state)

        result = execute_tool("list_sections", {})
        assert result["status"] == "success"
        assert result["sections"] == []

    def test_generate_notation_claude(self, tmp_path):
        """generate_notation_claude returns compose_inline action."""
        from src.orchestrator.composition_state import CompositionState
        from src.orchestrator.tool_executor import execute_tool, set_state

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")
        set_state(state)

        result = execute_tool("generate_notation_claude", {
            "section_name": "intro",
            "instructions": "Write 4 bars of C major",
            "instruments": ["Piano"],
        })

        assert result["status"] == "success"
        assert result["action"] == "compose_inline"

    def test_execution_time_tracked(self):
        """All tool results include execution_time_s."""
        from src.orchestrator.tool_executor import execute_tool

        result = execute_tool("list_sections", {})
        assert "execution_time_s" in result


class TestCompositionState:
    """Tests for composition state management."""

    def test_create_default_state(self):
        """Default state has expected structure."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        assert state.project["title"] == "Untitled"
        assert state.project["status"] == "planning"
        assert isinstance(state.form_plan, dict)
        assert isinstance(state.theme_catalog, dict)
        assert isinstance(state.completed_sections, dict)

    def test_save_and_load_plan(self, tmp_path):
        """Plan can be saved and loaded."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")
        state.project["title"] = "Test Sonata"
        state.project["genre"] = "classical"
        state.form_plan = {"form": "sonata", "key": "C major"}

        plan_path = state.save_plan()
        assert os.path.exists(plan_path)

        # Load into new state
        state2 = CompositionState()
        state2.project_dir = str(tmp_path / "test_comp")
        state2.load_plan(plan_path)
        assert state2.project["title"] == "Test Sonata"
        assert state2.form_plan["form"] == "sonata"

    def test_save_and_load_section(self, tmp_path):
        """Sections can be saved and loaded."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")

        musicxml = '<?xml version="1.0"?><score-partwise/>'
        state.save_section("intro", musicxml)

        loaded = state.load_section("intro")
        assert loaded == musicxml
        assert "intro" in state.completed_sections

    def test_list_sections(self, tmp_path):
        """list_sections returns section metadata."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")

        state.save_section("intro", "<score/>")
        state.save_section("verse", "<score/>")

        sections = state.list_sections()
        assert len(sections) == 2
        names = [s["name"] for s in sections]
        assert "intro" in names
        assert "verse" in names

    def test_save_and_load_themes(self, tmp_path):
        """Theme catalog can be saved and loaded."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")
        state.theme_catalog = [
            {"name": "Main Theme", "description": "Lyrical melody in C major"},
        ]

        themes_path = state.save_themes()
        assert os.path.exists(themes_path)

        state2 = CompositionState()
        state2.project_dir = str(tmp_path / "test_comp")
        state2.load_themes(themes_path)
        assert len(state2.theme_catalog) == 1
        assert state2.theme_catalog[0]["name"] == "Main Theme"

    def test_update_section_method(self, tmp_path):
        """update_section merges data correctly."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")

        state.update_section("project", {"title": "New Title"})
        assert state.project["title"] == "New Title"

        state.update_section("revision_notes", {"note": "Fixed measure 4"})
        assert len(state.revision_notes) == 1

    def test_to_context_string(self, tmp_path):
        """to_context_string produces compact output."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        state.project_dir = str(tmp_path / "test_comp")
        state.project = {"title": "Test", "genre": "jazz", "status": "composing"}
        state.form_plan = {"form": "AABA", "key": "Bb major", "tempo": 120}
        state.orchestration_state = {"instruments": ["Piano", "Bass", "Drums"]}
        state.completed_sections = {"intro": {"status": "completed"}}

        context = state.to_context_string()
        assert "Test" in context
        assert "jazz" in context
        assert "Piano" in context
        # Should be reasonably compact
        assert len(context) < 5000

    def test_load_missing_plan(self, tmp_path):
        """Loading a missing plan file doesn't crash."""
        from src.orchestrator.composition_state import CompositionState

        state = CompositionState()
        state.project_dir = str(tmp_path / "nonexistent")
        state.load_plan(str(tmp_path / "no_such_file.json"))
        # Should not raise, should keep defaults
        assert state.project["title"] == "Untitled"


class TestGitManager:
    """Tests for composition git operations."""

    def test_init_composition_repo(self, tmp_path):
        """Can initialize a git repo."""
        from src.utils.git_manager import init_composition_repo

        repo_path = str(tmp_path / "test_repo")
        result = init_composition_repo(repo_path)
        assert os.path.exists(os.path.join(result, ".git"))

    def test_commit(self, tmp_path):
        """Can commit changes to a composition repo."""
        from src.utils.git_manager import init_composition_repo, commit

        repo_path = str(tmp_path / "test_repo")
        init_composition_repo(repo_path)

        # Create a file
        test_file = os.path.join(repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("test content")

        commit_hash = commit(repo_path, "Add test file")
        assert commit_hash != ""
        assert len(commit_hash) == 8

    def test_commit_no_changes(self, tmp_path):
        """Commit with no changes returns empty string."""
        from src.utils.git_manager import init_composition_repo, commit

        repo_path = str(tmp_path / "test_repo")
        init_composition_repo(repo_path)

        commit_hash = commit(repo_path, "Nothing to commit")
        assert commit_hash == ""

    def test_log(self, tmp_path):
        """Can retrieve commit log."""
        from src.utils.git_manager import init_composition_repo, commit, log

        repo_path = str(tmp_path / "test_repo")
        init_composition_repo(repo_path)

        test_file = os.path.join(repo_path, "test.txt")
        with open(test_file, "w") as f:
            f.write("content")
        commit(repo_path, "Test commit")

        history = log(repo_path)
        assert len(history) >= 2  # init commit + test commit
        assert any("Test commit" in c["message"] for c in history)


class TestSystemPrompt:
    """Tests for system prompt construction."""

    def test_build_without_state(self):
        """System prompt builds without composition state."""
        from src.orchestrator.system_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "The Muser" in prompt
        assert "music" in prompt.lower()

    def test_build_with_state(self, tmp_path):
        """System prompt includes composition state."""
        from src.orchestrator.composition_state import CompositionState
        from src.orchestrator.system_prompt import build_system_prompt

        state = CompositionState()
        state.project_dir = str(tmp_path / "test")
        state.project = {"title": "My Song", "genre": "pop", "status": "composing"}

        prompt = build_system_prompt(state)
        assert "My Song" in prompt
        assert "pop" in prompt

    def test_prompt_sections_present(self):
        """Key sections are present in the system prompt."""
        from src.orchestrator.system_prompt import build_system_prompt

        prompt = build_system_prompt()
        assert "Composition Director" in prompt
        assert "Muser" in prompt


class TestMockedAgent:
    """Tests for the agent loop with mocked LLM provider."""

    @patch("src.orchestrator.agent.chat")
    def test_agent_turn_no_tools(self, mock_chat, tmp_path):
        """Agent returns text response when no tools are called."""
        from src.orchestrator.agent import run_agent_turn
        from src.orchestrator.llm_provider import LLMResponse
        from src.orchestrator.composition_state import CompositionState

        # Mock the LLM response (no tool calls)
        mock_chat.return_value = LLMResponse(
            content="Hello! I'm The Muser.",
            tool_calls=[],
            raw={},
            provider="mock",
            model="mock-model",
        )

        state = CompositionState()
        state.project_dir = str(tmp_path / "test")

        result = run_agent_turn(
            user_message="Hello",
            conversation_history=[],
            composition_state=state,
        )

        assert "The Muser" in result

    @patch("src.orchestrator.agent.chat")
    def test_agent_llm_failure(self, mock_chat, tmp_path):
        """Agent returns error message when LLM provider fails."""
        from src.orchestrator.agent import run_agent_turn
        from src.orchestrator.composition_state import CompositionState

        mock_chat.side_effect = RuntimeError("All LLM providers failed.")

        state = CompositionState()
        state.project_dir = str(tmp_path / "test")

        result = run_agent_turn(
            user_message="Hello",
            conversation_history=[],
            composition_state=state,
        )

        assert "error" in result.lower() or "failed" in result.lower()
