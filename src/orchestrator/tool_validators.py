"""
Pydantic models for validating tool call arguments.

Local LLMs hallucinate argument types more than Claude does.
Every tool call passes through validation before execution.
"""

from pydantic import BaseModel, Field
from typing import Optional


class GenerateNotationNotagen(BaseModel):
    period: str = Field(..., pattern="^(Medieval|Renaissance|Baroque|Classical|Romantic|Modern)$")
    composer: str
    instrumentation: str
    max_length: int = Field(default=1024, ge=64, le=4096)
    section_name: str = "notagen_output"


class GenerateAudioAceStep(BaseModel):
    tags: str = Field(..., min_length=1)
    lyrics: str = ""
    duration_s: int = Field(default=60, ge=5, le=300)
    num_candidates: int = Field(default=1, ge=1, le=4)
    seed: Optional[int] = None
    infer_step: Optional[int] = Field(default=None, ge=10, le=200)
    guidance_scale: Optional[float] = Field(default=None, ge=1.0, le=30.0)


class GenerateAudioAceStepLora(BaseModel):
    tags: str = Field(..., min_length=1)
    lyrics: str = ""
    duration_s: int = Field(default=60, ge=5, le=300)
    seed: Optional[int] = None
    infer_step: Optional[int] = Field(default=None, ge=10, le=200)
    guidance_scale: Optional[float] = Field(default=None, ge=1.0, le=30.0)
    lora_path: str = Field(..., min_length=1)


class GenerateAudioAceStepV15(BaseModel):
    tags: str = Field(..., min_length=1)
    lyrics: str = ""
    duration_s: int = Field(default=120, ge=5, le=600)
    num_candidates: int = Field(default=1, ge=1, le=8)
    seed: Optional[int] = None
    infer_step: Optional[int] = Field(default=None, ge=1, le=200)
    guidance_scale: Optional[float] = Field(default=None, ge=0.0, le=30.0)
    bpm: Optional[int] = Field(default=None, ge=30, le=300)
    key_scale: str = ""
    time_signature: str = ""


class RepaintAudioAceStep(BaseModel):
    src_audio: str = Field(..., min_length=1)
    tags: str = Field(..., min_length=1)
    start_s: float = Field(..., ge=0.0)
    end_s: float = Field(..., ge=0.0)
    lyrics: str = ""
    seed: Optional[int] = None


class CoverAudioAceStep(BaseModel):
    src_audio: str = Field(..., min_length=1)
    tags: str = Field(..., min_length=1)
    cover_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    lyrics: str = ""
    seed: Optional[int] = None


class ExtendAudioAceStep(BaseModel):
    src_audio: str = Field(..., min_length=1)
    tags: str = Field(..., min_length=1)
    extend_s: float = Field(default=30.0, ge=5.0, le=300.0)
    lyrics: str = ""
    seed: Optional[int] = None


class ValidateNotation(BaseModel):
    musicxml_path: str = Field(..., min_length=1)


class ValidateAudio(BaseModel):
    wav_path: str = Field(..., min_length=1)
    expected_duration_s: Optional[float] = None


class RenderPreview(BaseModel):
    musicxml_path: str = Field(..., min_length=1)
    soundfont: str = Field(default="preview", pattern="^(preview|draft)$")


class RenderScorePdf(BaseModel):
    musicxml_path: str = Field(..., min_length=1)
    renderer: str = Field(default="lilypond", pattern="^(lilypond|musescore)$")


class ApplyPostproduction(BaseModel):
    wav_path: str = Field(..., min_length=1)
    genre: str = Field(default="default", pattern="^(default|classical|pop|rock|electronic)$")


class ExportFinal(BaseModel):
    wav_path: str = Field(..., min_length=1)
    formats: list[str] = Field(default=["wav", "mp3", "flac"])
    output_dir: str = ""
    title: str = ""
    artist: str = "The Muser"
    genre: str = ""


class UpdateMemoryDocument(BaseModel):
    section: str = Field(
        ...,
        pattern="^(project|form_plan|theme_catalog|harmonic_plan|orchestration_state|voice_plan|revision_notes)$",
    )
    data: dict


class SaveCheckpoint(BaseModel):
    message: str = Field(..., min_length=1)


class CreateCompositionPlan(BaseModel):
    title: str = Field(..., min_length=1)
    genre: str = Field(..., min_length=1)
    instrumentation: list[str] = Field(..., min_length=1)
    form: str = ""
    key: str = ""
    tempo: int = Field(default=0, ge=0, le=400)
    time_signature: str = "4/4"
    mood: str = ""
    duration_estimate_s: int = 0


class TrainVoiceLora(BaseModel):
    voice_name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    training_data_dir: str = Field(..., min_length=1)
    epochs: int = Field(default=500, ge=10, le=5000)
    lora_rank: int = Field(default=32, ge=4, le=256)
    learning_rate: float = Field(default=0.0001, ge=1e-6, le=0.01)


class UpdateCompositionPlan(BaseModel):
    updates: dict = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=500)


