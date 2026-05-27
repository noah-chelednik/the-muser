"""Music notation format conversion utilities.

Provides conversion functions between ABC notation, MusicXML, MIDI, and
LilyPond formats using the ``music21`` library, plus MusicXML schema
validation via ``lxml``.

Known Limitations
-----------------
* The ``music21`` ABC parser is strict about headers.  Helper functions
  automatically inject missing ``X:`` (reference number) and ``M:``
  (meter) fields when they are absent, but highly unusual ABC dialects
  may still fail to parse.
* Round-tripping through MIDI is lossy — dynamics, articulations, text
  annotations, and precise rhythmic notation are not preserved.
* LilyPond export relies on ``music21``'s built-in converter, which may
  produce output that requires manual tweaks for publication-quality
  engraving.
* MusicXML validation downloads the schema on first use (cached
  afterwards).  If the schema URL is unreachable and no local copy
  exists, ``validate_musicxml`` returns a single-element list describing
  the connectivity error.

Usage::

    from src.notation.format_converter import abc_to_midi, validate_musicxml

    midi_path = abc_to_midi(abc_string, "/tmp/output.mid")
    errors = validate_musicxml("/tmp/score.musicxml")
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# MusicXML 4.0 schema URL (W3C-hosted).
_MUSICXML_SCHEMA_URL = "https://www.w3.org/2021/06/musicxml40/musicxml.xsd"

# ---------------------------------------------------------------------------
# ABC pre-processing helpers
# ---------------------------------------------------------------------------


def _ensure_abc_headers(abc_string: str) -> str:
    """Ensure the ABC string contains the minimum required headers.

    ``music21``'s ABC parser requires at least an ``X:`` (reference
    number) field and benefits from an explicit ``M:`` (meter).  This
    function prepends sensible defaults for any that are missing.

    Parameters
    ----------
    abc_string:
        Raw ABC notation string.

    Returns
    -------
    str
        ABC string guaranteed to start with ``X:`` and contain ``M:``.
    """
    lines = abc_string.strip().splitlines()
    header_keys = {line.split(":")[0].strip() for line in lines if ":" in line}

    preamble: list[str] = []
    if "X" not in header_keys:
        preamble.append("X:1")
    if "M" not in header_keys:
        preamble.append("M:4/4")
    # Ensure a default title and key if absent, as some parsers expect them.
    if "T" not in header_keys:
        preamble.append("T:Untitled")
    if "K" not in header_keys:
        preamble.append("K:C")

    if preamble:
        logger.debug(
            "Injected missing ABC headers: %s",
            ", ".join(preamble),
        )
        return "\n".join(preamble + lines)
    return abc_string


def _parse_abc(abc_string: str):
    """Parse an ABC string into a ``music21.stream.Score``.

    Applies header fixups and wraps parsing in error handling.

    Returns a ``music21.stream.Score``.

    Raises ``ValueError`` if parsing fails entirely.
    """
    from music21 import converter  # type: ignore[import-untyped]

    clean = _ensure_abc_headers(abc_string)

    try:
        score = converter.parse(clean, format="abc")
    except Exception as exc:
        raise ValueError(f"music21 failed to parse the ABC notation: {exc}") from exc

    return score


# ---------------------------------------------------------------------------
# Public conversion functions
# ---------------------------------------------------------------------------


def abc_to_musicxml(abc_string: str) -> str:
    """Convert an ABC notation string to a MusicXML string.

    Parameters
    ----------
    abc_string:
        ABC notation text.

    Returns
    -------
    str
        A complete MusicXML document as a string.

    Raises
    ------
    ValueError
        If the ABC cannot be parsed.
    RuntimeError
        If MusicXML serialisation fails.
    """
    score = _parse_abc(abc_string)

    try:
        from music21.musicxml import m21ToXml  # type: ignore[import-untyped]

        exporter = m21ToXml.GeneralObjectExporter(score)
        musicxml_bytes: bytes = exporter.parse()
        return musicxml_bytes.decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Failed to serialise score to MusicXML: {exc}") from exc


def abc_to_midi(abc_string: str, output_path: str) -> str:
    """Convert ABC notation to a MIDI file.

    Parameters
    ----------
    abc_string:
        ABC notation text.
    output_path:
        Destination file path for the MIDI file.

    Returns
    -------
    str
        The *output_path* on success (for convenient chaining).

    Raises
    ------
    ValueError
        If the ABC cannot be parsed.
    RuntimeError
        If MIDI writing fails.
    """
    score = _parse_abc(abc_string)

    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        score.write("midi", fp=str(out))
        logger.info("Wrote MIDI to %s", out)
        return str(out)
    except Exception as exc:
        raise RuntimeError(f"Failed to write MIDI file to {output_path}: {exc}") from exc


def musicxml_to_midi(musicxml_path: str, output_path: str) -> str:
    """Convert a MusicXML file to MIDI.

    Parameters
    ----------
    musicxml_path:
        Path to the source MusicXML file.
    output_path:
        Destination file path for the MIDI file.

    Returns
    -------
    str
        The *output_path* on success.

    Raises
    ------
    FileNotFoundError
        If *musicxml_path* does not exist.
    ValueError
        If the MusicXML cannot be parsed.
    RuntimeError
        If MIDI writing fails.
    """
    from music21 import converter  # type: ignore[import-untyped]

    src = Path(musicxml_path)
    if not src.exists():
        raise FileNotFoundError(f"MusicXML file not found: {musicxml_path}")

    try:
        score = converter.parse(str(src))
    except Exception as exc:
        raise ValueError(f"music21 failed to parse MusicXML at {musicxml_path}: {exc}") from exc

    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        score.write("midi", fp=str(out))
        logger.info("Converted %s -> %s (MIDI)", musicxml_path, out)
        return str(out)
    except Exception as exc:
        raise RuntimeError(f"Failed to write MIDI file to {output_path}: {exc}") from exc


def musicxml_to_lilypond(musicxml_path: str, output_path: str) -> str:
    """Convert a MusicXML file to LilyPond format.

    Parameters
    ----------
    musicxml_path:
        Path to the source MusicXML file.
    output_path:
        Destination file path for the ``.ly`` file.

    Returns
    -------
    str
        The *output_path* on success.

    Raises
    ------
    FileNotFoundError
        If *musicxml_path* does not exist.
    ValueError
        If the MusicXML cannot be parsed.
    RuntimeError
        If LilyPond export fails.

    Notes
    -----
    The output may require manual editing for publication-quality scores.
    ``music21``'s LilyPond exporter covers standard notation well but may
    not handle every advanced MusicXML feature (e.g. complex tuplet
    nesting, ossia staves).
    """
    from music21 import converter  # type: ignore[import-untyped]

    src = Path(musicxml_path)
    if not src.exists():
        raise FileNotFoundError(f"MusicXML file not found: {musicxml_path}")

    try:
        score = converter.parse(str(src))
    except Exception as exc:
        raise ValueError(f"music21 failed to parse MusicXML at {musicxml_path}: {exc}") from exc

    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        score.write("lilypond", fp=str(out))
        logger.info("Converted %s -> %s (LilyPond)", musicxml_path, out)
        return str(out)
    except Exception as exc:
        raise RuntimeError(f"Failed to write LilyPond file to {output_path}: {exc}") from exc


def midi_to_musicxml(midi_path: str) -> str:
    """Convert a MIDI file to a MusicXML string.

    Parameters
    ----------
    midi_path:
        Path to the source MIDI file.

    Returns
    -------
    str
        A MusicXML document as a string.

    Raises
    ------
    FileNotFoundError
        If *midi_path* does not exist.
    ValueError
        If the MIDI file cannot be parsed.
    RuntimeError
        If MusicXML serialisation fails.

    Notes
    -----
    MIDI-to-notation conversion is inherently lossy.  Quantisation
    artefacts and missing key / time-signature information may produce
    unexpected results.  Consider post-processing the returned MusicXML
    with ``music21`` stream operations for better notation quality.
    """
    from music21 import converter  # type: ignore[import-untyped]

    src = Path(midi_path)
    if not src.exists():
        raise FileNotFoundError(f"MIDI file not found: {midi_path}")

    try:
        score = converter.parse(str(src))
    except Exception as exc:
        raise ValueError(f"music21 failed to parse MIDI at {midi_path}: {exc}") from exc

    try:
        from music21.musicxml import m21ToXml  # type: ignore[import-untyped]

        exporter = m21ToXml.GeneralObjectExporter(score)
        musicxml_bytes: bytes = exporter.parse()
        return musicxml_bytes.decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Failed to serialise MIDI-derived score to MusicXML: {exc}") from exc


def validate_musicxml(musicxml_path: str) -> list[str]:
    """Validate a MusicXML file against the official MusicXML 4.0 schema.

    Parameters
    ----------
    musicxml_path:
        Path to the MusicXML file to validate.

    Returns
    -------
    list[str]
        A list of validation error messages.  An empty list means the
        document is valid.

    Notes
    -----
    Requires the ``lxml`` package.  On the first invocation the W3C
    MusicXML schema is fetched from the network and cached in a temporary
    directory.  Subsequent calls within the same process re-use the
    cached schema.  If the schema cannot be retrieved, the function
    returns a single-element list describing the connectivity error
    rather than raising.
    """
    src = Path(musicxml_path)
    if not src.exists():
        return [f"File not found: {musicxml_path}"]

    try:
        from lxml import etree  # type: ignore[import-untyped]
    except ImportError:
        return [
            "lxml is not installed; MusicXML schema validation is unavailable. "
            "Install it with: pip install lxml"
        ]

    # -- Load or cache the XSD schema --------------------------------------
    schema = _get_cached_schema()
    if schema is None:
        return [
            "Could not retrieve the MusicXML 4.0 schema for validation. "
            "Check your network connection or provide a local schema copy."
        ]

    # -- Parse and validate -------------------------------------------------
    errors: list[str] = []

    try:
        doc = etree.parse(str(src))
    except etree.XMLSyntaxError as exc:
        return [f"XML syntax error: {exc}"]

    if not schema.validate(doc):
        for err in schema.error_log:
            errors.append(f"Line {err.line}: {err.message}")

    return errors


# ---------------------------------------------------------------------------
# Schema caching helper
# ---------------------------------------------------------------------------

_schema_cache: object | None = None  # lxml.etree.XMLSchema once loaded


def _get_cached_schema():
    """Return a cached ``lxml.etree.XMLSchema`` for MusicXML 4.0.

    Returns ``None`` if the schema could not be fetched or parsed.
    """
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache

    try:
        from lxml import etree  # type: ignore[import-untyped]
        import urllib.request

        # Check for a local cached copy first.
        cache_dir = Path(tempfile.gettempdir()) / "muser_schemas"
        cache_file = cache_dir / "musicxml40.xsd"

        if cache_file.exists():
            logger.debug("Using cached MusicXML schema at %s", cache_file)
            schema_doc = etree.parse(str(cache_file))
        else:
            logger.info("Downloading MusicXML 4.0 schema from %s", _MUSICXML_SCHEMA_URL)
            response = urllib.request.urlopen(_MUSICXML_SCHEMA_URL, timeout=30)
            xsd_bytes = response.read()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(xsd_bytes)
            schema_doc = etree.parse(str(cache_file))

        _schema_cache = etree.XMLSchema(schema_doc)
        return _schema_cache

    except Exception as exc:
        logger.warning("Failed to load MusicXML schema: %s", exc)
        return None
