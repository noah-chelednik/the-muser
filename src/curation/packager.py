"""Phase 9: Platform packaging — upload-ready folders with copy-paste guides."""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path

from .models import (
    PipelineConfig,
    TrackMetadata,
    TrackSelection,
)
from .metadata import GENRE_DISPLAY

log = logging.getLogger(__name__)


def package_all(
    selections: dict[str, TrackSelection],
    metadata: dict[str, TrackMetadata],
    mastered_paths: dict[str, str],
    output_dir: Path,
    config: PipelineConfig,
) -> dict:
    """Create upload-ready folder structures for all platforms.

    Returns a summary dict for the HTML report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {}

    summary["distrokid"] = _package_distrokid(
        selections, metadata, mastered_paths, output_dir / "distrokid", config
    )
    summary["gumroad"] = _package_gumroad(
        selections, metadata, mastered_paths, output_dir / "gumroad", config
    )
    summary["fiverr"] = _package_fiverr(
        selections, metadata, mastered_paths, output_dir / "fiverr", config
    )
    summary["kofi"] = _package_kofi(
        selections, metadata, mastered_paths, output_dir / "kofi", config
    )

    log.info("Packaging complete.")
    return summary


# ---------------------------------------------------------------------------
# DistroKid
# ---------------------------------------------------------------------------


def _package_distrokid(
    selections: dict[str, TrackSelection],
    metadata: dict[str, TrackMetadata],
    mastered_paths: dict[str, str],
    dk_dir: Path,
    config: PipelineConfig,
) -> dict:
    dk_dir.mkdir(parents=True, exist_ok=True)
    max_per_album = config.packaging.get("distrokid_max_per_album", 35)

    # Group by genre
    by_genre: dict[str, list[TrackMetadata]] = {}
    for tid, meta in sorted(metadata.items(), key=lambda x: -x[1].composite_score):
        if tid not in mastered_paths:
            continue
        by_genre.setdefault(meta.genre_primary, []).append(meta)

    albums = []
    for genre, tracks in by_genre.items():
        display = GENRE_DISPLAY.get(genre, genre.replace("_", " ").title())
        # Split into volumes
        for vol_idx in range(0, len(tracks), max_per_album):
            chunk = tracks[vol_idx : vol_idx + max_per_album]
            vol_num = vol_idx // max_per_album + 1
            vol_suffix = f" Vol. {vol_num}" if len(tracks) > max_per_album else ""
            album_title = f"{display} Collection{vol_suffix}"
            safe_name = album_title.replace(" ", "_").replace("/", "-")

            album_dir = dk_dir / safe_name
            album_dir.mkdir(parents=True, exist_ok=True)

            # Copy WAVs with numbered filenames
            for idx, meta in enumerate(chunk, 1):
                src = Path(mastered_paths[meta.track_id])
                dst = album_dir / f"{idx:02d}_{_safe(meta.title)}.wav"
                if src.exists():
                    shutil.copy2(src, dst)

            # Write upload guide
            _write_distrokid_guide(album_dir, album_title, genre, display, chunk, config)

            # Write machine-readable metadata
            album_meta = {
                "album_title": album_title,
                "artist": config.artist_name,
                "genre": display,
                "track_count": len(chunk),
                "tracks": [
                    {
                        "index": i + 1,
                        "filename": f"{i + 1:02d}_{_safe(m.title)}.wav",
                        "title": m.title,
                        "duration": m.duration_formatted,
                        "bpm": m.bpm,
                        "key": m.key,
                    }
                    for i, m in enumerate(chunk)
                ],
            }
            with open(album_dir / "album_metadata.json", "w") as f:
                json.dump(album_meta, f, indent=2)

            albums.append({"title": album_title, "genre": genre, "tracks": len(chunk)})

    log.info("DistroKid: %d albums packaged.", len(albums))
    return {"albums": albums, "total_tracks": sum(a["tracks"] for a in albums)}


def _write_distrokid_guide(
    album_dir: Path,
    album_title: str,
    genre: str,
    display_genre: str,
    tracks: list[TrackMetadata],
    config: PipelineConfig,
) -> None:
    lines = [
        "=" * 50,
        "DISTROKID UPLOAD GUIDE",
        "=" * 50,
        "",
        f"Album: {album_title}",
        f"Artist: {config.artist_name}",
        f"Genre (primary): {display_genre}",
        "Release type: Album",
        "Release date: Earliest available",
        "Content ID: YES (enable)",
        "AI disclosure: YES (mark as AI-assisted)",
        "",
        "Track listing:",
    ]
    for i, m in enumerate(tracks, 1):
        mood = ", ".join(m.mood_tags[:3]) if m.mood_tags else genre
        lines.append(f"  {i:02d}. {m.title} ({m.duration_formatted}) — {mood}")

    lines += [
        "",
        "Steps:",
        "  1. Go to distrokid.com/new",
        "  2. Select 'Album'",
        f"  3. Artist: {config.artist_name}",
        f"  4. Album title: {album_title}",
        f"  5. Genre: {display_genre}",
        "  6. Drag all .wav files from this folder",
        "  7. Verify track titles match list above",
        "  8. Enable Content ID",
        "  9. Check AI-assisted box",
        "  10. Upload artwork (use shared cover image)",
        "  11. Submit",
        "",
        "=" * 50,
    ]
    (album_dir / "UPLOAD_GUIDE.txt").write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Gumroad
# ---------------------------------------------------------------------------


def _package_gumroad(
    selections: dict[str, TrackSelection],
    metadata: dict[str, TrackMetadata],
    mastered_paths: dict[str, str],
    gm_dir: Path,
    config: PipelineConfig,
) -> dict:
    gm_dir.mkdir(parents=True, exist_ok=True)
    min_pack = config.packaging.get("gumroad_min_pack_size", 8)

    # Group by genre
    by_genre: dict[str, list[TrackMetadata]] = {}
    for tid, meta in sorted(metadata.items(), key=lambda x: -x[1].composite_score):
        if tid not in mastered_paths:
            continue
        by_genre.setdefault(meta.genre_primary, []).append(meta)

    packs = []
    for genre, tracks in by_genre.items():
        if len(tracks) < min_pack:
            log.info("Gumroad: skipping %s (%d tracks, min %d)", genre, len(tracks), min_pack)
            continue

        display = GENRE_DISPLAY.get(genre, genre.replace("_", " ").title())
        price = config.pack_prices.get(genre, 19)
        pack_title = f"Royalty-Free {display} Pack — {len(tracks)} Tracks"
        safe_name = f"{genre}_pack"

        pack_dir = gm_dir / safe_name
        pack_dir.mkdir(parents=True, exist_ok=True)

        # Build ZIP with WAV + MP3
        zip_name = f"{safe_name}.zip"
        zip_path = pack_dir / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, meta in enumerate(tracks, 1):
                wav_src = Path(mastered_paths[meta.track_id])
                mp3_src = wav_src.with_suffix(".mp3")
                fname = f"{i:02d}_{_safe(meta.title)}"
                if wav_src.exists():
                    zf.write(wav_src, f"WAV/{fname}.wav")
                if mp3_src.exists():
                    zf.write(mp3_src, f"MP3/{fname}.mp3")
            # License file
            zf.writestr("LICENSE.txt", _license_text(config))
            # Track list
            zf.writestr("TRACK_LIST.txt", _track_list_text(tracks))

        # Write listing guide
        _write_gumroad_listing(
            pack_dir, pack_title, display, genre, price, tracks, zip_name, config
        )

        # Machine-readable
        pack_meta = {
            "title": pack_title,
            "genre": genre,
            "price_usd": price,
            "zip_filename": zip_name,
            "track_count": len(tracks),
            "tags": [
                genre,
                "royalty free",
                "background music",
                display.lower(),
                "instrumental",
                "ai music",
            ],
        }
        with open(pack_dir / "metadata.json", "w") as f:
            json.dump(pack_meta, f, indent=2)

        packs.append({"title": pack_title, "genre": genre, "tracks": len(tracks), "price": price})

    log.info("Gumroad: %d packs packaged.", len(packs))
    return {"packs": packs, "total_tracks": sum(p["tracks"] for p in packs)}


def _write_gumroad_listing(
    pack_dir: Path,
    title: str,
    display: str,
    genre: str,
    price: int,
    tracks: list[TrackMetadata],
    zip_name: str,
    config: PipelineConfig,
) -> None:
    desc = (
        f"{len(tracks)} original {display.lower()} tracks, perfect for films, "
        f"YouTube videos, podcasts, games, and presentations.\n"
        f"\n"
        f"Includes:\n"
        f"- {len(tracks)} tracks in WAV (44.1kHz/16-bit) + MP3 (320kbps)\n"
        f"- Durations: 30 seconds to 5 minutes\n"
        f"- All tracks mastered to streaming standard\n"
        f"\n"
        f"License: Royalty-free for personal and commercial use. "
        f"No resale of tracks as standalone music. Full license terms included.\n"
        f"\n"
        f"Created with AI-assisted composition tools."
    )
    tags_str = ", ".join(
        [genre, "royalty free", "background music", display.lower(), "instrumental"]
    )

    lines = [
        "=" * 50,
        "GUMROAD LISTING",
        "=" * 50,
        "",
        f"Product title: {title}",
        f"Price: ${price}",
        f"Tags: {tags_str}",
        "",
        "Description (paste this):",
        "---",
        desc,
        "---",
        "",
        "Steps:",
        "  1. Go to gumroad.com → Dashboard → New Product",
        "  2. Type: Digital product",
        "  3. Title: [paste from above]",
        f"  4. Price: ${price}",
        f"  5. Upload: {zip_name}",
        "  6. Description: [paste from above]",
        "  7. Tags: [paste from above]",
        "  8. Publish",
        "",
        "=" * 50,
    ]
    (pack_dir / "LISTING.txt").write_text("\n".join(lines))
    (pack_dir / "track_list.txt").write_text(_track_list_text(tracks))


# ---------------------------------------------------------------------------
# Fiverr
# ---------------------------------------------------------------------------


def _package_fiverr(
    selections: dict[str, TrackSelection],
    metadata: dict[str, TrackMetadata],
    mastered_paths: dict[str, str],
    fv_dir: Path,
    config: PipelineConfig,
) -> dict:
    fv_dir.mkdir(parents=True, exist_ok=True)
    demos_dir = fv_dir / "demos"
    demos_dir.mkdir(parents=True, exist_ok=True)

    per_genre = config.packaging.get("fiverr_demos_per_genre", 3)
    max_demos = config.packaging.get("fiverr_max_demos", 15)

    # Pick top N per major genre
    major_genres = ["cinematic", "pop", "lofi", "electronic", "rock", "ambient", "rnb"]
    by_genre: dict[str, list[TrackMetadata]] = {}
    for tid, meta in sorted(metadata.items(), key=lambda x: -x[1].composite_score):
        if tid not in mastered_paths:
            continue
        by_genre.setdefault(meta.genre_primary, []).append(meta)

    demos = []
    for genre in major_genres:
        tracks = by_genre.get(genre, [])[:per_genre]
        for i, meta in enumerate(tracks, 1):
            if len(demos) >= max_demos:
                break
            mp3_src = Path(mastered_paths[meta.track_id]).with_suffix(".mp3")
            if mp3_src.exists():
                dst = demos_dir / f"best_{genre}_{i}.mp3"
                shutil.copy2(mp3_src, dst)
                demos.append({"genre": genre, "title": meta.title, "file": dst.name})

    # Write gig setup guide
    _write_fiverr_guide(fv_dir, config)

    log.info("Fiverr: %d demo tracks packaged.", len(demos))
    return {"demos": demos, "total": len(demos)}


def _write_fiverr_guide(fv_dir: Path, config: PipelineConfig) -> None:
    guide = f"""{"=" * 50}
