"""Hierarchical composition planning for The Muser.

Provides a 4-level decomposition system for managing long compositions:

Level 1 (full-piece): Form plan as structured sections with measure ranges
Level 2 (phrase-level, ~32 measures): Harmonic progressions, thematic assignments
Level 3 (note-level, ~8 measures): Actual notation generation units
Level 4 (arrangement): Full orchestration and voicing

The planner supports zoom-in/zoom-out navigation so the LLM can work
at the appropriate level of detail while maintaining awareness of the
overall structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Context budget per level (approximate token count, ~4 chars per token)
_CHARS_PER_TOKEN = 4
_LEVEL_CONTEXT_BUDGETS = {
    1: 800,  # Full-piece overview: concise
    2: 1200,  # Phrase level: moderate detail
    3: 1500,  # Note level: most detail
    4: 1000,  # Arrangement: moderate detail
}


@dataclass
class Level1Section:
    """Full-piece level: form sections with measure ranges."""

    name: str
    start_measure: int
    end_measure: int
    key: str = ""
    tempo: int = 0
    description: str = ""
    status: str = "planned"  # planned, in_progress, complete

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_measure": self.start_measure,
            "end_measure": self.end_measure,
            "key": self.key,
            "tempo": self.tempo,
            "description": self.description,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Level1Section:
        return cls(
            name=data["name"],
            start_measure=data.get("start_measure", 1),
            end_measure=data.get("end_measure", 1),
            key=data.get("key", ""),
            tempo=data.get("tempo", 0),
            description=data.get("description", ""),
            status=data.get("status", "planned"),
        )


@dataclass
class Level2Phrase:
    """Phrase level (~32 measures): harmonic progressions, thematic assignments."""

    section_name: str
    start_measure: int
    end_measure: int
    harmonic_progression: str = ""
    themes: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_name": self.section_name,
            "start_measure": self.start_measure,
            "end_measure": self.end_measure,
            "harmonic_progression": self.harmonic_progression,
            "themes": list(self.themes),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Level2Phrase:
        return cls(
            section_name=data["section_name"],
            start_measure=data.get("start_measure", 1),
            end_measure=data.get("end_measure", 1),
            harmonic_progression=data.get("harmonic_progression", ""),
            themes=data.get("themes", []),
            description=data.get("description", ""),
        )


@dataclass
class Level3Detail:
    """Note level (~8 measures): actual notation content."""

    phrase_section: str
    start_measure: int
    end_measure: int
    content_type: str = "notation"  # notation, audio
    content_ref: str = ""  # file path or section name

    def to_dict(self) -> dict[str, Any]:
        return {
            "phrase_section": self.phrase_section,
            "start_measure": self.start_measure,
            "end_measure": self.end_measure,
            "content_type": self.content_type,
            "content_ref": self.content_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Level3Detail:
        return cls(
            phrase_section=data["phrase_section"],
            start_measure=data.get("start_measure", 1),
            end_measure=data.get("end_measure", 1),
            content_type=data.get("content_type", "notation"),
            content_ref=data.get("content_ref", ""),
        )


@dataclass
class Level4Arrangement:
    """Arrangement level: full orchestration and voicing."""

    section_name: str
    instrument_assignments: dict[str, str] = field(default_factory=dict)
    dynamics: str = ""
    articulations: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_name": self.section_name,
            "instrument_assignments": dict(self.instrument_assignments),
            "dynamics": self.dynamics,
            "articulations": self.articulations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Level4Arrangement:
        return cls(
            section_name=data["section_name"],
            instrument_assignments=data.get("instrument_assignments", {}),
            dynamics=data.get("dynamics", ""),
            articulations=data.get("articulations", ""),
        )


class HierarchicalPlanner:
    """
    4-level composition planning:
    Level 1 (full-piece): Form plan as structured sections
    Level 2 (phrase-level, ~32 measures): Harmonic progressions, thematic assignments
    Level 3 (note-level, ~8 measures): Actual notation generation units
    Level 4 (arrangement): Full orchestration and voicing

    Supports zoom-in / zoom-out navigation so the LLM agent can work
    at the appropriate level of detail.
    """

    def __init__(self) -> None:
        self.level1_plan: list[Level1Section] = []
        self.level2_phrases: dict[str, list[Level2Phrase]] = {}
        self.level3_details: dict[str, list[Level3Detail]] = {}
        self.level4_arrangements: dict[str, Level4Arrangement] = {}
        self.current_level: int = 1
        self.current_section: str = ""
        self._form: str = ""
        self._total_measures: int = 0

    # ----- Level 1: Full piece planning -----

    def plan_piece(
        self,
        form: str,
        total_measures: int,
        sections: list[dict[str, Any]],
    ) -> list[Level1Section]:
        """Create the Level 1 (full-piece) form plan.

        Args:
            form: Musical form name (e.g. 'sonata', 'ABA', 'verse-chorus').
            total_measures: Total number of measures in the piece.
            sections: List of section dicts, each with at least 'name',
                      'start_measure', 'end_measure'. Optional: 'key',
                      'tempo', 'description'.

        Returns:
            The created list of Level1Section objects.
        """
        self._form = form
        self._total_measures = total_measures
        self.level1_plan = []

        for sec in sections:
            section = Level1Section(
                name=sec["name"],
                start_measure=sec.get("start_measure", 1),
                end_measure=sec.get("end_measure", total_measures),
                key=sec.get("key", ""),
                tempo=sec.get("tempo", 0),
                description=sec.get("description", ""),
                status=sec.get("status", "planned"),
            )
            self.level1_plan.append(section)

        self.current_level = 1
        self.current_section = ""
        logger.info(
            "Planned piece: form=%s, measures=%d, sections=%d",
            form,
            total_measures,
            len(self.level1_plan),
        )
        return self.level1_plan

    # ----- Level 2: Phrase planning -----

    def plan_section(
        self,
        section_name: str,
        phrases: list[dict[str, Any]],
    ) -> list[Level2Phrase]:
        """Create Level 2 (phrase-level) plan for a section.

        Args:
            section_name: Name of the Level 1 section to decompose.
            phrases: List of phrase dicts with 'start_measure', 'end_measure',
                     and optional 'harmonic_progression', 'themes', 'description'.

        Returns:
            The created list of Level2Phrase objects.
        """
        phrase_list: list[Level2Phrase] = []
        for p in phrases:
            phrase = Level2Phrase(
                section_name=section_name,
                start_measure=p.get("start_measure", 1),
                end_measure=p.get("end_measure", 1),
                harmonic_progression=p.get("harmonic_progression", ""),
                themes=p.get("themes", []),
                description=p.get("description", ""),
            )
            phrase_list.append(phrase)

        self.level2_phrases[section_name] = phrase_list
        logger.info(
            "Planned %d phrases for section '%s'",
            len(phrase_list),
            section_name,
        )
        return phrase_list

    # ----- Level 3: Note-level planning -----

    def plan_measures(
        self,
        section: str,
        start: int,
        end: int,
        content_type: str = "notation",
        content_ref: str = "",
    ) -> Level3Detail:
        """Create a Level 3 (note-level) detail block.

        Args:
            section: Parent section name.
            start: Start measure.
            end: End measure.
            content_type: 'notation' or 'audio'.
            content_ref: File path or section reference.

        Returns:
            The created Level3Detail.
        """
        detail = Level3Detail(
            phrase_section=section,
            start_measure=start,
            end_measure=end,
            content_type=content_type,
            content_ref=content_ref,
        )
        self.level3_details.setdefault(section, []).append(detail)
        logger.info(
            "Planned measures %d-%d for section '%s'",
            start,
            end,
            section,
        )
        return detail

    # ----- Level 4: Arrangement planning -----

    def plan_arrangement(
        self,
        section: str,
        instruments: dict[str, str],
        dynamics: str = "",
        articulations: str = "",
    ) -> Level4Arrangement:
        """Create a Level 4 (arrangement) plan for a section.

        Args:
            section: Section name.
            instruments: Dict mapping instrument name to role description.
            dynamics: Dynamic markings description.
            articulations: Articulation notes.

        Returns:
            The created Level4Arrangement.
        """
        arrangement = Level4Arrangement(
            section_name=section,
            instrument_assignments=instruments,
            dynamics=dynamics,
            articulations=articulations,
        )
        self.level4_arrangements[section] = arrangement
        logger.info("Planned arrangement for section '%s'", section)
        return arrangement

    # ----- Navigation -----

    def get_current_level(self) -> int:
        """Return the current working level (1-4)."""
        return self.current_level

    def zoom_in(self, section: str) -> dict[str, Any]:
        """Zoom into a section to see detail at the next level down.

        Moves current_level from 1->2, 2->3, or 3->4.

        Args:
            section: Section name to zoom into.

        Returns:
            Dict with the detail at the next level, or an error message.
        """
        self.current_section = section

        if self.current_level == 1:
            # Zoom into Level 2 (phrases)
            phrases = self.level2_phrases.get(section, [])
            self.current_level = 2
            return {
                "level": 2,
                "section": section,
                "phrases": [p.to_dict() for p in phrases],
                "message": (
                    f"Zoomed into section '{section}' at phrase level. "
                    f"{len(phrases)} phrases defined."
                    + (" Use plan_section to define phrases." if not phrases else "")
                ),
            }

        elif self.current_level == 2:
            # Zoom into Level 3 (note details)
            details = self.level3_details.get(section, [])
            self.current_level = 3
            return {
                "level": 3,
                "section": section,
                "details": [d.to_dict() for d in details],
                "message": (
                    f"Zoomed into section '{section}' at note level. "
                    f"{len(details)} detail blocks defined."
                ),
            }

        elif self.current_level == 3:
            # Zoom into Level 4 (arrangement)
            arrangement = self.level4_arrangements.get(section)
            self.current_level = 4
            return {
                "level": 4,
                "section": section,
                "arrangement": arrangement.to_dict() if arrangement else {},
                "message": (
                    f"Zoomed into section '{section}' at arrangement level."
                    + (" No arrangement defined yet." if not arrangement else "")
                ),
            }

        else:
            return {
                "level": self.current_level,
                "section": section,
                "message": "Already at the deepest level (4). Cannot zoom in further.",
            }

    def zoom_out(self) -> dict[str, Any]:
        """Zoom out to see the overview at the next level up.

        Moves current_level from 4->3, 3->2, 2->1.

        Returns:
            Dict with the overview at the higher level, or an error message.
        """
        if self.current_level <= 1:
            return {
                "level": 1,
                "sections": [s.to_dict() for s in self.level1_plan],
                "message": "Already at the top level (1). Showing full piece overview.",
            }

        self.current_level = max(1, self.current_level - 1)

        if self.current_level == 1:
            self.current_section = ""
            return {
                "level": 1,
                "form": self._form,
                "total_measures": self._total_measures,
                "sections": [s.to_dict() for s in self.level1_plan],
                "message": (
                    f"Zoomed out to full-piece level. "
                    f"Form: {self._form}, {self._total_measures} measures, "
                    f"{len(self.level1_plan)} sections."
                ),
            }

        elif self.current_level == 2:
            section = self.current_section
            phrases = self.level2_phrases.get(section, [])
            return {
                "level": 2,
                "section": section,
                "phrases": [p.to_dict() for p in phrases],
                "message": f"Zoomed out to phrase level for section '{section}'.",
            }

        elif self.current_level == 3:
            section = self.current_section
            details = self.level3_details.get(section, [])
            return {
                "level": 3,
                "section": section,
                "details": [d.to_dict() for d in details],
                "message": f"Zoomed out to note level for section '{section}'.",
            }

        # Should not reach here, but handle gracefully
        return {"level": self.current_level, "message": "Zoom out complete."}

    # ----- Context generation -----

    def get_context_for_level(self, level: int, section: str = "") -> str:
        """Get a context string appropriate for the given working level.

        Ensures the context fits within context window budget by summarizing
        levels that are not currently in focus.

        Args:
            level: The working level (1-4).
            section: Section name for levels 2-4 (optional for level 1).

        Returns:
            Context string suitable for system prompt injection.
        """
        budget_tokens = _LEVEL_CONTEXT_BUDGETS.get(level, 1000)
        budget_chars = budget_tokens * _CHARS_PER_TOKEN

        lines: list[str] = []
        lines.append(f"## Hierarchical Plan (Level {level})")
        lines.append("")

        if self._form:
            lines.append(f"**Form:** {self._form} | {self._total_measures} measures")

        # Level 1 overview (always shown, detail depends on current level)
        if self.level1_plan:
            if level == 1:
                lines.append("**Sections:**")
                for s in self.level1_plan:
                    status_mark = {"planned": " ", "in_progress": ">", "complete": "x"}
                    mark = status_mark.get(s.status, " ")
                    line = f"  [{mark}] {s.name} (m.{s.start_measure}-{s.end_measure})"
                    if s.key:
                        line += f" | {s.key}"
                    if s.tempo:
                        line += f" | {s.tempo} BPM"
                    if s.description:
                        line += f" — {s.description[:60]}"
                    lines.append(line)
            else:
                # Abbreviated overview for deeper levels
                section_names = [s.name for s in self.level1_plan]
                lines.append(f"**Sections:** {', '.join(section_names)}")
                if section:
                    lines.append(f"**Focus:** {section}")

        # Level 2 detail (shown for levels 2+)
        if level >= 2 and section:
            phrases = self.level2_phrases.get(section, [])
            if phrases:
                lines.append(f"\n**Phrases in '{section}':**")
                for p in phrases:
                    line = f"  m.{p.start_measure}-{p.end_measure}"
                    if p.harmonic_progression:
                        line += f" | Harmony: {p.harmonic_progression[:50]}"
                    if p.themes:
                        line += f" | Themes: {', '.join(p.themes[:3])}"
                    if p.description:
                        line += f" — {p.description[:40]}"
                    lines.append(line)

        # Level 3 detail (shown for levels 3+)
        if level >= 3 and section:
            details = self.level3_details.get(section, [])
            if details:
                lines.append(f"\n**Note-level details in '{section}':**")
                for d in details:
                    line = f"  m.{d.start_measure}-{d.end_measure} [{d.content_type}]"
                    if d.content_ref:
                        line += f" -> {d.content_ref}"
                    lines.append(line)

        # Level 4 detail (shown only at level 4)
        if level >= 4 and section:
            arr = self.level4_arrangements.get(section)
            if arr:
                lines.append(f"\n**Arrangement for '{section}':**")
                for inst, role in arr.instrument_assignments.items():
                    lines.append(f"  {inst}: {role[:40]}")
                if arr.dynamics:
                    lines.append(f"  Dynamics: {arr.dynamics[:60]}")
                if arr.articulations:
                    lines.append(f"  Articulations: {arr.articulations[:60]}")

        result = "\n".join(lines)

        # Trim if over budget
        if len(result) > budget_chars:
            result = result[: budget_chars - 20] + "\n  [... trimmed]"

        return result

    # ----- Section status helpers -----

    def update_section_status(self, section_name: str, status: str) -> None:
        """Update the status of a Level 1 section."""
        for s in self.level1_plan:
            if s.name == section_name:
                s.status = status
                logger.info("Section '%s' status -> %s", section_name, status)
                return
        logger.warning("Section '%s' not found in Level 1 plan", section_name)

    def get_section(self, section_name: str) -> Level1Section | None:
        """Get a Level 1 section by name."""
        for s in self.level1_plan:
            if s.name == section_name:
                return s
        return None

    # ----- Serialization -----

    def to_dict(self) -> dict[str, Any]:
        """Serialize the planner state to a dict for JSON persistence."""
        return {
            "form": self._form,
            "total_measures": self._total_measures,
            "current_level": self.current_level,
            "current_section": self.current_section,
            "level1_plan": [s.to_dict() for s in self.level1_plan],
            "level2_phrases": {k: [p.to_dict() for p in v] for k, v in self.level2_phrases.items()},
            "level3_details": {k: [d.to_dict() for d in v] for k, v in self.level3_details.items()},
            "level4_arrangements": {k: v.to_dict() for k, v in self.level4_arrangements.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HierarchicalPlanner:
        """Deserialize a planner from a dict."""
        planner = cls()
        planner._form = data.get("form", "")
        planner._total_measures = data.get("total_measures", 0)
        planner.current_level = data.get("current_level", 1)
        planner.current_section = data.get("current_section", "")

        planner.level1_plan = [Level1Section.from_dict(s) for s in data.get("level1_plan", [])]
        planner.level2_phrases = {
            k: [Level2Phrase.from_dict(p) for p in v]
            for k, v in data.get("level2_phrases", {}).items()
        }
        planner.level3_details = {
            k: [Level3Detail.from_dict(d) for d in v]
            for k, v in data.get("level3_details", {}).items()
        }
        planner.level4_arrangements = {
            k: Level4Arrangement.from_dict(v)
            for k, v in data.get("level4_arrangements", {}).items()
        }

        return planner
