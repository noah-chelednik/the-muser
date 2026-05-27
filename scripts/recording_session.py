#!/usr/bin/env python3
"""Interactive recording session manager for The Muser voice training.

Guides the user through recording a catalog of songs for voice model training.
Tracks progress across sessions, suggests optimal recording order (demanding
songs early, breathy songs later, grouped by register), and exports metadata
compatible with the voice preprocessing pipeline.

Usage::

    # Start or resume a recording session
    python scripts/recording_session.py start

    # Show recording progress
    python scripts/recording_session.py status

    # Export metadata for preprocessing pipeline
    python scripts/recording_session.py export --output training_data/recording_manifest.json
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table

try:
    import yaml
except ImportError:
    print(
        "PyYAML is required. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "training_data" / "song_catalog.yaml"
SESSIONS_DIR = PROJECT_ROOT / "training_data" / "recording_sessions"

console = Console()

# ---------------------------------------------------------------------------
# Energy ordering for recording schedule
# ---------------------------------------------------------------------------
ENERGY_ORDER = {"powerful": 0, "moderate": 1, "soft": 2}
REGISTER_ORDER = {"chest": 0, "mixed": 1, "head": 2, "falsetto": 3}


# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------


def load_catalog() -> list[dict[str, Any]]:
    """Load the song catalog from YAML, returning a flat list of songs."""
    if not CATALOG_PATH.exists():
        console.print(
            f"[red]Catalog not found:[/red] {CATALOG_PATH}\nCreate it first or check the path.",
        )
        raise SystemExit(1)

    with open(CATALOG_PATH, "r") as f:
        raw = yaml.safe_load(f)

    songs: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for category_name, category_songs in raw.items():
            if isinstance(category_songs, list):
                for song in category_songs:
                    song.setdefault("category", category_name)
                    songs.append(song)
    elif isinstance(raw, list):
        songs = raw
    else:
        console.print("[red]Unexpected catalog format.[/red]")
        raise SystemExit(1)

    return songs


def song_id(song: dict) -> str:
    """Generate a stable unique identifier for a song."""
    title = song.get("title", "").strip().lower()
    artist = song.get("artist", "").strip().lower()
    return f"{title}|{artist}"


def sort_for_recording(songs: list[dict]) -> list[dict]:
    """Sort songs into optimal recording order.

    Strategy:
      1. Demanding (powerful/chest) songs first while voice is fresh.
      2. Group by register so the vocalist stays in one area longer.
      3. Breathy / soft / falsetto songs toward the end.
    """

    def sort_key(s: dict) -> tuple:
        energy = ENERGY_ORDER.get(s.get("energy", "moderate"), 1)
        register = REGISTER_ORDER.get(s.get("register", "mixed"), 1)
        # Within same energy, group by register
        return (energy, register, s.get("title", ""))

    return sorted(songs, key=sort_key)


# ---------------------------------------------------------------------------
# Session state management
# ---------------------------------------------------------------------------


def _list_session_files() -> list[Path]:
    """Return session JSON files sorted by number."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SESSIONS_DIR.glob("session_*.json"))
    return files


def _next_session_number() -> int:
    """Return the next session number."""
    files = _list_session_files()
    if not files:
        return 1
    last = files[-1].stem  # e.g. "session_005"
    try:
        return int(last.split("_")[1]) + 1
    except (IndexError, ValueError):
        return len(files) + 1


def _load_latest_session() -> dict | None:
    """Load the latest session file, or None if no sessions exist."""
    files = _list_session_files()
    if not files:
        return None
    with open(files[-1], "r") as f:
        return json.load(f)