FIVERR GIG SETUP GUIDE
{"=" * 50}

GIG 1: Custom Background Music
  Title: I will compose custom background music for your video
  Category: Music & Audio > Music Production
  Pricing:
    Basic ($35): 30 seconds, 1 revision, 24hr delivery
    Standard ($75): 60 seconds, 2 revisions, 24hr delivery
    Premium ($150): 3+ minutes, 3 revisions, 48hr delivery
  Tags: background music, custom music, YouTube music, video music
  Attach demos: best_cinematic_1.mp3, best_pop_1.mp3

  Description (paste this):
  ---
  Professional custom music for your project. Using cutting-edge AI
  composition tools with human creative direction, I deliver original,
  unique tracks tailored to your exact needs. 24-hour turnaround on
  most orders.

  What you get:
  - Original composition matching your mood/genre/tempo requirements
  - Mastered WAV + MP3 delivery
  - Royalty-free commercial license
  - Fast revisions

  Genres: cinematic, pop, lo-fi, electronic, rock, ambient, classical, R&B

  FAQ:
  Q: Is this AI-generated?
  A: I use AI tools for composition and production, with human creative
     direction for every track. Each piece is original and made to order.
  ---

GIG 2: Cinematic Trailer Music
  Title: I will create cinematic trailer music for your project
  Category: Music & Audio > Music Production
  Pricing:
    Basic ($50): 30 seconds, 1 revision, 24hr delivery
    Standard ($100): 60 seconds, 2 revisions, 24hr delivery
    Premium ($200): 2+ minutes, 3 revisions, 48hr delivery
  Tags: trailer music, cinematic, epic music, film score
  Attach demos: best_cinematic_1.mp3, best_cinematic_2.mp3

  Description (paste this):
  ---
  Epic cinematic and trailer music for your film, game, advertisement,
  or YouTube project. Custom-composed to match your vision with
  24-hour turnaround.

  Includes:
  - Original orchestral/cinematic composition
  - Mastered WAV + MP3
  - Royalty-free commercial license
  ---

