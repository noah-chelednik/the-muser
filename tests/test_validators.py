"""Tests for theory and audio validators.

All score tests programmatically build test fixtures using music21.
"""

from __future__ import annotations

import music21
from music21 import chord, meter, note, stream

import pytest

from src.notation.theory_validator import (
    TheoryCheckResult,
    check_empty_output,
    check_instrument_ranges,
    check_parallel_motion,
    check_repetitiveness,
    check_rhythm_consistency,
    validate_score,
)
from src.audio.audio_validator import check_audio, get_audio_info


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_score(
    *,
    part_name: str = "Piano",
    time_sig: str = "4/4",
    measures: list[list[tuple[str, float]]] | None = None,
) -> stream.Score:
    """Build a simple single-part score.

    Parameters
    ----------
    part_name:
        The name assigned to the single part.
    time_sig:
        Time signature string (e.g. ``"4/4"``).
    measures:
        Each inner list describes one measure as (pitch_or_'rest', quarterLength)
        tuples.  If *None*, a default 4-bar C-major pattern is generated.
    """
    if measures is None:
        measures = [
            [("C4", 4.0)],
            [("D4", 2.0), ("E4", 2.0)],
            [("F4", 1.0), ("G4", 1.0), ("A4", 1.0), ("B4", 1.0)],
            [("C5", 4.0)],
        ]

    score = stream.Score()
    part = stream.Part()
    part.partName = part_name

    ts = meter.TimeSignature(time_sig)

    for m_idx, m_contents in enumerate(measures):
        m = stream.Measure(number=m_idx + 1)
        if m_idx == 0:
            m.insert(0, ts)
        for pitch, ql in m_contents:
            if pitch.lower() == "rest":
                m.append(note.Rest(quarterLength=ql))
            else:
                m.append(note.Note(pitch, quarterLength=ql))
        part.append(m)

    score.append(part)
    return score


# ===========================================================================
# Rhythm checks
# ===========================================================================

class TestRhythmConsistency:
    """Tests for check_rhythm_consistency."""

    def test_rhythm_error_detection(self):
        """A non-first 4/4 measure with only 3 beats should produce an error."""
        score = _make_score(measures=[
            [("C4", 4.0)],  # Full first measure
            [("D4", 3.0)],  # Only 3 quarter-lengths in a 4/4 bar
        ])
        errors = check_rhythm_consistency(score)
        assert len(errors) == 1
        assert "3.0" in errors[0]

    def test_rhythm_correct(self):
        """A correct 4/4 measure should produce no errors."""
        score = _make_score(measures=[
            [("C4", 2.0), ("D4", 2.0)],
            [("E4", 4.0)],
        ])
        errors = check_rhythm_consistency(score)
        assert errors == []

    def test_pickup_measure_allowed(self):
        """A shorter first measure (anacrusis) should not be flagged."""
        score = _make_score(measures=[
            [("C4", 1.0)],          # Pickup: only 1 beat
            [("D4", 2.0), ("E4", 2.0)],  # Full bar
        ])
        errors = check_rhythm_consistency(score)
        assert errors == []


# ===========================================================================
# Instrument range checks
# ===========================================================================

class TestInstrumentRanges:
    """Tests for check_instrument_ranges."""

    def test_range_violation(self):
        """A violin note below G3 (MIDI 55) should be flagged as an error."""
        score = _make_score(
            part_name="Violin",
            measures=[[("C3", 4.0)]],  # C3 = MIDI 48, well below violin range
        )
        messages = check_instrument_ranges(score)
        errors = [m for m in messages if m.startswith("[error]")]
        assert len(errors) >= 1
        assert "outside range" in errors[0]

    def test_range_warning_boundary(self):
        """A violin note near the lower boundary should produce a warning."""
        # Violin low is MIDI 55 (G3).  MIDI 56 (G#3/Ab3) is within 2 semitones.
        score = _make_score(
            part_name="Violin",
            measures=[[("G#3", 4.0)]],  # MIDI 56, 1 semitone above boundary
        )
        messages = check_instrument_ranges(score)
        warnings = [m for m in messages if m.startswith("[warning]")]
        assert len(warnings) >= 1
        assert "near boundary" in warnings[0]

    def test_in_range_no_issues(self):
        """Notes well within the violin range should produce no messages."""
        score = _make_score(
            part_name="Violin",
            measures=[[("A4", 4.0)]],  # MIDI 69 -- comfortably in range
        )
        messages = check_instrument_ranges(score)
        assert messages == []