def _save_session(session: dict) -> Path:
    """Save session state to its JSON file."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    num = session["session_number"]
    path = SESSIONS_DIR / f"session_{num:03d}.json"
    with open(path, "w") as f:
        json.dump(session, f, indent=2, default=str)
    return path


def load_all_recordings() -> dict[str, dict]:
    """Load all recordings across all sessions, keyed by song_id.

    If the same song was recorded in multiple sessions, the latest recording
    (highest session number) wins.
    """
    recordings: dict[str, dict] = {}
    for session_file in _list_session_files():
        with open(session_file, "r") as f:
            session = json.load(f)
        for rec in session.get("recordings", []):
            sid = rec.get("song_id", "")
            if sid:
                rec["session_number"] = session.get("session_number", 0)
                rec["session_date"] = session.get("start_time", "")
                recordings[sid] = rec
    return recordings


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _song_panel(song: dict, index: int, total: int) -> Panel:
    """Create a Rich panel displaying song info for the recording prompt."""
    energy_colors = {"powerful": "red", "moderate": "yellow", "soft": "green"}
    register_colors = {
        "chest": "blue",
        "mixed": "magenta",
        "head": "cyan",
        "falsetto": "bright_cyan",
    }

    energy = song.get("energy", "moderate")
    register = song.get("register", "mixed")
    duration_s = song.get("estimated_duration_s", 240)
    duration_m = duration_s // 60
    duration_rem = duration_s % 60

    content = (
        f"[bold]{song.get('title', 'Unknown')}[/bold]\n"
        f"Artist: {song.get('artist', 'Unknown')}\n"
        f"Original Key: [bold]{song.get('original_key', '?')}[/bold]\n"
        f"Genre: {song.get('genre', '?')}\n"
        f"Energy: [{energy_colors.get(energy, 'white')}]{energy}[/{energy_colors.get(energy, 'white')}]  |  "
        f"Register: [{register_colors.get(register, 'white')}]{register}[/{register_colors.get(register, 'white')}]\n"
        f"Estimated Duration: {duration_m}m {duration_rem:02d}s\n"
        f"\n[dim]{song.get('training_value', '')}[/dim]"
    )

    return Panel(
        content,
        title=f"Song {index}/{total} — {song.get('category', '?')}",
        border_style="blue",
    )


def _format_duration(seconds: float) -> str:
    """Format seconds as Hh Mm Ss."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    parts.append(f"{s:02d}s")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli():
    """The Muser -- Recording Session Manager.

    Interactive CLI tool to guide voice recording sessions for voice model
    training. Tracks progress, suggests recording order, and exports metadata.
    """
    pass


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--resume/--new",
    default=True,
    help="Resume latest incomplete session or force a new one.",
)
@click.option(
    "--category",
    "-c",
    default=None,
    help="Only record songs from this category.",
)
def start(resume: bool, category: str | None) -> None:
    """Start a new recording session (or resume the latest)."""
    catalog = load_catalog()
    all_recordings = load_all_recordings()

    # Filter to unrecorded songs (or allow re-recording)
    unrecorded = [s for s in catalog if song_id(s) not in all_recordings]

    if category:
        unrecorded = [s for s in unrecorded if s.get("category") == category]
        if not unrecorded:
            console.print(
                f"[yellow]All songs in category '{category}' have been recorded "
                f"(or category does not exist).[/yellow]"
            )
            # Offer to re-record
            re_record = [s for s in catalog if s.get("category") == category]
            if re_record:
                if click.confirm("Re-record songs in this category?"):
                    unrecorded = re_record
                else:
                    return
            else:
                return

    if not unrecorded:
        console.print(
            "[green]All songs in the catalog have been recorded![/green]\n"
            "Use [bold]status[/bold] to review or [bold]start --new[/bold] to re-record."
        )
        if click.confirm("Re-record all songs?"):
            unrecorded = catalog
        else:
            return

    # Sort for optimal recording order
    ordered = sort_for_recording(unrecorded)

    # Resume or create session
    latest = _load_latest_session() if resume else None
    if latest and not latest.get("completed", False):
        session = latest
        session_num = session["session_number"]
        console.print(
            f"[cyan]Resuming session {session_num} "
            f"(started {session.get('start_time', '?')})[/cyan]"
        )
        # Remove songs already recorded in this session
        recorded_ids = {r["song_id"] for r in session.get("recordings", [])}
        ordered = [s for s in ordered if song_id(s) not in recorded_ids]
    else:
        session_num = _next_session_number()
        session = {
            "session_number": session_num,
            "start_time": datetime.now().isoformat(),
            "recordings": [],
            "completed": False,
            "skipped": [],
            "notes": "",
        }

    now = datetime.now()
    session_start = time.monotonic()

    console.print(
        Panel(
            f"[bold]Recording Session #{session_num}[/bold]\n"
            f"Date: {now.strftime('%Y-%m-%d')}\n"
            f"Time: {now.strftime('%H:%M:%S')}\n"
            f"Songs queued: {len(ordered)}\n\n"
            "[dim]Commands during recording:[/dim]\n"
            "  [bold]s[/bold] — Skip this song\n"
            "  [bold]q[/bold] — Save and quit session\n"
            "  [bold]n[/bold] — Add a note to this session",
            title="Session Info",
            border_style="green",
        )
    )

    total = len(ordered)
    for idx, song in enumerate(ordered, 1):
        # Check session duration
        elapsed = time.monotonic() - session_start
        elapsed_min = elapsed / 60.0

        if elapsed_min >= 75.0:
            console.print(
                "\n[bold red]You have been recording for over 75 minutes.[/bold red]\n"
                "[yellow]Vocal fatigue can degrade training data quality. "
                "Strongly recommend taking a break now.[/yellow]"
            )
            if not click.confirm("Continue recording?", default=False):
                break
        elif elapsed_min >= 60.0:
            console.print(
                f"\n[yellow]Session duration: {_format_duration(elapsed)} — "
                "consider wrapping up soon to avoid vocal fatigue.[/yellow]"
            )

        # Display song info
        console.print()
        console.print(_song_panel(song, idx, total))

        # Prompt for action
        action = (
            console.input(
                "\n[bold]Record this song, [s]kip, [q]uit, or [n]ote? "
                "Press Enter when done recording:[/bold] "
            )
            .strip()
            .lower()
        )

        if action == "q":
            console.print("[dim]Saving session and exiting...[/dim]")
            break

        if action == "s":
            session["skipped"].append(
                {
                    "song_id": song_id(song),
                    "title": song.get("title", ""),
                    "reason": "user_skip",
                }
            )
            console.print(f"[dim]Skipped: {song.get('title', '')}[/dim]")
            _save_session(session)
            continue

        if action == "n":
            note = console.input("[bold]Session note:[/bold] ").strip()
            session["notes"] = (
                session.get("notes", "") + f"\n[{datetime.now().isoformat()}] {note}"
            ).strip()
            console.print("[dim]Note saved. Now record this song.[/dim]")
            console.input("[bold]Press Enter when done recording:[/bold] ")

        # Post-recording prompts
        console.print("\n[bold cyan]Post-recording feedback:[/bold cyan]")

        # Quality rating
        while True:
            rating_str = console.input("  Quality rating [bold](1-5, 5=excellent)[/bold]: ").strip()
            try:
                quality = int(rating_str)
                if 1 <= quality <= 5:
                    break
            except ValueError:
                pass
            console.print("  [red]Please enter a number 1-5.[/red]")

        # Actual register
        register_default = song.get("register", "mixed")
        register_input = (
            console.input(
                f"  Actual register used [bold](chest/mixed/head/falsetto)[/bold] "
                f"[{register_default}]: "
            )
            .strip()
            .lower()
        )
        actual_register = (
            register_input
            if register_input in ("chest", "mixed", "head", "falsetto")
            else register_default
        )

        # Key used
        original_key = song.get("original_key", "?")
        key_input = console.input(
            f"  Key used [bold](original={original_key})[/bold] "
            f"Enter semitones transposed or 0 for original [0]: "
        ).strip()
        try:
            semitones = int(key_input) if key_input else 0
        except ValueError:
            semitones = 0
        key_used = original_key if semitones == 0 else f"{original_key} {semitones:+d} semitones"

        # Notes
        rec_notes = console.input("  Notes (optional, press Enter to skip): ").strip()

        recording = {
            "song_id": song_id(song),
            "title": song.get("title", ""),
            "artist": song.get("artist", ""),
            "category": song.get("category", ""),
            "original_key": original_key,
            "key_used": key_used,
            "semitones_transposed": semitones,
            "register_expected": song.get("register", "mixed"),
            "register_actual": actual_register,
            "energy": song.get("energy", "moderate"),
            "quality_rating": quality,
            "estimated_duration_s": song.get("estimated_duration_s", 240),
            "recorded_at": datetime.now().isoformat(),
            "notes": rec_notes,
        }

        session["recordings"].append(recording)
        _save_session(session)

        console.print(
            f"  [green]Saved![/green] "
            f"({len(session['recordings'])} recorded this session, "
            f"{len(all_recordings) + len(session['recordings'])} total)"
        )

    # Finalize session
    session["end_time"] = datetime.now().isoformat()
    elapsed = time.monotonic() - session_start
    session["duration_s"] = round(elapsed, 1)
    session["completed"] = True
    path = _save_session(session)

    console.print(
        Panel(
            f"Session #{session_num} complete.\n"
            f"Duration: {_format_duration(elapsed)}\n"
            f"Songs recorded: {len(session['recordings'])}\n"
            f"Songs skipped: {len(session['skipped'])}\n"
            f"Saved to: {path}",
            title="Session Summary",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@cli.command()
def status() -> None:
    """Show recording progress summary."""
    catalog = load_catalog()
    all_recordings = load_all_recordings()

    total_songs = len(catalog)
    recorded_count = len(all_recordings)

    # Header
    console.print(
        Panel(
            f"[bold]Recording Progress[/bold]\n"
            f"Total songs in catalog: {total_songs}\n"
            f"Songs recorded: {recorded_count}\n"
            f"Songs remaining: {total_songs - recorded_count}",
            title="The Muser -- Voice Training Status",
            border_style="blue",
        )
    )

    # Progress bar
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Overall", total=total_songs, completed=recorded_count)

    # Category breakdown
    categories: dict[str, dict] = {}
    for song in catalog:
        cat = song.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"total": 0, "recorded": 0, "quality_sum": 0, "quality_count": 0}
        categories[cat]["total"] += 1
        sid = song_id(song)
        if sid in all_recordings:
            categories[cat]["recorded"] += 1
            q = all_recordings[sid].get("quality_rating", 0)
            if q > 0:
                categories[cat]["quality_sum"] += q
                categories[cat]["quality_count"] += 1

    table = Table(title="Progress by Category")
    table.add_column("Category", style="cyan")
    table.add_column("Recorded", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Progress", justify="right")
    table.add_column("Avg Quality", justify="right")
    table.add_column("Remaining Time (est)", justify="right")

    total_remaining_s = 0
    for cat_name in sorted(categories.keys()):
        info = categories[cat_name]
        pct = (info["recorded"] / info["total"] * 100) if info["total"] else 0
        avg_q = (
            f"{info['quality_sum'] / info['quality_count']:.1f}"
            if info["quality_count"] > 0
            else "-"
        )
        # Estimate remaining time from unrecorded songs
        remaining_s = sum(
            s.get("estimated_duration_s", 240)
            for s in catalog
            if s.get("category") == cat_name and song_id(s) not in all_recordings
        )
        total_remaining_s += remaining_s

        pct_style = "green" if pct == 100 else ("yellow" if pct >= 50 else "red")
        table.add_row(
            cat_name,
            str(info["recorded"]),
            str(info["total"]),
            f"[{pct_style}]{pct:.0f}%[/{pct_style}]",
            avg_q,
            _format_duration(remaining_s) if remaining_s > 0 else "[green]done[/green]",
        )

    console.print(table)
    console.print(
        f"\n[bold]Estimated total remaining time:[/bold] {_format_duration(total_remaining_s)}"
    )

    # Quality distribution
    if all_recordings:
        quality_dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rec in all_recordings.values():
            q = rec.get("quality_rating", 0)
            if q in quality_dist:
                quality_dist[q] += 1

        quality_table = Table(title="Quality Distribution")
        quality_table.add_column("Rating", justify="center")
        quality_table.add_column("Count", justify="right")
        quality_table.add_column("Bar", min_width=30)

        max_count = max(quality_dist.values()) if quality_dist.values() else 1
        rating_colors = {1: "red", 2: "bright_red", 3: "yellow", 4: "green", 5: "bright_green"}
        rating_labels = {
            1: "Poor",
            2: "Below Average",
            3: "Acceptable",
            4: "Good",
            5: "Excellent",
        }
        for rating in sorted(quality_dist.keys()):
            count = quality_dist[rating]
            bar_len = int((count / max_count) * 30) if max_count > 0 else 0
            color = rating_colors.get(rating, "white")
            bar = f"[{color}]{'=' * bar_len}[/{color}]"
            quality_table.add_row(
                f"{rating} ({rating_labels[rating]})",
                str(count),
                bar,
            )

        console.print()
        console.print(quality_table)

    # Session history
    session_files = _list_session_files()
    if session_files:
        console.print()
        session_table = Table(title="Session History")
        session_table.add_column("Session", justify="center")
        session_table.add_column("Date", style="cyan")
        session_table.add_column("Duration")
        session_table.add_column("Recorded", justify="right")
        session_table.add_column("Skipped", justify="right")

        for sf in session_files:
            with open(sf, "r") as f:
                sess = json.load(f)
            num = sess.get("session_number", "?")
            start_str = sess.get("start_time", "?")
            try:
                dt = datetime.fromisoformat(start_str)
                date_display = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date_display = start_str
            duration = sess.get("duration_s", 0)
            rec_count = len(sess.get("recordings", []))
            skip_count = len(sess.get("skipped", []))
            session_table.add_row(
                f"#{num}",
                date_display,
                _format_duration(duration) if duration else "-",
                str(rec_count),
                str(skip_count),
            )

        console.print(session_table)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--output",
    "-o",
    default=str(PROJECT_ROOT / "training_data" / "recording_manifest.json"),
    help="Output JSON file path.",
)
@click.option(
    "--min-quality",
    type=int,
    default=1,
    help="Only export recordings with quality >= this threshold (1-5).",
)
@click.option(
    "--raw-dir",
    default=str(PROJECT_ROOT / "training_data" / "raw"),
    help="Directory containing raw recording WAV files.",
)
def export(output: str, min_quality: int, raw_dir: str) -> None:
    """Export recorded song metadata for the voice preprocessing pipeline.

    Produces a JSON manifest compatible with scripts/preprocess_voice.py,
    containing paths, keys, registers, quality ratings, and training metadata
    for each recorded song.
    """
    catalog = load_catalog()
    all_recordings = load_all_recordings()

    if not all_recordings:
        console.print("[yellow]No recordings found. Run 'start' first.[/yellow]")
        return

    # Build song lookup
    catalog_by_id = {song_id(s): s for s in catalog}

    raw_path = Path(raw_dir)
    audio_exts = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}

    # Find available audio files
    available_audio: dict[str, str] = {}
    if raw_path.is_dir():
        for f in raw_path.rglob("*"):
            if f.suffix.lower() in audio_exts:
                available_audio[f.stem.lower()] = str(f)

    entries = []
    skipped = 0

    for sid, rec in sorted(all_recordings.items()):
        quality = rec.get("quality_rating", 0)
        if quality < min_quality:
            skipped += 1
            continue

        cat_song = catalog_by_id.get(sid, {})

        # Try to find matching audio file
        title_slug = (
            rec.get("title", "")
            .lower()
            .replace(" ", "_")
            .replace("'", "")
            .replace('"', "")
            .replace("(", "")
            .replace(")", "")
            .replace(",", "")
        )
        audio_path = available_audio.get(title_slug, "")

        entry = {
            "song_id": sid,
            "title": rec.get("title", ""),
            "artist": rec.get("artist", ""),
            "category": rec.get("category", ""),
            "genre": cat_song.get("genre", ""),
            "original_key": rec.get("original_key", ""),
            "key_used": rec.get("key_used", ""),
            "semitones_transposed": rec.get("semitones_transposed", 0),
            "register_expected": rec.get("register_expected", ""),
            "register_actual": rec.get("register_actual", ""),
            "energy": rec.get("energy", ""),
            "quality_rating": quality,
            "estimated_duration_s": rec.get("estimated_duration_s", 240),
            "training_value": cat_song.get("training_value", ""),
            "recorded_at": rec.get("recorded_at", ""),
            "session_number": rec.get("session_number", 0),
            "audio_path": audio_path,
            "notes": rec.get("notes", ""),
        }
        entries.append(entry)

    # Sort by category then title
    entries.sort(key=lambda e: (e["category"], e["title"]))

    # Compute summary stats
    categories_summary: dict[str, int] = {}
    quality_summary: dict[int, int] = {}
    for e in entries:
        cat = e["category"]
        categories_summary[cat] = categories_summary.get(cat, 0) + 1
        q = e["quality_rating"]
        quality_summary[q] = quality_summary.get(q, 0) + 1

    manifest = {
        "export_time": datetime.now().isoformat(),
        "total_recordings": len(entries),
        "min_quality_filter": min_quality,
        "skipped_below_quality": skipped,
        "raw_audio_dir": raw_dir,
        "categories": categories_summary,
        "quality_distribution": quality_summary,
        "recordings": entries,
    }

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(
        Panel(
            f"Exported [bold]{len(entries)}[/bold] recordings to:\n"
            f"  [cyan]{out_path}[/cyan]\n\n"
            f"Skipped (quality < {min_quality}): {skipped}\n"
            f"Audio files matched: {sum(1 for e in entries if e['audio_path'])}\n"
            f"Audio files missing: {sum(1 for e in entries if not e['audio_path'])}\n\n"
            "Next step:\n"
            f"  python scripts/preprocess_voice.py \\\n"
            f"    --input-dir {raw_dir} \\\n"
            f"    --voice-name noah",
            title="Export Complete",
            border_style="green",
        )
    )

    # Category breakdown
    table = Table(title="Exported by Category")
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")
    for cat_name in sorted(categories_summary.keys()):
        table.add_row(cat_name, str(categories_summary[cat_name]))
    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
