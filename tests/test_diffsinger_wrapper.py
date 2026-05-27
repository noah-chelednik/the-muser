"""Tests for DiffSinger wrapper pure-logic functions."""

import pytest


class TestVocalExtraction:

    def test_extract_vocal_data(self, sample_musicxml_with_vocals):
        from src.generation.diffsinger_wrapper import _extract_vocal_data
        data = _extract_vocal_data(sample_musicxml_with_vocals)
        assert len(data["notes"]) > 0
        assert data["tempo"] > 0
        assert data["total_duration_s"] > 0

    def test_extract_handles_rests(self, sample_musicxml_path):
        from src.generation.diffsinger_wrapper import _extract_vocal_data
        data = _extract_vocal_data(sample_musicxml_path)
        assert isinstance(data["notes"], list)

    def test_find_vocal_part_by_name(self):
        import music21
        from src.generation.diffsinger_wrapper import _find_vocal_part
        score = music21.stream.Score()
        p1 = music21.stream.Part()
        p1.partName = "Piano"
        p2 = music21.stream.Part()
        p2.partName = "Soprano Vocals"
        score.append(p1)
        score.append(p2)
        found = _find_vocal_part(score)
        assert found is not None
        assert "Soprano" in found.partName

    def test_find_vocal_part_none(self):
        import music21
        from src.generation.diffsinger_wrapper import _find_vocal_part
        score = music21.stream.Score()
        p = music21.stream.Part()
        p.partName = "Strings"
        score.append(p)
        assert _find_vocal_part(score) is None


class TestPhonemeProcessing:

    def test_fallback_g2p_english(self):
        from src.generation.diffsinger_wrapper import _fallback_g2p
        result = _fallback_g2p(["hello", "world", ""])
        assert result["method"] == "fallback-rules"
        assert len(result["phonemes"]) == 3
        assert result["phonemes"][2] == ["SP"]

    def test_fallback_g2p_empty(self):
        from src.generation.diffsinger_wrapper import _fallback_g2p
        result = _fallback_g2p(["", "  "])
        assert all(p == ["SP"] for p in result["phonemes"])

    def test_distribute_phoneme_durations_sums_correctly(self):
        from src.generation.diffsinger_wrapper import _distribute_phoneme_durations
        phonemes = ["HH", "EH", "L", "OW"]
        total = 0.5
        durs = _distribute_phoneme_durations(phonemes, total)
        assert len(durs) == 4
        assert abs(sum(durs) - total) < 0.001

    def test_distribute_single_phoneme(self):
        from src.generation.diffsinger_wrapper import _distribute_phoneme_durations
        durs = _distribute_phoneme_durations(["AH"], 1.0)
        assert durs == [1.0]


class TestNoteConversion:

    def test_midi_to_note_name(self):
        from src.generation.diffsinger_wrapper import _midi_to_note_name
        assert _midi_to_note_name(60) == "C4"
        assert _midi_to_note_name(69) == "A4"
        assert _midi_to_note_name(0) == "rest"

    def test_note_name_to_midi(self):
        from src.generation.diffsinger_wrapper import _note_name_to_midi
        assert _note_name_to_midi("C4") == 60.0
        assert _note_name_to_midi("rest") == 0.0
        assert _note_name_to_midi("") == 0.0

    def test_roundtrip(self):
        from src.generation.diffsinger_wrapper import _midi_to_note_name, _note_name_to_midi
        for midi in [48, 60, 72, 84]:
            name = _midi_to_note_name(midi)
            back = _note_name_to_midi(name)
            assert back == float(midi)


class TestDSProjectBuilding:

    def test_build_ds_project_writes_json(self, sample_musicxml_with_vocals, tmp_path):
        import json
        from src.generation.diffsinger_wrapper import (
            _extract_vocal_data, _lyrics_to_phonemes, _build_ds_project,
        )
        vocal_data = _extract_vocal_data(sample_musicxml_with_vocals)
        phoneme_data = _lyrics_to_phonemes(vocal_data)
        ds_path = str(tmp_path / "test.ds")
        _build_ds_project(vocal_data, phoneme_data, ds_path)

        data = json.loads(open(ds_path).read())
        assert isinstance(data, list)
        assert len(data) == 1
        seg = data[0]
        assert "ph_seq" in seg
        assert "ph_dur" in seg
        assert "note_seq" in seg