class GenerateNotationClaude(BaseModel):
    section_name: str = Field(..., min_length=1, max_length=100)
    instructions: str = Field(..., min_length=1, max_length=5000)
    instruments: list[str] = Field(..., min_length=1)
    key: str = Field(default="C major", max_length=50)
    time_signature: str = Field(default="4/4", pattern=r"^\d+/\d+$")
    tempo: int = Field(default=120, ge=20, le=400)
    measures: int = Field(default=8, ge=1, le=128)


class ListSections(BaseModel):
    pass


class GetSection(BaseModel):
    section_name: str = Field(..., min_length=1, max_length=100)


class RenderQualityAudio(BaseModel):
    midi_path: str = Field(..., min_length=1)
    sfz_instrument: str = Field(default="", max_length=500)


class SelectVoice(BaseModel):
    voice_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")


class SeparateStemsDemucs(BaseModel):
    input_audio: str = Field(..., min_length=1)
    two_stems: bool = Field(default=True)


class FeminizeAudio(BaseModel):
    input_audio: str = Field(..., min_length=1)
    preset: str = Field(
        ..., pattern=r"^(powerful_mezzo|soft_feminine|androgynous|natural_male|deep_male)$"
    )
    voice_id: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")


class ConvertVoiceRvc(BaseModel):
    input_audio: str = Field(..., min_length=1)
    voice_id: str = Field(..., min_length=1, max_length=50)
    transpose: int = Field(default=0, ge=-24, le=24)
    f0_method: str = Field(default="rmvpe", pattern=r"^(rmvpe|crepe|harvest|dio|pm)$")


class RenderVocalsDiffsinger(BaseModel):
    musicxml_path: str = Field(..., min_length=1)
    lyrics: str = Field(..., min_length=1, max_length=10000)
    model_name: str = Field(default="", max_length=200)
    pitch_expressiveness: float = Field(default=1.0, ge=0.0, le=3.0)
    breathiness: float = Field(default=0.0, ge=0.0, le=1.0)
    voicing: float = Field(default=1.0, ge=0.0, le=1.0)
    tension: float = Field(default=0.5, ge=0.0, le=1.0)
    energy: float = Field(default=1.0, ge=0.1, le=3.0)
    gender: float = Field(default=0.0, ge=-1.0, le=1.0)


class RemixTrack(BaseModel):
    vocal_path: str = Field(..., min_length=1)
    instrumental_path: str = Field(..., min_length=1)
    vocal_level_db: float = Field(default=0.0, ge=-24.0, le=24.0)
    vocal_pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    apply_vocal_processing: bool = Field(default=True)
    vocal_style: str = Field(
        default="default",
        pattern=r"^(default|intimate|powerful|ethereal)$",
    )


class AddTheme(BaseModel):
    theme_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    abc_snippet: str = Field(default="", max_length=500)
    character: str = Field(..., min_length=1, max_length=500)


class RecordThemeAppearance(BaseModel):
    theme_id: str = Field(..., min_length=1, max_length=100)
    location: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)


class UpdateHarmonicPlan(BaseModel):
    operation: str = Field(..., pattern=r"^(add_key_center|add_modulation)$")
    measure: int = Field(..., ge=1)
    key: str = Field(default="", max_length=50)
    from_key: str = Field(default="", max_length=50)
    to_key: str = Field(default="", max_length=50)


class AddRevisionNote(BaseModel):
    note: str = Field(..., min_length=1, max_length=1000)


class UpdateSectionStatus(BaseModel):
    section_name: str = Field(..., min_length=1, max_length=100)
    status: str = Field(..., pattern=r"^(planned|in_progress|complete)$")


class PlanPieceSection(BaseModel):
    """Inline model for a section within plan_piece."""

    name: str = Field(..., min_length=1, max_length=100)
    start_measure: int = Field(..., ge=1)
    end_measure: int = Field(..., ge=1)
    key: str = Field(default="", max_length=50)
    tempo: int = Field(default=0, ge=0, le=400)
    description: str = Field(default="", max_length=500)


class PlanPiece(BaseModel):
    form: str = Field(..., min_length=1, max_length=100)
    total_measures: int = Field(..., ge=1, le=10000)
    sections: list[PlanPieceSection] = Field(..., min_length=1)


class ZoomIn(BaseModel):
    section: str = Field(..., min_length=1, max_length=100)


class ZoomOut(BaseModel):
    pass


# --- New tools (WS5) ---


class PlayAudio(BaseModel):
    wav_path: str = Field(..., min_length=1)
    start_s: float = Field(default=0.0, ge=0.0)
    duration_s: float = Field(default=0.0, ge=0.0)


class ApplyEq(BaseModel):
    wav_path: str = Field(..., min_length=1)
    frequency_hz: int = Field(..., ge=20, le=20000)
    gain_db: float = Field(..., ge=-24.0, le=24.0)
    q: float = Field(default=1.0, ge=0.1, le=10.0)
    output_path: str = Field(default="")


