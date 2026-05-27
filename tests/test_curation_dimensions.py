"""Tests for curation dimension analyzers (hard gates + soft scores)."""

import numpy as np

from src.curation.models import DimensionResult, PipelineConfig


def _default_gates():
    return PipelineConfig().hard_gates


def _default_weights():
    return PipelineConfig().soft_weights


class TestClippingGate:
    def test_clean_passes(self, clean_wav_samples):
        from src.curation.dimensions.clipping import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert result.hard_gate.passed

    def test_clipped_fails(self, clipped_wav_samples):
        from src.curation.dimensions.clipping import analyze

        samples, sr = clipped_wav_samples
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert not result.hard_gate.passed

    def test_empty_audio(self):
        from src.curation.dimensions.clipping import analyze

        result = analyze(np.zeros(100, dtype=np.float32), 44100, _default_gates())
        assert isinstance(result, DimensionResult)


class TestSilenceGate:
    def test_clean_passes(self, clean_wav_samples):
        from src.curation.dimensions.silence import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert result.hard_gate.passed

    def test_all_zeros_detected(self, silent_wav_samples):
        from src.curation.dimensions.silence import analyze

        samples, sr = silent_wav_samples
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert result.raw_metrics.get("silence_ratio", 0) >= 0.0


class TestLoudnessGate:
    def test_clean_audio(self, clean_wav_samples, tone_wav):
        from src.curation.dimensions.loudness import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_gates(), wav_path=tone_wav)
        assert result.hard_gate is not None
        assert isinstance(result.hard_gate.passed, bool)


class TestPhaseGate:
    def test_stereo_good_correlation(self, stereo_samples):
        from src.curation.dimensions.phase import analyze

        samples, sr = stereo_samples
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert result.hard_gate.passed

    def test_inverted_phase_fails(self):
        from src.curation.dimensions.phase import analyze

        sr = 44100
        t = np.linspace(0, 1, sr, dtype=np.float32)
        left = np.sin(2 * np.pi * 440 * t)
        right = -left
        samples = np.stack([left, right])
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert not result.hard_gate.passed


class TestEdgeClicksGate:
    def test_clean_passes(self, clean_wav_samples):
        from src.curation.dimensions.edge_clicks import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert result.hard_gate.passed


class TestArtifactsGate:
    def test_clean_passes(self, clean_wav_samples):
        from src.curation.dimensions.artifacts import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_gates())
        assert result.hard_gate is not None
        assert result.hard_gate.passed


class TestStructureScore:
    def test_returns_score(self, clean_wav_samples):
        from src.curation.dimensions.structure import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_weights(), genre="pop")
        assert 0.0 <= result.score <= 1.0


class TestRhythmScore:
    def test_returns_score(self, clean_wav_samples):
        from src.curation.dimensions.rhythm import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_weights(), genre="pop")
        assert 0.0 <= result.score <= 1.0


class TestHarmonyScore:
    def test_returns_score(self, clean_wav_samples):
        from src.curation.dimensions.harmony import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_weights(), genre="pop")
        assert 0.0 <= result.score <= 1.0


class TestFrequencyBalanceScore:
    def test_returns_score(self, clean_wav_samples):
        from src.curation.dimensions.frequency_balance import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_weights(), genre="pop")
        assert 0.0 <= result.score <= 1.0


class TestEvolutionScore:
    def test_returns_score(self, clean_wav_samples):
        from src.curation.dimensions.evolution import analyze

        samples, sr = clean_wav_samples
        result = analyze(samples, sr, _default_weights(), genre="pop")
        assert 0.0 <= result.score <= 1.0


class TestStereoMixScore:
    def test_returns_score(self, clean_wav_samples, stereo_samples):
        from src.curation.dimensions.stereo_mix import analyze

        samples, sr = clean_wav_samples
        stereo, _ = stereo_samples
        result = analyze(samples, sr, _default_weights(), genre="pop", samples_stereo=stereo)
        assert 0.0 <= result.score <= 1.0