GIG 3: Lo-Fi Beats & Chill Music
  Title: I will produce lo-fi beats and chill music
  Category: Music & Audio > Music Production
  Pricing:
    Basic ($25): 1 track, 60 seconds, 24hr delivery
    Standard ($50): 1 track, 2-3 minutes, 24hr delivery
    Premium ($100): 3 tracks, 2-3 minutes each, 48hr delivery
  Tags: lo-fi, chill beats, study music, ambient
  Attach demos: best_lofi_1.mp3, best_ambient_1.mp3

  Description (paste this):
  ---
  Chill lo-fi beats and ambient music for study, relaxation, podcasts,
  and content creation. Warm, nostalgic tones with modern production.

  Includes:
  - Original lo-fi/ambient composition
  - Mastered WAV + MP3
  - Royalty-free commercial license
  ---

{"=" * 50}
"""
    (fv_dir / "GIG_SETUP.txt").write_text(guide)


# ---------------------------------------------------------------------------
# Ko-fi
# ---------------------------------------------------------------------------


def _package_kofi(
    selections: dict[str, TrackSelection],
    metadata: dict[str, TrackMetadata],
    mastered_paths: dict[str, str],
    kf_dir: Path,
    config: PipelineConfig,
) -> dict:
    kf_dir.mkdir(parents=True, exist_ok=True)
    singles_dir = kf_dir / "singles"
    singles_dir.mkdir(parents=True, exist_ok=True)

    max_singles = config.packaging.get("kofi_max_singles", 20)

    # Top tracks by composite score
    sorted_meta = sorted(metadata.values(), key=lambda m: -m.composite_score)
    singles = []
    for meta in sorted_meta[:max_singles]:
        if meta.track_id not in mastered_paths:
            continue
        mp3_src = Path(mastered_paths[meta.track_id]).with_suffix(".mp3")
        if mp3_src.exists():
            dst = singles_dir / f"{_safe(meta.title)}.mp3"
            shutil.copy2(mp3_src, dst)
            singles.append(
                {
                    "title": meta.title,
                    "file": dst.name,
                    "genre": meta.genre_primary,
                    "price": 4,
                }
            )

    # Write listing guide
    _write_kofi_guide(kf_dir, singles, config)

    log.info("Ko-fi: %d singles packaged.", len(singles))
    return {"singles": singles, "total": len(singles)}


def _write_kofi_guide(kf_dir: Path, singles: list[dict], config: PipelineConfig) -> None:
    lines = [
        "=" * 50,
        "KO-FI SHOP SETUP",
        "=" * 50,
        "",
        "Per-track listings (create one shop item each):",
        "",
    ]
    for i, s in enumerate(singles, 1):
        display = GENRE_DISPLAY.get(s["genre"], s["genre"].title())
        lines += [
            f"{i}. Title: {s['title']} — {display} Track",
            f"   Price: ${s['price']}",
            f"   Description: Original {display.lower()} track. Mastered WAV + MP3.",
            "   Royalty-free for personal and commercial use.",
            f"   File: {s['file']}",
            "",
        ]

    lines += [
        "",
        "Also list genre packs (use same ZIPs from gumroad/ folder):",
        "  - Copy each ZIP and listing from the gumroad/ directory",
        "  - Ko-fi takes 0% platform fee (better margins than Gumroad's 10%)",
        "",
        "=" * 50,
    ]
    (kf_dir / "LISTING.txt").write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe(title: str) -> str:
    s = title.replace(" ", "_")
    s = "".join(c for c in s if c.isalnum() or c in ("_", "-"))
    return s[:80] or "untitled"


def _license_text(config: PipelineConfig) -> str:
    return f"""ROYALTY-FREE MUSIC LICENSE
{"=" * 40}

