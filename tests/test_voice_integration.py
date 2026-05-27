"""Voice pipeline integration tests for The Muser.

Comprehensive tests covering Demucs stem separation, RVC voice conversion,
Seed-VC zero-shot conversion, the 3-stage feminization pipeline, the voice
registry, and full pipeline chaining.

Mock-based tests run without GPU. GPU-dependent tests are marked with
``@pytest.mark.gpu``.
"""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# Mock-based tests (no GPU required)
# =========================================================================


class TestDemucsWrapperPythonApiFallback:
    """Verify Demucs falls back to CLI when the Python API is unavailable."""

    def test_demucs_wrapper_python_api_fallback(self, voice_test_audio, tmp_path):
        """When demucs Python import fails, the wrapper should invoke the CLI."""
        output_dir = str(tmp_path / "stems")

        # Make the Python API import fail so we hit the CLI fallback path
        with (
            patch(
                "src.voice.demucs_wrapper._separate_via_python",
                side_effect=ImportError("No module named 'demucs'"),
            ) as mock_python,
            patch(
                "src.voice.demucs_wrapper._separate_via_cli",
                return_value={"vocals": "/fake/vocals.wav", "no_vocals": "/fake/no_vocals.wav"},
            ) as mock_cli,
        ):
            from src.voice.demucs_wrapper import separate_stems

            result = separate_stems(
                input_audio=voice_test_audio,
                output_dir=output_dir,
                two_stems=True,
                model="htdemucs",
            )

            mock_python.assert_called_once()
            mock_cli.assert_called_once_with(
                voice_test_audio,
                output_dir,
                True,
                "htdemucs",
            )
            assert "vocals" in result
            assert "no_vocals" in result


class TestRVCWrapperFormantParams:
    """Verify convert_voice() passes all formant parameters correctly."""

    def test_rvc_wrapper_formant_params_python_api(self, voice_test_audio, tmp_path):
        """Formant parameters reach the Python API backend correctly."""
        model_file = tmp_path / "model.pth"
        model_file.write_bytes(b"fake model")
        output_path = str(tmp_path / "output.wav")

        # Mock the VoiceConverter import so _convert_via_python_api succeeds
        mock_converter_instance = MagicMock()

        mock_vc_class = MagicMock(return_value=mock_converter_instance)
        mock_module = MagicMock()
        mock_module.VoiceConverter = mock_vc_class

        with patch.dict(
            "sys.modules",
            {"rvc": MagicMock(), "rvc.infer": MagicMock(), "rvc.infer.infer": mock_module},
        ):
            from src.voice.rvc_wrapper import convert_voice

            result = convert_voice(
                input_audio=voice_test_audio,
                model_path=str(model_file),
                index_path="",
                transpose=6,
                f0_method="rmvpe",
                output_path=output_path,
                formant_shift=True,
                formant_quefrency=10.0,
                formant_timbre=1.25,
                index_rate=0.6,
                filter_radius=4,
                rms_mix_rate=0.15,
                protect=0.3,
            )

        # Verify the converter was called with the right formant params
        mock_converter_instance.convert_audio.assert_called_once()
        kwargs = mock_converter_instance.convert_audio.call_args
        # convert_audio is called via **convert_kwargs so check keyword args
        call_kwargs = kwargs.kwargs if kwargs.kwargs else kwargs[1]
        assert call_kwargs["formant_shifting"] is True
        assert call_kwargs["formant_qfrency"] == 10.0
        assert call_kwargs["formant_timbre"] == 1.25
        assert call_kwargs["index_rate"] == 0.6
        assert call_kwargs["filter_radius"] == 4
        assert call_kwargs["protect"] == 0.3
        assert call_kwargs["pitch"] == 6
        assert result == output_path

    def test_rvc_wrapper_formant_params_no_formant_shift(self, voice_test_audio, tmp_path):
        """When formant_shift=False, formant_shifting/qfrency/timbre are NOT sent."""
        model_file = tmp_path / "model.pth"
        model_file.write_bytes(b"fake model")
        output_path = str(tmp_path / "output.wav")

        mock_converter_instance = MagicMock()
        mock_vc_class = MagicMock(return_value=mock_converter_instance)
        mock_module = MagicMock()
        mock_module.VoiceConverter = mock_vc_class

        with patch.dict(
            "sys.modules",
            {"rvc": MagicMock(), "rvc.infer": MagicMock(), "rvc.infer.infer": mock_module},
        ):
            from src.voice.rvc_wrapper import convert_voice

            convert_voice(
                input_audio=voice_test_audio,
                model_path=str(model_file),
                output_path=output_path,
                formant_shift=False,
            )

        call_kwargs = mock_converter_instance.convert_audio.call_args.kwargs
        assert "formant_shifting" not in call_kwargs
        assert "formant_qfrency" not in call_kwargs
        assert "formant_timbre" not in call_kwargs


