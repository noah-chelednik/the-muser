"""Phase 10: HTML curation report generator."""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from datetime import datetime

from .models import (
    PipelineConfig,
    TrackSelection,
    TrackMetadata,
    DuplicatePair,
)

log = logging.getLogger(__name__)

# Hard-gate dimension names for display
HARD_GATE_DIMS = ["artifacts", "clipping", "silence", "loudness", "phase", "edge_clicks"]
SOFT_SCORE_DIMS = ["structure", "rhythm", "harmony", "freq_balance", "evolution", "stereo_mix"]
TIER_COLORS = {"S": "#FFD700", "A": "#4CAF50", "B": "#2196F3", "C": "#9E9E9E", "D": "#f44336"}
CONFIDENCE_COLORS = {"high": "#4CAF50", "uncertain": "#FF9800"}

_esc = html.escape  # shorthand for template use


def generate_report(
    selections: dict[str, TrackSelection],
    metadata: dict[str, TrackMetadata],
    duplicates: list[DuplicatePair],
    mastered_paths: dict[str, str],
    package_summary: dict,
    output_path: Path,
    config: PipelineConfig,
) -> Path:
    """Generate a self-contained HTML report."""
    # Compute stats
    total_candidates = sum(len(s.all_candidates) for s in selections.values())
    surviving = {tid: s for tid, s in selections.items() if not s.dropped}
    dropped = {tid: s for tid, s in selections.items() if s.dropped}
    mastered = {tid for tid in mastered_paths if mastered_paths[tid]}

    tier_counts = {}
    confidence_counts = {"high": 0, "uncertain": 0}
    genre_counts = {}
    for tid, meta in metadata.items():
        tier_counts[meta.tier] = tier_counts.get(meta.tier, 0) + 1
        genre_counts[meta.genre_primary] = genre_counts.get(meta.genre_primary, 0) + 1
    for s in surviving.values():
        confidence_counts[s.confidence] = confidence_counts.get(s.confidence, 0) + 1

    # Sort surviving by composite score
    sorted_surviving = sorted(
        surviving.values(),
        key=lambda s: -(s.selected_candidate.composite_score if s.selected_candidate else 0),
    )

    html_content = _build_html(
        total_candidates=total_candidates,
        total_tracks=len(selections),
        surviving=sorted_surviving,
        dropped=dropped,
        duplicates=duplicates,
        metadata=metadata,
        mastered_paths=mastered_paths,
        tier_counts=tier_counts,
        confidence_counts=confidence_counts,
        genre_counts=genre_counts,
        package_summary=package_summary,
        config=config,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content)
    log.info("Report written to %s", output_path)
    return output_path


def _build_html(**ctx) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Muser Curation Report</title>
<style>
{_css()}
</style>
</head>
<body>
<div class="container">
<h1>The Muser — Curation Report</h1>
<p class="subtitle">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

{_section_summary(ctx)}
{_section_platforms(ctx)}
{_section_release_set(ctx)}
{_section_dropped(ctx)}
{_section_duplicates(ctx)}
{_section_checklists(ctx)}
</div>

<script>
{_js()}
</script>
</body>
</html>"""


def _css() -> str:
    return """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
       background: #0d1117; color: #c9d1d9; line-height: 1.6; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { color: #58a6ff; margin-bottom: 5px; font-size: 28px; }
