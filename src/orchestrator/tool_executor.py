"""Tool dispatch and execution for The Muser orchestration.

Routes tool calls from Claude to the appropriate handler modules.
All handlers return structured dicts and never raise exceptions to
the caller — errors are captured and returned as error dicts.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call to the appropriate handler.

    Args:
        tool_name: Name of the tool to execute.
        tool_input: Input parameters for the tool.

    Returns:
        Result dict with at least a "status" key ("success" or "error").
    """
    logger.info("Executing tool: %s", tool_name)
    logger.debug("Tool input: %s", tool_input)

    start = time.time()
    try:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}
        result = handler(tool_input)
        elapsed = time.time() - start
        result["execution_time_s"] = round(elapsed, 2)
        logger.info("Tool %s completed in %.2fs", tool_name, elapsed)
        return result
    except Exception as e:
        elapsed = time.time() - start
        logger.exception("Tool %s failed after %.2fs", tool_name, elapsed)
        return {
            "status": "error",
            "error": str(e),
            "tool": tool_name,
            "execution_time_s": round(elapsed, 2),
        }


# ---------------------------------------------------------------------------
# Helper: best-of-N candidate selection
# ---------------------------------------------------------------------------

def _select_best_candidate(paths: list[str], num_candidates: int) -> dict:
    """Score candidates and return the best one."""
    if len(paths) == 1:
        return {"status": "success", "wav_paths": paths, "num_candidates": 1}

    try:
        from src.audio.audio_validator import evaluate_quality

        scores = []
        for p in paths:
            try:
                report = evaluate_quality(p)
                scores.append({"path": p, "score": report.composite_score, "grade": report.grade})
            except Exception:
                scores.append({"path": p, "score": 0.0, "grade": "F"})

        scores.sort(key=lambda x: x["score"], reverse=True)
        best = scores[0]

        return {
            "status": "success",
            "wav_paths": [best["path"]],
            "best_score": best["score"],
            "best_grade": best["grade"],
            "all_candidates": scores,
            "num_candidates": len(scores),
            "note": f"Generated {len(scores)} candidates, selected best (grade {best['grade']}). Set MUSER_BEST_OF_N=1 to skip.",
        }
    except ImportError:
        return {"status": "success", "wav_paths": paths, "num_candidates": len(paths)}


# ---------------------------------------------------------------------------
# Handler implementations
# ---------------------------------------------------------------------------

def _handle_create_composition_plan(inputs: dict) -> dict:
    from src.orchestrator.composition_state import CompositionState

    state = _get_state()
    state.project.update({
        "title": inputs.get("title", "Untitled"),
        "genre": inputs.get("genre", ""),
        "status": "planning",
    })
    state.form_plan = {
        "form": inputs.get("form", ""),
        "key": inputs.get("key", ""),
        "tempo": inputs.get("tempo", 0),
        "time_signature": inputs.get("time_signature", "4/4"),
        "sections": inputs.get("sections", []),
        "mood": inputs.get("mood", ""),
        "duration_estimate_s": inputs.get("duration_estimate_s", 0),
    }
    state.orchestration_state["instruments"] = inputs.get("instrumentation", [])
    state.save_plan()
    return {"status": "success", "message": f"Composition plan created: {state.project['title']}"}


def _handle_update_composition_plan(inputs: dict) -> dict:
    state = _get_state()
    updates = inputs.get("updates", {})
    reason = inputs.get("reason", "")

    if "project" in updates:
        state.project.update(updates["project"])
    if "form_plan" in updates:
        state.form_plan.update(updates["form_plan"])
    if "orchestration_state" in updates:
        state.orchestration_state.update(updates["orchestration_state"])

    state.revision_notes.append(f"Plan updated: {reason}")
    state.save_plan()
    return {"status": "success", "message": f"Plan updated: {reason}"}


def _handle_generate_notation_claude(inputs: dict) -> dict:
    section_name = inputs.get("section_name", "unnamed")
    return {
        "status": "success",
        "section_name": section_name,
        "message": (
            "Please compose MusicXML notation for this section. "
            "Write valid MusicXML 4.0 wrapped in ```xml code blocks. "
            f"Section: {section_name}. "
            f"Instructions: {inputs.get('instructions', '')}. "
            f"Key: {inputs.get('key', 'C major')}. "
            f"Time: {inputs.get('time_signature', '4/4')}. "
            f"Instruments: {inputs.get('instruments', [])}. "
            f"Measures: {inputs.get('measures', 4)}."
        ),
        "action": "compose_inline",
    }


