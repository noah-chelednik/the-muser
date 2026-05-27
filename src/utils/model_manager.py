"""GPU model lifecycle manager for The Muser.

Implements a singleton ``ModelManager`` that ensures only one large model
occupies VRAM at any time.  Before loading a new model the manager checks
free VRAM and, if necessary, unloads the previous model and clears the
CUDA cache.

Usage::

    from src.utils.model_manager import get_manager

    mgr = get_manager()
    notagen = mgr.load_notagen()
    # ... use notagen ...
    mgr.unload_current()

All heavy imports (``torch``, model-specific modules) are deferred until
the method that requires them is actually called so that importing this
module is cheap and safe in CPU-only environments.
"""

from __future__ import annotations

import gc
import logging
import sys
from typing import Any

from src.orchestrator.config import (
    ACESTEP_DIR,
    ACESTEP_V15_DIR,
    ACESTEP_V15_DIT_MODEL,
    DIFFSINGER_DIR,
    NOTAGEN_DIR,
    VRAM_BUDGET,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_torch(require_cuda: bool = True):
    """Lazily import ``torch`` and return the module.

    Parameters
    ----------
    require_cuda:
        If ``True`` (default for GPU models), raises ``RuntimeError`` when
        CUDA is not available.  If ``False``, returns torch even without
        CUDA (for CPU-offloaded models like ACE-Step).
    """
    try:
        import torch  # noqa: F811
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required for model management but is not installed."
        ) from exc
    if require_cuda and not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA is not available.  This model requires an NVIDIA GPU with "
            "CUDA support.  For CPU-only operation, use ACE-Step with "
            "cpu_offload=True."
        )
    return torch


def _get_device(prefer_cpu: bool = False):
    """Return the appropriate torch device.

    Parameters
    ----------
    prefer_cpu:
        If ``True``, always returns CPU device (for CPU offload mode).
        If ``False``, returns CUDA if available, else CPU.
    """
    torch = _import_torch(require_cuda=False)
    if prefer_cpu or not torch.cuda.is_available():
        return torch.device("cpu")
    return torch.device("cuda")


# ---------------------------------------------------------------------------
# ModelManager
# ---------------------------------------------------------------------------