class ApplyReverb(BaseModel):
    wav_path: str = Field(..., min_length=1)
    room_size: float = Field(default=0.5, ge=0.0, le=1.0)
    decay: float = Field(default=0.4, ge=0.0, le=1.0)
    mix: float = Field(default=0.3, ge=0.0, le=1.0)
    output_path: str = Field(default="")


class ApplyCompression(BaseModel):
    wav_path: str = Field(..., min_length=1)
    threshold_db: float = Field(default=-20.0, ge=-60.0, le=0.0)
    ratio: float = Field(default=4.0, ge=1.0, le=20.0)
    attack_ms: float = Field(default=10.0, ge=0.1, le=200.0)
    release_ms: float = Field(default=200.0, ge=10.0, le=2000.0)
    output_path: str = Field(default="")


class AdjustVolume(BaseModel):
    wav_path: str = Field(..., min_length=1)
    gain_db: float = Field(..., ge=-60.0, le=24.0)
    output_path: str = Field(default="")


class ExtractMidiFromAudio(BaseModel):
    audio_path: str = Field(..., min_length=1)
    output_path: str = Field(default="")
    onset_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_frequency_hz: float = Field(default=30.0, ge=20.0, le=2000.0)
    max_frequency_hz: float = Field(default=4000.0, ge=100.0, le=20000.0)


class ScoreAudioQuality(BaseModel):
    wav_path: str = Field(..., min_length=1)
    tags: str = Field(default="")
    lyrics: str = Field(default="")


class AnalyzeAudioDimensions(BaseModel):
    wav_path: str = Field(..., min_length=1)
    genre: str = Field(default="pop", max_length=50)


class MixTrackEntry(BaseModel):
    path: str = Field(..., min_length=1)
    volume_db: float = Field(default=0.0, ge=-60.0, le=24.0)
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    delay_ms: float = Field(default=0.0, ge=0.0, le=5000.0)


class MixTracks(BaseModel):
    tracks: list[MixTrackEntry] = Field(..., min_length=2, max_length=16)
    output_path: str = Field(default="")
    normalize: bool = Field(default=True)


class CheckTrainingStatus(BaseModel):
    pid: int = Field(default=0, ge=0)
    voice_name: str = Field(default="")


# Map tool names to their validators
TOOL_VALIDATORS = {
    "create_composition_plan": CreateCompositionPlan,
    "generate_notation_notagen": GenerateNotationNotagen,
    "generate_audio_acestep": GenerateAudioAceStep,
    "generate_audio_acestep_lora": GenerateAudioAceStepLora,
    "generate_audio_acestep_v15": GenerateAudioAceStepV15,
    "repaint_audio_acestep": RepaintAudioAceStep,
    "cover_audio_acestep": CoverAudioAceStep,
    "extend_audio_acestep": ExtendAudioAceStep,
    "validate_notation": ValidateNotation,
    "validate_audio": ValidateAudio,
    "render_preview": RenderPreview,
    "render_score_pdf": RenderScorePdf,
    "apply_postproduction": ApplyPostproduction,
    "export_final": ExportFinal,
    "update_memory_document": UpdateMemoryDocument,
    "save_checkpoint": SaveCheckpoint,
    "train_voice_lora": TrainVoiceLora,
    "update_composition_plan": UpdateCompositionPlan,
    "generate_notation_claude": GenerateNotationClaude,
    "list_sections": ListSections,
    "get_section": GetSection,
    "render_quality_audio": RenderQualityAudio,
    "select_voice": SelectVoice,
    "separate_stems_demucs": SeparateStemsDemucs,
    "convert_voice_rvc": ConvertVoiceRvc,
    "feminize_audio": FeminizeAudio,
    "render_vocals_diffsinger": RenderVocalsDiffsinger,
    "remix_track": RemixTrack,
    "add_theme": AddTheme,
    "record_theme_appearance": RecordThemeAppearance,
    "update_harmonic_plan": UpdateHarmonicPlan,
    "add_revision_note": AddRevisionNote,
    "update_section_status": UpdateSectionStatus,
    "plan_piece": PlanPiece,
    "zoom_in": ZoomIn,
    "zoom_out": ZoomOut,
    # New tools (WS5)
    "play_audio": PlayAudio,
    "apply_eq": ApplyEq,
    "apply_reverb": ApplyReverb,
    "apply_compression": ApplyCompression,
    "adjust_volume": AdjustVolume,
    "extract_midi_from_audio": ExtractMidiFromAudio,
    "score_audio_quality": ScoreAudioQuality,
    "analyze_audio_dimensions": AnalyzeAudioDimensions,
    "mix_tracks": MixTracks,
    "check_training_status": CheckTrainingStatus,
}


def validate_arguments(tool_name: str, arguments: dict) -> dict | str:
    """
    Validate and normalize tool arguments.
    Returns validated dict on success, error string on failure.
    """
    validator = TOOL_VALIDATORS.get(tool_name)
    if validator is None:
        return arguments  # No validator defined, pass through

    try:
        validated = validator(**arguments)
        return validated.model_dump()
    except Exception as e:
        return f"Invalid arguments for {tool_name}: {e}"
