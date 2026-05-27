"""Score rendering to PDF, PNG, and MIDI via LilyPond and MuseScore.

All GPL tools (LilyPond, MuseScore) are invoked as subprocesses only,
maintaining license isolation from the MIT-licensed orchestration code.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from src.orchestrator.config import LILYPOND_TIMEOUT, MUSESCORE_TIMEOUT

logger = logging.getLogger(__name__)


def _validate_input(path: str) -> Path:
    """Validate that the input file exists and return it as a Path."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    return p


def _ensure_output_dir(path: str) -> Path:
    """Ensure the output directory exists and return the path as a Path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _find_musescore() -> str:
    """Locate the MuseScore executable, preferring musescore3.

    Returns:
        The name of the MuseScore executable found on PATH.

    Raises:
        FileNotFoundError: If neither musescore3 nor musescore is found.
    """
    if shutil.which("musescore3"):
        return "musescore3"
    if shutil.which("musescore"):
        return "musescore"
    raise FileNotFoundError(
        "MuseScore not found. Install musescore3 or musescore and ensure it is on PATH."
    )


def render_pdf_lilypond(musicxml_path: str, output_path: str) -> str:
    """Render a MusicXML file to PDF via LilyPond.

    Converts MusicXML to LilyPond format using ``musicxml2ly``, then
    compiles the ``.ly`` file to PDF with ``lilypond --pdf``.

    Args:
        musicxml_path: Path to the input MusicXML file.
        output_path: Desired path for the output PDF file.

    Returns:
        The absolute path to the generated PDF file.

    Raises:
        FileNotFoundError: If the input file does not exist or required
            tools are missing.
        subprocess.CalledProcessError: If musicxml2ly or lilypond fails.
        subprocess.TimeoutExpired: If the process exceeds LILYPOND_TIMEOUT.
    """
    input_path = _validate_input(musicxml_path)
    out = _ensure_output_dir(output_path)

    from src.orchestrator.config import LILYPOND_PATH
    lilypond_bin = shutil.which(LILYPOND_PATH) or shutil.which("lilypond")
    # musicxml2ly lives alongside lilypond in the same directory
    musicxml2ly_bin = None
    if lilypond_bin:
        candidate = Path(lilypond_bin).parent / "musicxml2ly"
        if candidate.is_file():
            musicxml2ly_bin = str(candidate)
    if not musicxml2ly_bin:
        musicxml2ly_bin = shutil.which("musicxml2ly")
    if not musicxml2ly_bin:
        raise FileNotFoundError(
            "musicxml2ly not found. Install LilyPond and ensure it is on PATH, "
            "or set MUSER_LILYPOND_PATH."
        )
    if not lilypond_bin:
        raise FileNotFoundError(
            "lilypond not found. Install LilyPond and ensure it is on PATH, "
            "or set MUSER_LILYPOND_PATH."
        )

    # Step 1: Convert MusicXML -> LilyPond .ly
    ly_path = out.with_suffix(".ly")
    logger.info("Converting MusicXML to LilyPond: %s -> %s", input_path, ly_path)

    try:
        subprocess.run(
            [musicxml2ly_bin, "--output", str(ly_path), str(input_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=LILYPOND_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("musicxml2ly failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("musicxml2ly timed out after %d seconds", LILYPOND_TIMEOUT)
        raise

    if not ly_path.is_file():
        raise RuntimeError(f"musicxml2ly did not produce expected output: {ly_path}")

    # Step 2: Compile .ly -> PDF
    logger.info("Compiling LilyPond to PDF: %s -> %s", ly_path, out)

    try:
        subprocess.run(
            [
                lilypond_bin,
                "--pdf",
                f"--output={out.with_suffix('')}",
                str(ly_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=LILYPOND_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("lilypond failed (rc=%d): %s", exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("lilypond timed out after %d seconds", LILYPOND_TIMEOUT)
        raise

    if not out.is_file():
        raise RuntimeError(f"LilyPond did not produce expected PDF: {out}")

    logger.info("PDF rendered successfully: %s", out)
    return str(out.resolve())


def render_pdf_musescore(musicxml_path: str, output_path: str) -> str:
    """Render a MusicXML file to PDF via MuseScore.

    Args:
        musicxml_path: Path to the input MusicXML file.
        output_path: Desired path for the output PDF file.

    Returns:
        The absolute path to the generated PDF file.

    Raises:
        FileNotFoundError: If the input file or MuseScore is not found.
        subprocess.CalledProcessError: If MuseScore fails.
        subprocess.TimeoutExpired: If the process exceeds MUSESCORE_TIMEOUT.
    """
    input_path = _validate_input(musicxml_path)
    out = _ensure_output_dir(output_path)
    mscore = _find_musescore()

    logger.info("Rendering PDF via %s: %s -> %s", mscore, input_path, out)

    try:
        subprocess.run(
            [mscore, "-o", str(out), str(input_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=MUSESCORE_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("%s failed (rc=%d): %s", mscore, exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("%s timed out after %d seconds", mscore, MUSESCORE_TIMEOUT)
        raise

    if not out.is_file():
        raise RuntimeError(f"MuseScore did not produce expected PDF: {out}")

    logger.info("PDF rendered successfully: %s", out)
    return str(out.resolve())


def render_midi(musicxml_path: str, output_path: str) -> str:
    """Convert a MusicXML file to MIDI using music21.

    This is a pure-Python operation with no subprocess dependency.

    Args:
        musicxml_path: Path to the input MusicXML file.
        output_path: Desired path for the output MIDI file.

    Returns:
        The absolute path to the generated MIDI file.

    Raises:
        FileNotFoundError: If the input file does not exist.
        Exception: If music21 parsing or MIDI writing fails.
    """
    import music21

    input_path = _validate_input(musicxml_path)
    out = _ensure_output_dir(output_path)

    logger.info("Converting MusicXML to MIDI: %s -> %s", input_path, out)

    score = music21.converter.parse(str(input_path))
    score.write("midi", fp=str(out))

    if not out.is_file():
        raise RuntimeError(f"music21 did not produce expected MIDI file: {out}")

    logger.info("MIDI written successfully: %s (%d bytes)", out, out.stat().st_size)
    return str(out.resolve())


def render_png_musescore(musicxml_path: str, output_path: str) -> str:
    """Render a MusicXML file to PNG image(s) via MuseScore.

    MuseScore generates one PNG per page.  For multi-page scores the
    output filename is suffixed with page numbers (e.g. ``output-1.png``).
    This function returns the path as given; callers should glob for
    additional pages if needed.

    Args:
        musicxml_path: Path to the input MusicXML file.
        output_path: Desired path for the output PNG file.

    Returns:
        The absolute path to the (first) generated PNG file.

    Raises:
        FileNotFoundError: If the input file or MuseScore is not found.
        subprocess.CalledProcessError: If MuseScore fails.
        subprocess.TimeoutExpired: If the process exceeds MUSESCORE_TIMEOUT.
    """
    input_path = _validate_input(musicxml_path)
    out = _ensure_output_dir(output_path)
    mscore = _find_musescore()

    logger.info("Rendering PNG via %s: %s -> %s", mscore, input_path, out)

    try:
        subprocess.run(
            [mscore, "-o", str(out), str(input_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=MUSESCORE_TIMEOUT,
        )
    except subprocess.CalledProcessError as exc:
        logger.error("%s failed (rc=%d): %s", mscore, exc.returncode, exc.stderr)
        raise
    except subprocess.TimeoutExpired:
        logger.error("%s timed out after %d seconds", mscore, MUSESCORE_TIMEOUT)
        raise

    # MuseScore may produce output-1.png instead of output.png for the first page.
    if not out.is_file():
        stem = out.stem
        numbered = out.parent / f"{stem}-1.png"
        if numbered.is_file():
            logger.info("PNG rendered (multi-page, first page): %s", numbered)
            return str(numbered.resolve())
        raise RuntimeError(f"MuseScore did not produce expected PNG: {out}")

    logger.info("PNG rendered successfully: %s", out)
    return str(out.resolve())
