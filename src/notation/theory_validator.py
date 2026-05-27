"""Music theory validation for generated scores.

Uses music21 to analyze scores and detect common composition errors
such as out-of-range notes, rhythm inconsistencies, parallel fifths/octaves,
excessive repetition, and empty output.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import music21
from music21 import converter, interval, note, stream

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instrument ranges as (lowest_midi, highest_midi) inclusive
# ---------------------------------------------------------------------------
RANGES: dict[str, tuple[int, int]] = {
    "violin": (55, 103),  # G3 to G7
    "viola": (48, 91),  # C3 to G6
    "cello": (36, 76),  # C2 to E5
    "contrabass": (28, 67),  # E1 to G4
    "flute": (60, 96),  # C4 to C7
    "oboe": (58, 91),  # Bb3 to G6
    "clarinet": (50, 94),  # D3 to Bb6
    "bassoon": (34, 75),  # Bb1 to Eb5
    "horn": (34, 77),  # Bb1 to F5
    "trumpet": (54, 82),  # F#3 to Bb5
    "trombone": (40, 72),  # E2 to C5
    "tuba": (28, 58),  # E1 to Bb3
    "piano": (21, 108),  # A0 to C8
    "soprano": (60, 81),  # C4 to A5
    "alto": (55, 77),  # G3 to F5
    "tenor": (48, 72),  # C3 to C5
    "bass": (40, 65),  # E2 to F4
}

_BOUNDARY_SEMITONES = 2  # Notes within this many semitones of a limit trigger a warning.


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class TheoryCheckResult:
    """Aggregated result of all theory checks on a score."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A score passes validation if there are zero errors."""
        return len(self.errors) == 0

    def __str__(self) -> str:  # pragma: no cover
        lines = []
        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            lines.extend(f"  - {e}" for e in self.errors)
        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            lines.extend(f"  - {w}" for w in self.warnings)
        if not lines:
            lines.append("All checks passed.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _expected_quarter_length(ts: music21.meter.TimeSignature) -> float:
    """Return the expected total quarter-length for one full measure."""
    return ts.barDuration.quarterLength


def _match_instrument(part_name: str) -> str | None:
    """Fuzzy-match a part name to a key in RANGES (case-insensitive contains)."""
    if not part_name:
        return None
    lower = part_name.lower()
    for instrument_key in RANGES:
        if instrument_key in lower:
            return instrument_key
    return None


def _notes_in_measure(measure: stream.Measure) -> list[note.Note]:
    """Extract all Note objects from a measure (skipping rests and chords' constituent notes)."""
    result: list[note.Note] = []
    for el in measure.recurse().notesAndRests:
        if isinstance(el, note.Note):
            result.append(el)
        elif isinstance(el, music21.chord.Chord):
            for pitch in el.pitches:
                # Wrap each chord pitch as a standalone Note for uniform handling.
                n = note.Note(pitch)
                n.quarterLength = el.quarterLength
                result.append(n)
    return result


def _measure_signature(measure: stream.Measure) -> tuple[tuple[str, float], ...]:
    """Return a hashable signature of a measure's note/rest content.

    Each element is (pitch_name_or_'rest', quarterLength).
    """
    elements: list[tuple[str, float]] = []
    for el in measure.recurse().notesAndRests:
        if isinstance(el, note.Note):
            elements.append((el.nameWithOctave, el.quarterLength))
        elif isinstance(el, music21.chord.Chord):
            # Use sorted pitch names to ensure deterministic ordering.
            pitches = " ".join(sorted(p.nameWithOctave for p in el.pitches))
            elements.append((pitches, el.quarterLength))
        elif isinstance(el, note.Rest):
            elements.append(("rest", el.quarterLength))
    return tuple(elements)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_rhythm_consistency(score: stream.Score) -> list[str]:
    """Verify that note/rest durations in every measure sum to the time signature.

    The first measure of each part is allowed to be shorter (pickup / anacrusis).
    """
    errors: list[str] = []

    for part_idx, part in enumerate(score.parts):
        part_name = part.partName or f"Part {part_idx + 1}"
        current_ts: music21.meter.TimeSignature | None = None
        measures = list(part.getElementsByClass(stream.Measure))

        for m_idx, measure in enumerate(measures):
            # Update time signature if one is present in this measure.
            ts_in_measure = measure.getElementsByClass(music21.meter.TimeSignature)
            if ts_in_measure:
                current_ts = ts_in_measure[0]

            if current_ts is None:
                # Default to 4/4 if no time signature has been seen.
                current_ts = music21.meter.TimeSignature("4/4")

            expected_ql = _expected_quarter_length(current_ts)

            # Sum durations of all notes and rests at the top level of the measure.
            actual_ql = 0.0
            for el in measure.notesAndRests:
                actual_ql += el.quarterLength

            # Allow pickup measure (first measure may be shorter).
            is_first = m_idx == 0
            if is_first and actual_ql < expected_ql:
                continue

            # Use a small tolerance for floating-point comparison.
            if abs(actual_ql - expected_ql) > 0.01:
                errors.append(
                    f"{part_name}, measure {measure.number}: "
                    f"duration {actual_ql} quarter-lengths vs expected {expected_ql} "
                    f"({current_ts.ratioString})"
                )

    return errors


def check_instrument_ranges(score: stream.Score) -> list[str]:
    """Check that notes fall within the playable range for each instrument.

    Returns errors for out-of-range notes and warnings for notes near boundaries.
    """
    messages: list[str] = []

    for part_idx, part in enumerate(score.parts):
        part_name = part.partName or f"Part {part_idx + 1}"
        instrument_key = _match_instrument(part_name)

        if instrument_key is None:
            # Also check the music21 instrument object attached to the part.
            instr = part.getInstrument(returnDefault=False)
            if instr is not None:
                instrument_key = _match_instrument(instr.instrumentName or "")

        if instrument_key is None:
            logger.debug("No range data for part '%s'; skipping range check.", part_name)
            continue

        low, high = RANGES[instrument_key]

        for measure in part.getElementsByClass(stream.Measure):
            for n in _notes_in_measure(measure):
                midi = n.pitch.midi
                loc = (
                    f"{part_name} ({instrument_key}), measure {measure.number}, {n.nameWithOctave}"
                )
                if midi < low or midi > high:
                    messages.append(f"[error] {loc}: MIDI {midi} outside range {low}-{high}")
                elif midi < low + _BOUNDARY_SEMITONES or midi > high - _BOUNDARY_SEMITONES:
                    messages.append(
                        f"[warning] {loc}: MIDI {midi} near boundary of range {low}-{high}"
                    )

    return messages


def check_parallel_motion(score: stream.Score) -> list[str]:
    """Detect parallel perfect fifths and octaves between outer voices.

    Examines the highest and lowest parts (by order in the score) and checks
    successive harmonic intervals for parallel motion at unison, 5th, or octave.
    """
    warnings: list[str] = []

    parts = list(score.parts)
    if len(parts) < 2:
        return warnings

    top_part = parts[0]
    bottom_part = parts[-1]

    top_notes = list(top_part.recurse().getElementsByClass(note.Note))
    bottom_notes = list(bottom_part.recurse().getElementsByClass(note.Note))

    if len(top_notes) < 2 or len(bottom_notes) < 2:
        return warnings

    # Align notes by their absolute offset within the part (using
    # measure offset + note offset within measure) to form vertical pairs.
    def _get_part_offsets(part: stream.Part) -> dict[float, note.Note]:
        result: dict[float, note.Note] = {}
        for measure in part.getElementsByClass(stream.Measure):
            m_offset = float(measure.offset)
            for n in measure.getElementsByClass(note.Note):
                abs_offset = m_offset + float(n.offset)
                result[abs_offset] = n
        return result

    top_by_offset = _get_part_offsets(top_part)
    bottom_by_offset = _get_part_offsets(bottom_part)

    # Find shared offsets in sorted order.
    shared_offsets = sorted(set(top_by_offset.keys()) & set(bottom_by_offset.keys()))
    if len(shared_offsets) < 2:
        return warnings

    # Walk through successive pairs.
    _PARALLEL_INTERVALS = {0, 7, 12, 19, 24}  # Unison, P5, P8, P5+P8, P15 (in semitones mod 12)
    _PARALLEL_SIMPLE = {0, 7}  # Semitone classes to flag (unison and perfect fifth mod 12)

    prev_semitones: int | None = None
    prev_offset: float | None = None

    for offset in shared_offsets:
        top_n = top_by_offset[offset]
        bot_n = bottom_by_offset[offset]
        semitones = abs(top_n.pitch.midi - bot_n.pitch.midi)
        simple = semitones % 12

        if prev_semitones is not None:
            prev_simple = prev_semitones % 12
            if simple in _PARALLEL_SIMPLE and simple == prev_simple and semitones == prev_semitones:
                intv = interval.Interval(noteStart=bot_n, noteEnd=top_n)
                warnings.append(
                    f"Parallel {intv.niceName} between outer voices "
                    f"at offsets {prev_offset} and {offset}"
                )

        prev_semitones = semitones
        prev_offset = offset

    return warnings


def check_repetitiveness(score: stream.Score) -> list[str]:
    """Flag any part that has 4 or more identical consecutive measures."""
    warnings: list[str] = []
    threshold = 4

    for part_idx, part in enumerate(score.parts):
        part_name = part.partName or f"Part {part_idx + 1}"
        measures = list(part.getElementsByClass(stream.Measure))

        if len(measures) < threshold:
            continue

        streak = 1
        prev_sig = _measure_signature(measures[0])
        streak_start = measures[0].number

        for measure in measures[1:]:
            sig = _measure_signature(measure)
            if sig == prev_sig and sig:  # Don't count empty signatures as identical.
                streak += 1
            else:
                if streak >= threshold:
                    warnings.append(
                        f"{part_name}: {streak} identical consecutive measures "
                        f"starting at measure {streak_start}"
                    )
                streak = 1
                streak_start = measure.number
            prev_sig = sig

        # Check trailing streak.
        if streak >= threshold:
            warnings.append(
                f"{part_name}: {streak} identical consecutive measures "
                f"starting at measure {streak_start}"
            )

    return warnings


def check_empty_output(score: stream.Score) -> list[str]:
    """Detect empty scores, empty parts, or parts consisting entirely of rests."""
    errors: list[str] = []

    parts = list(score.parts)
    if not parts:
        errors.append("Score contains no parts.")
        return errors

    for part_idx, part in enumerate(parts):
        part_name = part.partName or f"Part {part_idx + 1}"
        measures = list(part.getElementsByClass(stream.Measure))

        if not measures:
            errors.append(f"{part_name}: part has no measures.")
            continue

        has_notes = False
        for measure in measures:
            notes_in_m = list(measure.recurse().getElementsByClass(note.Note))
            chords_in_m = list(measure.recurse().getElementsByClass(music21.chord.Chord))
            if notes_in_m or chords_in_m:
                has_notes = True
                break

        if not has_notes:
            errors.append(f"{part_name}: part contains only rests (no pitched content).")

    return errors


# ---------------------------------------------------------------------------
# Top-level validator
# ---------------------------------------------------------------------------


def validate_score(
    score_or_path: Union[stream.Score, str, Path],
) -> TheoryCheckResult:
    """Run all theory checks against a score.

    Parameters
    ----------
    score_or_path:
        A ``music21.stream.Score`` object, or a file path to a MusicXML,
        ABC, or MIDI file that can be parsed by ``music21.converter``.

    Returns
    -------
    TheoryCheckResult
        Aggregated errors and warnings from every check.
    """
    result = TheoryCheckResult()

    # --- Parse input -------------------------------------------------------
    if isinstance(score_or_path, (str, Path)):
        path = Path(score_or_path)
        if not path.exists():
            result.errors.append(f"File not found: {path}")
            return result
        try:
            score = converter.parse(str(path))
        except Exception as exc:
            result.errors.append(f"Failed to parse '{path}': {exc}")
            return result
        # converter.parse may return an Opus; extract first Score.
        if isinstance(score, stream.Opus):
            score = score.scores[0] if score.scores else stream.Score()
        if not isinstance(score, stream.Score):
            # Wrap in a Score if converter returned a Part or other stream.
            wrapper = stream.Score()
            wrapper.append(score)
            score = wrapper
    else:
        score = score_or_path

    # --- Run checks --------------------------------------------------------
    logger.info("Running theory validation on score with %d part(s).", len(score.parts))

    # Empty output check (errors).
    result.errors.extend(check_empty_output(score))

    # Rhythm consistency (errors).
    result.errors.extend(check_rhythm_consistency(score))

    # Instrument range (mixed errors and warnings).
    range_messages = check_instrument_ranges(score)
    for msg in range_messages:
        if msg.startswith("[error]"):
            result.errors.append(msg[len("[error] ") :])
        elif msg.startswith("[warning]"):
            result.warnings.append(msg[len("[warning] ") :])
        else:
            result.warnings.append(msg)

    # Parallel motion (warnings).
    result.warnings.extend(check_parallel_motion(score))

    # Repetitiveness (warnings).
    result.warnings.extend(check_repetitiveness(score))

    if result.passed:
        logger.info("Theory validation passed (%d warning(s)).", len(result.warnings))
    else:
        logger.warning(
            "Theory validation failed: %d error(s), %d warning(s).",
            len(result.errors),
            len(result.warnings),
        )

    return result