def _handle_generate_notation_notagen(inputs: dict) -> dict:
    from src.generation.notagen_wrapper import generate_symbolic
    from src.notation.format_converter import abc_to_musicxml

    result = generate_symbolic(
        period=inputs.get("period", "Romantic"),
        composer=inputs.get("composer", "Chopin"),
        instrumentation=inputs.get("instrumentation", "Piano"),
        max_length=inputs.get("max_length", 1024),
    )

    if result.get("error"):
        return {"status": "error", "error": result["error"]}

    abc = result["abc"]
    try:
        musicxml = abc_to_musicxml(abc)
    except Exception as e:
        return {
            "status": "error",
            "error": f"ABC to MusicXML conversion failed: {e}",
            "abc": abc,
        }

    section_name = inputs.get("section_name", "notagen_output")
    state = _get_state()
    state.save_section(section_name, musicxml)

    return {
        "status": "success",
        "section_name": section_name,
        "abc": abc,
        "musicxml_length": len(musicxml),
        "generation_time_s": result.get("generation_time_s", 0),
    }


def _handle_generate_audio_acestep(inputs: dict) -> dict:
    from src.generation.acestep_wrapper import generate_audio
    from src.orchestrator.config import BEST_OF_N

    num_candidates = inputs.get("num_candidates")
    if num_candidates is None:
        num_candidates = BEST_OF_N

    paths = generate_audio(
        tags=inputs["tags"],
        lyrics=inputs.get("lyrics", ""),
        duration_s=inputs.get("duration_s", 120),
        num_candidates=num_candidates,
        seed=inputs.get("seed"),
        infer_step=inputs.get("infer_step"),
        guidance_scale=inputs.get("guidance_scale"),
    )

    if not paths:
        return {"status": "error", "error": "ACE-Step generation produced no output"}

    return _select_best_candidate(paths, num_candidates)


def _handle_generate_audio_acestep_lora(inputs: dict) -> dict:
    from src.generation.acestep_wrapper import generate_audio

    paths = generate_audio(
        tags=inputs["tags"],
        lyrics=inputs.get("lyrics", ""),
        duration_s=inputs.get("duration_s", 120),
        seed=inputs.get("seed"),
        infer_step=inputs.get("infer_step"),
        guidance_scale=inputs.get("guidance_scale"),
        lora_path=inputs.get("lora_path"),
    )

    if not paths:
        return {"status": "error", "error": "ACE-Step LoRA generation produced no output"}

    return {"status": "success", "wav_paths": paths}


def _handle_generate_audio_acestep_v15(inputs: dict) -> dict:
    from src.generation.acestep_wrapper import generate_audio
    from src.orchestrator.config import BEST_OF_N

    num_candidates = inputs.get("num_candidates")
    if num_candidates is None:
        num_candidates = BEST_OF_N

    paths = generate_audio(
        tags=inputs["tags"],
        lyrics=inputs.get("lyrics", ""),
        duration_s=inputs.get("duration_s", 120),
        num_candidates=num_candidates,
        seed=inputs.get("seed"),
        infer_step=inputs.get("infer_step"),
        guidance_scale=inputs.get("guidance_scale"),
        bpm=inputs.get("bpm"),
        key_scale=inputs.get("key_scale", ""),
        time_signature=inputs.get("time_signature", ""),
    )

    if not paths:
        return {"status": "error", "error": "ACE-Step v1.5 generation produced no output"}

    return _select_best_candidate(paths, num_candidates)


def _handle_repaint_audio_acestep(inputs: dict) -> dict:
    from src.generation.acestep_wrapper import repaint_audio

    paths = repaint_audio(
        src_audio=inputs["src_audio"],
        tags=inputs["tags"],
        start_s=inputs["start_s"],
        end_s=inputs["end_s"],
        lyrics=inputs.get("lyrics", ""),
        seed=inputs.get("seed"),
    )

    if not paths:
        return {"status": "error", "error": "ACE-Step repaint produced no output"}

    return {"status": "success", "wav_paths": paths}


def _handle_cover_audio_acestep(inputs: dict) -> dict:
    from src.generation.acestep_wrapper import cover_audio

    paths = cover_audio(
        src_audio=inputs["src_audio"],
        tags=inputs["tags"],
        cover_strength=inputs.get("cover_strength", 0.5),
        lyrics=inputs.get("lyrics", ""),
        seed=inputs.get("seed"),
    )

    if not paths:
        return {"status": "error", "error": "ACE-Step cover produced no output"}

    return {"status": "success", "wav_paths": paths}


