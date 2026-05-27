"""Tests for the curation pipeline (analyzer, selector, config, models)."""

import pytest
from pathlib import Path

from src.curation.models import (
    PipelineConfig, CandidateAnalysis, DimensionResult,
    HardGateResult, TrackSelection, CorpusProfile, BandStats,
    TrackMetadata, DuplicatePair,
)


class TestCurationModels:

    def test_pipeline_config_defaults(self):
        c = PipelineConfig()
        assert c.parallel_workers == 8
        assert c.artist_name == ""
        assert "structure" in c.soft_weights

    def test_candidate_analysis_construction(self):
        ca = CandidateAnalysis(track_id="t1", candidate_id="t1_c01", wav_path="/tmp/t.wav")
        assert ca.composite_score == 0.0
        assert ca.hard_gates_passed is False

    def test_dimension_result(self):
        d = DimensionResult(name="clipping", score=0.9, hard_gate=HardGateResult(
            passed=True, value=0.0001, threshold=0.001,
        ))
        assert d.hard_gate.passed

    def test_track_selection(self):
        ts = TrackSelection(track_id="t1", title="Test", genre="pop")
        assert ts.dropped is False
        assert ts.confidence == "high"

    def test_corpus_profile(self):
        cp = CorpusProfile(genre="pop", track_count=10)
        assert cp.genre == "pop"

    def test_track_metadata(self):
        tm = TrackMetadata(track_id="t1", title="Song")
        assert tm.ai_disclosure != ""

    def test_duplicate_pair(self):
        dp = DuplicatePair(kept_id="a", dropped_id="b", similarity=0.95)
        assert dp.similarity == 0.95


class TestCurationConfig:

    def test_load_config_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.curation.config.DEFAULT_CONFIG_PATH", tmp_path / "nonexistent.json")
        from src.curation.config import load_config
        config = load_config(config_path=str(tmp_path / "nonexistent.json"))
        assert isinstance(config, PipelineConfig)

    def test_load_config_with_file(self, tmp_path):
        import json
        cfg_path = tmp_path / "test_config.json"
        cfg_path.write_text(json.dumps({"parallel_workers": 4, "artist_name": "Test"}))
        from src.curation.config import load_config
        config = load_config(config_path=str(cfg_path))
        assert config.parallel_workers == 4
        assert config.artist_name == "Test"

    def test_env_overrides(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUSER_ARTIST_NAME", "EnvArtist")
        from src.curation.config import load_config
        config = load_config(config_path=str(tmp_path / "nonexistent.json"))
        assert config.artist_name == "EnvArtist"


class TestAnalyzer:

    def test_parse_candidate_filename(self):
        from src.curation.analyzer import _parse_candidate_filename
        tid, cid = _parse_candidate_filename("/path/to/P1-A01_c02.wav")
        assert tid == "P1-A01"
        assert cid == "P1-A01_c02"

    def test_parse_fallback(self):
        from src.curation.analyzer import _parse_candidate_filename
        tid, cid = _parse_candidate_filename("/path/to/random_name.wav")
        assert tid == "random_name"

    def test_compute_composite(self):
        from src.curation.analyzer import compute_composite
        dims = {
            "structure": DimensionResult(name="structure", score=0.8),
            "rhythm": DimensionResult(name="rhythm", score=0.7),
            "harmony": DimensionResult(name="harmony", score=0.6),
            "freq_balance": DimensionResult(name="freq_balance", score=0.5),
            "evolution": DimensionResult(name="evolution", score=0.4),
            "stereo_mix": DimensionResult(name="stereo_mix", score=0.3),
        }
        config = PipelineConfig()
        score = compute_composite(dims, config, "pop")
        assert 0.0 < score < 1.0

    def test_analyze_candidate(self, tone_wav):
        from src.curation.analyzer import analyze_candidate
        config = PipelineConfig()
        result = analyze_candidate(tone_wav, "pop", config)
        assert result.track_id != ""
        assert result.duration_s > 0
        assert isinstance(result.hard_gates_passed, bool)
        assert 0.0 <= result.composite_score <= 1.0

    def test_analyze_candidate_bad_file(self, tmp_path):
        from src.curation.analyzer import analyze_candidate
        config = PipelineConfig()
        bad_path = str(tmp_path / "nonexistent.wav")
        result = analyze_candidate(bad_path, "pop", config)
        assert result.composite_score == 0.0
