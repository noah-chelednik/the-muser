"""Configuration loader for the curation pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import PipelineConfig

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = BASE_DIR / "curation_config.json"


def load_config(
    config_path: str | Path | None = None,
    production_run: str | None = None,
) -> PipelineConfig:
    """Load pipeline config from JSON file + env overrides."""
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if cfg_path.exists():
        with open(cfg_path) as f:
            data = json.load(f)
    else:
        data = {}

    # CLI override for production run
    if production_run:
        data["production_run"] = production_run

    config = PipelineConfig(**data)

    # Resolve production run directory
    if config.production_run:
        config.production_run_dir = str(BASE_DIR / "production_run" / config.production_run)

    # Env overrides
    config.artist_name = os.environ.get("MUSER_ARTIST_NAME", config.artist_name)
    config.copyright_holder = os.environ.get("MUSER_COPYRIGHT_HOLDER", config.copyright_holder)
    yr = os.environ.get("MUSER_RELEASE_YEAR")
    if yr:
        config.release_year = int(yr)

    return config