class TestRVCWrapperCLICommandConstruction:
    """Verify the CLI fallback constructs the correct subprocess command."""

    def test_rvc_wrapper_cli_command_construction(self, voice_test_audio, tmp_path):
        """Mocked subprocess.run receives the correct CLI args including formant params."""
        model_file = tmp_path / "model.pth"
        model_file.write_bytes(b"fake model")
        output_path = str(tmp_path / "output.wav")

        # Force ImportError on Python API so it falls through to CLI
        with (
            patch(
                "src.voice.rvc_wrapper._convert_via_python_api",
                side_effect=ImportError("no rvc"),
            ),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stderr="", stdout=""),
            ) as mock_run,
        ):
            from src.voice.rvc_wrapper import convert_voice

            convert_voice(
                input_audio=voice_test_audio,
                model_path=str(model_file),
                index_path="/some/index.index",
                transpose=4,
                f0_method="crepe",
                output_path=output_path,
                formant_shift=True,
                formant_quefrency=12.0,
                formant_timbre=1.3,
                index_rate=0.8,
                filter_radius=5,
                rms_mix_rate=0.2,
                protect=0.4,
            )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]

        # Verify basic args
        assert "--input_path" in cmd
        assert voice_test_audio in cmd
        assert "--output_path" in cmd
        assert output_path in cmd
        assert "--pitch" in cmd
        idx_pitch = cmd.index("--pitch")
        assert cmd[idx_pitch + 1] == "4"
        assert "--f0_method" in cmd
        idx_f0 = cmd.index("--f0_method")
        assert cmd[idx_f0 + 1] == "crepe"

        # Verify formant params
        assert "--formant_shifting" in cmd
        idx_fs = cmd.index("--formant_shifting")
        assert cmd[idx_fs + 1] == "true"
        assert "--formant_qfrency" in cmd
        idx_fq = cmd.index("--formant_qfrency")
        assert cmd[idx_fq + 1] == "12.0"
        assert "--formant_timbre" in cmd
        idx_ft = cmd.index("--formant_timbre")
        assert cmd[idx_ft + 1] == "1.3"

        # Verify extended params are present
        assert "--index_rate" in cmd
        idx_ir = cmd.index("--index_rate")
        assert cmd[idx_ir + 1] == "0.8"
        assert "--filter_radius" in cmd
        idx_fr = cmd.index("--filter_radius")
        assert cmd[idx_fr + 1] == "5"
        assert "--volume_envelope" in cmd
        idx_ve = cmd.index("--volume_envelope")
        assert cmd[idx_ve + 1] == "0.2"
        assert "--protect" in cmd
        idx_pr = cmd.index("--protect")
        assert cmd[idx_pr + 1] == "0.4"

    def test_rvc_cli_no_formant_flags_when_disabled(self, voice_test_audio, tmp_path):
        """When formant_shift=False, formant CLI flags are absent."""
        model_file = tmp_path / "model.pth"
        model_file.write_bytes(b"fake model")
        output_path = str(tmp_path / "output.wav")

        with (
            patch(
                "src.voice.rvc_wrapper._convert_via_python_api",
                side_effect=ImportError("no rvc"),
            ),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0, stderr="", stdout=""),
            ) as mock_run,
        ):
            from src.voice.rvc_wrapper import convert_voice

            convert_voice(
                input_audio=voice_test_audio,
                model_path=str(model_file),
                output_path=output_path,
                formant_shift=False,
            )

        cmd = mock_run.call_args[0][0]
        assert "--formant_shifting" not in cmd
        assert "--formant_qfrency" not in cmd
        assert "--formant_timbre" not in cmd


