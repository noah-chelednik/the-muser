"""MIDI to audio rendering via sfizz (SFZ sample-based synthesis).

Sfizz provides high-quality sample-based instrument rendering using the
SFZ format.  This module defaults to the Sonatina Symphonic Orchestra
instrument library but supports arbitrary SFZ instrument paths.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from src.orchestrator.config import FLUIDSYNTH_TIMEOUT, SAMPLE_RATE, SONATINA_SSO_DIR, VSCO_CE_DIR

logger = logging.getLogger(__name__)

# Re-use the FluidSynth timeout for sfizz rendering as the workload is similar.
SFIZZ_TIMEOUT = FLUIDSYNTH_TIMEOUT


def _find_default_sfz() -> Path:
    """Locate the default SFZ instrument, preferring VSCO 2 CE over Sonatina.

    Search order:
    1. VSCO 2 Community Edition (higher quality orchestral samples)
    2. Sonatina Symphonic Orchestra (fallback)

    Returns:
        Path to a usable ``.sfz`` file.

    Raises:
        FileNotFoundError: If no SFZ files are found in either library.
    """
    # Try VSCO 2 CE first (higher quality)
    if VSCO_CE_DIR.is_dir():
        vsco_preferred = [
            "Strings/Chamber Strings/Chamber Strings.sfz",
            "Strings/Solo Violin/Solo Violin.sfz",
            "Keys/Piano/Piano.sfz",
        ]
        for rel in vsco_preferred:
            candidate = VSCO_CE_DIR / rel
            if candidate.is_file():
                logger.debug("Using VSCO 2 CE instrument: %s", candidate)
                return candidate

        vsco_sfz = sorted(VSCO_CE_DIR.rglob("*.sfz"))
        if vsco_sfz:
            logger.debug("Using first VSCO 2 CE instrument: %s", vsco_sfz[0])
            return vsco_sfz[0]

    # Fall back to Sonatina SSO
    if SONATINA_SSO_DIR.is_dir():
        preferred = [
            "Strings/Ensemble Strings.sfz",
            "Piano/Grand Piano.sfz",
            "Grand Piano.sfz",
        ]
        for rel in preferred:
            candidate = SONATINA_SSO_DIR / rel
            if candidate.is_file():
                return candidate

        sfz_files = sorted(SONATINA_SSO_DIR.rglob("*.sfz"))
        if sfz_files:
            return sfz_files[0]

    raise FileNotFoundError(
        "No SFZ instrument library found. Install VSCO 2 CE to "
        f"{VSCO_CE_DIR} or Sonatina SSO to {SONATINA_SSO_DIR}."
    )


def _find_sfizz_command() -> str:
    """Locate the sfizz rendering command.

    Returns:
        The name of the sfizz CLI tool found on PATH.

    Raises:
        FileNotFoundError: If no sfizz rendering tool is found.
    """
    for cmd in ("sfizz_render", "sfizz"):
        if shutil.which(cmd):
            return cmd
    raise FileNotFoundError(
        "sfizz_render not found. Install sfizz and ensure sfizz_render is on PATH."
    )


def render_sfizz(
    midi_path: str,
    output_path: str,
    sfz_instrument: str | None = None,
) -> str:
    """Render a MIDI file to WAV audio using sfizz.

    Args:
        midi_path: Path to the input MIDI file.
        output_path: Desired path for the output WAV file.
        sfz_instrument: Path to an ``.sfz`` instrument file.  If *None*,
            the default Sonatina SSO instrument is used.

    Returns:
        The absolute path to the generated WAV file.

    Raises:
        FileNotFoundError: If the MIDI file, SFZ instrument, or sfizz
            binary is not found.
        subprocess.CalledProcessError: If sfizz exits with an error.
        subprocess.TimeoutExpired: If rendering exceeds the timeout.
    """
    midi = Path(midi_path)
    if not midi.is_file():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")

    if sfz_instrument is not None:
        sfz_path = Path(sfz_instrument)
        if not sfz_path.is_file():
            raise FileNotFoundError(f"SFZ instrument not found: {sfz_instrument}")
    else:
        sfz_path = _find_default_sfz()

    sfizz_cmd = _find_sfizz_command()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sfizz_cmd,
        "--sfz", str(sfz_path),
        "--midi", str(midi),
        "--wav", str(out),
        "--sample-rate", str(SAMPLE_RATE),
    ]

    logger.info(
        "Rendering MIDI via sfizz: %s -> %s (sfz=%s)",
        midi, out, sfz_path.name,
    )

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=SFIZZ_TIMEOUT,
        )
        if result.stderr:
            logger.debug("sfizz stderr: %s", result.stderr.strip())
    except subprocess.CalledProcessError as exc:
        logger.error("sfizz failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("sfizz timed out after %d seconds", SFIZZ_TIMEOUT)
        raise

    if not out.is_file():
        raise RuntimeError(f"sfizz did not produce expected output: {out}")

    logger.info("WAV rendered successfully: %s (%d bytes)", out, out.stat().st_size)
    return str(out.resolve())


def list_sfz_instruments() -> list[str]:
    """Scan all SFZ libraries for available instruments.

    Searches VSCO 2 CE first, then Sonatina SSO.  Instrument names are
    prefixed with the library name for disambiguation.

    Returns:
        A sorted list of instrument names (e.g. ``"vsco2/Strings/Solo Violin"``).
        Returns an empty list if no libraries are found.
    """
    instruments: list[str] = []

    if VSCO_CE_DIR.is_dir():
        for sfz_file in sorted(VSCO_CE_DIR.rglob("*.sfz")):
            relative = sfz_file.relative_to(VSCO_CE_DIR)
            name = f"vsco2/{relative.with_suffix('')}"
            instruments.append(name)
        logger.debug("Found %d VSCO 2 CE instruments", len(instruments))

    sonatina_count = 0
    if SONATINA_SSO_DIR.is_dir():
        for sfz_file in sorted(SONATINA_SSO_DIR.rglob("*.sfz")):
            relative = sfz_file.relative_to(SONATINA_SSO_DIR)
            name = f"sonatina/{relative.with_suffix('')}"
            instruments.append(name)
            sonatina_count += 1
        logger.debug("Found %d Sonatina SSO instruments", sonatina_count)

    if not instruments:
        logger.warning("No SFZ instrument libraries found")

    return sorted(instruments)
