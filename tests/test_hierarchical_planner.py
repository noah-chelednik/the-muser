"""Tests for the hierarchical composition planner."""

import pytest
from src.orchestrator.hierarchical_planner import (
    HierarchicalPlanner, Level1Section, Level2Phrase,
    Level3Detail, Level4Arrangement,
)


class TestLevel1Planning:

    def test_plan_piece_creates_sections(self):
        p = HierarchicalPlanner()
        sections = p.plan_piece("ABA", 64, [
            {"name": "A", "start_measure": 1, "end_measure": 24},
            {"name": "B", "start_measure": 25, "end_measure": 48},
            {"name": "A'", "start_measure": 49, "end_measure": 64},
        ])
        assert len(sections) == 3
        assert sections[0].name == "A"
        assert p._form == "ABA"
        assert p._total_measures == 64

    def test_plan_piece_sets_level_1(self):
        p = HierarchicalPlanner()
        p.plan_piece("sonata", 100, [{"name": "Expo", "start_measure": 1, "end_measure": 50}])
        assert p.current_level == 1

    def test_section_key_and_tempo(self):
        p = HierarchicalPlanner()
        sections = p.plan_piece("rondo", 32, [
            {"name": "A", "start_measure": 1, "end_measure": 16, "key": "C major", "tempo": 120},
        ])
        assert sections[0].key == "C major"
        assert sections[0].tempo == 120


class TestZoomNavigation:

    @pytest.fixture
    def planner_with_plan(self):
        p = HierarchicalPlanner()
        p.plan_piece("ABA", 48, [
            {"name": "A", "start_measure": 1, "end_measure": 16},
            {"name": "B", "start_measure": 17, "end_measure": 32},
            {"name": "A2", "start_measure": 33, "end_measure": 48},
        ])
        return p

    def test_zoom_in_1_to_2(self, planner_with_plan):
        result = planner_with_plan.zoom_in("A")
        assert result["level"] == 2
        assert planner_with_plan.current_level == 2

    def test_zoom_in_2_to_3(self, planner_with_plan):
        planner_with_plan.zoom_in("A")
        result = planner_with_plan.zoom_in("A")
        assert result["level"] == 3

    def test_zoom_in_3_to_4(self, planner_with_plan):
        planner_with_plan.zoom_in("A")
        planner_with_plan.zoom_in("A")
        result = planner_with_plan.zoom_in("A")
        assert result["level"] == 4

    def test_zoom_in_at_4_stays(self, planner_with_plan):
        for _ in range(4):
            planner_with_plan.zoom_in("A")
        result = planner_with_plan.zoom_in("A")
        assert "deepest" in result["message"].lower() or result["level"] == 4

    def test_zoom_out_to_1(self, planner_with_plan):
        planner_with_plan.zoom_in("A")
        result = planner_with_plan.zoom_out()
        assert result["level"] == 1

    def test_zoom_out_at_1_stays(self, planner_with_plan):
        result = planner_with_plan.zoom_out()
        assert result["level"] == 1
        assert "top level" in result["message"].lower() or "already" in result["message"].lower()

    def test_no_plan_zoom_in_returns_empty(self):
        p = HierarchicalPlanner()
        result = p.zoom_in("A")
        assert result["level"] == 2
        assert result["phrases"] == []

    def test_no_plan_zoom_out_returns_overview(self):
        p = HierarchicalPlanner()
        result = p.zoom_out()
        assert result["level"] == 1


class TestContextGeneration:

    def test_level1_context(self):
        p = HierarchicalPlanner()
        p.plan_piece("ABA", 48, [
            {"name": "A", "start_measure": 1, "end_measure": 16, "key": "C major"},
        ])
        ctx = p.get_context_for_level(1)
        assert "ABA" in ctx
        assert "48" in ctx

    def test_context_trimming(self):
        p = HierarchicalPlanner()
        sections = [{"name": f"S{i}", "start_measure": i*10+1, "end_measure": (i+1)*10, "description": "x"*200} for i in range(20)]
        p.plan_piece("long", 200, sections)
        ctx = p.get_context_for_level(1)
        assert len(ctx) < 5000


class TestSerialization:

    def test_roundtrip(self):
        p = HierarchicalPlanner()
        p.plan_piece("ABA", 48, [
            {"name": "A", "start_measure": 1, "end_measure": 16, "key": "C major"},
            {"name": "B", "start_measure": 17, "end_measure": 32},
        ])
        p.plan_section("A", [
            {"start_measure": 1, "end_measure": 8, "harmonic_progression": "I-IV-V-I"},
        ])

        data = p.to_dict()
        p2 = HierarchicalPlanner.from_dict(data)

        assert p2._form == "ABA"
        assert p2._total_measures == 48
        assert len(p2.level1_plan) == 2
        assert len(p2.level2_phrases["A"]) == 1

    def test_level1_section_roundtrip(self):
        s = Level1Section(name="Intro", start_measure=1, end_measure=8, key="G major")
        d = s.to_dict()
        s2 = Level1Section.from_dict(d)
        assert s2.name == "Intro"
        assert s2.key == "G major"


class TestSectionStatus:

    def test_update_status(self):
        p = HierarchicalPlanner()
        p.plan_piece("AB", 32, [
            {"name": "A", "start_measure": 1, "end_measure": 16},
        ])
        p.update_section_status("A", "in_progress")
        assert p.level1_plan[0].status == "in_progress"

    def test_get_section(self):
        p = HierarchicalPlanner()
        p.plan_piece("AB", 32, [
            {"name": "A", "start_measure": 1, "end_measure": 16},
        ])
        s = p.get_section("A")
        assert s is not None
        assert s.name == "A"
        assert p.get_section("Z") is None