class TestSeedVCWrapperParameterValidation:
    """Verify Seed-VC input validation and parameter clamping."""

    def test_missing_input_audio_raises(self):
        """FileNotFoundError when input_audio does not exist."""
        from src.voice.seedvc_wrapper import convert_voice_seedvc

        with pytest.raises(FileNotFoundError, match="Input audio not found"):
            convert_voice_seedvc(
                input_audio="/nonexistent/input.wav",
                reference_audio="/nonexistent/ref.wav",
            )

    def test_missing_reference_audio_raises(self, voice_test_audio):
        """FileNotFoundError when reference_audio does not exist."""
        from src.voice.seedvc_wrapper import convert_voice_seedvc

        with pytest.raises(FileNotFoundError, match="Reference audio not found"):
            convert_voice_seedvc(
                input_audio=voice_test_audio,
                reference_audio="/nonexistent/ref.wav",
            )

    def test_diffusion_steps_clamped(self, voice_test_audio, tmp_path):
        """diffusion_steps is clamped to [1, 50] before reaching backend."""
        ref_audio = tmp_path / "ref.wav"
        # Reuse the voice_test_audio content for the reference
        shutil.copy2(voice_test_audio, str(ref_audio))

        # We mock both backends to capture the clamped value
        with (
            patch(
                "src.voice.seedvc_wrapper._convert_via_python_api",
                side_effect=ImportError("no seedvc"),
            ),
            patch(
                "src.voice.seedvc_wrapper._convert_via_cli",
                return_value="/fake/output.wav",
            ) as mock_cli,
        ):
            from src.voice.seedvc_wrapper import convert_voice_seedvc

            # Pass an out-of-range value (100 -> clamped to 50)
            convert_voice_seedvc(
                input_audio=voice_test_audio,
                reference_audio=str(ref_audio),
                diffusion_steps=100,
            )

        _, kwargs = mock_cli.call_args
        assert kwargs["diffusion_steps"] == 50

    def test_diffusion_steps_clamped_low(self, voice_test_audio, tmp_path):
        """diffusion_steps below 1 is clamped to 1."""
        ref_audio = tmp_path / "ref.wav"
        shutil.copy2(voice_test_audio, str(ref_audio))

        with (
            patch(
                "src.voice.seedvc_wrapper._convert_via_python_api",
                side_effect=ImportError("no seedvc"),
            ),
            patch(
                "src.voice.seedvc_wrapper._convert_via_cli",
                return_value="/fake/output.wav",
            ) as mock_cli,
        ):
            from src.voice.seedvc_wrapper import convert_voice_seedvc

            convert_voice_seedvc(
                input_audio=voice_test_audio,
                reference_audio=str(ref_audio),
                diffusion_steps=-5,
            )

        _, kwargs = mock_cli.call_args
        assert kwargs["diffusion_steps"] == 1

    def test_length_adjust_clamped(self, voice_test_audio, tmp_path):
        """length_adjust is clamped to [0.5, 2.0]."""
        ref_audio = tmp_path / "ref.wav"
        shutil.copy2(voice_test_audio, str(ref_audio))

        with (
            patch(
                "src.voice.seedvc_wrapper._convert_via_python_api",
                side_effect=ImportError("no seedvc"),
            ),
            patch(
                "src.voice.seedvc_wrapper._convert_via_cli",
                return_value="/fake/output.wav",
            ) as mock_cli,
        ):
            from src.voice.seedvc_wrapper import convert_voice_seedvc

            # Too high
            convert_voice_seedvc(
                input_audio=voice_test_audio,
                reference_audio=str(ref_audio),
                length_adjust=5.0,
            )

        _, kwargs = mock_cli.call_args
        assert kwargs["length_adjust"] == 2.0

    def test_auto_output_path(self, voice_test_audio, tmp_path):
        """When output_path is None, an auto-generated path is used."""
        ref_audio = tmp_path / "ref.wav"
        shutil.copy2(voice_test_audio, str(ref_audio))

        with (
            patch(
                "src.voice.seedvc_wrapper._convert_via_python_api",
                side_effect=ImportError("no seedvc"),
            ),
            patch(
                "src.voice.seedvc_wrapper._convert_via_cli",
                return_value="/fake/output.wav",
            ) as mock_cli,
        ):
            from src.voice.seedvc_wrapper import convert_voice_seedvc

            convert_voice_seedvc(
                input_audio=voice_test_audio,
                reference_audio=str(ref_audio),
                output_path=None,
            )

        _, kwargs = mock_cli.call_args
        assert "_seedvc" in kwargs["output_path"]


