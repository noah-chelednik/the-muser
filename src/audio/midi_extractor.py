"""Audio-to-MIDI extraction for The Muser.

Bridges the audio generation world (ACE-Step) and the notation world
(NotaGen/MusicXML) by extracting MIDI note data from audio files.

Uses basic-pitch (Spotify, Apache 2.0) when available, with a
librosa-based fallback for basic pitch tracking.
"""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_midi(
    audio_path: str,
    output_midi_path: str = "",
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_note_length_ms: float = 50.0,
    min_frequency_hz: float = 30.0,
    max_frequency_hz: float = 4000.0,
) -> dict:
    """Extract MIDI from an audio file.

    Args:
        audio_path: Path to input audio file.
        output_midi_path: Output MIDI path (auto-generated if empty).
        onset_threshold: Onset detection sensitivity (0-1).
        frame_threshold: Frame activation threshold (0-1).
        min_note_length_ms: Minimum note duration in milliseconds.
        min_frequency_hz: Minimum frequency to detect.
        max_frequency_hz: Maximum frequency to detect.

    Returns:
        Dict with midi_path, note_count, duration_s, and method used.
    """
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if not output_midi_path:
        output_midi_path = str(src.parent / f"{src.stem}_extracted.mid")

    Path(output_midi_path).parent.mkdir(parents=True, exist_ok=True)

    result = _try_basic_pitch(
        audio_path, output_midi_path,
        onset_threshold, frame_threshold,
        min_note_length_ms, min_frequency_hz, max_frequency_hz,
    )
    if result is not None:
        return result

    return _fallback_librosa(
        audio_path, output_midi_path,
        min_frequency_hz, max_frequency_hz,
    )


def _try_basic_pitch(
    audio_path: str,
    output_path: str,
    onset_threshold: float,
    frame_threshold: float,
    min_note_length_ms: float,
    min_frequency_hz: float,
    max_frequency_hz: float,
) -> dict | None:
    """Try MIDI extraction via basic-pitch (Apache 2.0)."""
    try:
        from basic_pitch.inference import predict
        from basic_pitch import ICASSP_2022_MODEL_PATH
    except ImportError:
        return None

    logger.info("Extracting MIDI via basic-pitch: %s", audio_path)

    try:
        model_output, midi_data, note_events = predict(
            audio_path,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_length_ms / 1000.0,
            minimum_frequency=min_frequency_hz,
            maximum_frequency=max_frequency_hz,
        )

        midi_data.write(output_path)

        note_count = sum(len(inst.notes) for inst in midi_data.instruments)
        duration = midi_data.get_end_time()

        logger.info(
            "basic-pitch extracted %d notes (%.1fs) -> %s",
            note_count, duration, output_path,
        )

        return {
            "midi_path": output_path,
            "note_count": note_count,
            "duration_s": round(duration, 2),
            "method": "basic_pitch",
        }
    except Exception as exc:
        logger.warning("basic-pitch failed: %s. Trying librosa fallback.", exc)
        return None


def _fallback_librosa(
    audio_path: str,
    output_path: str,
    min_frequency_hz: float,
    max_frequency_hz: float,
) -> dict:
    """Fallback MIDI extraction via librosa pitch tracking."""
    import librosa
    import numpy as np
    import pretty_midi

    logger.info("Extracting MIDI via librosa fallback: %s", audio_path)

    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr

    pitches, magnitudes = librosa.piptrack(
        y=y, sr=sr, fmin=min_frequency_hz, fmax=max_frequency_hz,
    )

    hop_length = 512
    time_per_frame = hop_length / sr

    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0, name="Extracted")

    current_note = None
    current_start = 0.0
    min_mag = 0.1

    for t in range(pitches.shape[1]):
        idx = magnitudes[:, t].argmax()
        freq = pitches[idx, t]
        mag = magnitudes[idx, t]
        time_s = t * time_per_frame

        if freq > min_frequency_hz and mag > min_mag:
            midi_num = int(round(librosa.hz_to_midi(freq)))
            midi_num = max(0, min(127, midi_num))

            if current_note is None or current_note != midi_num:
                if current_note is not None and time_s - current_start > 0.05:
                    note = pretty_midi.Note(
                        velocity=80, pitch=current_note,
                        start=current_start, end=time_s,
                    )
                    instrument.notes.append(note)
                current_note = midi_num
                current_start = time_s
        else:
            if current_note is not None and time_s - current_start > 0.05:
                note = pretty_midi.Note(
                    velocity=80, pitch=current_note,
                    start=current_start, end=time_s,
                )
                instrument.notes.append(note)
            current_note = None

    if current_note is not None:
        note = pretty_midi.Note(
            velocity=80, pitch=current_note,
            start=current_start, end=duration,
        )
        instrument.notes.append(note)

    midi.instruments.append(instrument)
    midi.write(output_path)

    note_count = len(instrument.notes)
    logger.info(
        "librosa extracted %d notes (%.1fs) -> %s",
        note_count, duration, output_path,
    )

    return {
        "midi_path": output_path,
        "note_count": note_count,
        "duration_s": round(duration, 2),
        "method": "librosa_piptrack",
    }
