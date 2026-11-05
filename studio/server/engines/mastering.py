"""One-click Finish: mastering to each platform's loudness and true-peak target.

The chain (EQ, glue compression, colour, width) comes from a mastering preset;
the final loudness is reached by an iterative gain + true-peak limiter loop and
then *measured*, so the reported numbers are real, not assumed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from . import dsp, fx
from .loudness import integrated_lufs, true_peak_db


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    lufs: float
    true_peak_db: float
    note: str
    easy: bool = False


TARGETS: dict[str, Target] = {
    t.key: t
    for t in [
        Target(
            "spotify",
            "Spotify",
            -14.0,
            -1.0,
            "Spotify plays everything at about -14 LUFS. Peaks kept under -1 dBTP so the lossy encode stays clean.",
            True,
        ),
        Target(
            "youtube",
            "YouTube",
            -14.0,
            -1.0,
            "YouTube turns louder uploads down to about -14 LUFS, so there is no benefit in going louder.",
            True,
        ),
        Target(
            "soundcloud",
            "SoundCloud",
            -10.0,
            -1.0,
            "SoundCloud does not turn most tracks down, so a louder, competitive master works well. -1 dBTP avoids transcode crackle.",
            True,
        ),
        Target(
            "club",
            "Club / DJ",
            -8.0,
            -0.5,
            "Loud and dense for club systems and DJ sets. Use the WAV export for the booth.",
            True,
        ),
        Target(
            "apple", "Apple Music", -16.0, -1.0, "Apple Music Sound Check plays at about -16 LUFS."
        ),
        Target("tidal", "Tidal", -14.0, -1.0, "Tidal normalizes to about -14 LUFS."),
        Target(
            "amazon", "Amazon Music", -14.0, -2.0, "Amazon recommends -2 dBTP for its encoders."
        ),
        Target(
            "podcast", "Podcast / Spoken", -16.0, -1.0, "Common podcast spec (-16 LUFS stereo)."
        ),
        Target(
            "broadcast",
            "Broadcast (EBU R128)",
            -23.0,
            -1.0,
            "European TV and radio loudness standard.",
        ),
        Target("cd", "CD / Loud master", -9.0, -0.3, "Classic loud master for CD or downloads."),
    ]
}

TOLERANCE_LU = 0.5


def finish(
    x: np.ndarray,
    sr: int,
    target: str | Target = "spotify",
    chain: list[dict] | None = None,
    lufs: float | None = None,
    true_peak: float | None = None,
    max_iter: int = 6,
) -> tuple[np.ndarray, dict]:
    """Master ``x`` to a platform target. Returns (audio, report)."""
    t = TARGETS[target] if isinstance(target, str) else target
    goal = float(lufs if lufs is not None else t.lufs)
    ceiling = float(true_peak if true_peak is not None else t.true_peak_db)

    if x.ndim == 1:
        x = x[:, None]
    in_lufs = integrated_lufs(x, sr)
    if not np.isfinite(in_lufs):
        from .errors import FriendlyError

        raise FriendlyError("This song is silent, so there is nothing to master.")

    # 1) gain-stage into the chain (so presets behave the same on quiet or loud input)
    staged = x * dsp.db2lin(-18.0 - in_lufs)
    body = [c for c in (chain or []) if c.get("type") != "limiter"]
    limiter_release = next(
        (
            c.get("params", {}).get("release_ms", 80)
            for c in (chain or [])
            if c.get("type") == "limiter"
        ),
        80,
    )
    y, engine = fx.render_chain(staged, sr, body)
    pre = integrated_lufs(y, sr)
    if not np.isfinite(pre):
        y, pre = staged, integrated_lufs(staged, sr)

    # 2) iterative gain + true-peak limiter until the measured loudness hits the goal
    gain_db = goal - pre
    out = y
    measured = pre
    for _ in range(max_iter):
        out = dsp.true_peak_limit(
            y * dsp.db2lin(gain_db), sr, ceiling_db=ceiling, release_ms=limiter_release
        )
        measured = integrated_lufs(out, sr)
        err = goal - measured
        if abs(err) <= TOLERANCE_LU * 0.6:
            break
        gain_db += err * (
            1.0 if err < 0 else 1.15
        )  # limiting eats loudness: push a bit more on the way up
        gain_db = min(gain_db, 30.0)
    # 3) dense targets (club, CD) on very dynamic material: the limiter alone saturates,
    #    so add gentle soft-clip drive before it until the goal is reached
    drive_db = 0.0
    if goal - measured > TOLERANCE_LU:
        lin_ceiling = dsp.db2lin(ceiling)
        for _ in range(10):
            drive_db += max(1.0, (goal - measured) * 1.5)
            pre_clip = y * dsp.db2lin(gain_db)
            k = dsp.db2lin(drive_db)
            clipped = np.tanh(pre_clip * k / lin_ceiling) * lin_ceiling / np.tanh(k)
            out = dsp.true_peak_limit(clipped, sr, ceiling_db=ceiling, release_ms=limiter_release)
            measured = integrated_lufs(out, sr)
            if goal - measured <= TOLERANCE_LU * 0.6:
                break
        if measured > goal + TOLERANCE_LU:
            out = dsp.true_peak_limit(
                out * dsp.db2lin(goal - measured),
                sr,
                ceiling_db=ceiling,
                release_ms=limiter_release,
            )
            measured = integrated_lufs(out, sr)
    tp = true_peak_db(out, sr)
    report = {
        "target": asdict(t),
        "goal_lufs": goal,
        "goal_true_peak_db": ceiling,
        "input_lufs": round(in_lufs, 2),
        "lufs": round(measured, 2),
        "true_peak_db": round(tp, 2),
        "within_tolerance": abs(measured - goal) <= TOLERANCE_LU and tp <= ceiling + 0.05,
        "fx_engine": engine,
        "gain_db": round(gain_db, 2),
        "drive_db": round(drive_db, 2),
    }
    return out.astype(np.float32), report