class TestFeminizePipelineThreeStages:
    """Verify the 3-stage feminization pipeline chains correctly."""

    def test_feminize_pipeline_three_stages(self, voice_test_audio, tmp_path):
        """All three stages are called in order with correct intermediate paths."""
        output_path = str(tmp_path / "feminized.wav")
        model_path = str(tmp_path / "model.pth")
        Path(model_path).write_bytes(b"fake model")

        stage_calls = []

        def fake_stage1(input_audio, output_path, formant_ratio=1.07):
            stage_calls.append(("stage1", input_audio, output_path, formant_ratio))
            # Create the output file so stage 2 can find it
            Path(output_path).write_bytes(b"stage1 output")
            return output_path

        def fake_stage2(input_audio, output_path, rvc_model_path, **kwargs):
            stage_calls.append(("stage2", input_audio, output_path, rvc_model_path))
            Path(output_path).write_bytes(b"stage2 output")
            return output_path

        def fake_stage3(input_audio, output_path, **kwargs):
            stage_calls.append(("stage3", input_audio, output_path))
            Path(output_path).write_bytes(b"stage3 output")
            return output_path

        with (
            patch(
                "scripts.feminize_voice._stage1_formant_preshift",
                side_effect=fake_stage1,
            ),
            patch(
                "scripts.feminize_voice._stage2_rvc_conversion",
                side_effect=fake_stage2,
            ),
            patch(
                "scripts.feminize_voice._stage3_postprocess_eq",
                side_effect=fake_stage3,
            ),
        ):
            from scripts.feminize_voice import feminize_audio

            result = feminize_audio(
                input_audio=voice_test_audio,
                output_path=output_path,
                rvc_model_path=model_path,
                pre_formant_ratio=1.08,
                transpose=6,
            )

        # Verify all three stages were called
        assert len(stage_calls) == 3
        assert stage_calls[0][0] == "stage1"
        assert stage_calls[1][0] == "stage2"
        assert stage_calls[2][0] == "stage3"

        # Stage 1 receives the original input
        assert stage_calls[0][1] == voice_test_audio
        assert stage_calls[0][3] == 1.08  # formant_ratio

        # Stage 2 receives stage 1 output and the model
        assert stage_calls[1][2] != stage_calls[0][2]  # different output paths
        assert stage_calls[1][3] == model_path

        # Stage 3 writes to the final output path
        assert stage_calls[2][2] == output_path

        assert result == output_path