h2 { color: #58a6ff; margin: 30px 0 15px; font-size: 22px; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
h3 { color: #8b949e; margin: 20px 0 10px; font-size: 16px; }
.subtitle { color: #8b949e; margin-bottom: 25px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 15px 0; }
.stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center; }
.stat-card .number { font-size: 32px; font-weight: bold; color: #58a6ff; }
.stat-card .label { font-size: 13px; color: #8b949e; }
.bar-chart { margin: 10px 0; }
.bar-row { display: flex; align-items: center; margin: 4px 0; }
.bar-label { width: 160px; font-size: 13px; color: #8b949e; text-align: right; padding-right: 10px; }
.bar-fill { height: 20px; background: #1f6feb; border-radius: 3px; min-width: 2px; transition: width 0.3s; }
.bar-count { font-size: 13px; color: #8b949e; padding-left: 8px; }
.track-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 10px 0; }
.track-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.track-title { font-size: 16px; font-weight: bold; color: #c9d1d9; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; color: #0d1117; }
.track-meta { font-size: 13px; color: #8b949e; margin: 8px 0; }
.gates { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }
.gate { font-size: 12px; padding: 2px 6px; border-radius: 3px; }
.gate-pass { background: #1a3a1a; color: #3fb950; }
.gate-fail { background: #3a1a1a; color: #f85149; }
.scores { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
.score-bar { display: flex; align-items: center; gap: 4px; font-size: 12px; }
.score-bar-fill { width: 60px; height: 8px; background: #21262d; border-radius: 4px; overflow: hidden; }
.score-bar-inner { height: 100%; border-radius: 4px; }
audio { width: 100%; max-width: 400px; height: 32px; margin-top: 8px; }
.dropped-card { background: #1a1215; border: 1px solid #3a1a1a; border-radius: 8px; padding: 12px; margin: 8px 0; }
.dropped-reason { color: #f85149; font-size: 13px; }
.dup-card { background: #1a1a12; border: 1px solid #3a3a1a; border-radius: 8px; padding: 12px; margin: 8px 0; }
.checklist { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 10px 0; }
.checklist label { display: block; padding: 4px 0; font-size: 14px; cursor: pointer; }
.checklist input[type=checkbox] { margin-right: 8px; }
.checklist input:checked + span { text-decoration: line-through; color: #484f58; }
details { margin: 10px 0; }
summary { cursor: pointer; color: #58a6ff; font-weight: bold; padding: 8px 0; }
.platform-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 12px; }
.platform-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
.platform-card h3 { margin: 0 0 8px; color: #58a6ff; }
.filter-bar { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; margin: 15px 0; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.filter-bar select, .filter-bar input { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 6px 10px; font-size: 13px; }
"""


def _section_summary(ctx) -> str:
    tc = ctx["total_candidates"]
    tt = ctx["total_tracks"]
    ns = len(ctx["surviving"])
    nd = len(ctx["dropped"])
    ndup = len(ctx["duplicates"])
    nm = len(ctx["mastered_paths"])

    tier_html = ""
    for tier in ["S", "A", "B", "C", "D"]:
        count = ctx["tier_counts"].get(tier, 0)
        color = TIER_COLORS.get(tier, "#888")
        tier_html += f'<span class="badge" style="background:{color}">{tier}: {count}</span> '

    # Genre bar chart
    genre_html = ""
    max_count = max(ctx["genre_counts"].values()) if ctx["genre_counts"] else 1
    for genre, count in sorted(ctx["genre_counts"].items(), key=lambda x: -x[1]):
        pct = count / max_count * 100
        genre_html += f"""<div class="bar-row">
<span class="bar-label">{genre}</span>
<div class="bar-fill" style="width:{pct}%"></div>
<span class="bar-count">{count}</span>
</div>"""

    return f"""
<h2>Executive Summary</h2>
<div class="stat-grid">
<div class="stat-card"><div class="number">{tc}</div><div class="label">Candidates Analyzed</div></div>
<div class="stat-card"><div class="number">{tt}</div><div class="label">Unique Tracks</div></div>
<div class="stat-card"><div class="number">{ns}</div><div class="label">Surviving</div></div>
<div class="stat-card"><div class="number">{nd}</div><div class="label">Dropped</div></div>
<div class="stat-card"><div class="number">{ndup}</div><div class="label">Duplicates Removed</div></div>
<div class="stat-card"><div class="number">{nm}</div><div class="label">Mastered</div></div>
</div>
<h3>Tier Distribution</h3>
<p>{tier_html}</p>
<h3>Confidence</h3>
<p>High: {ctx['confidence_counts'].get('high',0)} &nbsp; | &nbsp;
Uncertain: {ctx['confidence_counts'].get('uncertain',0)}</p>
<h3>Genre Distribution</h3>
<div class="bar-chart">{genre_html}</div>
"""


def _section_platforms(ctx) -> str:
    ps = ctx["package_summary"]
    cards = ""

    dk = ps.get("distrokid", {})
    dk_albums = dk.get("albums", [])
    cards += f"""<div class="platform-card">
<h3>DistroKid</h3>
<p>{len(dk_albums)} albums, {dk.get('total_tracks', 0)} tracks</p>
<p style="font-size:13px;color:#8b949e">{'<br>'.join(a['title']+f' ({a["tracks"]} tracks)' for a in dk_albums)}</p>
</div>"""

    gm = ps.get("gumroad", {})
    gm_packs = gm.get("packs", [])
    total_rev = sum(p.get("price", 0) for p in gm_packs)
    cards += f"""<div class="platform-card">
<h3>Gumroad</h3>
<p>{len(gm_packs)} packs, {gm.get('total_tracks', 0)} tracks</p>
<p style="font-size:13px;color:#8b949e">Potential revenue (if all sell): ${total_rev}</p>
</div>"""

    fv = ps.get("fiverr", {})
    cards += f"""<div class="platform-card">
<h3>Fiverr</h3>
<p>{fv.get('total', 0)} demo tracks</p>
</div>"""

    kf = ps.get("kofi", {})
    cards += f"""<div class="platform-card">
<h3>Ko-fi</h3>
<p>{kf.get('total', 0)} singles</p>
</div>"""

    return f"""<h2>Platform Summary</h2>
<div class="platform-grid">{cards}</div>"""


def _section_release_set(ctx) -> str:
    tracks_html = ""
    for sel in ctx["surviving"]:
        meta = ctx["metadata"].get(sel.track_id)
        if not meta or not sel.selected_candidate:
            continue
        cand = sel.selected_candidate
        tier = meta.tier
        tier_color = TIER_COLORS.get(tier, "#888")
        conf_color = CONFIDENCE_COLORS.get(sel.confidence, "#888")

        # Hard gate indicators
        gates_html = ""
        for dim in HARD_GATE_DIMS:
            dr = cand.dimensions.get(dim)
            if dr and dr.hard_gate:
                cls = "gate-pass" if dr.hard_gate.passed else "gate-fail"
                sym = "PASS" if dr.hard_gate.passed else "FAIL"
                gates_html += f'<span class="gate {cls}">{dim}: {sym}</span>'

        # Soft score bars
        scores_html = ""
        for dim in SOFT_SCORE_DIMS:
            dr = cand.dimensions.get(dim)
            score = dr.score if dr else 0
            pct = score * 100
            hue = int(score * 120)  # 0=red, 120=green
            scores_html += f"""<div class="score-bar">
<span style="width:70px">{dim}</span>
<div class="score-bar-fill"><div class="score-bar-inner" style="width:{pct}%;background:hsl({hue},70%,45%)"></div></div>
<span>{score:.2f}</span>
</div>"""

        # Audio player
        wav_path = ctx["mastered_paths"].get(sel.track_id, "")
        audio_html = ""
        if wav_path:
            rel = Path(wav_path).name
            audio_html = f'<audio controls preload="none"><source src="mastered/{rel}" type="audio/wav"></audio>'

        key_str = f" | {meta.key}" if meta.key else ""
        bpm_str = f" | {meta.bpm} BPM" if meta.bpm else ""

        tracks_html += f"""
<div class="track-card" data-genre="{meta.genre_primary}" data-tier="{tier}" data-confidence="{sel.confidence}">
<div class="track-header">
<span class="track-title">{_esc(meta.title)}</span>
<span class="badge" style="background:{tier_color}">{tier}</span>
<span class="badge" style="background:{conf_color}">{sel.confidence}</span>
<span class="badge" style="background:#30363d;color:#8b949e">{meta.genre_primary}</span>
</div>
<div class="track-meta">
{meta.duration_formatted}{key_str}{bpm_str} | Score: {cand.composite_score:.4f} | ID: {sel.track_id}
</div>
<div class="gates">{gates_html}</div>
<div class="scores">{scores_html}</div>
{audio_html}
</div>"""

    return f"""<h2>Release Set ({len(ctx['surviving'])} tracks)</h2>
<div class="filter-bar">
<label>Genre: <select id="filter-genre" onchange="filterTracks()">
<option value="all">All</option>
{''.join(f'<option value="{g}">{g}</option>' for g in sorted(ctx["genre_counts"].keys()))}
</select></label>
<label>Tier: <select id="filter-tier" onchange="filterTracks()">
<option value="all">All</option>
{''.join(f'<option value="{t}">{t}</option>' for t in ["S","A","B","C","D"])}
</select></label>
<label>Confidence: <select id="filter-conf" onchange="filterTracks()">
<option value="all">All</option>
<option value="high">High</option>
<option value="uncertain">Uncertain</option>
</select></label>
</div>
{tracks_html}"""


def _section_dropped(ctx) -> str:
    if not ctx["dropped"]:
        return "<h2>Dropped Tracks</h2><p>None — all tracks had at least one viable candidate.</p>"

    cards = ""
    for tid, sel in sorted(ctx["dropped"].items()):
        failures_html = ""
        for cand in sel.all_candidates:
            fails = ", ".join(cand.gate_failures) if cand.gate_failures else "unknown"
            failures_html += f"<div style='font-size:12px;margin:2px 0'>{cand.candidate_id}: {fails}</div>"

        cards += f"""<div class="dropped-card">
<div class="track-header">
<span class="track-title">{_esc(sel.title or tid)}</span>
<span class="badge" style="background:#30363d;color:#8b949e">{sel.genre}</span>
</div>
<div class="dropped-reason">{_esc(sel.drop_reason)}</div>
<details><summary>Candidate details</summary>{failures_html}</details>
</div>"""

    return f"<h2>Dropped Tracks ({len(ctx['dropped'])})</h2>{cards}"


def _section_duplicates(ctx) -> str:
    if not ctx["duplicates"]:
        return "<h2>Duplicates Removed</h2><p>None detected.</p>"

    cards = ""
    for dup in ctx["duplicates"]:
        cards += f"""<div class="dup-card">
Dropped <strong>{dup.dropped_id}</strong> (duplicate of <strong>{dup.kept_id}</strong>)
— similarity: {dup.similarity:.4f} {'(same genre)' if dup.same_genre else '(cross-genre)'}
</div>"""

    return f"<h2>Duplicates Removed ({len(ctx['duplicates'])})</h2>{cards}"


def _section_checklists(ctx) -> str:
    ps = ctx["package_summary"]
    out = "<h2>Upload Checklists</h2>"

    # DistroKid
    dk_albums = ps.get("distrokid", {}).get("albums", [])
    if dk_albums:
        items = ""
        for a in dk_albums:
            items += f'<label><input type="checkbox" data-key="dk-{a["title"]}"><span>{a["title"]} ({a["tracks"]} tracks)</span></label>\n'
        out += f"""<details open><summary>DistroKid ({len(dk_albums)} albums)</summary>
<div class="checklist">{items}</div></details>"""

    # Gumroad
    gm_packs = ps.get("gumroad", {}).get("packs", [])
    if gm_packs:
        items = ""
        for p in gm_packs:
            items += f'<label><input type="checkbox" data-key="gm-{p["genre"]}"><span>{p["title"]} — ${p["price"]}</span></label>\n'
        out += f"""<details open><summary>Gumroad ({len(gm_packs)} packs)</summary>
<div class="checklist">{items}</div></details>"""

    # Fiverr
    out += """<details open><summary>Fiverr (3 gigs)</summary>
<div class="checklist">
<label><input type="checkbox" data-key="fv-gig1"><span>Gig 1: Custom Background Music</span></label>
<label><input type="checkbox" data-key="fv-gig2"><span>Gig 2: Cinematic Trailer Music</span></label>
<label><input type="checkbox" data-key="fv-gig3"><span>Gig 3: Lo-Fi Beats & Chill Music</span></label>
</div></details>"""

    # Ko-fi
    kf_total = ps.get("kofi", {}).get("total", 0)
    out += f"""<details open><summary>Ko-fi ({kf_total} singles)</summary>
<div class="checklist">
<label><input type="checkbox" data-key="kf-singles"><span>Upload {kf_total} singles</span></label>
<label><input type="checkbox" data-key="kf-packs"><span>Upload genre packs (copy from Gumroad)</span></label>
</div></details>"""

    return out


def _js() -> str:
    return """
// Persist checkbox state in localStorage
document.querySelectorAll('.checklist input[type=checkbox]').forEach(cb => {
    const key = 'muser_' + cb.dataset.key;
    cb.checked = localStorage.getItem(key) === 'true';
    cb.addEventListener('change', () => localStorage.setItem(key, cb.checked));
});

// Filter tracks
function filterTracks() {
    const genre = document.getElementById('filter-genre').value;
    const tier = document.getElementById('filter-tier').value;
    const conf = document.getElementById('filter-conf').value;
    document.querySelectorAll('.track-card').forEach(card => {
        const g = genre === 'all' || card.dataset.genre === genre;
        const t = tier === 'all' || card.dataset.tier === tier;
        const c = conf === 'all' || card.dataset.confidence === conf;
        card.style.display = (g && t && c) ? '' : 'none';
    });
}
"""