def _handle_extend_audio_acestep(inputs: dict) -> dict:
    from src.generation.acestep_wrapper import extend_audio

    paths = extend_audio(
        src_audio=inputs["src_audio"],
        tags=inputs["tags"],
        extend_s=inputs.get("extend_s", 30.0),
        lyrics=inputs.get("lyrics", ""),
        seed=inputs.get("seed"),
    )

    if not paths:
        return {"status": "error", "error": "ACE-Step extend produced no output"}

    return {"status": "success", "wav_paths": paths}


def _handle_render_vocals_diffsinger(inputs: dict) -> dict:
    import os
    from src.generation.diffsinger_wrapper import synthesize_singing, render_vocals

    musicxml_path = inputs["musicxml_path"]
    model_name = inputs.get("model_name", "")

    try:
        # Prefer synthesize_singing for MusicXML input (full pipeline)
        if musicxml_path.endswith((".musicxml", ".xml", ".mxl")):
            # Resolve model directory from voice registry if needed
            voice_model_dir = model_name
            if model_name and not os.path.isdir(model_name):
                from src.voice.voice_registry import get_voice
                voice = get_voice(model_name)
                if voice and voice.get("type") == "diffsinger":
                    voice_model_dir = voice.get("model_path", "")

            if not voice_model_dir:
                from src.orchestrator.config import DIFFSINGER_DIR
                voice_model_dir = str(DIFFSINGER_DIR / "checkpoints" / "default")

            output = synthesize_singing(
                musicxml_path=musicxml_path,
                voice_model_dir=voice_model_dir,
                pitch_expressiveness=inputs.get("pitch_expressiveness", 1.0),
                breathiness=inputs.get("breathiness", 0.0),
                voicing=inputs.get("voicing", 1.0),
                tension=inputs.get("tension", 0.5),
                energy=inputs.get("energy", 1.0),
                gender=inputs.get("gender", 0.0),
            )
        else:
            # Legacy path: .ds file input
            output = render_vocals(
                ds_file=musicxml_path,
                model_path=model_name,
            )
        return {"status": "success", "output_path": output}
    except Exception as e:
        return {"status": "error", "error": f"DiffSinger rendering failed: {e}"}


def _handle_convert_voice_rvc(inputs: dict) -> dict:
    from src.voice.rvc_wrapper import convert_voice
    from src.voice.voice_registry import get_voice

    voice = get_voice(inputs["voice_id"])
    if voice is None:
        return {"status": "error", "error": f"Voice not found: {inputs['voice_id']}"}

    output = convert_voice(
        input_audio=inputs["input_audio"],
        model_path=voice["model_path"],
        index_path=voice.get("index_path", ""),
        transpose=inputs.get("transpose", 0),
        f0_method=inputs.get("f0_method", "rmvpe"),
    )
    return {"status": "success", "output_path": output}


def _handle_feminize_audio(inputs: dict) -> dict:
    from pathlib import Path
    from src.voice.voice_registry import get_voice

    input_audio = inputs["input_audio"]
    preset = inputs["preset"]
    voice_id = inputs["voice_id"]

    # Validate input file exists
    if not Path(input_audio).exists():
        return {"status": "error", "error": f"Input audio not found: {input_audio}"}

    # Look up voice in registry
    voice = get_voice(voice_id)
    if voice is None:
        return {"status": "error", "error": f"Voice not found: {voice_id}"}

    model_path = voice.get("model_path", "")
    index_path = voice.get("index_path", "")

    if not model_path or not Path(model_path).exists():
        return {"status": "error", "error": f"Voice model file not found for '{voice_id}': {model_path}"}

    from src.orchestrator.config import FEMINIZATION_PRESETS
    preset_params = FEMINIZATION_PRESETS

    params = preset_params.get(preset)
    if params is None:
        return {"status": "error", "error": f"Unknown preset: {preset}"}

    # Generate output path
    stem = Path(input_audio).stem
    parent = Path(input_audio).parent
    output_path = str(parent / f"{stem}_fem_{preset}.wav")

    try:
        from scripts.feminize_voice import feminize_audio

        result_path = feminize_audio(
            input_audio=input_audio,
            output_path=output_path,
            rvc_model_path=model_path,
            rvc_index_path=index_path,
            transpose=params["transpose"],
            f0_method=params["f0_method"],
            pre_formant_ratio=params.get("pre_formant_ratio", 1.07),
            formant_timbre=params.get("formant_timbre", 1.15),
            presence_boost_db=params.get("presence_boost_db", 1.5),
            chest_cut_db=params.get("chest_cut_db", 1.0),
            add_breathiness=params.get("add_breathiness", False),
        )

        return {
            "status": "success",
            "output_path": result_path,
            "preset": preset,
            "voice_id": voice_id,
        }
    except ImportError:
        from src.voice.rvc_wrapper import convert_voice

        result_path = convert_voice(
            input_audio=input_audio,
            model_path=model_path,
            index_path=index_path,
            transpose=params["transpose"],
            f0_method=params["f0_method"],
            output_path=output_path,
            formant_shift=params.get("formant_shift", False),
        )

        return {
            "status": "success",
            "output_path": result_path,
            "preset": preset,
            "voice_id": voice_id,
        }


