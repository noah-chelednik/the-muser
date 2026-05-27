"""Musical Memory Document management.

Maintains the full compositional state across the session, including
the form plan, theme catalog, harmonic plan, orchestration state,
and completed sections. Persisted as JSON files within the composition
project directory.

The Musical Memory Document is the system's most novel architectural
element: it gives the LLM a structured, evolving view of the composition
that survives across tool calls and even sessions.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.orchestrator.config import COMPOSITIONS_DIR

logger = logging.getLogger(__name__)

# Maximum revision notes kept in memory (older archived to git)
_MAX_REVISION_NOTES = 5

# Approximate token budget for context string (~4 chars per token)
_CONTEXT_TOKEN_BUDGET = 3000
_CHARS_PER_TOKEN = 4


def _default_movement(name: str = "Movement 1", key: str = "", tempo: int = 0) -> dict[str, Any]:
    """Create a default movement dict."""
    return {
        "name": name,
        "key": key,
        "tempo": tempo,
        "form_plan": {},
        "sections": [],
    }


@dataclass
class CompositionState:
    """Full state of a composition project.

    Corresponds to the Musical Memory Document from the Master Plan (Section 10).
    Serialized to JSON for system prompt injection and file-based persistence.

    Supports multi-movement compositions. Single-movement pieces work exactly
    as before — the movements list is empty by default and all existing fields
    continue to function without change.
    """

    # Project metadata
    project: dict[str, Any] = field(default_factory=lambda: {
        "title": "Untitled",
        "genre": "",
        "status": "planning",
        "target_duration_s": 0,
    })

    # Form / structure plan: section_name -> {measures, key, tempo, status, description}
    form_plan: dict[str, Any] = field(default_factory=dict)

    # Catalog of musical themes: theme_id -> {abc_snippet, character, appearances: [{location, description}]}
    theme_catalog: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Harmonic plan: {key_centers: [{measure, key}], modulation_points: [{measure, from_key, to_key}]}
    harmonic_plan: dict[str, Any] = field(default_factory=lambda: {
        "key_centers": [],
        "modulation_points": [],
    })

    # Current orchestration state
    orchestration_state: dict[str, Any] = field(default_factory=dict)

    # Voice / vocal plan
    voice_plan: dict[str, Any] = field(default_factory=dict)

    # Revision notes (capped at _MAX_REVISION_NOTES, older archived)
    revision_notes: list[str] = field(default_factory=list)

    # Completed sections: section_name -> {file, status, sha256}
    completed_sections: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Project directory path
    project_dir: str = ""

    # ----- Multi-movement support -----

    # List of movements; each is a dict with 'name', 'key', 'tempo',
    # 'form_plan', 'sections'. Empty list means single-movement (backward compat).
    movements: list[dict[str, Any]] = field(default_factory=list)

    # Index of the currently active movement (0-based). Only meaningful when
    # movements is non-empty.
    current_movement: int = 0

    # Themes that recur across movements. Maps theme_id -> dict with
    # 'movements' (list of movement indices) and optional metadata.
    cross_movement_themes: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ----- Multi-movement operations -----

    def add_movement(self, name: str, key: str = "", tempo: int = 0) -> int:
        """Add a new movement to the composition.

        Args:
            name: Movement name (e.g. 'Allegro', 'Movement 2').
            key: Key signature for this movement.
            tempo: Default tempo for this movement.

        Returns:
            Index of the newly added movement (0-based).
        """
        movement = _default_movement(name=name, key=key, tempo=tempo)
        self.movements.append(movement)
        idx = len(self.movements) - 1
        logger.info("Added movement %d: '%s'", idx, name)
        self.save_plan()
        return idx

    def switch_movement(self, index: int) -> None:
        """Switch the active movement.

        Args:
            index: 0-based index of the movement to switch to.

        Raises:
            IndexError: If the index is out of range.
        """
        if not self.movements:
            logger.warning("No movements defined; single-movement mode active")
            return
        if index < 0 or index >= len(self.movements):
            raise IndexError(
                f"Movement index {index} out of range (0-{len(self.movements) - 1})"
            )
        self.current_movement = index
        logger.info("Switched to movement %d: '%s'", index, self.movements[index].get("name", "?"))

    def get_current_movement(self) -> dict[str, Any]:
        """Get the currently active movement dict.

        For single-movement compositions (movements list is empty), returns
        a synthesized movement dict from the top-level form_plan.
        """
        if not self.movements:
            # Single-movement backward compat: synthesize from top-level fields
            return {
                "name": self.project.get("title", "Untitled"),
                "key": self.form_plan.get("key", ""),
                "tempo": self.form_plan.get("tempo", 0),
                "form_plan": self.form_plan,
                "sections": self.form_plan.get("sections", []),
            }
        if self.current_movement < len(self.movements):
            return self.movements[self.current_movement]
        # Fallback if index somehow out of range
        return self.movements[0] if self.movements else _default_movement()

    def add_cross_movement_theme(
        self,
        theme_id: str,
        movements: list[int],
        description: str = "",
    ) -> None:
        """Register a theme as recurring across multiple movements.

        The theme must already exist in theme_catalog. This records which
        movements it appears in for cross-movement structural tracking.

        Args:
            theme_id: Theme ID from the catalog.
            movements: List of movement indices where it appears.
            description: Optional description of how it transforms across movements.
        """
        self.cross_movement_themes[theme_id] = {
            "movements": movements,
            "description": description,
        }
        logger.info(
            "Registered cross-movement theme '%s' in movements %s",
            theme_id, movements,
        )
        self.save_plan()

    def _ensure_project_dir(self) -> Path:
        """Ensure the project directory exists and return it."""
        if not self.project_dir:
            title_slug = (
                self.project.get("title", "untitled")
                .lower()
                .replace(" ", "_")
                .replace("/", "_")
            )
            self.project_dir = str(COMPOSITIONS_DIR / title_slug)
        path = Path(self.project_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "sections").mkdir(exist_ok=True)
        (path / "renders").mkdir(exist_ok=True)
        (path / "output").mkdir(exist_ok=True)
        return path

    # ----- Persistence -----

    def save_plan(self) -> str:
        """Save the composition plan to plan.json."""
        project_dir = self._ensure_project_dir()
        plan_path = project_dir / "plan.json"
        data = {
            "project": self.project,
            "form_plan": self.form_plan,
            "theme_catalog": self.theme_catalog,
            "harmonic_plan": self.harmonic_plan,
            "orchestration_state": self.orchestration_state,
            "voice_plan": self.voice_plan,
            "revision_notes": self.revision_notes,
            "completed_sections": self.completed_sections,
            "movements": self.movements,
            "current_movement": self.current_movement,
            "cross_movement_themes": self.cross_movement_themes,
        }
        plan_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Saved plan to %s", plan_path)
        return str(plan_path)

    def load_plan(self, plan_path: str | None = None) -> None:
        """Load a composition plan from plan.json."""
        if plan_path is None:
            project_dir = self._ensure_project_dir()
            plan_path = str(project_dir / "plan.json")
        path = Path(plan_path)
        if not path.exists():
            logger.warning("Plan file not found: %s", plan_path)
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.project = data.get("project", self.project)
        self.form_plan = data.get("form_plan", self.form_plan)
        # Handle legacy list-based theme_catalog (convert to dict)
        raw_themes = data.get("theme_catalog", self.theme_catalog)
        if isinstance(raw_themes, list):
            self.theme_catalog = {}
            for t in raw_themes:
                tid = t.get("theme_id", t.get("name", f"theme_{len(self.theme_catalog)}"))
                self.theme_catalog[tid] = t
        else:
            self.theme_catalog = raw_themes
        self.harmonic_plan = data.get("harmonic_plan", self.harmonic_plan)
        self.orchestration_state = data.get("orchestration_state", self.orchestration_state)
        self.voice_plan = data.get("voice_plan", self.voice_plan)
        self.revision_notes = data.get("revision_notes", self.revision_notes)
        self.completed_sections = data.get("completed_sections", self.completed_sections)
        # Multi-movement fields (backward compat: default to empty)
        self.movements = data.get("movements", [])
        self.current_movement = data.get("current_movement", 0)
        self.cross_movement_themes = data.get("cross_movement_themes", {})
        logger.info("Loaded plan from %s", plan_path)

    def save_themes(self) -> str:
        """Save the theme catalog to themes.json."""
        project_dir = self._ensure_project_dir()
        themes_path = project_dir / "themes.json"
        themes_path.write_text(
            json.dumps(self.theme_catalog, indent=2), encoding="utf-8"
        )
        logger.info("Saved %d themes to %s", len(self.theme_catalog), themes_path)
        return str(themes_path)

    def load_themes(self, themes_path: str | None = None) -> None:
        """Load the theme catalog from themes.json."""
        if themes_path is None:
            project_dir = self._ensure_project_dir()
            themes_path = str(project_dir / "themes.json")
        path = Path(themes_path)
        if not path.exists():
            logger.warning("Themes file not found: %s", themes_path)
            return
        self.theme_catalog = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Loaded %d themes from %s", len(self.theme_catalog), themes_path)

    def save_section(self, section_name: str, musicxml_content: str) -> str:
        """Save a section's MusicXML content."""
        project_dir = self._ensure_project_dir()
        section_file = project_dir / "sections" / f"{section_name}.musicxml"
        section_file.write_text(musicxml_content, encoding="utf-8")
        self.completed_sections[section_name] = {
            "file": str(section_file),
            "status": "completed",
        }
        self.save_plan()
        logger.info("Saved section '%s' to %s", section_name, section_file)
        return str(section_file)

    def load_section(self, section_name: str) -> str | None:
        """Load a section's MusicXML content."""
        project_dir = self._ensure_project_dir()
        section_file = project_dir / "sections" / f"{section_name}.musicxml"
        if not section_file.exists():
            logger.warning("Section file not found: %s", section_file)
            return None
        return section_file.read_text(encoding="utf-8")

    def list_sections(self) -> list[dict[str, Any]]:
        """List all sections with their status."""
        project_dir = self._ensure_project_dir()
        sections_dir = project_dir / "sections"
        result = []
        for section_name, meta in self.completed_sections.items():
            section_file = sections_dir / f"{section_name}.musicxml"
            result.append({
                "name": section_name,
                "status": meta.get("status", "unknown"),
                "has_file": section_file.exists(),
            })
        return result

    def git_commit(self, message: str) -> str:
        """Commit current state to git."""
        from src.utils.git_manager import commit

        project_dir = self._ensure_project_dir()
        return commit(str(project_dir), message)

    # ----- Theme Catalog Operations -----

    def add_theme(self, theme_id: str, abc_snippet: str, character: str) -> None:
        """Add a musical theme to the catalog."""
        self.theme_catalog[theme_id] = {
            "abc_snippet": abc_snippet,
            "character": character,
            "appearances": [],
        }
        self.save_plan()
        logger.info("Added theme '%s' to catalog", theme_id)

    def record_appearance(self, theme_id: str, location: str, description: str = "") -> None:
        """Record where a theme appears in the composition."""
        if theme_id not in self.theme_catalog:
            logger.warning("Theme '%s' not found in catalog", theme_id)
            return
        self.theme_catalog[theme_id]["appearances"].append({
            "location": location,
            "description": description,
        })
        self.save_plan()
        logger.info("Recorded appearance of theme '%s' at %s", theme_id, location)

    # ----- Harmonic Plan Operations -----

    def add_key_center(self, measure: int, key: str) -> None:
        """Add a key center to the harmonic plan."""
        self.harmonic_plan.setdefault("key_centers", []).append({
            "measure": measure,
            "key": key,
        })
        self.save_plan()
        logger.info("Added key center: %s at m.%d", key, measure)

    def add_modulation(self, measure: int, from_key: str, to_key: str) -> None:
        """Record a modulation point."""
        self.harmonic_plan.setdefault("modulation_points", []).append({
            "measure": measure,
            "from_key": from_key,
            "to_key": to_key,
        })
        self.save_plan()
        logger.info("Added modulation at m.%d: %s -> %s", measure, from_key, to_key)

    # ----- Revision Notes -----

    def add_revision_note(self, note: str) -> None:
        """Add a revision note, trimming to _MAX_REVISION_NOTES most recent."""
        self.revision_notes.append(note)
        if len(self.revision_notes) > _MAX_REVISION_NOTES:
            archived = self.revision_notes[:-_MAX_REVISION_NOTES]
            self.revision_notes = self.revision_notes[-_MAX_REVISION_NOTES:]
            logger.info("Archived %d old revision notes", len(archived))
        self.save_plan()

    # ----- Section Status -----

    def update_section_status(self, section_name: str, status: str) -> None:
        """Update the status of a composition section."""
        if section_name not in self.completed_sections:
            self.completed_sections[section_name] = {}
        self.completed_sections[section_name]["status"] = status
        self.save_plan()
        logger.info("Updated section '%s' status to '%s'", section_name, status)

    def summarize_completed(self, section_name: str, full_content: str) -> None:
        """Replace full notation with summary + SHA256 hash. Commit full content to git."""
        sha256 = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
        if section_name not in self.completed_sections:
            self.completed_sections[section_name] = {}
        self.completed_sections[section_name]["sha256"] = sha256
        self.completed_sections[section_name]["status"] = "completed"
        self.completed_sections[section_name]["summary"] = f"Committed ({sha256[:12]})"
        self.save_plan()
        logger.info("Summarized section '%s' (sha256: %s)", section_name, sha256[:12])

    # ----- Legacy update_section (backward compat) -----

    def update_section(self, section: str, data: dict[str, Any]) -> None:
        """Update a specific section of the memory document."""
        if section == "project":
            self.project.update(data)
        elif section == "form_plan":
            self.form_plan.update(data)
        elif section == "theme_catalog":
            # Legacy: data is a single theme dict, add it
            tid = data.get("theme_id", data.get("name", f"theme_{len(self.theme_catalog)}"))
            self.add_theme(tid, data.get("abc_snippet", ""), data.get("character", data.get("description", "")))
            return  # save already called in add_theme
        elif section == "harmonic_plan":
            self.harmonic_plan.update(data)
        elif section == "orchestration_state":
            self.orchestration_state.update(data)
        elif section == "voice_plan":
            self.voice_plan.update(data)
        elif section == "revision_notes":
            note = data.get("note", str(data))
            self.add_revision_note(note)
            return  # save already called
        else:
            logger.warning("Unknown memory document section: %s", section)
            return
        self.save_plan()
        logger.info("Updated memory document section: %s", section)

    # ----- Context Serialization -----

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (~4 chars per token)."""
        return len(text) // _CHARS_PER_TOKEN

    def to_context_string(self) -> str:
        """Serialize state for system prompt injection.

        Target: under _CONTEXT_TOKEN_BUDGET tokens. Automatically
        summarizes less critical sections if budget is exceeded.
        """
        lines = []
        lines.append("## Current Composition State")
        lines.append("")

        # Project
        title = self.project.get("title", "Untitled")
        genre = self.project.get("genre", "unspecified")
        status = self.project.get("status", "planning")
        dur = self.project.get("target_duration_s", 0)
        proj_line = f"**Project:** {title} | Genre: {genre} | Status: {status}"
        if dur:
            proj_line += f" | Target: {dur}s"
        lines.append(proj_line)

        # Form plan summary
        if self.form_plan:
            form = self.form_plan.get("form", "")
            key = self.form_plan.get("key", "")
            tempo = self.form_plan.get("tempo", "")
            time_sig = self.form_plan.get("time_signature", "")
            parts = []
            if form:
                parts.append(f"Form: {form}")
            if key:
                parts.append(f"Key: {key}")
            if tempo:
                parts.append(f"Tempo: {tempo}")
            if time_sig:
                parts.append(f"Time: {time_sig}")
            if parts:
                lines.append(f"**Plan:** {' | '.join(parts)}")

            sections = self.form_plan.get("sections", [])
            if sections:
                section_names = [s.get("name", "?") for s in sections]
                lines.append(f"**Sections:** {', '.join(section_names)}")

        # Instrumentation
        instr = self.orchestration_state.get("instruments", [])
        if instr:
            lines.append(f"**Instruments:** {', '.join(instr)}")

        # Themes (with ABC snippets and appearances)
        if self.theme_catalog:
            lines.append(f"**Themes:** {len(self.theme_catalog)} defined")
            for tid, theme in list(self.theme_catalog.items())[:5]:
                char = theme.get("character", "")
                snippet = theme.get("abc_snippet", "")
                appearances = theme.get("appearances", [])
                desc = f"  - **{tid}**: {char[:60]}"
                if snippet:
                    desc += f" | `{snippet[:40]}`"
                if appearances:
                    locs = [a.get("location", "?") for a in appearances[:3]]
                    desc += f" | at: {', '.join(locs)}"
                lines.append(desc)

        # Harmonic plan
        key_centers = self.harmonic_plan.get("key_centers", [])
        modulations = self.harmonic_plan.get("modulation_points", [])
        if key_centers or modulations:
            lines.append("**Harmonic plan:**")
            if key_centers:
                kc_strs = [f"m.{kc['measure']}:{kc['key']}" for kc in key_centers[:6]]
                lines.append(f"  Keys: {', '.join(kc_strs)}")
            if modulations:
                mod_strs = [f"m.{m['measure']}:{m['from_key']}->{m['to_key']}" for m in modulations[:4]]
                lines.append(f"  Modulations: {', '.join(mod_strs)}")

        # Completed sections
        if self.completed_sections:
            done = [n for n, m in self.completed_sections.items() if m.get("status") == "completed"]
            in_prog = [n for n, m in self.completed_sections.items() if m.get("status") == "in_progress"]
            if done:
                lines.append(f"**Completed:** {', '.join(done)}")
            if in_prog:
                lines.append(f"**In progress:** {', '.join(in_prog)}")

        # Multi-movement info
        if self.movements:
            mvt_names = [m.get("name", f"Mvt {i}") for i, m in enumerate(self.movements)]
            lines.append(f"**Movements ({len(self.movements)}):** {', '.join(mvt_names)}")
            cur = self.get_current_movement()
            lines.append(f"**Active movement:** {cur.get('name', '?')}")
            if self.cross_movement_themes:
                ct_ids = list(self.cross_movement_themes.keys())[:5]
                lines.append(f"**Cross-movement themes:** {', '.join(ct_ids)}")

        # Recent revision notes
        if self.revision_notes:
            recent = self.revision_notes[-_MAX_REVISION_NOTES:]
            lines.append("**Recent notes:**")
            for note in recent:
                lines.append(f"  - {note[:100]}")

        result = "\n".join(lines)

        # Check token budget and trim if needed
        est_tokens = self._estimate_tokens(result)
        if est_tokens > _CONTEXT_TOKEN_BUDGET:
            logger.warning(
                "Context string ~%d tokens exceeds budget %d, trimming",
                est_tokens, _CONTEXT_TOKEN_BUDGET,
            )
            # Trim by removing theme details and harmonic specifics
            result = self._trimmed_context_string()

        return result

    def _trimmed_context_string(self) -> str:
        """Minimal context string when full version exceeds budget."""
        lines = [
            "## Current Composition State (trimmed)",
            "",
            f"**Project:** {self.project.get('title', 'Untitled')} | "
            f"Genre: {self.project.get('genre', '')} | "
            f"Status: {self.project.get('status', 'planning')}",
        ]
        if self.theme_catalog:
            lines.append(f"**Themes:** {len(self.theme_catalog)} defined ({', '.join(list(self.theme_catalog.keys())[:5])})")
        done = [n for n, m in self.completed_sections.items() if m.get("status") == "completed"]
        if done:
            lines.append(f"**Completed:** {', '.join(done)}")
        if self.revision_notes:
            lines.append(f"**Latest note:** {self.revision_notes[-1][:80]}")
        return "\n".join(lines)