# ===========================================================================
# Repetitiveness checks
# ===========================================================================

class TestRepetitiveness:
    """Tests for check_repetitiveness."""

    def test_repetitiveness_detection(self):
        """5 identical measures should trigger a repetitiveness warning."""
        identical_measure = [("C4", 2.0), ("E4", 2.0)]
        score = _make_score(measures=[identical_measure] * 5)
        warnings = check_repetitiveness(score)
        assert len(warnings) == 1
        assert "5 identical consecutive measures" in warnings[0]

    def test_no_repetitiveness(self):
        """Varied measures should not trigger repetitiveness warnings."""
        score = _make_score(measures=[
            [("C4", 4.0)],
            [("D4", 4.0)],
            [("E4", 4.0)],
            [("F4", 4.0)],
            [("G4", 4.0)],
        ])
        warnings = check_repetitiveness(score)
        assert warnings == []

    def test_three_identical_below_threshold(self):
        """3 identical measures (below the threshold of 4) should not warn."""
        same = [("C4", 4.0)]
        score = _make_score(measures=[same, same, same, [("D4", 4.0)]])
        warnings = check_repetitiveness(score)
        assert warnings == []


# ===========================================================================
# Empty output checks
# ===========================================================================

class TestEmptyOutput:
    """Tests for check_empty_output."""

    def test_empty_score_detection(self):
        """A score with no parts should produce an error."""
        score = stream.Score()
        errors = check_empty_output(score)
        assert any("no parts" in e for e in errors)

    def test_rests_only_detection(self):
        """A part containing only rests should be flagged."""
        score = _make_score(measures=[
            [("rest", 4.0)],
            [("rest", 4.0)],
        ])
        errors = check_empty_output(score)
        assert any("only rests" in e for e in errors)

    def test_non_empty_passes(self):
        """A part with actual notes should not be flagged."""
        score = _make_score(measures=[[("C4", 4.0)]])
        errors = check_empty_output(score)
        assert errors == []


# ===========================================================================
# Parallel motion checks
# ===========================================================================

class TestParallelMotion:
    """Tests for check_parallel_motion."""

    def test_parallel_octaves_detected(self):
        """Two parts moving in parallel octaves should produce a warning."""
        score = stream.Score()

        top = stream.Part()
        top.partName = "Soprano"
        bottom = stream.Part()
        bottom.partName = "Bass"

        ts = meter.TimeSignature("4/4")

        # Build parallel octaves: C5-C4 -> D5-D4 -> E5-E4 -> F5-F4
        top_m = stream.Measure(number=1)
        top_m.insert(0, ts)
        for p in ["C5", "D5", "E5", "F5"]:
            top_m.append(note.Note(p, quarterLength=1.0))
        top.append(top_m)

        bot_m = stream.Measure(number=1)
        bot_m.insert(0, meter.TimeSignature("4/4"))
        for p in ["C4", "D4", "E4", "F4"]:
            bot_m.append(note.Note(p, quarterLength=1.0))
        bottom.append(bot_m)

        score.append(top)
        score.append(bottom)

        warnings = check_parallel_motion(score)
        assert len(warnings) >= 1

    def test_no_parallel_issues(self):
        """Contrary / oblique motion should not produce warnings."""
        score = stream.Score()

        top = stream.Part()
        top.partName = "Soprano"
        bottom = stream.Part()
        bottom.partName = "Bass"

        ts = meter.TimeSignature("4/4")

        # Contrary motion: soprano ascending, bass descending.
        top_m = stream.Measure(number=1)
        top_m.insert(0, ts)
        for p in ["C5", "D5", "E5", "F5"]:
            top_m.append(note.Note(p, quarterLength=1.0))
        top.append(top_m)

        bot_m = stream.Measure(number=1)
        bot_m.insert(0, meter.TimeSignature("4/4"))
        for p in ["C4", "B3", "A3", "G3"]:
            bot_m.append(note.Note(p, quarterLength=1.0))
        bottom.append(bot_m)

        score.append(top)
        score.append(bottom)

        warnings = check_parallel_motion(score)
        assert warnings == []