class TestFeminizePresetsAllValid:
    """Verify all 5 feminization presets produce valid parameter dicts."""

    def test_feminize_presets_all_valid(self):
        """Each preset has the required keys with correct value types."""
        from scripts.feminize_voice import FEMINIZATION_PRESETS

        expected_keys = {
            "pre_formant_ratio",
            "transpose",
            "formant_timbre",
            "f0_method",
            "presence_boost_db",
            "chest_cut_db",
            "add_breathiness",
        }

        assert len(FEMINIZATION_PRESETS) == 5, (
            f"Expected 5 presets, got {len(FEMINIZATION_PRESETS)}"
        )

        for preset_name, params in FEMINIZATION_PRESETS.items():
            missing = expected_keys - set(params.keys())
            assert not missing, f"Preset '{preset_name}' missing keys: {missing}"

            assert isinstance(params["pre_formant_ratio"], (int, float)), (
                f"Preset '{preset_name}': pre_formant_ratio should be numeric"
            )
            assert isinstance(params["transpose"], int), (
                f"Preset '{preset_name}': transpose should be int"
            )
            assert isinstance(params["formant_timbre"], (int, float)), (
                f"Preset '{preset_name}': formant_timbre should be numeric"
            )
            assert isinstance(params["f0_method"], str), (
                f"Preset '{preset_name}': f0_method should be str"
            )
            assert isinstance(params["presence_boost_db"], (int, float)), (
                f"Preset '{preset_name}': presence_boost_db should be numeric"
            )
            assert isinstance(params["chest_cut_db"], (int, float)), (
                f"Preset '{preset_name}': chest_cut_db should be numeric"
            )
            assert isinstance(params["add_breathiness"], bool), (
                f"Preset '{preset_name}': add_breathiness should be bool"
            )

    def test_presets_match_config(self):
        """Presets in feminize_voice.py match those in orchestrator config."""
        from scripts.feminize_voice import FEMINIZATION_PRESETS as script_presets
        from src.orchestrator.config import FEMINIZATION_PRESETS as config_presets

        assert set(script_presets.keys()) == set(config_presets.keys()), (
            "Preset names differ between feminize_voice.py and config.py"
        )

        for name in script_presets:
            for key in script_presets[name]:
                assert script_presets[name][key] == config_presets[name][key], (
                    f"Preset '{name}' key '{key}' differs: "
                    f"script={script_presets[name][key]} vs config={config_presets[name][key]}"
                )


class TestVoiceRegistryOperations:
    """Test register, get, list, remove lifecycle for voice entries."""

    def test_voice_registry_operations(self, tmp_path):
        """Full CRUD lifecycle: register -> get -> list -> remove."""
        from src.voice.voice_registry import (
            get_voice,
            list_voices,
            register_voice,
            remove_voice,
        )

        voice_id = "_integration_test_voice"

        # Ensure clean state
        remove_voice(voice_id)
        assert get_voice(voice_id) is None

        # Register
        model_path = str(tmp_path / "integ.pth")
        Path(model_path).write_bytes(b"fake")
        voice = register_voice(
            voice_id=voice_id,
            name="Integration Test Voice",
            voice_type="rvc",
            model_path=model_path,
            description="For integration tests",
            gender="female",
            range="soprano",
            use_cases=["testing", "integration"],
        )
        assert voice["id"] == voice_id
        assert voice["gender"] == "female"

        # Get
        retrieved = get_voice(voice_id)
        assert retrieved is not None
        assert retrieved["name"] == "Integration Test Voice"
        assert retrieved["model_path"] == model_path

        # List
        all_voices = list_voices()
        ids = [v["id"] for v in all_voices]
        assert voice_id in ids

        # Remove
        assert remove_voice(voice_id) is True
        assert get_voice(voice_id) is None
        assert remove_voice(voice_id) is False  # already gone

    def test_registry_fixture_works(self, voice_registry_with_test_model):
        """The voice_registry_with_test_model fixture provides a valid entry."""
        voice = voice_registry_with_test_model
        assert voice["id"] == "_test_fixture_voice"
        assert voice["type"] == "rvc"
        assert "model_path" in voice

        from src.voice.voice_registry import get_voice

        assert get_voice("_test_fixture_voice") is not None