class ModelManager:
    """Singleton manager responsible for loading / unloading GPU models.

    Only **one** model is kept in VRAM at a time.  Calling any ``load_*``
    method will check the VRAM budget and, if necessary, evict the
    currently-loaded model first.
    """

    def __init__(self) -> None:
        self._current_model: Any | None = None
        self._current_name: str | None = None

    # -- VRAM helpers -------------------------------------------------------

    def get_vram_free_gb(self) -> float:
        """Return the amount of free VRAM in gigabytes on the default device."""
        torch = _import_torch()
        free_bytes, _total_bytes = torch.cuda.mem_get_info()
        return free_bytes / (1024**3)

    def unload_current(self) -> None:
        """Unload the currently-loaded model and release VRAM."""
        if self._current_model is None:
            logger.debug("unload_current called but no model is loaded.")
            return

        name = self._current_name
        logger.info("Unloading model '%s' from VRAM.", name)

        try:
            # Handle tuple models (e.g., v1.5 dit_handler + llm_handler)
            if isinstance(self._current_model, tuple):
                for m in self._current_model:
                    try:
                        if hasattr(m, "unload"):
                            m.unload()
                    except Exception:
                        pass
            del self._current_model
        except Exception:  # pragma: no cover – defensive
            pass

        self._current_model = None
        self._current_name = None

        gc.collect()

        try:
            torch = _import_torch()
            torch.cuda.empty_cache()
        except RuntimeError:
            # CUDA may not be available; already logged at import time.
            pass

        logger.info("Model '%s' unloaded; CUDA cache cleared.", name)

    def _check_vram(self, required_gb: float) -> None:
        """Ensure at least *required_gb* of VRAM is available.

        If the free VRAM is insufficient and a model is currently loaded,
        ``unload_current`` is called first.  If VRAM is *still* insufficient
        after unloading, ``RuntimeError`` is raised.
        """
        free = self.get_vram_free_gb()
        logger.debug("VRAM check: %.2f GB free, %.2f GB required.", free, required_gb)

        if free >= required_gb:
            return

        if self._current_model is not None:
            logger.info(
                "Insufficient VRAM (%.2f GB free / %.2f GB needed); unloading '%s'.",
                free,
                required_gb,
                self._current_name,
            )
            self.unload_current()
            free = self.get_vram_free_gb()

        if free < required_gb:
            raise RuntimeError(
                f"Not enough VRAM to load model: {free:.2f} GB free but "
                f"{required_gb:.2f} GB required.  Close other GPU processes "
                f"or reduce the VRAM budget."
            )

    # -- Model loaders ------------------------------------------------------

    def load_notagen(self) -> Any:
        """Load the NotaGen symbolic-music generation model.

        Returns the loaded model object (or module-level inference handle).
        The model directory is added to ``sys.path`` so that NotaGen's
        internal imports resolve correctly.

        Raises ``RuntimeError`` on VRAM or import failures.
        """
        if self._current_name == "notagen" and self._current_model is not None:
            logger.debug("NotaGen is already loaded; returning cached model.")
            return self._current_model

        required_gb = VRAM_BUDGET.get("notagen", 24.0)
        self._check_vram(required_gb)

        notagen_path = str(NOTAGEN_DIR)
        if notagen_path not in sys.path:
            sys.path.insert(0, notagen_path)
            logger.debug("Added %s to sys.path.", notagen_path)

        # Add the inference subdirectory to sys.path so NotaGen's
        # relative imports (samplings, config, etc.) resolve correctly.
        inference_path = str(NOTAGEN_DIR / "inference")
        if inference_path not in sys.path:
            sys.path.insert(0, inference_path)
            logger.debug("Added %s to sys.path.", inference_path)

        try:
            torch = _import_torch()
            from transformers import GPT2Config

            # Import the actual model class from NotaGen's inference/utils.py.
            from utils import NotaGenLMHeadModel  # type: ignore[import-untyped]
            from config import (  # type: ignore[import-untyped]
                PATCH_SIZE,
                PATCH_LENGTH,
                PATCH_NUM_LAYERS,
                CHAR_NUM_LAYERS,
                HIDDEN_SIZE,
            )

            # Locate the checkpoint – prefer the consolidated weights file.
            ckpt_path = NOTAGEN_DIR / "weights" / "notagen.pth"
            if not ckpt_path.exists():
                # Fallback: look for any .pth or .bin in the weights directory.
                weights_dir = NOTAGEN_DIR / "weights"
                candidates = (
                    (sorted(weights_dir.glob("*.pth")) + sorted(weights_dir.glob("*.bin")))
                    if weights_dir.is_dir()
                    else []
                )
                if not candidates:
                    raise FileNotFoundError(f"No NotaGen checkpoint found in {weights_dir}")
                ckpt_path = candidates[-1]

            logger.info("Loading NotaGen checkpoint from %s", ckpt_path)

            # Build model configs matching the checkpoint architecture.
            patch_config = GPT2Config(
                num_hidden_layers=PATCH_NUM_LAYERS,
                max_length=PATCH_LENGTH,
                max_position_embeddings=PATCH_LENGTH,
                n_embd=HIDDEN_SIZE,
                num_attention_heads=HIDDEN_SIZE // 64,
                vocab_size=1,
            )
            byte_config = GPT2Config(
                num_hidden_layers=CHAR_NUM_LAYERS,
                max_length=PATCH_SIZE + 1,
                max_position_embeddings=PATCH_SIZE + 1,
                hidden_size=HIDDEN_SIZE,
                num_attention_heads=HIDDEN_SIZE // 64,
                vocab_size=128,
            )

            model = NotaGenLMHeadModel(
                encoder_config=patch_config,
                decoder_config=byte_config,
            )
            checkpoint = torch.load(str(ckpt_path), map_location="cuda", weights_only=False)
            # NotaGen checkpoints wrap the state dict under a 'model' key.
            state = checkpoint["model"] if "model" in checkpoint else checkpoint
            model.load_state_dict(state, strict=False)
            model.cuda().eval()

            self._current_model = model
            self._current_name = "notagen"
            logger.info(
                "NotaGen loaded successfully (VRAM free: %.2f GB).", self.get_vram_free_gb()
            )
            return self._current_model

        except Exception as exc:
            logger.error("Failed to load NotaGen: %s", exc)
            # Clean up partial loads.
            self._current_model = None
            self._current_name = None
            gc.collect()
            try:
                _import_torch().cuda.empty_cache()
            except RuntimeError:
                pass
            raise RuntimeError(f"Failed to load NotaGen model: {exc}") from exc

    def load_acestep(self, cpu_offload: bool = False) -> Any:
        """Load the ACE-Step audio generation model.

        Parameters
        ----------
        cpu_offload:
            If ``True``, enable CPU offload mode (~8 GB peak VRAM, moves
            components in/out of GPU as needed).  Slower but allows other
            processes to share the GPU.

        Returns the loaded ACEStepPipeline object.  Note that the
        pipeline lazy-loads checkpoint weights on the first ``__call__``,
        not at construction time.

        Raises ``RuntimeError`` on import failures.
        """
        if self._current_name == "acestep" and self._current_model is not None:
            logger.debug("ACE-Step is already loaded; returning cached model.")
            return self._current_model

        torch = _import_torch(require_cuda=False)
        use_cpu = cpu_offload or not torch.cuda.is_available()

        if not use_cpu:
            required_gb = VRAM_BUDGET.get("acestep", 18.0)
            self._check_vram(required_gb)

        acestep_path = str(ACESTEP_DIR)
        if acestep_path not in sys.path:
            sys.path.insert(0, acestep_path)
            logger.debug("Added %s to sys.path.", acestep_path)

        try:
            from acestep.pipeline_ace_step import ACEStepPipeline  # type: ignore[import-untyped]

            # Determine checkpoint_dir: use local dir if weight subdirs
            # exist, otherwise pass None to trigger HF auto-download.
            weight_subdirs = (
                "music_dcae_f8c8",
                "music_vocoder",
                "ace_step_transformer",
                "umt5-base",
            )
            has_local_weights = all((ACESTEP_DIR / d).is_dir() for d in weight_subdirs)
            checkpoint_dir = str(ACESTEP_DIR) if has_local_weights else None

            device_id = -1 if use_cpu else 0
            dtype = "float32" if use_cpu else "bfloat16"

            logger.info(
                "Initialising ACE-Step pipeline (checkpoint_dir=%s, "
                "device_id=%d, dtype=%s, cpu_offload=%s)",
                checkpoint_dir,
                device_id,
                dtype,
                use_cpu,
            )

            pipeline = ACEStepPipeline(
                checkpoint_dir=checkpoint_dir,
                device_id=device_id,
                dtype=dtype,
                cpu_offload=use_cpu,
            )

            if use_cpu:
                logger.info(
                    "ACE-Step initialised with CPU offload. "
                    "Weights will load on first generation call."
                )
            else:
                logger.info(
                    "ACE-Step initialised on GPU (device_id=0). "
                    "Weights will load on first generation call."
                )

            self._current_model = pipeline
            self._current_name = "acestep"
            self._cpu_offload = use_cpu
            return self._current_model

        except Exception as exc:
            logger.error("Failed to load ACE-Step: %s", exc)
            self._current_model = None
            self._current_name = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise RuntimeError(f"Failed to load ACE-Step model: {exc}") from exc

    def load_acestep_v15(self) -> tuple[Any, Any]:
        """Load ACE-Step v1.5 handlers (DiT + LLM).

        Returns a tuple of (dit_handler, llm_handler).

        Raises ``RuntimeError`` on import or initialization failures.
        """
        if self._current_name == "acestep_v15" and self._current_model is not None:
            logger.debug("ACE-Step v1.5 is already loaded; returning cached handlers.")
            return self._current_model

        torch = _import_torch(require_cuda=False)

        if torch.cuda.is_available():
            required_gb = VRAM_BUDGET.get("acestep_v15", 22.0)
            self._check_vram(required_gb)

        v15_path = str(ACESTEP_V15_DIR)
        if v15_path not in sys.path:
            sys.path.insert(0, v15_path)
            logger.debug("Added %s to sys.path.", v15_path)

        try:
            from acestep.handler import AceStepHandler
            from acestep.llm_inference import LLMHandler

            logger.info(
                "Initialising ACE-Step v1.5 (model=%s, project=%s)",
                ACESTEP_V15_DIT_MODEL,
                ACESTEP_V15_DIR,
            )

            dit_handler = AceStepHandler()
            llm_handler = LLMHandler()

            # Initialize the DiT model
            status, success = dit_handler.initialize_service(
                project_root=str(ACESTEP_V15_DIR),
                config_path=ACESTEP_V15_DIT_MODEL,
                device="auto",
                use_flash_attention=False,
                compile_model=False,
                offload_to_cpu=not torch.cuda.is_available(),
            )

            if not success:
                raise RuntimeError(f"ACE-Step v1.5 init failed: {status}")

            logger.info("ACE-Step v1.5 initialised: %s", status)

            handlers = (dit_handler, llm_handler)
            self._current_model = handlers
            self._current_name = "acestep_v15"
            return handlers

        except Exception as exc:
            logger.error("Failed to load ACE-Step v1.5: %s", exc)
            self._current_model = None
            self._current_name = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise RuntimeError(f"Failed to load ACE-Step v1.5: {exc}") from exc

    def load_diffsinger(
        self,
        voice_model_dir: str | None = None,
        prefer_onnx: bool = True,
    ) -> Any:
        """Load the DiffSinger singing-voice synthesis model.

        Loads the acoustic model, variance model, and vocoder as a unit.
        Supports both ONNX inference (fast, lower VRAM) and PyTorch
        (full-featured, higher VRAM).

        Parameters
        ----------
        voice_model_dir:
            Path to a specific voice model directory containing acoustic
            and variance checkpoints.  If ``None``, uses the default
            DiffSinger checkpoints directory.
        prefer_onnx:
            If ``True`` (default), load ONNX models when available for
            faster inference.  Falls back to PyTorch if ONNX models are
            not found.

        Returns the loaded model object (or a dict of model components
        when using ONNX mode).

        Raises ``RuntimeError`` on VRAM or import failures.
        """
        if self._current_name == "diffsinger" and self._current_model is not None:
            logger.debug("DiffSinger is already loaded; returning cached model.")
            return self._current_model

        from pathlib import Path as _Path

        # Resolve voice model directory
        if voice_model_dir:
            model_dir = _Path(voice_model_dir)
        else:
            model_dir = DIFFSINGER_DIR / "checkpoints" / "default"

        # Detect available model formats
        has_onnx_acoustic = (model_dir / "acoustic.onnx").exists()
        has_onnx_variance = (model_dir / "variance.onnx").exists()
        has_pt_acoustic = (model_dir / "acoustic.ckpt").exists() or (
            model_dir / "acoustic.pt"
        ).exists()

        use_onnx = prefer_onnx and has_onnx_acoustic

        if use_onnx:
            return self._load_diffsinger_onnx(model_dir, has_onnx_variance)
        elif has_pt_acoustic:
            return self._load_diffsinger_pytorch(model_dir)
        else:
            # Try the legacy cascade inference approach
            return self._load_diffsinger_cascade()

    def _load_diffsinger_onnx(self, model_dir: Any, has_variance: bool) -> Any:
        """Load DiffSinger using ONNX Runtime (fast, low VRAM).

        ONNX models can run on CPU or GPU and typically use ~2-4 GB.
        """

        # ONNX uses much less VRAM than PyTorch
        required_gb = min(VRAM_BUDGET.get("diffsinger", 8.0), 4.0)

        # Only check VRAM if CUDA is available; ONNX can run on CPU
        try:
            torch = _import_torch(require_cuda=False)
            if torch.cuda.is_available():
                self._check_vram(required_gb)
        except RuntimeError:
            pass

        try:
            import onnxruntime as ort  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "onnxruntime is required for ONNX DiffSinger inference. "
                "Install with: pip install onnxruntime-gpu (or onnxruntime)"
            ) from exc

        logger.info("Loading DiffSinger ONNX models from %s", model_dir)

        # Configure providers
        providers: list[str] = []
        try:
            if ort.get_device() == "GPU":
                providers.append("CUDAExecutionProvider")
        except Exception:
            pass
        providers.append("CPUExecutionProvider")

        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_opts.intra_op_num_threads = 4

        try:
            acoustic_path = model_dir / "acoustic.onnx"
            acoustic_session = ort.InferenceSession(
                str(acoustic_path),
                sess_opts,
                providers=providers,
            )
            logger.info("Loaded acoustic ONNX model: %s", acoustic_path)

            variance_session = None
            if has_variance:
                variance_path = model_dir / "variance.onnx"
                variance_session = ort.InferenceSession(
                    str(variance_path),
                    sess_opts,
                    providers=providers,
                )
                logger.info("Loaded variance ONNX model: %s", variance_path)

            # Check for vocoder
            vocoder_session = None
            vocoder_onnx = model_dir / "vocoder.onnx"
            if not vocoder_onnx.exists():
                # Check for vocoder name and look in DiffSinger checkpoints
                vocoder_txt = model_dir / "vocoder.txt"
                if vocoder_txt.exists():
                    vocoder_name = vocoder_txt.read_text().strip()
                    vocoder_onnx = DIFFSINGER_DIR / "checkpoints" / vocoder_name / "model.onnx"

            if vocoder_onnx.exists():
                try:
                    vocoder_session = ort.InferenceSession(
                        str(vocoder_onnx),
                        sess_opts,
                        providers=providers,
                    )
                    logger.info("Loaded vocoder ONNX model: %s", vocoder_onnx)
                except Exception as exc:
                    logger.warning("Failed to load vocoder ONNX: %s", exc)

            model = {
                "type": "onnx",
                "acoustic": acoustic_session,
                "variance": variance_session,
                "vocoder": vocoder_session,
                "model_dir": str(model_dir),
                "providers": providers,
                "session_options": sess_opts,
            }

            self._current_model = model
            self._current_name = "diffsinger"
            logger.info("DiffSinger ONNX loaded successfully.")
            return self._current_model

        except Exception as exc:
            logger.error("Failed to load DiffSinger ONNX: %s", exc)
            self._current_model = None
            self._current_name = None
            gc.collect()
            raise RuntimeError(f"Failed to load DiffSinger ONNX: {exc}") from exc

    def _load_diffsinger_pytorch(self, model_dir: Any) -> Any:
        """Load DiffSinger using PyTorch (full-featured, higher VRAM)."""
        required_gb = VRAM_BUDGET.get("diffsinger", 8.0)
        self._check_vram(required_gb)

        diffsinger_path = str(DIFFSINGER_DIR)
        if diffsinger_path not in sys.path:
            sys.path.insert(0, diffsinger_path)
            logger.debug("Added %s to sys.path.", diffsinger_path)

        try:
            torch = _import_torch()

            logger.info("Loading DiffSinger PyTorch from %s", model_dir)

            # Load acoustic checkpoint
            acoustic_ckpt = model_dir / "acoustic.ckpt"
            if not acoustic_ckpt.exists():
                acoustic_ckpt = model_dir / "acoustic.pt"

            variance_ckpt = model_dir / "variance.ckpt"
            if not variance_ckpt.exists():
                variance_ckpt = model_dir / "variance.pt"

            # Try to use DiffSinger's own model loading
            try:
                from inference.ds_cascade import DiffSingerCascadeInfer  # type: ignore[import-untyped]

                model = DiffSingerCascadeInfer(
                    device="cuda",
                    ckpt_path=str(acoustic_ckpt) if acoustic_ckpt.exists() else None,
                )

                self._current_model = model
                self._current_name = "diffsinger"
                logger.info(
                    "DiffSinger PyTorch loaded via CascadeInfer (VRAM free: %.2f GB).",
                    self.get_vram_free_gb(),
                )
                return self._current_model

            except (ImportError, TypeError):
                # CascadeInfer may not accept ckpt_path; try without it
                pass

            # Manual checkpoint loading
            logger.info("Loading acoustic checkpoint: %s", acoustic_ckpt)
            acoustic_state = torch.load(
                str(acoustic_ckpt),
                map_location="cuda",
                weights_only=False,
            )

            variance_state = None
            if variance_ckpt.exists():
                logger.info("Loading variance checkpoint: %s", variance_ckpt)
                variance_state = torch.load(
                    str(variance_ckpt),
                    map_location="cuda",
                    weights_only=False,
                )

            model = {
                "type": "pytorch",
                "acoustic_state": acoustic_state,
                "variance_state": variance_state,
                "model_dir": str(model_dir),
            }

            self._current_model = model
            self._current_name = "diffsinger"
            logger.info(
                "DiffSinger PyTorch loaded (VRAM free: %.2f GB).",
                self.get_vram_free_gb(),
            )
            return self._current_model

        except Exception as exc:
            logger.error("Failed to load DiffSinger PyTorch: %s", exc)
            self._current_model = None
            self._current_name = None
            gc.collect()
            try:
                _import_torch().cuda.empty_cache()
            except RuntimeError:
                pass
            raise RuntimeError(f"Failed to load DiffSinger PyTorch: {exc}") from exc

    def _load_diffsinger_cascade(self) -> Any:
        """Legacy loader: use DiffSinger's built-in CascadeInfer.

        This path is used when no specific voice model directory is provided
        and we rely on DiffSinger's default configuration.
        """
        required_gb = VRAM_BUDGET.get("diffsinger", 8.0)
        self._check_vram(required_gb)

        diffsinger_path = str(DIFFSINGER_DIR)
        if diffsinger_path not in sys.path:
            sys.path.insert(0, diffsinger_path)
            logger.debug("Added %s to sys.path.", diffsinger_path)

        try:
            torch = _import_torch()

            from inference.ds_cascade import DiffSingerCascadeInfer  # type: ignore[import-untyped]

            logger.info("Initialising DiffSinger CascadeInfer from %s", DIFFSINGER_DIR)
            model = DiffSingerCascadeInfer(device="cuda")

            self._current_model = model
            self._current_name = "diffsinger"
            logger.info(
                "DiffSinger loaded successfully (VRAM free: %.2f GB).",
                self.get_vram_free_gb(),
            )
            return self._current_model

        except Exception as exc:
            logger.error("Failed to load DiffSinger: %s", exc)
            self._current_model = None
            self._current_name = None
            gc.collect()
            try:
                _import_torch().cuda.empty_cache()
            except RuntimeError:
                pass
            raise RuntimeError(f"Failed to load DiffSinger model: {exc}") from exc

    # -- Introspection ------------------------------------------------------

    @property
    def current_model_name(self) -> str | None:
        """Return the name of the currently-loaded model, or ``None``."""
        return self._current_name

    @property
    def is_loaded(self) -> bool:
        """Return ``True`` if any model is currently loaded."""
        return self._current_model is not None

    def __repr__(self) -> str:
        loaded = self._current_name or "none"
        return f"<ModelManager loaded={loaded!r}>"


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------

_manager: ModelManager | None = None


def get_manager() -> ModelManager:
    """Return the global ``ModelManager`` singleton, creating it on first call."""
    global _manager
    if _manager is None:
        _manager = ModelManager()
    return _manager