Copyright {config.release_year} {config.copyright_holder}. All rights reserved.

LICENSE GRANT:
You are granted a non-exclusive, worldwide, perpetual license to use these
audio tracks in personal and commercial projects, including but not limited to:
- YouTube videos, podcasts, and social media content
- Films, documentaries, and advertisements
- Video games and applications
- Presentations and corporate videos
- Websites and online content

RESTRICTIONS:
- You may NOT resell, redistribute, or sublicense these tracks as standalone
  music files or as part of another music library or sample pack.
- You may NOT claim authorship or copyright of the original compositions.
- You may NOT use these tracks in a way that competes with the original sale.

ATTRIBUTION:
Attribution is appreciated but not required. If you choose to credit,
please use: "Music by {config.copyright_holder}"

AI DISCLOSURE:
These tracks were created with AI-assisted composition tools with human
creative direction.

This license is perpetual and irrevocable once purchased.
"""


def _track_list_text(tracks: list[TrackMetadata]) -> str:
    lines = ["TRACK LIST", "=" * 40, ""]
    for i, m in enumerate(tracks, 1):
        key_str = f", {m.key}" if m.key else ""
        bpm_str = f", {m.bpm} BPM" if m.bpm else ""
        mood = ", ".join(m.mood_tags[:3]) if m.mood_tags else ""
        lines.append(f"{i:02d}. {m.title} ({m.duration_formatted}{key_str}{bpm_str})")
        if mood:
            lines.append(f"    Mood: {mood}")
    return "\n".join(lines)