class TestFullPipelineMocked:
    """Mock the entire generate -> separate -> convert -> remix pipeline."""

    def test_full_pipeline_mocked(self, voice_test_audio, tmp_path):
        """Verify the full voice pipeline chains correctly when all stages are mocked."""
        stems_dir = tmp_path / "stems" / "htdemucs" / "voice_test"
        stems_dir.mkdir(parents=True)
        vocals_path = str(stems_dir / "vocals.wav")
        accompaniment_path = str(stems_dir / "no_vocals.wav")
        converted_path = str(tmp_path / "converted_vocals.wav")
        final_path = str(tmp_path / "final_mix.wav")

        # Create fake stem files
        import numpy as np
        import soundfile as sf

        sr = 44100
        dur = 1.0
        t = np.linspace(0, dur, int(sr * dur), dtype=np.float32)
        vocals_audio = 0.5 * np.sin(2 * np.pi * 220 * t)
        accomp_audio = 0.3 * np.sin(2 * np.pi * 110 * t)

        sf.write(vocals_path, vocals_audio, sr)
        sf.write(accompaniment_path, accomp_audio, sr)

        # Step 1: Separate stems (mocked)
        with patch(
            "src.voice.demucs_wrapper.separate_stems",
            return_value={"vocals": vocals_path, "no_vocals": accompaniment_path},
        ) as mock_separate:
            from src.voice.demucs_wrapper import separate_stems

            stems = separate_stems(input_audio=voice_test_audio)

        mock_separate.assert_called_once()
        assert "vocals" in stems
        assert "no_vocals" in stems

        # Step 2: Convert voice (mocked — creates actual output for step 3)
        sf.write(converted_path, vocals_audio * 0.8, sr)  # fake converted

        model_file = tmp_path / "model.pth"
        model_file.write_bytes(b"fake model")

        with (
            patch(
                "src.voice.rvc_wrapper._convert_via_python_api",
                side_effect=ImportError("no rvc"),
            ),
            patch(
                "subprocess.run",
                return_value=MagicMock(returncode=0),
            ),
        ):
            from src.voice.rvc_wrapper import convert_voice

            result = convert_voice(
                input_audio=stems["vocals"],
                model_path=str(model_file),
                output_path=converted_path,
                transpose=4,
                formant_shift=True,
                formant_quefrency=10.0,
                formant_timbre=1.2,
            )

        assert result == converted_path

        # Step 3: Remix (simple mix of converted vocals + accompaniment)
        converted_audio, _ = sf.read(converted_path)
        accomp, _ = sf.read(accompaniment_path)
        min_len = min(len(converted_audio), len(accomp))
        mixed = converted_audio[:min_len] + accomp[:min_len]
        sf.write(final_path, mixed, sr)

        assert Path(final_path).exists()
        final_audio, final_sr = sf.read(final_path)
        assert final_sr == sr
        assert len(final_audio) > 0


# =========================================================================
# GPU tests (require CUDA and real models)
# =========================================================================


@pytest.mark.gpu
class TestDemucsGPU:
    """GPU-dependent Demucs tests requiring the real model."""

    def test_demucs_separates_stems_from_real_audio(self, voice_test_audio, tmp_path):
        """Generate short audio, separate with Demucs, verify 4 stems exist."""
        from src.voice.demucs_wrapper import separate_stems

        stems = separate_stems(
            input_audio=voice_test_audio,
            output_dir=str(tmp_path / "stems"),
            two_stems=False,
            model="htdemucs",
        )

        assert len(stems) == 4, f"Expected 4 stems, got {list(stems.keys())}"
        for stem_name in ["vocals", "drums", "bass", "other"]:
            assert stem_name in stems, f"Missing stem: {stem_name}"
            assert Path(stems[stem_name]).exists(), f"Stem file does not exist: {stems[stem_name]}"


