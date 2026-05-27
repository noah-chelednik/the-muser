"""DiffSinger vocal synthesis wrapper for The Muser.

Provides score-driven singing voice synthesis from MusicXML notation.
Supports both ONNX inference (fast, production) and PyTorch fallback.

The pipeline:
    1. Parse MusicXML to extract vocal melody (pitch, duration, timing, lyrics)
    2. Convert lyrics to phoneme sequences (G2P or SOFA alignment)
    3. Build DiffSinger .ds project file
    4. Run variance prediction (pitch, energy, breathiness, voicing, tension)
    5. Run acoustic model diffusion
    6. Vocode to waveform

Usage::

    from src.generation.diffsinger_wrapper import synthesize_singing

    wav_path = synthesize_singing(
        musicxml_path="score.musicxml",
        voice_model_dir="voices/my-voice-diffsinger/",
        pitch_expressiveness=1.0,
        breathiness=0.2,
        tension=0.5,
    )
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src.orchestrator.config import (
    DIFFSINGER_DIR,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# DiffSinger internal parameters
DS_HOP_SIZE = 512
DS_SAMPLE_RATE = 44100
DS_MEL_BINS = 128

# Phoneme inventory for English (DiffSinger ARPAbet variant)
# These are the standard phonemes used by DiffSinger English models.
_ARPABET_VOWELS = {
    "AA",
    "AE",
    "AH",
    "AO",
    "AW",
    "AX",
    "AXR",
    "AY",
    "EH",
    "ER",
    "EY",
    "IH",
    "IX",
    "IY",
    "OW",
    "OY",
    "UH",
    "UW",
    "UX",
}
_ARPABET_CONSONANTS = {
    "B",
    "CH",
    "D",
    "DH",
    "DX",
    "EL",
    "EM",
    "EN",
    "F",
    "G",
    "HH",
    "JH",
    "K",
    "L",
    "M",
    "N",
    "NG",
    "NX",
    "P",
    "Q",
    "R",
    "S",
    "SH",
    "T",
    "TH",
    "V",
    "W",
    "WH",
    "Y",
    "Z",
    "ZH",
}
_SILENCE_PHONEMES = {"SP", "AP", ""}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def synthesize_singing(
    musicxml_path: str,
    voice_model_dir: str,
    output_path: str | None = None,
    pitch_expressiveness: float = 1.0,
    breathiness: float = 0.0,
    voicing: float = 1.0,
    tension: float = 0.5,
    energy: float = 1.0,
    gender: float = 0.0,
) -> str:
    """Synthesize singing from a MusicXML score.

    This is the main entry point for score-driven vocal synthesis.
    Parses the MusicXML, builds a DiffSinger project, and runs inference.

    Args:
        musicxml_path: Path to MusicXML file containing the vocal part.
        voice_model_dir: Path to the trained DiffSinger voice model directory.
            Should contain acoustic.onnx/ckpt, variance.onnx/ckpt, and config.
        output_path: Output WAV file path. Auto-generated if None.
        pitch_expressiveness: Scale factor for pitch variation (0.0 = flat, 1.0 = natural,
            >1.0 = exaggerated). Controls how much of the predicted pitch curve is applied.
        breathiness: Target breathiness level (0.0 = clean, 1.0 = very breathy).
        voicing: Voicing strength (0.0 = whispered, 1.0 = fully voiced).
        tension: Vocal tension (0.0 = relaxed, 1.0 = very tense).
        energy: Energy/volume scale (0.5 = soft, 1.0 = normal, 1.5 = loud).
        gender: Gender shift (-1.0 = feminize, 0.0 = neutral, 1.0 = masculinize).

    Returns:
        Path to the rendered vocal audio WAV file.

    Raises:
        FileNotFoundError: If musicxml_path or voice_model_dir doesn't exist.
        RuntimeError: If synthesis fails.
    """
    mxml_path = Path(musicxml_path)
    model_dir = Path(voice_model_dir)

    if not mxml_path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {musicxml_path}")
    if not model_dir.exists():
        raise FileNotFoundError(f"Voice model directory not found: {voice_model_dir}")

    if output_path is None:
        output_path = str(mxml_path.parent / f"{mxml_path.stem}_vocals.wav")

    logger.info(
        "Synthesizing singing: %s with model %s -> %s",
        musicxml_path,
        voice_model_dir,
        output_path,
    )

    # Step 1: Extract vocal data from MusicXML
    vocal_data = _extract_vocal_data(str(mxml_path))

    if not vocal_data["notes"]:
        raise RuntimeError(f"No vocal notes found in {musicxml_path}")

    logger.info(
        "Extracted %d notes, total duration %.1fs",
        len(vocal_data["notes"]),
        vocal_data["total_duration_s"],
    )

    # Step 2: Build phoneme sequence from lyrics
    phoneme_data = _lyrics_to_phonemes(vocal_data)

    # Step 3: Build .ds project file
    with tempfile.TemporaryDirectory(prefix="muser_ds_") as tmpdir:
        ds_path = os.path.join(tmpdir, "project.ds")
        _build_ds_project(
            vocal_data=vocal_data,
            phoneme_data=phoneme_data,
            ds_path=ds_path,
            pitch_expressiveness=pitch_expressiveness,
            breathiness=breathiness,
            voicing=voicing,
            tension=tension,
            energy=energy,
            gender=gender,
        )

        # Step 4: Run inference
        _run_inference(
            ds_path=ds_path,
            model_dir=str(model_dir),
            output_path=output_path,
        )

    if not os.path.exists(output_path):
        raise RuntimeError(f"Synthesis produced no output file: {output_path}")

    logger.info("Singing synthesis complete: %s", output_path)
    return output_path


def musicxml_to_ds(
    musicxml_path: str,
    lyrics: str,
    output_path: str | None = None,
) -> str:
    """Convert MusicXML + lyrics to DiffSinger .ds format.

    Extracts the vocal melody from MusicXML and combines it with provided
    lyrics to produce a .ds project file suitable for DiffSinger inference.

    Args:
        musicxml_path: Path to MusicXML file with vocal part.
        lyrics: Lyrics text, space-separated syllables matching notes.
        output_path: Output .ds file path. Auto-generated if None.

    Returns:
        Path to the generated .ds file.

    Raises:
        FileNotFoundError: If the MusicXML file doesn't exist.
    """
    mxml_path = Path(musicxml_path)
    if not mxml_path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {musicxml_path}")

    if output_path is None:
        output_path = str(mxml_path.parent / f"{mxml_path.stem}.ds")

    # Extract vocal data
    vocal_data = _extract_vocal_data(str(mxml_path))

    # Override lyrics if provided
    if lyrics:
        syllables = lyrics.split()
        for i, note in enumerate(vocal_data["notes"]):
            if i < len(syllables):
                note["lyric"] = syllables[i]
            else:
                note["lyric"] = ""

    # Build phoneme data
    phoneme_data = _lyrics_to_phonemes(vocal_data)

    # Build the .ds project
    _build_ds_project(
        vocal_data=vocal_data,
        phoneme_data=phoneme_data,
        ds_path=output_path,
    )

    logger.info("Generated DS file: %s (%d notes)", output_path, len(vocal_data["notes"]))
    return output_path


def render_vocals(
    ds_file: str,
    model_path: str = "",
    output_path: str | None = None,
) -> str:
    """Render singing vocals from a DiffSinger project file.

    Lower-level API that takes an already-prepared .ds file and runs
    DiffSinger inference directly.

    Args:
        ds_file: Path to .ds file (DiffSinger project).
        model_path: Path to DiffSinger voice model directory.
        output_path: Output WAV path. Auto-generated if None.

    Returns:
        Path to rendered vocal audio.

    Raises:
        FileNotFoundError: If input file or model doesn't exist.
        RuntimeError: If rendering fails.
    """
    input_path = Path(ds_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {ds_file}")

    if not model_path:
        model_path = str(DIFFSINGER_DIR / "checkpoints" / "default")

    if output_path is None:
        output_path = str(input_path.parent / f"{input_path.stem}_vocals.wav")

    logger.info("DiffSinger render: %s -> %s", ds_file, output_path)

    _run_inference(
        ds_path=ds_file,
        model_dir=model_path,
        output_path=output_path,
    )

    if not os.path.exists(output_path):
        raise RuntimeError(f"DiffSinger rendering produced no output: {output_path}")

    logger.info("DiffSinger render complete: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# MusicXML extraction
# ---------------------------------------------------------------------------


def _extract_vocal_data(musicxml_path: str) -> dict[str, Any]:
    """Extract vocal melody data from a MusicXML file.

    Parses the score looking for a vocal/voice part and extracts
    note pitches, durations, offsets, and lyrics.

    Returns a dict with:
        - notes: list of {midi, duration_beats, offset_beats, lyric, is_rest}
        - tempo: BPM from the score
        - total_duration_s: total duration in seconds
        - key: key signature string
        - time_signature: time signature string
    """
    try:
        import music21
    except ImportError:
        raise RuntimeError(
            "music21 is required for MusicXML parsing. Install with: pip install music21"
        )

    score = music21.converter.parse(musicxml_path)

    # Try to find a vocal part
    vocal_part = _find_vocal_part(score)
    if vocal_part is None:
        # Fall back to first part
        parts = list(score.parts)
        if not parts:
            raise RuntimeError(f"No parts found in {musicxml_path}")
        vocal_part = parts[0]
        logger.info("No explicit vocal part found; using first part: %s", vocal_part.partName)

    # Extract tempo
    tempo = 120.0  # default
    for mm in score.flatten().getElementsByClass("MetronomeMark"):
        tempo = mm.number
        break

    # Extract key
    key_str = "C major"
    for ks in score.flatten().getElementsByClass("KeySignature"):
        try:
            key_str = str(ks.asKey())
        except Exception:
            pass
        break

    # Extract time signature
    time_sig = "4/4"
    for ts in score.flatten().getElementsByClass("TimeSignature"):
        time_sig = ts.ratioString
        break

    # Extract notes
    notes_data: list[dict[str, Any]] = []
    for element in vocal_part.flatten().notesAndRests:
        if element.isRest:
            notes_data.append(
                {
                    "midi": 0,
                    "duration_beats": float(element.quarterLength),
                    "offset_beats": float(element.offset),
                    "lyric": "",
                    "is_rest": True,
                }
            )
        elif hasattr(element, "pitch"):
            # Get lyrics
            lyric_text = ""
            if element.lyrics:
                lyric_parts = []
                for lyr in element.lyrics:
                    if lyr.text:
                        lyric_parts.append(lyr.text)
                lyric_text = " ".join(lyric_parts)

            notes_data.append(
                {
                    "midi": element.pitch.midi,
                    "duration_beats": float(element.quarterLength),
                    "offset_beats": float(element.offset),
                    "lyric": lyric_text,
                    "is_rest": False,
                    "pitch_name": element.pitch.nameWithOctave,
                }
            )
        elif hasattr(element, "pitches") and element.pitches:
            # Chord: use the highest note (melody)
            top_pitch = max(element.pitches, key=lambda p: p.midi)
            lyric_text = ""
            if element.lyrics:
                lyric_parts = []
                for lyr in element.lyrics:
                    if lyr.text:
                        lyric_parts.append(lyr.text)
                lyric_text = " ".join(lyric_parts)

            notes_data.append(
                {
                    "midi": top_pitch.midi,
                    "duration_beats": float(element.quarterLength),
                    "offset_beats": float(element.offset),
                    "lyric": lyric_text,
                    "is_rest": False,
                    "pitch_name": top_pitch.nameWithOctave,
                }
            )

    # Calculate total duration
    beats_per_second = tempo / 60.0
    total_beats = max(
        (n["offset_beats"] + n["duration_beats"] for n in notes_data),
        default=0.0,
    )
    total_duration_s = total_beats / beats_per_second if beats_per_second > 0 else 0.0

    return {
        "notes": notes_data,
        "tempo": tempo,
        "total_duration_s": total_duration_s,
        "key": key_str,
        "time_signature": time_sig,
        "beats_per_second": beats_per_second,
    }


def _find_vocal_part(score: Any) -> Any:
    """Find the vocal part in a music21 Score.

    Looks for parts with vocal-related names or MIDI program changes
    indicating a vocal instrument.
    """
    vocal_keywords = {
        "vocal",
        "voice",
        "vocals",
        "sing",
        "soprano",
        "alto",
        "tenor",
        "bass",
        "baritone",
        "mezzo",
        "choir",
    }

    for part in score.parts:
        name = (part.partName or "").lower()
        if any(kw in name for kw in vocal_keywords):
            logger.info("Found vocal part: %s", part.partName)
            return part

    # Check MIDI instrument programs (vocals are typically 52-54, 85)
    for part in score.parts:
        for inst in part.getElementsByClass("Instrument"):
            if hasattr(inst, "midiProgram"):
                if inst.midiProgram in (52, 53, 54, 85):
                    logger.info("Found vocal part by MIDI program: %s", part.partName)
                    return part

    return None


# ---------------------------------------------------------------------------
# Phoneme processing
# ---------------------------------------------------------------------------


def _lyrics_to_phonemes(vocal_data: dict[str, Any]) -> dict[str, Any]:
    """Convert lyrics text to phoneme sequences.

    Tries multiple G2P backends:
    1. g2p_en (English grapheme-to-phoneme)
    2. phonemizer
    3. Simple rule-based fallback

    Returns a dict mapping note indices to phoneme data.
    """
    notes = vocal_data["notes"]
    phoneme_data: dict[str, Any] = {
        "method": "unknown",
        "notes": [],
    }

    # Collect all lyrics for batch processing
    lyrics_list: list[str] = []
    for note in notes:
        lyrics_list.append(note.get("lyric", ""))

    # Try G2P
    phoneme_results = _g2p_batch(lyrics_list)
    phoneme_data["notes"] = phoneme_results["phonemes"]
    phoneme_data["method"] = phoneme_results["method"]

    logger.info("Phoneme conversion method: %s", phoneme_data["method"])
    return phoneme_data


def _g2p_batch(texts: list[str]) -> dict[str, Any]:
    """Convert a batch of text strings to phoneme sequences.

    Returns dict with 'phonemes' (list of phoneme lists) and 'method'.
    """
    # Try g2p_en
    result = _try_g2p_en(texts)
    if result is not None:
        return result

    # Try phonemizer
    result = _try_phonemizer(texts)
    if result is not None:
        return result

    # Fallback
    return _fallback_g2p(texts)


def _try_g2p_en(texts: list[str]) -> dict[str, Any] | None:
    """Try using g2p_en for grapheme-to-phoneme conversion."""
    try:
        from g2p_en import G2p  # type: ignore[import-untyped]
    except ImportError:
        return None

    g2p = G2p()
    phonemes_list: list[list[str]] = []

    for text in texts:
        if not text or not text.strip():
            phonemes_list.append(["SP"])
            continue

        try:
            raw = g2p(text.strip())
            # Filter out empty strings and spaces; keep stress markers
            phonemes = []
            for p in raw:
                p = p.strip()
                if p and p != " ":
                    # Remove stress numbers for DiffSinger compatibility
                    cleaned = "".join(c for c in p if not c.isdigit())
                    if cleaned:
                        phonemes.append(cleaned)
            if not phonemes:
                phonemes = ["SP"]
            phonemes_list.append(phonemes)
        except Exception as exc:
            logger.warning("g2p_en failed for '%s': %s", text, exc)
            phonemes_list.append(["SP"])

    return {"phonemes": phonemes_list, "method": "g2p_en"}


def _try_phonemizer(texts: list[str]) -> dict[str, Any] | None:
    """Try using phonemizer for G2P conversion."""
    try:
        from phonemizer import phonemize  # type: ignore[import-untyped]
        from phonemizer.separator import Separator  # type: ignore[import-untyped]
    except ImportError:
        return None

    phonemes_list: list[list[str]] = []
    separator = Separator(phone=" ", syllable="", word=" ")

    for text in texts:
        if not text or not text.strip():
            phonemes_list.append(["SP"])
            continue

        try:
            result = phonemize(
                text.strip(),
                language="en-us",
                backend="espeak",
                separator=separator,
                strip=True,
            )
            phonemes = [p for p in result.split() if p.strip()]
            if not phonemes:
                phonemes = ["SP"]
            phonemes_list.append(phonemes)
        except Exception as exc:
            logger.warning("phonemizer failed for '%s': %s", text, exc)
            phonemes_list.append(["SP"])

    return {"phonemes": phonemes_list, "method": "phonemizer"}


def _fallback_g2p(texts: list[str]) -> dict[str, Any]:
    """Simple rule-based fallback for G2P conversion.

    Not accurate but ensures the pipeline can always proceed.
    Results should be manually reviewed.
    """
    logger.warning("Using fallback G2P. Install g2p_en for better results: pip install g2p_en")

    phonemes_list: list[list[str]] = []

    # Simple vowel-based splitting
    vowels = set("aeiouAEIOU")

    for text in texts:
        if not text or not text.strip():
            phonemes_list.append(["SP"])
            continue

        word = text.strip().lower()
        phonemes: list[str] = []

        i = 0
        while i < len(word):
            if word[i] in vowels:
                # Vowel phoneme
                phoneme = word[i].upper()
                # Check for diphthongs
                if i + 1 < len(word) and word[i + 1] in vowels:
                    phoneme += word[i + 1].upper()
                    i += 1
                phonemes.append(phoneme)
            elif word[i].isalpha():
                # Consonant
                phoneme = word[i].upper()
                # Common digraphs
                if i + 1 < len(word):
                    digraph = word[i : i + 2]
                    if digraph in ("th", "sh", "ch", "ng", "wh", "zh"):
                        phoneme = digraph.upper()
                        i += 1
                phonemes.append(phoneme)
            i += 1

        if not phonemes:
            phonemes = ["SP"]
        phonemes_list.append(phonemes)

    return {"phonemes": phonemes_list, "method": "fallback-rules"}


# ---------------------------------------------------------------------------
# .ds project file generation
# ---------------------------------------------------------------------------


def _build_ds_project(
    vocal_data: dict[str, Any],
    phoneme_data: dict[str, Any],
    ds_path: str,
    pitch_expressiveness: float = 1.0,
    breathiness: float = 0.0,
    voicing: float = 1.0,
    tension: float = 0.5,
    energy: float = 1.0,
    gender: float = 0.0,
) -> None:
    """Build a DiffSinger .ds project file from extracted data.

    The .ds format is a JSON list where each element represents a segment
    (typically one utterance/phrase) with phoneme sequences, note information,
    and variance parameters.
    """

    notes = vocal_data["notes"]
    phonemes_per_note = phoneme_data["notes"]
    bps = vocal_data["beats_per_second"]

    # Build flat phoneme and note sequences
    ph_seq: list[str] = []
    ph_dur: list[float] = []
    note_seq: list[str] = []
    note_dur: list[float] = []
    ph_num: list[int] = []

    for i, note in enumerate(notes):
        note_duration_s = note["duration_beats"] / bps if bps > 0 else 0.5
        phonemes = phonemes_per_note[i] if i < len(phonemes_per_note) else ["SP"]

        if note["is_rest"]:
            # Rest: single SP phoneme
            ph_seq.append("SP")
            ph_dur.append(note_duration_s)
            note_seq.append("rest")
            note_dur.append(note_duration_s)
            ph_num.append(1)
        else:
            # Voiced note: phonemes share the note duration
            midi = note["midi"]
            note_name = note.get("pitch_name", _midi_to_note_name(midi))

            num_phones = len(phonemes)
            if num_phones == 0:
                phonemes = ["SP"]
                num_phones = 1

            # Distribute duration among phonemes
            # Consonants get shorter durations, vowels get longer
            phone_durs = _distribute_phoneme_durations(phonemes, note_duration_s)

            ph_seq.extend(phonemes)
            ph_dur.extend(phone_durs)
            note_seq.append(note_name)
            note_dur.append(note_duration_s)
            ph_num.append(num_phones)

    # Build the DS segment
    segment: dict[str, Any] = {
        "offset": 0.0,
        "text": " ".join(n.get("lyric", "") for n in notes if n.get("lyric")),
        "ph_seq": " ".join(ph_seq),
        "ph_dur": " ".join(f"{d:.6f}" for d in ph_dur),
        "ph_num": " ".join(str(n) for n in ph_num),
        "note_seq": " ".join(note_seq),
        "note_dur": " ".join(f"{d:.6f}" for d in note_dur),
        "input_type": "phoneme",
    }

    # Add expression parameters as per-frame variance hints
    total_frames = int(sum(ph_dur) * DS_SAMPLE_RATE / DS_HOP_SIZE)

    if breathiness != 0.0:
        # Breathiness curve: constant value across all frames
        # DiffSinger expects dB values, map 0..1 to -96..-20 dB range
        breathiness_db = -96.0 + breathiness * 76.0
        segment["breathiness"] = " ".join([f"{breathiness_db:.1f}"] * max(1, total_frames))

    if tension != 0.5:
        # Tension: map 0..1 to logit range -5..5
        tension_logit = (tension - 0.5) * 10.0
        segment["tension"] = " ".join([f"{tension_logit:.2f}"] * max(1, total_frames))

    if voicing != 1.0:
        # Voicing strength in dB (-96..0)
        voicing_db = -96.0 + voicing * 96.0
        segment["voicing"] = " ".join([f"{voicing_db:.1f}"] * max(1, total_frames))

    if energy != 1.0:
        # Energy scaling: stored as a multiplier for post-processing
        segment["energy_scale"] = energy

    if gender != 0.0:
        # Gender parameter: passed directly to DiffSinger
        segment["gender"] = " ".join([f"{gender:.2f}"] * max(1, total_frames))

    if pitch_expressiveness != 1.0:
        segment["pitch_expr"] = pitch_expressiveness

    # Write the .ds file (list of segments)
    ds_data = [segment]
    Path(ds_path).write_text(
        json.dumps(ds_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "Built .ds project: %d phonemes, %d notes, %.1fs total",
        len(ph_seq),
        len(note_seq),
        sum(ph_dur),
    )


def _distribute_phoneme_durations(
    phonemes: list[str],
    total_duration_s: float,
) -> list[float]:
    """Distribute a note's duration among its phonemes.

    Consonants typically occupy 30-80ms, while vowels take up the
    remaining duration. This heuristic ensures natural-sounding
    consonant-vowel timing.
    """
    if not phonemes:
        return [total_duration_s]

    if len(phonemes) == 1:
        return [total_duration_s]

    # Classify phonemes as consonant or vowel
    weights: list[float] = []
    for ph in phonemes:
        ph_upper = ph.upper().rstrip("0123456789")
        if ph_upper in _ARPABET_VOWELS or ph_upper in ("SP", "AP"):
            weights.append(3.0)  # Vowels get 3x weight
        elif ph_upper in _ARPABET_CONSONANTS:
            weights.append(1.0)  # Consonants get 1x weight
        elif any(c in ph.lower() for c in "aeiou"):
            weights.append(2.5)  # Likely vowel
        else:
            weights.append(1.0)  # Default to consonant weight

    total_weight = sum(weights)
    if total_weight == 0:
        return [total_duration_s / len(phonemes)] * len(phonemes)

    durations: list[float] = []
    for w in weights:
        dur = total_duration_s * (w / total_weight)
        # Enforce minimum duration (10ms)
        dur = max(dur, 0.01)
        durations.append(dur)

    # Normalize to match total duration exactly
    scale = total_duration_s / sum(durations)
    durations = [d * scale for d in durations]

    return durations


def _midi_to_note_name(midi: int) -> str:
    """Convert a MIDI note number to a note name (e.g., 60 -> 'C4')."""
    if midi <= 0:
        return "rest"

    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (midi // 12) - 1
    note = note_names[midi % 12]
    return f"{note}{octave}"


# ---------------------------------------------------------------------------
# Inference engine
# ---------------------------------------------------------------------------


def _run_inference(
    ds_path: str,
    model_dir: str,
    output_path: str,
) -> None:
    """Run DiffSinger inference on a .ds project file.

    Tries inference methods in order:
    1. ONNX Runtime (fast, production)
    2. PyTorch (via DiffSinger's built-in inference)
    3. CLI subprocess (last resort)

    Args:
        ds_path: Path to .ds project file.
        model_dir: Path to voice model directory.
        output_path: Output WAV file path.
    """
    model_dir_path = Path(model_dir)

    # Determine available model formats
    has_onnx_acoustic = (model_dir_path / "acoustic.onnx").exists()
    has_onnx_variance = (model_dir_path / "variance.onnx").exists()
    has_pt_acoustic = (model_dir_path / "acoustic.ckpt").exists() or (
        model_dir_path / "acoustic.pt"
    ).exists()
    has_pt_variance = (model_dir_path / "variance.ckpt").exists() or (
        model_dir_path / "variance.pt"
    ).exists()

    # Try ONNX inference first
    if has_onnx_acoustic:
        try:
            _run_onnx_inference(ds_path, model_dir, output_path)
            return
        except Exception as exc:
            logger.warning(
                "ONNX inference failed, falling back to PyTorch: %s",
                exc,
            )

    # Try PyTorch inference via ModelManager
    if has_pt_acoustic or _diffsinger_python_available():
        try:
            _run_pytorch_inference(ds_path, model_dir, output_path)
            return
        except Exception as exc:
            logger.warning(
                "PyTorch inference failed, falling back to CLI: %s",
                exc,
            )

    # Last resort: CLI subprocess
    _run_cli_inference(ds_path, model_dir, output_path)


def _run_onnx_inference(
    ds_path: str,
    model_dir: str,
    output_path: str,
) -> None:
    """Run inference using ONNX Runtime for fast production inference.

    Loads acoustic and variance ONNX models and runs the full synthesis
    pipeline without requiring PyTorch/CUDA.
    """
    try:
        import onnxruntime as ort  # type: ignore[import-untyped]
        import numpy as np
    except ImportError:
        raise RuntimeError(
            "onnxruntime is required for ONNX inference. "
            "Install with: pip install onnxruntime-gpu (or onnxruntime for CPU)"
        )

    model_dir_path = Path(model_dir)
    acoustic_path = model_dir_path / "acoustic.onnx"
    variance_path = model_dir_path / "variance.onnx"

    if not acoustic_path.exists():
        raise FileNotFoundError(f"Acoustic ONNX model not found: {acoustic_path}")

    logger.info("Running ONNX inference (acoustic=%s)", acoustic_path)

    # Configure ONNX Runtime
    providers = []
    if ort.get_device() == "GPU":
        providers.append("CUDAExecutionProvider")
    providers.append("CPUExecutionProvider")

    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess_opts.intra_op_num_threads = 4

    # Load project
    ds_data = json.loads(Path(ds_path).read_text(encoding="utf-8"))
    if isinstance(ds_data, list):
        ds_data = ds_data[0]

    # Parse phoneme sequence and durations
    ph_seq = ds_data.get("ph_seq", "").split()
    ph_dur_str = ds_data.get("ph_dur", "").split()
    ph_dur = (
        np.array([float(d) for d in ph_dur_str], dtype=np.float32)
        if ph_dur_str
        else np.array([0.5], dtype=np.float32)
    )

    note_seq_str = ds_data.get("note_seq", "").split()
    note_dur_str = ds_data.get("note_dur", "").split()

    # Convert note names to MIDI numbers
    note_midi = (
        np.array(
            [_note_name_to_midi(n) for n in note_seq_str],
            dtype=np.float32,
        )
        if note_seq_str
        else np.zeros(1, dtype=np.float32)
    )

    note_dur = (
        np.array(
            [float(d) for d in note_dur_str],
            dtype=np.float32,
        )
        if note_dur_str
        else np.array([1.0], dtype=np.float32)
    )

    # Build encoder input (phoneme indices)
    # For ONNX models, phonemes are typically encoded as integer indices
    ph_indices = np.array(
        [_phoneme_to_index(p) for p in ph_seq],
        dtype=np.int64,
    ).reshape(1, -1)

    ph_dur_frames = np.array(
        [max(1, int(d * DS_SAMPLE_RATE / DS_HOP_SIZE)) for d in ph_dur],
        dtype=np.int64,
    ).reshape(1, -1)

    total_frames = int(ph_dur_frames.sum())

    # Run variance model if available
    variance_outputs: dict[str, np.ndarray] = {}
    if variance_path.exists():
        try:
            var_session = ort.InferenceSession(
                str(variance_path),
                sess_opts,
                providers=providers,
            )
            var_inputs = {
                "ph_seq": ph_indices,
                "ph_dur": ph_dur_frames,
            }

            # Add note info if model expects it
            var_input_names = {inp.name for inp in var_session.get_inputs()}
            if "note_midi" in var_input_names:
                var_inputs["note_midi"] = note_midi.reshape(1, -1)
            if "note_dur" in var_input_names:
                note_dur_frames = np.array(
                    [max(1, int(d * DS_SAMPLE_RATE / DS_HOP_SIZE)) for d in note_dur],
                    dtype=np.int64,
                ).reshape(1, -1)
                var_inputs["note_dur"] = note_dur_frames

            var_outputs = var_session.run(None, var_inputs)
            var_output_names = [o.name for o in var_session.get_outputs()]
            for name, val in zip(var_output_names, var_outputs):
                variance_outputs[name] = val
                logger.debug("Variance output '%s': shape=%s", name, val.shape)

        except Exception as exc:
            logger.warning("Variance model inference failed: %s. Using defaults.", exc)

    # Run acoustic model
    acoustic_session = ort.InferenceSession(
        str(acoustic_path),
        sess_opts,
        providers=providers,
    )

    acoustic_inputs: dict[str, np.ndarray] = {
        "ph_seq": ph_indices,
        "ph_dur": ph_dur_frames,
    }

    # Add variance predictions
    acoustic_input_names = {inp.name for inp in acoustic_session.get_inputs()}
    for var_name, var_val in variance_outputs.items():
        if var_name in acoustic_input_names:
            acoustic_inputs[var_name] = var_val

    # Add note information if expected
    if "note_midi" in acoustic_input_names:
        acoustic_inputs["note_midi"] = note_midi.reshape(1, -1)

    acoustic_outputs = acoustic_session.run(None, acoustic_inputs)

    # The acoustic model outputs a mel spectrogram
    mel = acoustic_outputs[0]  # Shape: [1, T, mel_bins] or [1, mel_bins, T]
    if mel.ndim == 3 and mel.shape[-1] == DS_MEL_BINS:
        mel = mel.transpose(0, 2, 1)  # -> [1, mel_bins, T]

    logger.info("Acoustic model output: mel shape %s", mel.shape)

    # Vocode mel to waveform
    wav = _vocode_mel(mel, model_dir, providers, sess_opts)

    # Apply energy scaling if specified
    energy_scale = ds_data.get("energy_scale", 1.0)
    if energy_scale != 1.0:
        wav = wav * energy_scale

    # Write output
    _write_wav(wav, output_path, DS_SAMPLE_RATE)


def _run_pytorch_inference(
    ds_path: str,
    model_dir: str,
    output_path: str,
) -> None:
    """Run inference using PyTorch and the DiffSinger Python library.

    Uses the ModelManager to handle GPU memory and model loading.
    """
    from src.utils.model_manager import get_manager

    mgr = get_manager()

    try:
        infer_model = mgr.load_diffsinger()
    except RuntimeError as exc:
        raise RuntimeError(f"Could not load DiffSinger model: {exc}") from exc

    # Load the .ds project
    ds_data = json.loads(Path(ds_path).read_text(encoding="utf-8"))
    if isinstance(ds_data, list):
        ds_data = ds_data[0]

    logger.info("Running PyTorch inference on %s", ds_path)

    try:
        # DiffSinger's cascade inference takes a .ds dict directly
        result = infer_model.infer(ds_data)

        if hasattr(result, "wav") or isinstance(result, dict):
            wav = result.wav if hasattr(result, "wav") else result.get("wav")
            if wav is not None:
                import numpy as np

                if not isinstance(wav, np.ndarray):
                    wav = wav.cpu().numpy()
                _write_wav(wav, output_path, DS_SAMPLE_RATE)
                return
        elif isinstance(result, (list, tuple)):
            # Some DiffSinger versions return (wav, sr)
            wav = result[0]
            import numpy as np

            if not isinstance(wav, np.ndarray):
                wav = wav.cpu().numpy()
            _write_wav(wav, output_path, DS_SAMPLE_RATE)
            return

        raise RuntimeError(f"Unexpected inference result type: {type(result)}")

    except AttributeError:
        # Model doesn't have .infer() method; try the CLI path instead
        logger.warning("DiffSinger model lacks .infer() method; falling back to CLI.")
        _run_cli_inference(ds_path, model_dir, output_path)


def _run_cli_inference(
    ds_path: str,
    model_dir: str,
    output_path: str,
) -> None:
    """Run DiffSinger inference via command-line subprocess.

    This is the most compatible method but requires DiffSinger to be
    properly installed with its CLI entry points.
    """
    logger.info("Running CLI inference: %s -> %s", ds_path, output_path)

    # Try DiffSinger's inference script
    infer_script = DIFFSINGER_DIR / "scripts" / "infer.py"
    if not infer_script.exists():
        # Try alternative locations
        for candidate in [
            DIFFSINGER_DIR / "inference" / "ds" / "infer.py",
            DIFFSINGER_DIR / "run_infer.py",
        ]:
            if candidate.exists():
                infer_script = candidate
                break

    # Determine config path
    config_path = Path(model_dir) / "acoustic_config.yaml"
    if not config_path.exists():
        config_path = DIFFSINGER_DIR / "configs" / "acoustic.yaml"

    cmd = [
        "python3",
        str(infer_script),
        "--config",
        str(config_path),
        "--exp_name",
        "default",
        "--infer_input",
        ds_path,
        "--out",
        output_path,
    ]

    # Add checkpoint path
    ckpt = Path(model_dir) / "acoustic.ckpt"
    if ckpt.exists():
        cmd.extend(["--ckpt", str(ckpt)])

    logger.info("CLI command: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(DIFFSINGER_DIR),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"DiffSinger CLI failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout[-500:] if result.stdout else '(empty)'}\n"
            f"stderr: {result.stderr[-500:] if result.stderr else '(empty)'}"
        )


def _diffsinger_python_available() -> bool:
    """Check if DiffSinger Python package is importable."""
    diffsinger_path = str(DIFFSINGER_DIR)
    import sys

    if diffsinger_path not in sys.path:
        sys.path.insert(0, diffsinger_path)
    try:
        from inference.ds_cascade import DiffSingerCascadeInfer  # type: ignore[import-untyped]

        return True
    except (ImportError, ModuleNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Vocoder
# ---------------------------------------------------------------------------


_NC_VOCODERS = {"nsf-hifigan", "nsf_hifigan"}


def _vocode_mel(
    mel: "np.ndarray",
    model_dir: str,
    providers: list[str] | None = None,
    sess_opts: Any = None,
) -> "np.ndarray":
    """Convert mel spectrogram to waveform using the vocoder.

    Resolution chain (license-aware):
      1. fish-hifigan (Apache 2.0) — commercial-safe, recommended
      2. NSF-HiFiGAN (CC-BY-NC-SA 4.0) — only if user explicitly opts in
      3. Griffin-Lim — always available, lower quality but fully open
    """
    import numpy as np
    from src.orchestrator.config import DIFFSINGER_VOCODER, DIFFSINGER_VOCODER_NC_ACK

    model_dir_path = Path(model_dir)

    vocoder_name = DIFFSINGER_VOCODER
    vocoder_txt = model_dir_path / "vocoder.txt"
    if vocoder_txt.exists():
        vocoder_name = vocoder_txt.read_text().strip()

    if vocoder_name == "griffin-lim":
        logger.info("Using Griffin-Lim vocoder (safe default).")
        return _griffin_lim(mel)

    if vocoder_name.replace("-", "_") in _NC_VOCODERS and not DIFFSINGER_VOCODER_NC_ACK:
        logger.warning(
            "NSF-HiFiGAN vocoder uses CC-BY-NC-SA 4.0 — output CANNOT be "
            "commercially distributed. Set MUSER_VOCODER_NC_ACK=true to "
            "acknowledge, or install fish-hifigan (Apache 2.0) for "
            "commercial-safe output. Falling back to Griffin-Lim."
        )
        return _griffin_lim(mel)

    vocoder_onnx = model_dir_path / "vocoder.onnx"
    if not vocoder_onnx.exists():
        vocoder_onnx = DIFFSINGER_DIR / "checkpoints" / vocoder_name / "model.onnx"

    if vocoder_onnx.exists():
        try:
            import onnxruntime as ort  # type: ignore[import-untyped]

            if providers is None:
                providers = ["CPUExecutionProvider"]
            if sess_opts is None:
                sess_opts = ort.SessionOptions()

            vocoder_session = ort.InferenceSession(
                str(vocoder_onnx),
                sess_opts,
                providers=providers,
            )

            input_names = {inp.name for inp in vocoder_session.get_inputs()}
            inputs: dict[str, np.ndarray] = {}

            if "mel" in input_names:
                inputs["mel"] = mel
            elif "input" in input_names:
                inputs["input"] = mel

            if "f0" in input_names:
                n_frames = mel.shape[-1] if mel.ndim == 3 else mel.shape[-2]
                f0 = np.full((1, n_frames), 440.0, dtype=np.float32)
                inputs["f0"] = f0

            outputs = vocoder_session.run(None, inputs)
            wav = outputs[0].squeeze()

            license_tag = (
                "CC-BY-NC-SA 4.0"
                if vocoder_name.replace("-", "_") in _NC_VOCODERS
                else "Apache 2.0"
            )
            logger.info(
                "Vocoder %s output: %d samples (%.1fs) [license: %s]",
                vocoder_name,
                len(wav),
                len(wav) / DS_SAMPLE_RATE,
                license_tag,
            )
            return wav

        except Exception as exc:
            logger.warning("ONNX vocoder failed: %s. Using Griffin-Lim.", exc)

    logger.warning("No vocoder available; using Griffin-Lim (lower quality).")
    return _griffin_lim(mel)


def _griffin_lim(mel: "np.ndarray", n_iter: int = 60) -> "np.ndarray":
    """Basic Griffin-Lim reconstruction from mel spectrogram.

    This is a fallback when no neural vocoder is available.
    Quality will be noticeably lower than HiFi-GAN.
    """
    import numpy as np

    try:
        import librosa
    except ImportError:
        raise RuntimeError(
            "librosa is required for Griffin-Lim vocoding. Install with: pip install librosa"
        )

    # Squeeze batch dimension
    if mel.ndim == 3:
        mel = mel.squeeze(0)

    # mel shape should be [mel_bins, T]
    if mel.shape[0] != DS_MEL_BINS and mel.shape[1] == DS_MEL_BINS:
        mel = mel.T

    # Convert from log mel to linear
    mel_linear = librosa.db_to_amplitude(mel)

    # Invert mel filterbank
    mel_basis = librosa.filters.mel(
        sr=DS_SAMPLE_RATE,
        n_fft=2048,
        n_mels=DS_MEL_BINS,
    )

    # Pseudo-inverse of mel filterbank
    mel_inv = np.linalg.pinv(mel_basis)
    S = np.maximum(1e-10, mel_inv @ mel_linear)

    # Griffin-Lim
    wav = librosa.griffinlim(
        S,
        n_iter=n_iter,
        hop_length=DS_HOP_SIZE,
        win_length=2048,
    )

    return wav.astype(np.float32)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _write_wav(wav: "np.ndarray", path: str, sample_rate: int) -> None:
    """Write a numpy array to a WAV file."""
    import numpy as np

    try:
        import soundfile as sf

        # Ensure float32 and clip to valid range
        wav = np.clip(wav.astype(np.float32), -1.0, 1.0)
        # Squeeze any extra dimensions
        while wav.ndim > 1:
            wav = wav.squeeze(0)
        sf.write(path, wav, sample_rate)
    except ImportError:
        # Fallback to scipy
        try:
            from scipy.io import wavfile

            wav_int16 = np.clip(wav * 32767, -32768, 32767).astype(np.int16)
            while wav_int16.ndim > 1:
                wav_int16 = wav_int16.squeeze(0)
            wavfile.write(path, sample_rate, wav_int16)
        except ImportError:
            raise RuntimeError(
                "Neither soundfile nor scipy is available for WAV writing. "
                "Install with: pip install soundfile"
            )


def _note_name_to_midi(note_name: str) -> float:
    """Convert a note name (e.g., 'C4', 'F#5') to MIDI number."""
    if note_name in ("rest", "SP", ""):
        return 0.0

    try:
        import librosa

        return float(librosa.note_to_midi(note_name))
    except (ImportError, Exception):
        pass

    # Manual conversion
    note_map = {
        "C": 0,
        "D": 2,
        "E": 4,
        "F": 5,
        "G": 7,
        "A": 9,
        "B": 11,
    }
    name = note_name.rstrip("0123456789-")
    octave_str = note_name[len(name) :]

    base = name[0].upper()
    if base not in note_map:
        return 0.0

    midi = note_map[base]
    if "#" in name:
        midi += 1
    elif "b" in name:
        midi -= 1

    try:
        octave = int(octave_str) if octave_str else 4
    except ValueError:
        octave = 4

    return float((octave + 1) * 12 + midi)


# Simple phoneme-to-index mapping for ONNX models
# This should match the phoneme vocabulary used during training
_PHONEME_VOCAB: dict[str, int] = {}


def _phoneme_to_index(phoneme: str) -> int:
    """Convert a phoneme string to an integer index.

    Uses a simple hash-based mapping if no vocabulary file is available.
    In production, the vocabulary should match the training config.
    """
    if not _PHONEME_VOCAB:
        _build_phoneme_vocab()

    return _PHONEME_VOCAB.get(phoneme.upper(), _PHONEME_VOCAB.get("SP", 0))


def _build_phoneme_vocab() -> None:
    """Build the phoneme vocabulary mapping.

    Tries to load from the DiffSinger installation, falls back to
    a standard English phoneme set.
    """
    global _PHONEME_VOCAB

    # Try loading from DiffSinger's phoneme list
    vocab_path = DIFFSINGER_DIR / "dictionaries" / "phonemes.txt"
    if not vocab_path.exists():
        vocab_path = DIFFSINGER_DIR / "assets" / "phonemes.txt"

    if vocab_path.exists():
        try:
            lines = vocab_path.read_text(encoding="utf-8").strip().split("\n")
            for idx, line in enumerate(lines):
                phone = line.strip().split()[0] if line.strip() else ""
                if phone:
                    _PHONEME_VOCAB[phone.upper()] = idx
            logger.debug("Loaded %d phonemes from %s", len(_PHONEME_VOCAB), vocab_path)
            return
        except Exception as exc:
            logger.warning("Failed to load phoneme vocab: %s", exc)

    # Standard ARPAbet + extras
    standard_phones = [
        "SP",
        "AP",  # Silence, aspirate
        "AA",
        "AE",
        "AH",
        "AO",
        "AW",
        "AX",
        "AXR",
        "AY",
        "B",
        "CH",
        "D",
        "DH",
        "DX",
        "EH",
        "EL",
        "EM",
        "EN",
        "ER",
        "EY",
        "F",
        "G",
        "HH",
        "IH",
        "IX",
        "IY",
        "JH",
        "K",
        "L",
        "M",
        "N",
        "NG",
        "NX",
        "OW",
        "OY",
        "P",
        "Q",
        "R",
        "S",
        "SH",
        "T",
        "TH",
        "UH",
        "UW",
        "UX",
        "V",
        "W",
        "WH",
        "Y",
        "Z",
        "ZH",
    ]
    _PHONEME_VOCAB.update({ph: idx for idx, ph in enumerate(standard_phones)})
