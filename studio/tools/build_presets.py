"""Generate the factory preset library (studio/presets/**.json).

Run:  python -m studio.tools.build_presets
Every chain uses only the effect types in studio/server/engines/fx.py, and the
test suite validates every file, so a typo here fails CI instead of the UI.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "presets"


# ---------------------------------------------------------------- effect helpers
def gain(g):
    return {"type": "gain", "params": {"gain_db": g}}


def hp(f):
    return {"type": "highpass", "params": {"cutoff_hz": f}}


def lp(f):
    return {"type": "lowpass", "params": {"cutoff_hz": f}}


def ls(f, g, q=0.7):
    return {"type": "lowshelf", "params": {"cutoff_hz": f, "gain_db": g, "q": q}}


def pk(f, g, q=1.0):
    return {"type": "peak", "params": {"freq_hz": f, "gain_db": g, "q": q}}


def hs(f, g, q=0.7):
    return {"type": "highshelf", "params": {"cutoff_hz": f, "gain_db": g, "q": q}}


def comp(t, r, a=10, rel=120, mk=0):
    return {
        "type": "compressor",
        "params": {
            "threshold_db": t,
            "ratio": r,
            "attack_ms": a,
            "release_ms": rel,
            "makeup_db": mk,
        },
    }


def gate(t, r=4, a=1, rel=100):
    return {
        "type": "gate",
        "params": {"threshold_db": t, "ratio": r, "attack_ms": a, "release_ms": rel},
    }


def dee(f=6500, t=-30, r=4):
    return {"type": "deesser", "params": {"frequency_hz": f, "threshold_db": t, "ratio": r}}


def sat(d, m=1.0):
    return {"type": "saturation", "params": {"drive_db": d, "mix": m}}


def crush(b, m=1.0):
    return {"type": "bitcrush", "params": {"bit_depth": b, "mix": m}}


def cho(rate=1.0, depth=0.25, cd=7, fb=0.0, m=0.5):
    return {
        "type": "chorus",
        "params": {
            "rate_hz": rate,
            "depth": depth,
            "centre_delay_ms": cd,
            "feedback": fb,
            "mix": m,
        },
    }


def ph(rate=0.5, depth=0.5, cf=1300, fb=0.0, m=0.5):
    return {
        "type": "phaser",
        "params": {
            "rate_hz": rate,
            "depth": depth,
            "centre_frequency_hz": cf,
            "feedback": fb,
            "mix": m,
        },
    }


def dly(ms, fb=0.3, m=0.2):
    return {"type": "delay", "params": {"time_ms": ms, "feedback": fb, "mix": m}}


def rev(room=0.5, damp=0.5, m=0.25, w=1.0):
    return {"type": "reverb", "params": {"room_size": room, "damping": damp, "width": w, "mix": m}}


def wid(w):
    return {"type": "width", "params": {"width": w}}


def lim(c=-1.0, rel=80):
    return {"type": "limiter", "params": {"ceiling_db": c, "release_ms": rel}}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


PRESETS: list[dict] = []


def add(category, name, desc, tags, sub="", **body):
    pid = f"{category}/{slug(name)}"
    PRESETS.append(
        {
            "id": pid,
            "name": name,
            "category": category,
            "subcategory": sub,
            "tags": tags,
            "description": desc,
            "version": 1,
            "factory": True,
            **body,
        }
    )
    return pid


# ---------------------------------------------------------------- mix chains (per stem)
M = {}
M["drums_punchy"] = add(
    "mix",
    "Punchy Drums",
    "Tight low end, snappy transients, glue compression.",
    ["punchy", "modern"],
    "drums",
    role="drums",
    chain=[hp(30), pk(60, 2.5, 1.2), pk(400, -2.5, 1.5), comp(-18, 4, 8, 90, 3), hs(8000, 2)],
)
M["drums_lofi"] = add(
    "mix",
    "Dusty Drums",
    "Rolled-off highs and tape-style saturation for lo-fi beats.",
    ["lofi", "warm", "vintage"],
    "drums",
    role="drums",
    chain=[hp(40), lp(7500), sat(8, 0.6), comp(-20, 3, 20, 150, 2)],
)
M["drums_trap"] = add(
    "mix",
    "Trap Drums",
    "Hard hats, big low end and a forward snare.",
    ["trap", "hip hop", "hard"],
    "drums",
    role="drums",
    chain=[hp(25), ls(80, 3), pk(220, 2, 1.4), comp(-16, 5, 5, 80, 3), hs(9000, 3), sat(4, 0.4)],
)
M["drums_house"] = add(
    "mix",
    "Four on the Floor",
    "Clean, wide house drums with controlled kick.",
    ["house", "dance", "club"],
    "drums",
    role="drums",
    chain=[hp(30), pk(55, 2, 1.0), pk(350, -3, 1.2), comp(-14, 3, 15, 100, 2), wid(1.15)],
)
M["drums_rock"] = add(
    "mix",
    "Live Rock Kit",
    "Room-y acoustic kit with natural punch.",
    ["rock", "live", "acoustic"],
    "drums",
    role="drums",
    chain=[
        hp(35),
        pk(100, 2, 1),
        pk(500, -2, 1.5),
        pk(4000, 2, 1),
        comp(-20, 4, 12, 120, 3),
        rev(0.35, 0.4, 0.12),
    ],
)
M["drums_jazz"] = add(
    "mix",
    "Brushed Jazz",
    "Soft dynamics, natural room, gentle top.",
    ["jazz", "soft", "natural"],
    "drums",
    role="drums",
    chain=[hp(40), comp(-24, 2, 25, 200, 1), hs(10000, 1.5), rev(0.4, 0.5, 0.15)],
)
M["drums_crushed"] = add(
    "mix",
    "Crushed Drums",
    "Parallel smash for aggressive energy.",
    ["aggressive", "drill", "parallel"],
    "drums",
    role="drums",
    chain=[hp(30), comp(-30, 10, 1, 60, 8), sat(10, 0.5), hs(7000, 2)],
)
M["bass_tight"] = add(
    "mix",
    "Tight Bass",
    "Controlled sub with defined midrange so it reads on phones.",
    ["clean", "modern"],
    "bass",
    role="bass",
    chain=[hp(30), comp(-20, 4, 15, 120, 3), pk(800, 2, 1.2), lp(9000)],
)
M["bass_808"] = add(
    "mix",
    "808 Weight",
    "Big sub with harmonic saturation so it translates on small speakers.",
    ["808", "trap", "hip hop"],
    "bass",
    role="bass",
    chain=[hp(25), sat(9, 0.5), ls(60, 2), comp(-18, 4, 10, 150, 2), lp(6000)],
)
M["bass_warm"] = add(
    "mix",
    "Warm Bass",
    "Rounded, soft low end for chill styles.",
    ["warm", "lofi", "chill"],
    "bass",
    role="bass",
    chain=[hp(35), lp(3500), sat(5, 0.4), comp(-22, 3, 20, 180, 2)],
)
M["bass_growl"] = add(
    "mix",
    "Growl Bass",
    "Driven midrange for EDM and dubstep.",
    ["edm", "aggressive", "dubstep"],
    "bass",
    role="bass",
    chain=[hp(30), sat(14, 0.7), pk(1200, 3, 1), comp(-16, 6, 5, 80, 3), wid(1.1)],
)
M["bass_synthwave"] = add(
    "mix",
    "Retro Synth Bass",
    "Analog-style bass with gentle chorus.",
    ["synthwave", "retro", "80s"],
    "bass",
    role="bass",
    chain=[hp(35), comp(-20, 3, 10, 120, 2), cho(0.4, 0.15, 8, 0, 0.2), lp(8000)],
)
M["bass_upright"] = add(
    "mix",
    "Upright Bass",
    "Natural woody tone for jazz and acoustic.",
    ["jazz", "acoustic"],
    "bass",
    role="bass",
    chain=[hp(40), pk(250, -2, 1.2), pk(1500, 2, 1), comp(-24, 2.5, 20, 200, 2)],
)
M["keys_lush"] = add(
    "mix",
    "Lush Keys",
    "Wide, soft and spacious pads and chords.",
    ["pads", "ambient", "wide"],
    "keys",
    role="keys",
    chain=[hp(120), pk(300, -2, 1), cho(0.6, 0.3, 9, 0, 0.3), rev(0.7, 0.4, 0.3), wid(1.3)],
)
M["keys_tape"] = add(
    "mix",
    "Tape Keys",
    "Wobbly, warm, lo-fi keys.",
    ["lofi", "vintage", "warm"],
    "keys",
    role="keys",
    chain=[hp(100), lp(6000), cho(0.3, 0.4, 12, 0, 0.35), sat(6, 0.5), rev(0.5, 0.6, 0.2)],
)
M["keys_clean"] = add(
    "mix",
    "Clean Piano",
    "Clear, present piano for pop and ballads.",
    ["pop", "piano", "clean"],
    "keys",
    role="keys",
    chain=[
        hp(60),
        pk(250, -2, 1),
        pk(3000, 1.5, 1),
        comp(-20, 2, 15, 150, 1),
        rev(0.45, 0.5, 0.15),
    ],
)
M["keys_stab"] = add(
    "mix",
    "House Stabs",
    "Punchy chord stabs that cut through.",
    ["house", "dance"],
    "keys",
    role="keys",
    chain=[hp(150), comp(-18, 4, 3, 80, 2), dly(375, 0.25, 0.15), rev(0.4, 0.5, 0.15)],
)
M["keys_organ"] = add(
    "mix",
    "Gospel Organ",
    "Warm organ with rotary-style motion.",
    ["gospel", "soul", "organ"],
    "keys",
    role="keys",
    chain=[hp(70), cho(5.5, 0.2, 4, 0, 0.35), sat(4, 0.4), rev(0.5, 0.5, 0.2)],
)
M["lead_bright"] = add(
    "mix",
    "Bright Lead",
    "Upfront synth lead with delay throws.",
    ["edm", "pop", "lead"],
    "lead",
    role="lead",
    chain=[
        hp(200),
        pk(2500, 2, 1),
        comp(-18, 3, 8, 100, 2),
        dly(375, 0.3, 0.18),
        rev(0.5, 0.5, 0.15),
    ],
)
M["lead_retro"] = add(
    "mix",
    "Retro Lead",
    "Chorused 80s lead with big hall.",
    ["synthwave", "80s", "retro"],
    "lead",
    role="lead",
    chain=[hp(180), cho(0.8, 0.35, 8, 0.1, 0.4), dly(450, 0.35, 0.2), rev(0.75, 0.4, 0.25)],
)
M["lead_dark"] = add(
    "mix",
    "Dark Lead",
    "Filtered, gritty melody for drill and trap.",
    ["drill", "trap", "dark"],
    "lead",
    role="lead",
    chain=[hp(150), lp(7000), sat(6, 0.5), rev(0.6, 0.6, 0.2)],
)
M["lead_soft"] = add(
    "mix",
    "Soft Melody",
    "Gentle melody that sits back in the mix.",
    ["chill", "lofi", "soft"],
    "lead",
    role="lead",
    chain=[hp(200), lp(9000), comp(-24, 2, 20, 200, 1), rev(0.55, 0.5, 0.25)],
)
M["guitar_crunch"] = add(
    "mix",
    "Crunch Guitar",
    "Driven rhythm guitar with presence.",
    ["rock", "guitar"],
    "guitar",
    role="guitar",
    chain=[hp(90), sat(12, 0.7), pk(400, -2, 1), pk(3000, 2, 1), comp(-18, 3, 10, 120, 2)],
)
M["guitar_clean"] = add(
    "mix",
    "Clean Strum",
    "Bright acoustic or clean electric guitar.",
    ["acoustic", "folk", "guitar"],
    "guitar",
    role="guitar",
    chain=[hp(90), pk(200, -2.5, 1), hs(9000, 2), comp(-22, 2.5, 15, 150, 1), rev(0.4, 0.5, 0.15)],
)
M["guitar_ambient"] = add(
    "mix",
    "Ambient Guitar",
    "Shimmering delays and long tails.",
    ["ambient", "guitar", "post rock"],
    "guitar",
    role="guitar",
    chain=[hp(120), dly(500, 0.5, 0.3), cho(0.5, 0.3, 10, 0, 0.3), rev(0.9, 0.3, 0.4)],
)
M["bus_glue"] = add(
    "mix",
    "Mix Bus Glue",
    "Gentle bus compression that makes parts feel like one record.",
    ["bus", "glue"],
    "bus",
    role="bus",
    chain=[comp(-14, 2, 30, 200, 1)],
)
M["bus_warm"] = add(
    "mix",
    "Warm Bus",
    "Analog-style warmth and soft top.",
    ["bus", "warm", "analog"],
    "bus",
    role="bus",
    chain=[sat(3, 0.5), ls(120, 1), hs(10000, -1), comp(-16, 2, 30, 250, 1)],
)
M["bus_air"] = add(
    "mix",
    "Airy Bus",
    "Opens up the top and widens.",
    ["bus", "bright", "wide"],
    "bus",
    role="bus",
    chain=[hs(12000, 2.5), wid(1.15), comp(-14, 1.8, 30, 200, 0.5)],
)
M["bus_clean"] = add(
    "mix",
    "Transparent Bus",
    "Only cleans up rumble. Leaves your mix alone.",
    ["bus", "clean"],
    "bus",
    role="bus",
    chain=[hp(25)],
)
M["bus_punch"] = add(
    "mix",
    "Punch Bus",
    "Slower attack lets drums hit, then holds the mix together.",
    ["bus", "punchy"],
    "bus",
    role="bus",
    chain=[comp(-16, 3, 40, 120, 2), pk(80, 1, 1)],
)

# ---------------------------------------------------------------- mastering
PLAT = {}
for key, label, desc in [
    ("spotify", "Spotify", "-14 LUFS, -1 dBTP. Matches Spotify's normal loudness setting."),
    ("youtube", "YouTube", "-14 LUFS, -1 dBTP. YouTube turns louder uploads down anyway."),
    (
        "soundcloud",
        "SoundCloud",
        "-10 LUFS, -1 dBTP. SoundCloud doesn't normalize, so it runs louder.",
    ),
    ("club", "Club / DJ", "-8 LUFS, -0.5 dBTP. Loud and dense for DJ sets."),
    ("apple", "Apple Music", "-16 LUFS, -1 dBTP. Sound Check target."),
    ("tidal", "Tidal", "-14 LUFS, -1 dBTP."),
    ("amazon", "Amazon Music", "-14 LUFS, -2 dBTP."),
    ("podcast", "Podcast", "-16 LUFS, -1 dBTP. Spoken word standard."),
    ("broadcast", "Broadcast (EBU R128)", "-23 LUFS, -1 dBTP."),
    ("cd", "CD / Loud Master", "-9 LUFS, -0.3 dBTP."),
]:
    chain = [hp(25), comp(-16, 2, 30, 200, 1), hs(10000, 1)]
    if key == "club":
        chain = [hp(28), ls(70, 1.5), comp(-14, 3, 20, 150, 2), sat(3, 0.4), hs(9000, 1.5)]
    if key in ("podcast", "broadcast"):
        chain = [hp(70), dee(6000, -28, 3), comp(-20, 3, 10, 150, 2)]
    PLAT[key] = add(
        "master",
        f"{label} Master",
        desc,
        ["platform", key],
        "platform",
        master={"target": key, "chain": chain, "release_ms": 80},
    )

GM = {}
for name, desc, tags, target, chain in [
    (
        "Hip Hop Master",
        "Weighty low end, crisp top, controlled transients.",
        ["hip hop", "trap"],
        "spotify",
        [hp(25), ls(70, 2), comp(-16, 3, 15, 120, 2), sat(3, 0.4), hs(10000, 1.5)],
    ),
    (
        "EDM Master",
        "Loud, bright and wide for festival tracks.",
        ["edm", "dance"],
        "soundcloud",
        [hp(28), comp(-14, 3, 15, 100, 2), sat(4, 0.4), hs(11000, 2), wid(1.15)],
    ),
    (
        "Lo-fi Master",
        "Soft, warm and not too loud.",
        ["lofi", "chill"],
        "spotify",
        [hp(30), lp(15000), sat(4, 0.5), comp(-18, 2, 30, 250, 1)],
    ),
    (
        "Rock Master",
        "Mid-forward energy and punch.",
        ["rock", "indie"],
        "spotify",
        [hp(30), pk(2500, 1.5, 0.8), comp(-16, 3, 20, 150, 2), sat(3, 0.4)],
    ),
    (
        "Pop Master",
        "Polished, bright and present.",
        ["pop"],
        "spotify",
        [hp(25), comp(-15, 2.5, 25, 150, 1.5), pk(3000, 1, 0.8), hs(12000, 2)],
    ),
    (
        "Acoustic Master",
        "Gentle and dynamic, keeps the natural feel.",
        ["acoustic", "folk", "jazz"],
        "apple",
        [hp(30), comp(-22, 1.5, 40, 300, 0.5), hs(12000, 1)],
    ),
    (
        "Cinematic Master",
        "Wide dynamic range for film and ambient pieces.",
        ["cinematic", "ambient", "orchestral"],
        "apple",
        [hp(25), comp(-24, 1.5, 50, 400, 0.5), wid(1.1)],
    ),
    (
        "Techno Master",
        "Hypnotic, dense and steady.",
        ["techno", "house", "club"],
        "club",
        [hp(28), comp(-14, 4, 10, 100, 2), ls(60, 1), hs(9000, 1)],
    ),
    (
        "R&B Master",
        "Smooth highs, rich low end.",
        ["rnb", "soul"],
        "spotify",
        [hp(25), ls(90, 1.5), comp(-17, 2.5, 25, 180, 1.5), hs(9000, 1), dee(7500, -26, 2)],
    ),
    (
        "Metal Master",
        "Aggressive and loud with tamed harshness.",
        ["metal", "rock"],
        "cd",
        [hp(35), pk(3500, -1.5, 1.2), comp(-12, 4, 10, 100, 2), sat(4, 0.3)],
    ),
    (
        "Drill Master",
        "Dark, heavy sub and sharp hats.",
        ["drill", "uk"],
        "soundcloud",
        [hp(25), ls(60, 2.5), comp(-15, 3, 12, 110, 2), hs(10000, 1.5)],
    ),
]:
    GM[slug(name)] = add(
        "master",
        name,
        desc,
        tags + ["genre"],
        "genre",
        master={"target": target, "chain": chain, "release_ms": 80},
    )

# ---------------------------------------------------------------- vocals
for name, desc, tags, chain in [
    (
        "Radio Pop Vocal",
        "Bright, compressed and upfront.",
        ["pop", "bright"],
        [
            hp(90),
            pk(300, -2.5, 1.2),
            comp(-20, 4, 5, 80, 4),
            dee(7000, -28, 4),
            hs(10000, 3),
            rev(0.45, 0.5, 0.12),
        ],
    ),
    (
        "Rap Vocal",
        "Dry, punchy and clear on top of the beat.",
        ["hip hop", "rap", "dry"],
        [hp(100), pk(250, -3, 1.2), comp(-18, 5, 3, 60, 4), pk(4000, 2, 1), dee(6500, -26, 4)],
    ),
    (
        "Trap Ad-libs",
        "Telephone-style filtered ad-libs with delay.",
        ["trap", "adlib", "fx"],
        [hp(400), lp(4500), sat(6, 0.5), dly(250, 0.35, 0.25)],
    ),
    (
        "Soft Indie Vocal",
        "Breathy and intimate.",
        ["indie", "folk", "soft"],
        [hp(80), comp(-24, 2.5, 15, 150, 2), hs(11000, 2), rev(0.5, 0.5, 0.18)],
    ),
    (
        "R&B Silk",
        "Smooth top, warm body and lush space.",
        ["rnb", "smooth"],
        [
            hp(80),
            pk(350, -2, 1),
            comp(-20, 3, 10, 120, 3),
            dee(7500, -28, 3),
            cho(0.4, 0.1, 6, 0, 0.12),
            rev(0.6, 0.4, 0.2),
        ],
    ),
    (
        "Rock Grit",
        "Driven, mid-forward rock vocal.",
        ["rock", "gritty"],
        [hp(100), sat(8, 0.4), pk(2000, 2.5, 1), comp(-18, 4, 8, 100, 3), dly(120, 0.1, 0.1)],
    ),
    (
        "Choir Hall",
        "Big hall for backing vocals and choirs.",
        ["choir", "gospel", "backing"],
        [hp(150), comp(-22, 2, 20, 200, 2), rev(0.85, 0.4, 0.35), wid(1.4)],
    ),
    (
        "Podcast Voice",
        "Clean, even speech.",
        ["speech", "podcast"],
        [
            hp(80),
            gate(-50, 4, 1, 120),
            dee(6000, -30, 3),
            comp(-22, 3.5, 10, 150, 4),
            pk(3000, 1.5, 1),
        ],
    ),
    (
        "Lo-fi Vocal",
        "Muffled vintage tone.",
        ["lofi", "vintage"],
        [hp(300), lp(5000), sat(6, 0.5), crush(12, 0.2), rev(0.4, 0.6, 0.2)],
    ),
    (
        "Airy Ballad",
        "Lots of air and a long plate.",
        ["ballad", "pop"],
        [hp(90), comp(-22, 3, 10, 150, 3), hs(12000, 3.5), dee(8000, -28, 3), rev(0.75, 0.3, 0.25)],
    ),
    (
        "Afrobeats Vocal",
        "Bright vocal with a short slap delay.",
        ["afrobeats", "dancehall"],
        [hp(90), comp(-19, 3.5, 6, 90, 3), hs(9000, 2), dly(110, 0.15, 0.12), rev(0.4, 0.5, 0.12)],
    ),
    (
        "Doubled Wide",
        "Fake double-tracking for a wide chorus vocal.",
        ["wide", "chorus"],
        [hp(90), comp(-20, 3, 8, 100, 3), cho(0.9, 0.15, 12, 0, 0.35), wid(1.5)],
    ),
    (
        "Metal Scream",
        "Tight, aggressive and dense.",
        ["metal", "aggressive"],
        [hp(120), comp(-14, 8, 2, 60, 5), sat(10, 0.4), pk(3500, -2, 1.5)],
    ),
    ("Gentle De-ess", "Just tames harsh S sounds.", ["fix", "clean"], [dee(6500, -32, 5)]),
    ("Megaphone", "Thin bullhorn effect.", ["fx", "creative"], [hp(800), lp(3500), sat(14, 0.8)]),
]:
    add("vocal", name, desc, tags, "vocals", role="vocals", chain=chain)

# ---------------------------------------------------------------- fx / creative
for name, desc, tags, chain in [
    ("Big Hall", "Huge concert hall.", ["reverb", "space"], [rev(0.9, 0.35, 0.4)]),
    ("Small Room", "Subtle room to glue dry parts.", ["reverb", "room"], [rev(0.25, 0.6, 0.15)]),
    ("Slapback", "Short 1950s echo.", ["delay", "vintage"], [dly(110, 0.1, 0.25)]),
    (
        "Dub Echo",
        "Long feedback delay with dark tone.",
        ["delay", "dub"],
        [dly(500, 0.6, 0.35), lp(4000)],
    ),
    (
        "Ping Space",
        "Delay into reverb for dreamy tails.",
        ["delay", "reverb", "dreamy"],
        [dly(375, 0.4, 0.25), rev(0.7, 0.4, 0.3)],
    ),
    (
        "Telephone",
        "Narrow band like a phone call.",
        ["filter", "lofi"],
        [hp(500), lp(3000), sat(5, 0.6)],
    ),
    (
        "Radio",
        "AM radio color.",
        ["filter", "vintage"],
        [hp(300), lp(5000), sat(8, 0.5), crush(10, 0.3)],
    ),
    ("Bitcrusher", "8-bit video game grit.", ["distortion", "retro"], [crush(6, 0.7)]),
    (
        "Tape Warble",
        "Wobbly cassette chorus.",
        ["chorus", "lofi"],
        [cho(0.25, 0.5, 15, 0, 0.5), lp(9000)],
    ),
    (
        "Jet Phaser",
        "Sweeping phaser for synths and drums.",
        ["phaser", "modulation"],
        [ph(0.3, 0.7, 1000, 0.5, 0.6)],
    ),
    (
        "Underwater",
        "Muffled, far-away filter.",
        ["filter", "transition"],
        [lp(700), rev(0.6, 0.8, 0.3)],
    ),
    ("Super Wide", "Extra stereo width.", ["width", "stereo"], [wid(1.8)]),
    ("Mono Maker", "Collapse to mono for checks or bass.", ["width", "utility"], [wid(0.0)]),
    ("Fuzz", "Heavy saturation.", ["distortion"], [sat(28, 0.8), lp(8000)]),
    (
        "Shimmer Pad",
        "Bright, washed-out ambience.",
        ["reverb", "ambient"],
        [cho(0.6, 0.4, 10, 0.2, 0.4), rev(0.95, 0.2, 0.5), hs(8000, 3)],
    ),
]:
    add("fx", name, desc, tags, "creative", chain=chain)


# ---------------------------------------------------------------- genre starters (Easy vibes)
# ACE-Step 1.5 settings tuned per genre for the 8 GB profile (src/utils/vram_profile.py:
# 2B turbo DiT, 0.6B LM on the pt backend, CPU offload, INT8). The turbo DiT is distilled for 8 steps, so
# infer_step stays 8; guidance_scale is applied by non-turbo DiTs. Durations stay short because every extra
# second costs offloaded-DiT time on a 2080 Super. All tracks are instrumental unless the user adds lyrics.
ACESTEP_8GB = {
    "Lo-fi Chill": ("lo-fi hip hop instrumental, dusty vinyl crackle, warm tape-saturated Rhodes electric piano playing mellow seventh chords, soft laid-back boom bap drums with lazy swing, round sub bass, gentle jazz guitar licks, rainy night mood, relaxed and nostalgic, wide warm mix", "A minor", "4", 8, 5.0, 40),
    "Hip Hop": ("boom bap hip hop instrumental, hard punchy kick and crisp snare, dusty soul sample chops with vinyl texture, deep round bass line, head-nodding groove with slight swing, 90s New York feel, gritty analog mix", "F minor", "4", 8, 6.0, 36),
    "Trap": ("dark modern trap instrumental, heavy distorted 808 bass with long glide, rolling hi-hats with triplet stutters and fast rolls, crisp snares and claps, eerie bell and pluck melody, sparse minor key atmosphere, club-ready loud mix", "F# minor", "4", 8, 7.0, 32),
    "UK Drill": ("UK drill instrumental, sliding 808 bass, dark minor piano melody, skippy triplet hi-hats, sharp snare on the third beat, cold ominous London night mood, tight dry mix", "G minor", "4", 8, 7.0, 32),
    "Phonk": ("Memphis phonk instrumental, distorted saturated 808, chopped cowbell melody, aggressive lo-fi trap drums, dark vocal chop samples, gritty tape distortion, drift-car energy", "D minor", "4", 8, 7.0, 32),
    "Techno": ("driving techno, relentless four-on-the-floor kick, off-beat open hi-hats, rumbling rolling bassline, hypnotic filtered synth stabs that evolve slowly, dark warehouse atmosphere, tension building with filter sweeps, powerful club mix", "A minor", "4", 8, 6.0, 40),
    "House": ("deep house groove, four-on-the-floor kick with swung hi-hats and claps, warm Rhodes and organ chord stabs, round plucked bass line, smooth late-night club feel, soft pads, groovy and uplifting", "A minor", "4", 8, 6.0, 40),
    "EDM Anthem": ("festival EDM anthem, euphoric supersaw chords, big sidechain-pumping drop, rising white noise riser build-up, punchy kick, bright plucked lead hook, emotional major key melody, huge wide mix", "C major", "4", 8, 7.0, 40),
    "Synthwave": ("retro 1980s synthwave, gated reverb snare, analog pulsing arpeggio bass, lush detuned Juno-style pads, neon night drive mood, soaring lead synth melody, warm tape sheen", "A minor", "4", 8, 6.0, 40),
    "Chillwave": ("chillwave, hazy dreamy synths, washed-out reverb, slow warm arpeggios, soft side-chained pads, relaxed drum machine groove, summer nostalgia, lo-fi tape warble", "E major", "4", 8, 5.0, 40),
    "Ambient": ("ambient soundscape, slow evolving pads, deep shimmering reverb, soft textural drones, distant piano notes, no drums, calm and spacious, gentle movement, meditative", "D major", "4", 8, 4.5, 45),
    "Cinematic": ("cinematic orchestral score, sweeping legato strings, powerful low brass, taiko-style percussion hits, rising tension then heroic climax, timpani rolls, epic and emotional, wide concert hall reverb", "D minor", "4", 8, 6.5, 45),
    "Jazz Lounge": ("smooth jazz lounge trio, brushed drums with ride cymbal swing, walking upright bass, warm piano comping with extended seventh and ninth chords, relaxed late-night club, intimate room sound", "Bb major", "4", 8, 5.0, 40),
    "R&B Slow Jam": ("smooth R&B slow jam instrumental, lush electric piano and warm pads, soft finger-snap snare, deep sub bass, silky chord progression with ninth chords, sensual late-night mood, polished warm mix", "Eb major", "4", 8, 5.5, 40),
    "Pop": ("upbeat modern pop instrumental, catchy bright synth hook, punchy four-on-the-floor kick and claps, plucked chord stabs, bouncy bass, clean polished radio mix, euphoric chorus lift", "G major", "4", 8, 6.5, 36),
    "Rock": ("energetic rock band, overdriven rhythm guitars playing power chords, live acoustic drums with big snare, punchy electric bass, driving eighth-note groove, anthemic and raw, room ambience", "E minor", "4", 8, 6.5, 36),
    "Metal": ("heavy metal, down-tuned palm-muted chugging riffs, double bass drum, tight aggressive snare, high-gain guitar harmonies, dark and powerful, thick low end", "D minor", "4", 8, 7.0, 36),
    "Afrobeats": ("afrobeats groove, log drum bass line, shaker and congas with syncopated percussion, bright plucked guitar, warm sunny synth chords, bouncy mid-tempo dance rhythm, joyful", "F major", "4", 8, 6.0, 36),
    "Reggaeton": ("reggaeton dembow pop beat, classic dembow kick and snare pattern, latin percussion, catchy plucked synth hook, deep punchy bass, warm club energy", "A minor", "4", 8, 6.5, 36),
    "Drum and Bass": ("liquid drum and bass, fast two-step breakbeat at 174 bpm, deep rolling sub bass, atmospheric pads, soulful chord stabs, crisp snares, uplifting and flowing energy", "F minor", "4", 8, 6.5, 36),
    "Dubstep": ("heavy dubstep, half-time drums with huge snare, growling wobble bass with fast modulation, aggressive sound design, cinematic riser into drop, sub weight, dark and powerful", "F minor", "4", 8, 7.0, 36),
    "Country Pop": ("country pop, strummed acoustic guitar, bright twangy electric guitar fills, steady rock drums with tambourine, warm bass, feel-good singalong energy, polished modern Nashville mix", "G major", "4", 8, 6.0, 36),
    "Indie Folk": ("indie folk rock, fingerpicked acoustic guitar, soft brushed drums, warm upright bass, gentle harmonium, intimate and heartfelt, airy room sound", "D major", "4", 8, 5.5, 40),
    "Gospel Soul": ("gospel soul, Hammond organ with rotary speaker, warm choir pads, uplifting piano chords, gentle shuffle drums, rich bass, joyful and reverent, live church room warmth", "Ab major", "4", 8, 5.5, 40),
}


def _acestep(name, bpm):
    tags, key, sig, steps, cfg, dur = ACESTEP_8GB[name]
    return {
        "acestep": {
            "profile": "8gb",
            "tags": f"{tags}, {bpm} bpm",
            "lyrics": "[instrumental]",
            "bpm": bpm,
            "key_scale": key,
            "time_signature": sig,
            "infer_step": steps,
            "guidance_scale": cfg,
            "duration_s": dur,
            "num_candidates": 1,
        }
    }


def genre(
    name, emoji, prompt, desc, tags, easy, bpm, stems, master, macros, duration=30, lyrics=""
):
    return add(
        "genre",
        name,
        desc,
        tags,
        "starter",
        easy=easy,
        icon=emoji,
        generate={
            "prompt": prompt,
            "bpm": bpm,
            "duration_s": duration,
            "lyrics": lyrics,
            **(_acestep(name, bpm) if name in ACESTEP_8GB else {}),
        },
        stems=stems,
        master=master,
        macros=macros,
    )


def mac(e=50, v=50, b=50, br=50, s=50):
    return {"energy": e, "vocals": v, "bass": b, "brightness": br, "space": s}


G = GM
genre(
    "Lo-fi Chill",
    "moon",
    "lofi hip hop beat, dusty vinyl, mellow rhodes, rainy night",
    "Mellow beats to study to.",
    ["lofi", "chill"],
    True,
    78,
    {
        "drums": M["drums_lofi"],
        "bass": M["bass_warm"],
        "keys": M["keys_tape"],
        "lead": M["lead_soft"],
    },
    G["lo-fi-master"],
    mac(35, 40, 55, 30, 60),
)
genre(
    "Hip Hop",
    "mic",
    "boom bap hip hop beat, hard drums, soulful sample chops",
    "Head-nod boom bap.",
    ["hip hop", "rap"],
    True,
    90,
    {
        "drums": M["drums_punchy"],
        "bass": M["bass_tight"],
        "keys": M["keys_clean"],
        "lead": M["lead_soft"],
    },
    G["hip-hop-master"],
    mac(60, 60, 60, 50, 35),
)
genre(
    "Trap",
    "fire",
    "dark trap beat, rolling hi-hats, heavy 808, eerie bells",
    "Hard 808s and rolling hats.",
    ["trap", "hip hop"],
    True,
    140,
    {
        "drums": M["drums_trap"],
        "bass": M["bass_808"],
        "keys": M["keys_lush"],
        "lead": M["lead_dark"],
    },
    G["hip-hop-master"],
    mac(75, 55, 75, 55, 40),
)
genre(
    "House",
    "disco",
    "deep house groove, warm chords, four on the floor",
    "Warm dance floor groove.",
    ["house", "dance"],
    True,
    124,
    {
        "drums": M["drums_house"],
        "bass": M["bass_tight"],
        "keys": M["keys_stab"],
        "lead": M["lead_bright"],
    },
    G["techno-master"],
    mac(65, 45, 60, 55, 50),
)
genre(
    "Techno",
    "bolt",
    "driving techno, hypnotic synth, pounding kick",
    "Hypnotic and relentless.",
    ["techno", "club"],
    False,
    130,
    {
        "drums": M["drums_house"],
        "bass": M["bass_growl"],
        "keys": M["keys_stab"],
        "lead": M["lead_dark"],
    },
    G["techno-master"],
    mac(80, 30, 65, 50, 45),
)
genre(
    "EDM Anthem",
    "rocket",
    "festival edm anthem, big supersaw drop, euphoric",
    "Big drops and bright leads.",
    ["edm", "dance"],
    True,
    128,
    {
        "drums": M["drums_punchy"],
        "bass": M["bass_growl"],
        "keys": M["keys_lush"],
        "lead": M["lead_bright"],
    },
    G["edm-master"],
    mac(85, 55, 65, 70, 55),
)
genre(
    "Synthwave",
    "sunset",
    "synthwave, retro 80s, neon night drive, gated drums",
    "Neon 80s night drive.",
    ["synthwave", "80s"],
    True,
    105,
    {
        "drums": M["drums_punchy"],
        "bass": M["bass_synthwave"],
        "keys": M["keys_lush"],
        "lead": M["lead_retro"],
    },
    G["pop-master"],
    mac(60, 50, 55, 60, 70),
)
genre(
    "Ambient",
    "cloud",
    "ambient soundscape, slow evolving pads, calm",
    "Floating, calm textures.",
    ["ambient", "calm"],
    True,
    70,
    {
        "drums": M["drums_jazz"],
        "bass": M["bass_warm"],
        "keys": M["keys_lush"],
        "lead": M["lead_soft"],
    },
    G["cinematic-master"],
    mac(15, 30, 35, 45, 90),
    duration=40,
)
genre(
    "Cinematic",
    "film",
    "cinematic orchestral score, epic strings, heroic brass",
    "Epic film score.",
    ["cinematic", "orchestral"],
    True,
    90,
    {
        "drums": M["drums_rock"],
        "bass": M["bass_warm"],
        "keys": M["keys_lush"],
        "lead": M["lead_retro"],
    },
    G["cinematic-master"],
    mac(55, 40, 50, 50, 80),
    duration=40,
)
genre(
    "Jazz Lounge",
    "sax",
    "smooth jazz lounge, brushed drums, upright bass, piano trio",
    "Late night jazz club.",
    ["jazz", "lounge"],
    True,
    96,
    {
        "drums": M["drums_jazz"],
        "bass": M["bass_upright"],
        "keys": M["keys_clean"],
        "lead": M["lead_soft"],
    },
    G["acoustic-master"],
    mac(35, 55, 45, 50, 55),
)
genre(
    "Rock",
    "guitar",
    "energetic rock, driving guitars, live drums",
    "Guitars up, drums loud.",
    ["rock", "band"],
    True,
    120,
    {
        "drums": M["drums_rock"],
        "bass": M["bass_tight"],
        "keys": M["guitar_crunch"],
        "lead": M["guitar_crunch"],
    },
    G["rock-master"],
    mac(75, 60, 55, 55, 35),
)
genre(
    "Pop",
    "star",
    "upbeat pop song, catchy hook, bright synths",
    "Radio-ready and catchy.",
    ["pop"],
    True,
    115,
    {
        "drums": M["drums_punchy"],
        "bass": M["bass_tight"],
        "keys": M["keys_clean"],
        "lead": M["lead_bright"],
    },
    G["pop-master"],
    mac(65, 70, 55, 65, 45),
)
genre(
    "UK Drill",
    "skull",
    "uk drill beat, sliding 808, dark piano, triplet hats",
    "Dark slides and sharp hats.",
    ["drill", "uk"],
    True,
    142,
    {
        "drums": M["drums_crushed"],
        "bass": M["bass_808"],
        "keys": M["keys_clean"],
        "lead": M["lead_dark"],
    },
    G["drill-master"],
    mac(75, 55, 80, 50, 35),
)
genre(
    "R&B Slow Jam",
    "rose",
    "smooth rnb slow jam, lush chords, soft hip hop drums",
    "Silky late night R&B.",
    ["rnb", "soul"],
    True,
    72,
    {
        "drums": M["drums_lofi"],
        "bass": M["bass_warm"],
        "keys": M["keys_lush"],
        "lead": M["lead_soft"],
    },
    G["r-b-master"],
    mac(40, 70, 60, 50, 60),
)
genre(
    "Afrobeats",
    "sun",
    "afrobeats groove, log drums, house influenced percussion, sunny",
    "Bouncy, sunny groove.",
    ["afrobeats", "dance"],
    True,
    108,
    {
        "drums": M["drums_house"],
        "bass": M["bass_tight"],
        "keys": M["keys_stab"],
        "lead": M["lead_bright"],
    },
    G["pop-master"],
    mac(65, 65, 60, 60, 45),
)
genre(
    "Phonk",
    "car",
    "phonk, cowbell melody, distorted 808, memphis trap drums",
    "Cowbells and distorted 808s.",
    ["phonk", "trap"],
    False,
    130,
    {
        "drums": M["drums_crushed"],
        "bass": M["bass_808"],
        "keys": M["keys_tape"],
        "lead": M["lead_dark"],
    },
    G["drill-master"],
    mac(80, 30, 80, 45, 35),
)
genre(
    "Drum and Bass",
    "wave",
    "liquid drum and bass edm, fast breakbeats, deep sub",
    "Fast breaks, deep sub.",
    ["dnb", "edm"],
    False,
    174,
    {
        "drums": M["drums_punchy"],
        "bass": M["bass_growl"],
        "keys": M["keys_lush"],
        "lead": M["lead_bright"],
    },
    G["edm-master"],
    mac(80, 40, 70, 60, 55),
)
genre(
    "Dubstep",
    "speaker",
    "heavy dubstep edm, wobble bass, half time drums",
    "Wobbles and half-time weight.",
    ["dubstep", "edm"],
    False,
    140,
    {
        "drums": M["drums_crushed"],
        "bass": M["bass_growl"],
        "keys": M["keys_lush"],
        "lead": M["lead_dark"],
    },
    G["edm-master"],
    mac(90, 30, 85, 55, 40),
)
genre(
    "Indie Folk",
    "leaf",
    "indie folk rock, acoustic guitar, warm and intimate",
    "Warm and acoustic.",
    ["indie", "folk"],
    False,
    100,
    {
        "drums": M["drums_jazz"],
        "bass": M["bass_upright"],
        "keys": M["guitar_clean"],
        "lead": M["guitar_clean"],
    },
    G["acoustic-master"],
    mac(40, 70, 45, 55, 50),
)
genre(
    "Metal",
    "horns",
    "heavy metal rock, down tuned riffs, double kick",
    "Down-tuned and heavy.",
    ["metal", "rock"],
    False,
    150,
    {
        "drums": M["drums_crushed"],
        "bass": M["bass_growl"],
        "keys": M["guitar_crunch"],
        "lead": M["guitar_crunch"],
    },
    G["metal-master"],
    mac(95, 55, 60, 55, 25),
)
genre(
    "Gospel Soul",
    "church",
    "gospel soul pop, organ, choir, uplifting",
    "Uplifting organ and choir.",
    ["gospel", "soul"],
    False,
    88,
    {
        "drums": M["drums_punchy"],
        "bass": M["bass_warm"],
        "keys": M["keys_organ"],
        "lead": M["lead_soft"],
    },
    G["r-b-master"],
    mac(60, 75, 55, 55, 65),
)
genre(
    "Chillwave",
    "palm",
    "chillwave synthwave, dreamy, hazy summer",
    "Hazy, dreamy summer.",
    ["chillwave", "synthwave"],
    False,
    95,
    {
        "drums": M["drums_lofi"],
        "bass": M["bass_synthwave"],
        "keys": M["keys_tape"],
        "lead": M["lead_retro"],
    },
    G["lo-fi-master"],
    mac(40, 45, 50, 45, 75),
)
genre(
    "Country Pop",
    "hat",
    "country pop, acoustic strum, steady rock drums",
    "Strummy and sing-along.",
    ["country", "pop"],
    False,
    104,
    {
        "drums": M["drums_rock"],
        "bass": M["bass_tight"],
        "keys": M["guitar_clean"],
        "lead": M["guitar_clean"],
    },
    G["pop-master"],
    mac(55, 70, 50, 60, 45),
)
genre(
    "Reggaeton",
    "maracas",
    "reggaeton dembow pop beat, latin percussion, catchy synth",
    "Dembow bounce.",
    ["reggaeton", "latin"],
    False,
    95,
    {
        "drums": M["drums_punchy"],
        "bass": M["bass_808"],
        "keys": M["keys_stab"],
        "lead": M["lead_bright"],
    },
    G["pop-master"],
    mac(70, 65, 70, 60, 40),
)


# ---------------------------------------------------------------- Easy sliders (macros)
# Each slider is 0..100 with 50 = neutral (the vibe's own sound). A ranged value
# [a, b] is interpolated across the active half: "when": "above" uses 50..100,
# "below" uses 0..50, "both" (default) uses 0..100. "only": "stems" applies when
# the track has stems, "mix" when it is a single stereo file.
MACROS = {
    "version": 1,
    "sliders": [
        {
            "key": "energy",
            "label": "Energy",
            "help": "Calm to hype. Drives drums, compression and grit.",
            "maps": [
                {"scope": "role:drums", "only": "stems", "op": "gain", "value": [-5, 4]},
                {"scope": "role:bass", "only": "stems", "op": "gain", "value": [-2, 2]},
                {
                    "scope": "master",
                    "when": "above",
                    "op": "insert",
                    "fx": {
                        "type": "compressor",
                        "params": {
                            "threshold_db": [-8, -22],
                            "ratio": [1.5, 4],
                            "attack_ms": 25,
                            "release_ms": 150,
                            "makeup_db": [0, 2],
                        },
                    },
                },
                {
                    "scope": "master",
                    "when": "above",
                    "op": "insert",
                    "fx": {"type": "saturation", "params": {"drive_db": [0, 7], "mix": 0.5}},
                },
                {
                    "scope": "master",
                    "only": "mix",
                    "when": "below",
                    "op": "insert",
                    "fx": {
                        "type": "peak",
                        "params": {"freq_hz": 3500, "gain_db": [-3, 0], "q": 0.7},
                    },
                },
            ],
        },
        {
            "key": "vocals",
            "label": "Vocals",
            "help": "Pull the voice back or push it to the front.",
            "maps": [
                {"scope": "roles:vocals,lead", "only": "stems", "op": "gain", "value": [-9, 6]},
                {
                    "scope": "roles:vocals,lead",
                    "only": "stems",
                    "op": "insert",
                    "fx": {
                        "type": "peak",
                        "params": {"freq_hz": 3000, "gain_db": [-2, 3], "q": 0.9},
                    },
                },
                {
                    "scope": "master",
                    "only": "mix",
                    "op": "insert",
                    "fx": {
                        "type": "peak",
                        "params": {"freq_hz": 2500, "gain_db": [-4, 3], "q": 0.8},
                    },
                },
            ],
        },
        {
            "key": "bass",
            "label": "Bass",
            "help": "Thin to heavy low end.",
            "maps": [
                {"scope": "role:bass", "only": "stems", "op": "gain", "value": [-9, 6]},
                {
                    "scope": "master",
                    "op": "insert",
                    "fx": {
                        "type": "lowshelf",
                        "params": {"cutoff_hz": 90, "gain_db": [-5, 5], "q": 0.7},
                    },
                },
            ],
        },
        {
            "key": "brightness",
            "label": "Brightness",
            "help": "Dark and warm to crisp and airy.",
            "maps": [
                {
                    "scope": "master",
                    "op": "insert",
                    "fx": {
                        "type": "highshelf",
                        "params": {"cutoff_hz": 7500, "gain_db": [-6, 6], "q": 0.7},
                    },
                },
                {
                    "scope": "master",
                    "when": "below",
                    "op": "insert",
                    "fx": {"type": "lowpass", "params": {"cutoff_hz": [7000, 20000]}},
                },
            ],
        },
        {
            "key": "space",
            "label": "Space",
            "help": "Dry and close to big and wide.",
            "maps": [
                {
                    "scope": "roles:drums,keys,lead,vocals,guitar,other",
                    "only": "stems",
                    "op": "insert",
                    "fx": {
                        "type": "reverb",
                        "params": {
                            "room_size": [0.3, 0.85],
                            "damping": 0.5,
                            "width": 1.0,
                            "mix": [0.0, 0.3],
                        },
                    },
                },
                {
                    "scope": "master",
                    "only": "mix",
                    "op": "insert",
                    "fx": {
                        "type": "reverb",
                        "params": {
                            "room_size": [0.3, 0.8],
                            "damping": 0.55,
                            "width": 1.0,
                            "mix": [0.0, 0.16],
                        },
                    },
                },
                {
                    "scope": "master",
                    "op": "insert",
                    "fx": {"type": "width", "params": {"width": [0.75, 1.45]}},
                },
            ],
        },
    ],
}


def main() -> None:
    if ROOT.exists():
        for d in ROOT.iterdir():
            if d.is_dir():
                shutil.rmtree(d)
    for p in PRESETS:
        f = ROOT / p["category"] / (p["id"].split("/", 1)[1] + ".json")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(p, indent=2) + "\n", encoding="utf-8")
    (ROOT / "macros").mkdir(parents=True, exist_ok=True)
    (ROOT / "macros" / "easy_sliders.json").write_text(
        json.dumps(MACROS, indent=2) + "\n", encoding="utf-8"
    )
    counts: dict[str, int] = {}
    for p in PRESETS:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    print(f"Wrote {len(PRESETS)} presets: {counts}")


if __name__ == "__main__":
    main()