@pytest.mark.gpu
class TestRVCGPU:
    """GPU-dependent RVC tests requiring a real model."""

    def test_rvc_converts_voice(self, voice_test_audio, tmp_path):
        """Convert test audio via RVC if a model file is available."""
        from src.orchestrator.config import VOICES_DIR

        # Look for any .pth model in voices directory
        model_files = list(VOICES_DIR.glob("*.pth")) if VOICES_DIR.exists() else []
        if not model_files:
            pytest.skip("No RVC model files found in voices directory")

        model_path = str(model_files[0])
        index_files = list(VOICES_DIR.glob("*.index"))
        index_path = str(index_files[0]) if index_files else ""
        output_path = str(tmp_path / "rvc_output.wav")

        from src.voice.rvc_wrapper import convert_voice

        result = convert_voice(
            input_audio=voice_test_audio,
            model_path=model_path,
            index_path=index_path,
            transpose=0,
            output_path=output_path,
        )

        assert Path(result).exists(), f"RVC output not found: {result}"

        import soundfile as sf

        audio, sr = sf.read(result)
        assert len(audio) > 0
        assert sr > 0


@pytest.mark.gpu
class TestFeminizationGPU:
    """GPU-dependent end-to-end feminization pipeline tests."""

    def test_feminization_pipeline_end_to_end(self, voice_test_audio, tmp_path):
        """Run feminize_audio() with each preset on test audio."""
        from src.orchestrator.config import VOICES_DIR

        model_files = list(VOICES_DIR.glob("*.pth")) if VOICES_DIR.exists() else []
        if not model_files:
            pytest.skip("No RVC model files found in voices directory")

        model_path = str(model_files[0])

        from scripts.feminize_voice import FEMINIZATION_PRESETS, feminize_audio

        for preset_name, params in FEMINIZATION_PRESETS.items():
            output_path = str(tmp_path / f"fem_{preset_name}.wav")
            result = feminize_audio(
                input_audio=voice_test_audio,
                output_path=output_path,
                rvc_model_path=model_path,
                **params,
            )
            assert Path(result).exists(), f"Preset '{preset_name}' output not found: {result}"


@pytest.mark.gpu
class TestFullVoiceConversionPipelineGPU:
    """Full generate -> separate -> convert -> remix pipeline on GPU."""

    def test_full_voice_conversion_pipeline(self, voice_test_audio, tmp_path):
        """Run the entire pipeline: separate stems, convert vocals, remix."""
        from src.orchestrator.config import VOICES_DIR

        model_files = list(VOICES_DIR.glob("*.pth")) if VOICES_DIR.exists() else []
        if not model_files:
            pytest.skip("No RVC model files found in voices directory")

        # Step 1: Separate
        from src.voice.demucs_wrapper import separate_stems

        stems = separate_stems(
            input_audio=voice_test_audio,
            output_dir=str(tmp_path / "stems"),
            two_stems=True,
        )
        assert "vocals" in stems

        # Step 2: Convert
        from src.voice.rvc_wrapper import convert_voice

        converted_path = str(tmp_path / "converted.wav")
        convert_voice(
            input_audio=stems["vocals"],
            model_path=str(model_files[0]),
            output_path=converted_path,
            transpose=4,
            formant_shift=True,
        )
        assert Path(converted_path).exists()

        # Step 3: Remix
        import soundfile as sf

        converted, sr1 = sf.read(converted_path)
        if "no_vocals" in stems:
            accomp, sr2 = sf.read(stems["no_vocals"])
            min_len = min(len(converted), len(accomp))
            mixed = converted[:min_len] + accomp[:min_len]
        else:
            mixed = converted

        final_path = str(tmp_path / "final_remix.wav")
        sf.write(final_path, mixed, sr1)
        assert Path(final_path).exists()

        final_audio, _ = sf.read(final_path)
        assert len(final_audio) > 0