def _handle_select_voice(inputs: dict) -> dict:
    from src.voice.voice_registry import get_voice

    voice = get_voice(inputs["voice_id"])
    if voice is None:
        return {"status": "error", "error": f"Voice not found: {inputs['voice_id']}"}
    return {"status": "success", "voice": voice}


def _handle_separate_stems_demucs(inputs: dict) -> dict:
    from src.voice.demucs_wrapper import separate_stems

    result = separate_stems(
        input_audio=inputs["input_audio"],
        output_dir=inputs.get("output_dir", ""),
        two_stems=inputs.get("two_stems", True),
    )
    return {"status": "success", "stems": result}


def _handle_validate_notation(inputs: dict) -> dict:
    from src.notation.theory_validator import validate_score

    result = validate_score(inputs["musicxml_path"])
    return {
        "status": "success",
        "passed": result.passed,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def _handle_validate_audio(inputs: dict) -> dict:
    from src.audio.audio_validator import check_audio

    result = check_audio(
        wav_path=inputs["wav_path"],
        expected_duration_s=inputs.get("expected_duration_s"),
    )
    return {"status": "success", **result}


def _handle_render_preview(inputs: dict) -> dict:
    from src.notation.score_renderer import render_midi
    from src.audio.fluidsynth_renderer import render_fluidsynth

    musicxml_path = inputs["musicxml_path"]
    soundfont = inputs.get("soundfont", "preview")

    # MusicXML -> MIDI -> WAV
    import tempfile
    fd, midi_path = tempfile.mkstemp(suffix=".mid")
    os.close(fd)
    render_midi(musicxml_path, midi_path)

    wav_path = musicxml_path.replace(".musicxml", "_preview.wav")
    render_fluidsynth(midi_path, wav_path, soundfont=soundfont)

    return {"status": "success", "wav_path": wav_path, "midi_path": midi_path}


def _handle_render_score_pdf(inputs: dict) -> dict:
    from src.notation.score_renderer import render_pdf_lilypond, render_pdf_musescore

    musicxml_path = inputs["musicxml_path"]
    renderer = inputs.get("renderer", "lilypond")
    pdf_path = musicxml_path.replace(".musicxml", ".pdf")

    if renderer == "lilypond":
        result = render_pdf_lilypond(musicxml_path, pdf_path)
    else:
        result = render_pdf_musescore(musicxml_path, pdf_path)

    return {"status": "success", "pdf_path": result}


def _handle_render_quality_audio(inputs: dict) -> dict:
    from src.audio.sfizz_renderer import render_sfizz

    midi_path = inputs["midi_path"]
    sfz = inputs.get("sfz_instrument")
    wav_path = midi_path.replace(".mid", "_quality.wav")

    result = render_sfizz(midi_path, wav_path, sfz_instrument=sfz)
    return {"status": "success", "wav_path": result}


def _handle_update_memory_document(inputs: dict) -> dict:
    state = _get_state()
    state.update_section(inputs["section"], inputs["data"])
    return {"status": "success", "message": f"Updated section: {inputs['section']}"}


def _handle_save_checkpoint(inputs: dict) -> dict:
    state = _get_state()
    try:
        commit_hash = state.git_commit(inputs["message"])
        return {"status": "success", "commit": commit_hash}
    except Exception as e:
        return {"status": "error", "error": f"Git commit failed: {e}"}


def _handle_list_sections(inputs: dict) -> dict:
    state = _get_state()
    sections = state.list_sections()
    return {"status": "success", "sections": sections}


def _handle_get_section(inputs: dict) -> dict:
    state = _get_state()
    content = state.load_section(inputs["section_name"])
    if content is None:
        return {"status": "error", "error": f"Section not found: {inputs['section_name']}"}
    return {"status": "success", "musicxml": content}


def _handle_apply_postproduction(inputs: dict) -> dict:
    from src.audio.postproduction import apply_postproduction

    output = inputs["wav_path"].replace(".wav", "_mastered.wav")
    result = apply_postproduction(
        wav_path=inputs["wav_path"],
        output_path=output,
        genre=inputs.get("genre", "default"),
    )
    return {"status": "success", "output_path": result}


def _handle_export_final(inputs: dict) -> dict:
    from pathlib import Path
    from src.audio.export import export_composition

    wav_path = inputs["wav_path"]
    formats = inputs.get("formats", ["wav", "mp3", "flac"])
    output_dir = inputs.get("output_dir", "")
    if not output_dir:
        output_dir = str(Path(wav_path).parent)

    outputs = export_composition(
        wav_path=wav_path,
        output_dir=output_dir,
        formats=formats,
        title=inputs.get("title", ""),
        artist=inputs.get("artist", "The Muser"),
        genre=inputs.get("genre", ""),
    )

    return {"status": "success", "outputs": outputs}


def _handle_remix_track(inputs: dict) -> dict:
    from pathlib import Path
    from src.audio.postproduction import remix_vocals_with_instrumental

    vocal_path = inputs["vocal_path"]
    instrumental_path = inputs["instrumental_path"]

    # Derive output path next to the vocal file.
    voc = Path(vocal_path)
    output = str(voc.parent / (voc.stem + "_remixed.wav"))

    result = remix_vocals_with_instrumental(
        vocal_path=vocal_path,
        instrumental_path=instrumental_path,
        output_path=output,
        vocal_level_db=inputs.get("vocal_level_db", 0.0),
        vocal_pan=inputs.get("vocal_pan", 0.0),
        apply_vocal_processing=inputs.get("apply_vocal_processing", True),
        vocal_style=inputs.get("vocal_style", "default"),
    )
    return {"status": "success", "output_path": result}


def _handle_train_voice_lora(inputs: dict) -> dict:
    import subprocess
    from pathlib import Path
    from src.orchestrator.config import PROJECT_ROOT

    voice_name = inputs["voice_name"]
    training_data_dir = inputs["training_data_dir"]
    epochs = inputs.get("epochs", 500)
    lora_rank = inputs.get("lora_rank", 32)
    learning_rate = inputs.get("learning_rate", 0.0001)

    script_path = PROJECT_ROOT / "scripts" / "train_acestep_lora.sh"
    if not script_path.is_file():
        return {"status": "error", "error": f"Training script not found: {script_path}"}

    if not Path(training_data_dir).is_dir():
        return {"status": "error", "error": f"Training data directory not found: {training_data_dir}"}

    env = {
        **dict(__import__("os").environ),
        "VOICE_NAME": voice_name,
        "TRAIN_DATA_DIR": training_data_dir,
        "EPOCHS": str(epochs),
        "LORA_RANK": str(lora_rank),
        "LEARNING_RATE": str(learning_rate),
    }

    try:
        process = subprocess.Popen(
            ["bash", str(script_path)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return {
            "status": "success",
            "message": f"LoRA training started for voice '{voice_name}' (PID: {process.pid})",
            "pid": process.pid,
            "voice_name": voice_name,
            "epochs": epochs,
            "lora_rank": lora_rank,
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed to start LoRA training: {e}"}


def _handle_add_theme(inputs: dict) -> dict:
    state = _get_state()
    state.add_theme(
        theme_id=inputs["theme_id"],
        abc_snippet=inputs.get("abc_snippet", ""),
        character=inputs["character"],
    )
    return {"status": "success", "message": f"Added theme: {inputs['theme_id']}"}


def _handle_record_theme_appearance(inputs: dict) -> dict:
    state = _get_state()
    theme_id = inputs["theme_id"]
    if theme_id not in state.theme_catalog:
        return {"status": "error", "error": f"Theme not found: {theme_id}"}
    state.record_appearance(
        theme_id=theme_id,
        location=inputs["location"],
        description=inputs.get("description", ""),
    )
    return {"status": "success", "message": f"Recorded appearance of '{theme_id}' at {inputs['location']}"}


def _handle_update_harmonic_plan(inputs: dict) -> dict:
    state = _get_state()
    operation = inputs["operation"]
    measure = inputs["measure"]

    if operation == "add_key_center":
        key = inputs.get("key", "")
        if not key:
            return {"status": "error", "error": "Key is required for add_key_center"}
        state.add_key_center(measure, key)
        return {"status": "success", "message": f"Added key center: {key} at m.{measure}"}
    elif operation == "add_modulation":
        from_key = inputs.get("from_key", "")
        to_key = inputs.get("to_key", "")
        if not from_key or not to_key:
            return {"status": "error", "error": "from_key and to_key required for add_modulation"}
        state.add_modulation(measure, from_key, to_key)
        return {"status": "success", "message": f"Added modulation at m.{measure}: {from_key} -> {to_key}"}
    else:
        return {"status": "error", "error": f"Unknown operation: {operation}"}


def _handle_add_revision_note(inputs: dict) -> dict:
    state = _get_state()
    state.add_revision_note(inputs["note"])
    return {"status": "success", "message": "Revision note added"}


def _handle_update_section_status(inputs: dict) -> dict:
    state = _get_state()
    state.update_section_status(inputs["section_name"], inputs["status"])
    return {"status": "success", "message": f"Section '{inputs['section_name']}' status -> {inputs['status']}"}


def _handle_plan_piece(inputs: dict) -> dict:
    from src.orchestrator.hierarchical_planner import HierarchicalPlanner

    planner = _get_planner()
    form = inputs["form"]
    total_measures = inputs["total_measures"]
    sections = inputs["sections"]

    # Convert Pydantic-serialized sections (may be BaseModel instances) to plain dicts
    section_dicts = []
    for s in sections:
        if isinstance(s, dict):
            section_dicts.append(s)
        else:
            section_dicts.append(dict(s))

    result = planner.plan_piece(form, total_measures, section_dicts)

    return {
        "status": "success",
        "message": (
            f"Hierarchical piece plan created: {form} form, "
            f"{total_measures} measures, {len(result)} sections."
        ),
        "form": form,
        "total_measures": total_measures,
        "sections": [s.to_dict() for s in result],
        "context": planner.get_context_for_level(1),
    }


def _handle_zoom_in(inputs: dict) -> dict:
    planner = _get_planner()
    section = inputs["section"]

    if not planner.level1_plan:
        return {
            "status": "error",
            "error": "No piece plan exists. Call plan_piece first.",
        }

    result = planner.zoom_in(section)
    result["status"] = "success"
    result["context"] = planner.get_context_for_level(planner.current_level, section)
    return result


def _handle_zoom_out(inputs: dict) -> dict:
    planner = _get_planner()

    if not planner.level1_plan:
        return {
            "status": "error",
            "error": "No piece plan exists. Call plan_piece first.",
        }

    result = planner.zoom_out()
    result["status"] = "success"
    result["context"] = planner.get_context_for_level(
        planner.current_level, planner.current_section
    )
    return result


# ---------------------------------------------------------------------------
# State management (session-level singleton)
# ---------------------------------------------------------------------------

_session_state: CompositionState | None = None
_session_planner: "HierarchicalPlanner | None" = None


def _get_state() -> "CompositionState":
    """Get or create the session-level composition state."""
    global _session_state
    if _session_state is None:
        from src.orchestrator.composition_state import CompositionState
        _session_state = CompositionState()
    return _session_state


def set_state(state: "CompositionState") -> None:
    """Set the session-level composition state."""
    global _session_state
    _session_state = state


def _get_planner() -> "HierarchicalPlanner":
    """Get or create the session-level hierarchical planner."""
    global _session_planner
    if _session_planner is None:
        from src.orchestrator.hierarchical_planner import HierarchicalPlanner
        _session_planner = HierarchicalPlanner()
    return _session_planner


def set_planner(planner: "HierarchicalPlanner") -> None:
    """Set the session-level hierarchical planner."""
    global _session_planner
    _session_planner = planner


# ---------------------------------------------------------------------------
# New tool handlers (WS5)
# ---------------------------------------------------------------------------

def _handle_play_audio(inputs: dict) -> dict:
    from src.audio.player import play_audio
    return play_audio(
        wav_path=inputs["wav_path"],
        start_s=inputs.get("start_s", 0.0),
        duration_s=inputs.get("duration_s", 0.0),
    )


def _handle_apply_eq(inputs: dict) -> dict:
    from src.audio.effects import apply_eq
    wav = inputs["wav_path"]
    out = inputs.get("output_path") or wav.replace(".wav", "_eq.wav")
    result = apply_eq(wav, out, inputs["frequency_hz"], inputs["gain_db"], inputs.get("q", 1.0))
    return {"status": "success", "output_path": result}


def _handle_apply_reverb(inputs: dict) -> dict:
    from src.audio.effects import apply_reverb
    wav = inputs["wav_path"]
    out = inputs.get("output_path") or wav.replace(".wav", "_reverb.wav")
    result = apply_reverb(wav, out, inputs.get("room_size", 0.5), inputs.get("decay", 0.4), inputs.get("mix", 0.3))
    return {"status": "success", "output_path": result}


def _handle_apply_compression(inputs: dict) -> dict:
    from src.audio.effects import apply_compression
    wav = inputs["wav_path"]
    out = inputs.get("output_path") or wav.replace(".wav", "_comp.wav")
    result = apply_compression(
        wav, out, inputs.get("threshold_db", -20.0), inputs.get("ratio", 4.0),
        inputs.get("attack_ms", 10.0), inputs.get("release_ms", 200.0),
    )
    return {"status": "success", "output_path": result}


def _handle_adjust_volume(inputs: dict) -> dict:
    from src.audio.effects import adjust_volume
    wav = inputs["wav_path"]
    out = inputs.get("output_path") or wav.replace(".wav", "_vol.wav")
    result = adjust_volume(wav, out, inputs["gain_db"])
    return {"status": "success", "output_path": result}


def _handle_extract_midi_from_audio(inputs: dict) -> dict:
    from src.audio.midi_extractor import extract_midi
    result = extract_midi(
        audio_path=inputs["audio_path"],
        output_midi_path=inputs.get("output_path", ""),
        onset_threshold=inputs.get("onset_threshold", 0.5),
        min_frequency_hz=inputs.get("min_frequency_hz", 30.0),
        max_frequency_hz=inputs.get("max_frequency_hz", 4000.0),
    )
    result["status"] = "success"
    return result


def _handle_score_audio_quality(inputs: dict) -> dict:
    from dataclasses import asdict
    from src.audio.audio_validator import evaluate_quality

    report = evaluate_quality(
        audio_path=inputs["wav_path"],
        tags=inputs.get("tags", ""),
        lyrics=inputs.get("lyrics", ""),
    )

    grades = {"A": "Production ready", "B": "Good quality, minor issues", "C": "Needs post-production", "D": "Consider regenerating", "F": "Poor quality, regenerate"}

    return {
        "status": "success",
        "grade": report.grade,
        "composite_score": report.composite_score,
        "recommendation": grades.get(report.grade, ""),
        "metrics": {
            "energy": report.energy_score,
            "dynamic_range": report.dynamic_range_score,
            "spectral_richness": report.spectral_richness,
            "spectral_consistency": report.spectral_centroid_consistency,
            "onset_density": report.onset_density,
            "harmonic_to_noise": report.harmonic_to_noise_ratio,
            "loudness_range": report.loudness_range,
            "silence_ratio": report.silence_ratio,
            "clipping_ratio": report.clipping_ratio,
        },
    }


def _handle_analyze_audio_dimensions(inputs: dict) -> dict:
    from src.curation.analyzer import analyze_candidate
    from src.curation.models import PipelineConfig

    config = PipelineConfig()
    analysis = analyze_candidate(
        wav_path=inputs["wav_path"],
        genre=inputs.get("genre", "pop"),
        config=config,
    )

    dims = {}
    for name, d in analysis.dimensions.items():
        entry = {"score": d.score, "raw_metrics": d.raw_metrics}
        if d.hard_gate is not None:
            entry["gate_passed"] = d.hard_gate.passed
            entry["gate_reason"] = d.hard_gate.reason
        dims[name] = entry

    return {
        "status": "success",
        "composite_score": analysis.composite_score,
        "hard_gates_passed": analysis.hard_gates_passed,
        "gate_failures": analysis.gate_failures,
        "dimensions": dims,
    }


def _handle_mix_tracks(inputs: dict) -> dict:
    from src.audio.mixer import mix_n_tracks
    from pathlib import Path

    tracks = [dict(t) if isinstance(t, dict) else t.dict() for t in inputs["tracks"]]
    out = inputs.get("output_path", "")
    if not out:
        out = str(Path(tracks[0]["path"]).parent / "mixdown.wav")

    result = mix_n_tracks(tracks, out, normalize=inputs.get("normalize", True))
    return {"status": "success", "output_path": result, "num_tracks": len(tracks)}


_training_jobs: dict[int, dict] = {}


def _handle_check_training_status(inputs: dict) -> dict:
    pid = inputs.get("pid", 0)
    voice_name = inputs.get("voice_name", "")

    if pid == 0 and not voice_name:
        jobs = []
        for p, info in _training_jobs.items():
            proc = info.get("process")
            status = "running" if proc and proc.poll() is None else "completed" if proc and proc.poll() == 0 else "failed"
            jobs.append({"pid": p, "voice_name": info.get("voice_name", ""), "status": status})
        return {"status": "success", "jobs": jobs}

    if pid > 0 and pid in _training_jobs:
        info = _training_jobs[pid]
        proc = info.get("process")
        log_path = info.get("log_path", "")

        if proc is None:
            return {"status": "error", "error": f"No process for PID {pid}"}

        poll = proc.poll()
        if poll is None:
            status = "running"
        elif poll == 0:
            status = "completed"
            vn = info.get("voice_name", "")
            if vn:
                try:
                    from src.voice.voice_registry import register_voice
                    from src.orchestrator.config import VOICES_DIR
                    lora_path = VOICES_DIR / f"{vn}-acestep-lora.safetensors"
                    if lora_path.exists():
                        register_voice(voice_id=vn, name=vn, voice_type="acestep_lora", model_path=str(lora_path))
                except Exception:
                    pass
        else:
            status = "failed"

        last_lines = ""
        if log_path and os.path.exists(log_path):
            with open(log_path) as f:
                lines = f.readlines()
                last_lines = "".join(lines[-10:])

        return {"status": "success", "training_status": status, "pid": pid, "voice_name": info.get("voice_name", ""), "log_tail": last_lines}

    return {"status": "error", "error": f"Training job not found: pid={pid}"}


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS = {
    # Generation
    "create_composition_plan": _handle_create_composition_plan,
    "update_composition_plan": _handle_update_composition_plan,
    "generate_notation_claude": _handle_generate_notation_claude,
    "generate_notation_notagen": _handle_generate_notation_notagen,
    "generate_audio_acestep": _handle_generate_audio_acestep,
    "generate_audio_acestep_lora": _handle_generate_audio_acestep_lora,
    # v1.5
    "generate_audio_acestep_v15": _handle_generate_audio_acestep_v15,
    "repaint_audio_acestep": _handle_repaint_audio_acestep,
    "cover_audio_acestep": _handle_cover_audio_acestep,
    "extend_audio_acestep": _handle_extend_audio_acestep,
    # Voice
    "render_vocals_diffsinger": _handle_render_vocals_diffsinger,
    "convert_voice_rvc": _handle_convert_voice_rvc,
    "feminize_audio": _handle_feminize_audio,
    "select_voice": _handle_select_voice,
    "separate_stems_demucs": _handle_separate_stems_demucs,
    "train_voice_lora": _handle_train_voice_lora,
    # Validation
    "validate_notation": _handle_validate_notation,
    "validate_audio": _handle_validate_audio,
    # Rendering
    "render_preview": _handle_render_preview,
    "render_score_pdf": _handle_render_score_pdf,
    "render_quality_audio": _handle_render_quality_audio,
    # State
    "update_memory_document": _handle_update_memory_document,
    "save_checkpoint": _handle_save_checkpoint,
    "list_sections": _handle_list_sections,
    "get_section": _handle_get_section,
    "add_theme": _handle_add_theme,
    "record_theme_appearance": _handle_record_theme_appearance,
    "update_harmonic_plan": _handle_update_harmonic_plan,
    "add_revision_note": _handle_add_revision_note,
    "update_section_status": _handle_update_section_status,
    # Hierarchical planning
    "plan_piece": _handle_plan_piece,
    "zoom_in": _handle_zoom_in,
    "zoom_out": _handle_zoom_out,
    # Post-production
    "apply_postproduction": _handle_apply_postproduction,
    "export_final": _handle_export_final,
    "remix_track": _handle_remix_track,
    # Playback
    "play_audio": _handle_play_audio,
    # Effects
    "apply_eq": _handle_apply_eq,
    "apply_reverb": _handle_apply_reverb,
    "apply_compression": _handle_apply_compression,
    "adjust_volume": _handle_adjust_volume,
    # Bridge
    "extract_midi_from_audio": _handle_extract_midi_from_audio,
    # Quality & curation
    "score_audio_quality": _handle_score_audio_quality,
    "analyze_audio_dimensions": _handle_analyze_audio_dimensions,
    # Mixer
    "mix_tracks": _handle_mix_tracks,
    # Training
    "check_training_status": _handle_check_training_status,
}
