"""Phase 8: Deterministic metadata generation from analysis results."""

from __future__ import annotations

import logging

from .models import PipelineConfig, TrackSelection, TrackMetadata

log = logging.getLogger(__name__)

# Mood vocabulary — words that describe emotional character
MOOD_VOCAB = frozenset(
    {
        "dramatic",
        "intense",
        "powerful",
        "calm",
        "peaceful",
        "melancholic",
        "upbeat",
        "energetic",
        "dark",
        "bright",
        "ethereal",
        "aggressive",
        "romantic",
        "mysterious",
        "triumphant",
        "nostalgic",
        "hopeful",
        "haunting",
        "playful",
        "majestic",
        "intimate",
        "bold",
        "dreamy",
        "rebellious",
        "warm",
        "cold",
        "epic",
        "gentle",
        "gritty",
        "smooth",
        "atmospheric",
        "climactic",
        "building",
        "emerging",
        "chill",
        "mellow",
        "relaxing",
        "driving",
        "jarring",
        "sharp",
        "vast",
        "sparse",
        "lush",
        "soaring",
        "brooding",
        "somber",
        "jubilant",
        "fierce",
        "tender",
        "raw",
        "polished",
        "hypnotic",
        "meditative",
        "suspenseful",
        "heroic",
        "tragic",
        "wistful",
        "serene",
        "ominous",
        "whimsical",
        "vibrant",
        "soulful",
        "cinematic",
        "personal",
        "conclusive",
    }
)

# Instrument vocabulary
INSTRUMENT_VOCAB = frozenset(
    {
        "piano",
        "guitar",
        "drums",
        "bass",
        "strings",
        "brass",
        "violin",
        "cello",
        "flute",
        "saxophone",
        "trumpet",
        "synth",
        "synthesizer",
        "organ",
        "harp",
        "clarinet",
        "oboe",
        "percussion",
        "timpani",
        "mandolin",
        "banjo",
        "accordion",
        "harmonica",
        "sitar",
        "tabla",
        "koto",
        "shamisen",
        "erhu",
        "didgeridoo",
        "bagpipes",
        "lute",
        "harpsichord",
        "vibraphone",
        "marimba",
        "xylophone",
        "glockenspiel",
        "woodwinds",
        "choir",
        "vocals",
        "voice",
        "808",
        "hi-hats",
        "kick",
        "pad",
        "oud",
        "shakuhachi",
        "taiko",
        "bansuri",
        "duduk",
        "zither",
        "electric_guitar",
        "acoustic_guitar",
        "double_bass",
    }
)

# Genre display names for platform listings
GENRE_DISPLAY = {
    "cinematic": "Cinematic / Film Score",
    "classical": "Classical / Orchestral",
    "classical_commercial": "Classical / Orchestral",
    "classical_expanded": "Classical / Orchestral",
    "ancient": "World / Ancient",
    "pop": "Pop",
    "rock": "Rock",
    "electronic": "Electronic",
    "lofi": "Lo-Fi / Chill",
    "ambient": "Ambient / Meditation",
    "rnb": "R&B / Soul",
    "dark_experimental": "Dark / Experimental",
    "signature": "Signature / Artist",
}


def generate_metadata(
    selections: dict[str, TrackSelection],
    config: PipelineConfig,
) -> dict[str, TrackMetadata]:
    """Generate distribution-ready metadata for all selected tracks."""
    metadata: dict[str, TrackMetadata] = {}

    for track_id, sel in selections.items():
        if sel.dropped or not sel.selected_candidate:
            continue

        analysis = sel.selected_candidate
        tags_raw = sel.tags.lower().replace(",", " ").split()

        # Extract mood and instrument tags from original tags
        mood_tags = [t for t in tags_raw if t in MOOD_VOCAB]
        instrument_tags = [t for t in tags_raw if t in INSTRUMENT_VOCAB]

        # BPM from rhythm analysis
        bpm = 0
        rhythm_dim = analysis.dimensions.get("rhythm")
        if rhythm_dim:
            bpm = int(rhythm_dim.raw_metrics.get("bpm", 0))

        # Key from harmony analysis
        key = ""
        harmony_dim = analysis.dimensions.get("harmony")
        if harmony_dim:
            key = harmony_dim.raw_metrics.get("key", "")

        # Duration formatting
        dur_s = int(sel.duration_s)
        dur_fmt = f"{dur_s // 60}:{dur_s % 60:02d}"

        # Tier from composite score
        score = analysis.composite_score
        tier = _compute_tier(score)

        # Platform assignments
        assignments = _assign_platforms(track_id, sel.genre, score, config)

        meta = TrackMetadata(
            track_id=track_id,
            title=sel.title or track_id,
            artist=config.artist_name,
            genre_primary=sel.genre,
            mood_tags=mood_tags[:5],
            instrument_tags=instrument_tags[:5],
            bpm=bpm,
            key=key,
            duration_s=dur_s,
            duration_formatted=dur_fmt,
            year=config.release_year,
            copyright=f"{config.release_year} {config.copyright_holder}",
            composite_score=round(score, 4),
            confidence=sel.confidence,
            tier=tier,
            platform_assignments=assignments,
        )
        metadata[track_id] = meta

    log.info("Generated metadata for %d tracks.", len(metadata))
    return metadata


def _compute_tier(score: float) -> str:
    if score >= 0.95:
        return "S"
    elif score >= 0.90:
        return "A"
    elif score >= 0.80:
        return "B"
    elif score >= 0.70:
        return "C"
    else:
        return "D"


def _assign_platforms(
    track_id: str,
    genre: str,
    score: float,
    config: PipelineConfig,
) -> list[str]:
    """Determine which platforms/packages a track belongs to."""
    assignments = []

    # All surviving tracks go to DistroKid
    assignments.append(f"distrokid_{genre}_album")

    # All go to Gumroad genre pack
    assignments.append(f"gumroad_{genre}_pack")

    # Top tracks per genre go to Fiverr demos (handled in packager)
    # Top tracks go to Ko-fi singles (handled in packager)

    return assignments