# ===========================================================================
# Integration: validate_score
# ===========================================================================

class TestValidateScore:
    """Tests for the top-level validate_score function."""

    def test_valid_score_passes(self):
        """A well-formed 4-bar piano piece should pass all checks."""
        score = _make_score(
            part_name="Piano",
            measures=[
                [("C4", 2.0), ("E4", 2.0)],
                [("D4", 2.0), ("F4", 2.0)],
                [("E4", 1.0), ("G4", 1.0), ("A4", 1.0), ("B4", 1.0)],
                [("C5", 4.0)],
            ],
        )
        result = validate_score(score)
        assert isinstance(result, TheoryCheckResult)
        assert result.passed, f"Expected pass but got errors: {result.errors}"

    def test_validate_score_from_file(self, tmp_path):
        """Write a MusicXML file and validate from path."""
        score = _make_score(
            part_name="Piano",
            measures=[
                [("C4", 2.0), ("E4", 2.0)],
                [("G4", 4.0)],
            ],
        )
        out = tmp_path / "test_score.musicxml"
        score.write("musicxml", fp=str(out))
        assert out.exists()

        result = validate_score(str(out))
        assert isinstance(result, TheoryCheckResult)
        # The file should parse and pass basic checks.
        assert result.passed, f"Expected pass but got errors: {result.errors}"

    def test_validate_score_missing_file(self):
        """Validating a nonexistent file should return an error."""
        result = validate_score("/nonexistent/path/score.musicxml")
        assert not result.passed
        assert any("not found" in e.lower() for e in result.errors)

    def test_validate_aggregates_multiple_issues(self):
        """Ensure that errors from different checks are aggregated."""
        # Build a score with a rhythm error AND an out-of-range note.
        # Note: first measure is allowed to be a pickup, so we need 2 measures.
        score = _make_score(
            part_name="Violin",
            measures=[
                [("C4", 4.0)],  # Valid first measure
                [("C2", 3.0)],  # C2 = out of range; 3 beats = rhythm error
            ],
        )
        result = validate_score(score)
        assert not result.passed
        assert len(result.errors) >= 2


# ===========================================================================
# Audio validator
# ===========================================================================

class TestAudioValidator:
    """Tests for audio_validator functions."""

    def test_audio_validator_missing_file(self):
        """check_audio on a non-existent file should return issues."""
        result = check_audio("/nonexistent/audio/file.wav")
        assert not result["valid"]
        assert len(result["issues"]) > 0
        assert any("file_not_found" in issue for issue in result["issues"])

    def test_get_audio_info_missing_file(self):
        """get_audio_info on a non-existent file should contain an error key."""
        info = get_audio_info("/nonexistent/audio/file.wav")
        assert "error" in info
        assert "not found" in info["error"].lower()

    @pytest.mark.system
    def test_check_audio_info(self, tmp_path):
        """Integration test: generate a short WAV and validate it.

        Requires ffmpeg/ffprobe to be installed (marked as @pytest.mark.system).
        """
        import shutil
        import subprocess

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            pytest.skip("ffmpeg not available")

        # Generate a 2-second 440 Hz sine tone.
        wav_path = str(tmp_path / "tone.wav")
        subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=2",
                "-ar", "44100",
                "-ac", "1",
                wav_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        # --- get_audio_info ---
        info = get_audio_info(wav_path)
        assert "error" not in info
        assert info["sample_rate"] == 44100
        assert info["channels"] == 1
        assert 1.8 <= info["duration_s"] <= 2.2

        # --- check_audio (should be valid) ---
        result = check_audio(wav_path, expected_duration_s=2.0)
        assert result["valid"], f"Expected valid but got issues: {result['issues']}"
        assert result["sample_rate"] == 44100
        assert result["channels"] == 1
