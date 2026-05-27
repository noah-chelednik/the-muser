"""Pydantic data models for the curation pipeline."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Analysis models
# ---------------------------------------------------------------------------


class HardGateResult(BaseModel):
    """Result of a single hard-gate check."""

    passed: bool
    value: float
    threshold: float
    reason: str = ""


class DimensionResult(BaseModel):
    """Result of a single analysis dimension (hard gate or soft score)."""

    name: str
    score: float = 0.0  # 0.0–1.0
    hard_gate: Optional[HardGateResult] = None
    raw_metrics: dict = Field(default_factory=dict)


class CandidateAnalysis(BaseModel):
    """Full analysis of one candidate WAV file."""

    track_id: str
    candidate_id: str  # e.g. "P1-A01_c01"
    wav_path: str
    duration_s: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    dimensions: dict[str, DimensionResult] = Field(default_factory=dict)
    hard_gates_passed: bool = False
    gate_failures: list[str] = Field(default_factory=list)
    composite_score: float = 0.0


# ---------------------------------------------------------------------------
# Selection models
# ---------------------------------------------------------------------------


class TrackSelection(BaseModel):
    """Selection result for one track (across all its candidates)."""

    track_id: str
    title: str = ""
    genre: str = ""
    category: str = ""
    tags: str = ""
    duration_s: float = 0.0
    selected_candidate: Optional[CandidateAnalysis] = None
    all_candidates: list[CandidateAnalysis] = Field(default_factory=list)
    dropped: bool = False
    drop_reason: str = ""
    confidence: str = "high"  # "high" or "uncertain"
    old_score: float = 0.0  # Original 9-metric scorer
    new_score: float = 0.0  # New 12-dimension composite


class DuplicatePair(BaseModel):
    """A pair of tracks flagged as near-duplicates."""

    kept_id: str
    dropped_id: str
    similarity: float
    same_genre: bool = False


# ---------------------------------------------------------------------------
# Corpus profiling
# ---------------------------------------------------------------------------


class BandStats(BaseModel):
    mean: float = 0.0
    std: float = 0.0


class CorpusProfile(BaseModel):
    """Statistical profile for one genre, computed from the corpus."""

    genre: str
    track_count: int = 0
    frequency_bands: dict[str, BandStats] = Field(default_factory=dict)
    evolution_distance: BandStats = Field(default_factory=BandStats)
    stereo_width: BandStats = Field(default_factory=BandStats)
    spectral_centroid: BandStats = Field(default_factory=BandStats)


# ---------------------------------------------------------------------------
# Metadata & packaging
# ---------------------------------------------------------------------------


class TrackMetadata(BaseModel):
    """Distribution-ready metadata for one track."""

    track_id: str
    title: str
    artist: str = ""
    genre_primary: str = ""
    mood_tags: list[str] = Field(default_factory=list)
    instrument_tags: list[str] = Field(default_factory=list)
    bpm: int = 0
    key: str = ""
    duration_s: int = 0
    duration_formatted: str = ""
    year: int = 2026
    copyright: str = ""
    ai_disclosure: str = "Created with AI-assisted composition tools"
    composite_score: float = 0.0
    confidence: str = "high"
    tier: str = ""
    platform_assignments: list[str] = Field(default_factory=list)


class AlbumPackage(BaseModel):
    """A DistroKid album grouping."""

    album_title: str
    genre: str
    tracks: list[TrackMetadata] = Field(default_factory=list)


class GumroadPack(BaseModel):
    """A Gumroad genre pack."""

    pack_title: str
    genre: str
    price_usd: int = 19
    tracks: list[TrackMetadata] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------


class PipelineConfig(BaseModel):
    """Full pipeline configuration."""

    production_run: str = ""
    production_run_dir: str = ""

    hard_gates: dict = Field(
        default_factory=lambda: {
            "artifact_count_per_min": 10,
            "clipped_ratio_max": 0.001,
            "silence_gap_max_s": 2.0,
            "silence_total_ratio_max": 0.15,
            "lufs_min": -40,
            "lufs_max": -4,
            "true_peak_max_dbtp": 2.0,
            "phase_correlation_min": -0.1,
            "edge_click_threshold": 0.3,
        }
    )

    soft_weights: dict = Field(
        default_factory=lambda: {
            "structure": 0.20,
            "rhythm": 0.20,
            "harmony": 0.15,
            "freq_balance": 0.15,
            "evolution": 0.15,
            "stereo_mix": 0.15,
        }
    )

    genre_weight_overrides: dict = Field(
        default_factory=lambda: {
            "cinematic": {"structure": 0.25, "evolution": 0.20, "rhythm": 0.15},
            "ambient": {
                "rhythm": 0.10,
                "structure": 0.10,
                "freq_balance": 0.25,
                "stereo_mix": 0.25,
            },
            "electronic": {"rhythm": 0.25, "freq_balance": 0.20},
            "classical": {"harmony": 0.25, "structure": 0.25, "rhythm": 0.10},
            "rock": {"rhythm": 0.25, "freq_balance": 0.20},
        }
    )

    duplicate_detection: dict = Field(
        default_factory=lambda: {
            "cross_genre_threshold": 0.03,
            "within_genre_threshold": 0.06,
            "self_test": True,
        }
    )

    packaging: dict = Field(
        default_factory=lambda: {
            "distrokid_max_per_album": 35,
            "gumroad_min_pack_size": 8,
            "fiverr_demos_per_genre": 3,
            "fiverr_max_demos": 15,
            "kofi_max_singles": 20,
        }
    )

    postproduction: dict = Field(
        default_factory=lambda: {
            "genre_preset_map": {
                "cinematic": "classical",
                "classical": "classical",
                "classical_commercial": "classical",
                "classical_expanded": "classical",
                "ancient": "classical",
                "pop": "pop",
                "rnb": "pop",
                "signature": "pop",
                "lofi": "default",
                "ambient": "default",
                "electronic": "electronic",
                "dark_experimental": "electronic",
                "rock": "rock",
            }
        }
    )

    pack_prices: dict = Field(
        default_factory=lambda: {
            "cinematic": 24,
            "classical": 19,
            "classical_commercial": 19,
            "classical_expanded": 19,
            "pop": 19,
            "rock": 19,
            "electronic": 19,
            "lofi": 14,
            "ambient": 14,
            "rnb": 19,
            "ancient": 14,
            "dark_experimental": 14,
            "signature": 24,
        }
    )

    parallel_workers: int = 8
    artist_name: str = ""
    copyright_holder: str = ""
    release_year: int = 2026
