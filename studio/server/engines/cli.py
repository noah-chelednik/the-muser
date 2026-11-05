"""Command line helper used by the setup scripts.

Examples::

    python -m studio.server.engines.cli hardware
    python -m studio.server.engines.cli install --core
    python -m studio.server.engines.cli install --extras separate,denoise
    python -m studio.server.engines.cli status
"""

from __future__ import annotations

import argparse
import sys

from . import hardware, installer, registry, selector
from .errors import FriendlyError

# Friendly extra names for setup flags -> registry engine keys.
EXTRAS: dict[str, list[str]] = {
    "separate": ["audio-separator"],
    "demucs": ["demucs"],
    "denoise": ["deepfilternet"],
    "optional": ["audio-separator", "demucs", "deepfilternet"],
}


def core_keys() -> list[str]:
    return [s.key for s in registry.ENGINES if s.tier == "core"]


def cmd_hardware(_: argparse.Namespace) -> int:
    hw = hardware.detect()
    d = hw.to_dict()
    print(f"  OS: {d['os']}   CPU threads: {d['cpu_count']}   RAM: {d['ram_gb']:.0f} GB")
    if hw.has_gpu:
        print(f"  GPU: {d['gpu']} ({d['vram_gb']:.0f} GB VRAM)   tier: {d['tier']}")
    else:
        print("  GPU: none detected   tier: cpu (all Easy mode tools still work)")
    if hw.compute_cap:
        print(
            f"  Compute capability: {hw.compute_cap}   bf16: {'yes' if hw.bf16 else 'no (fp16 used)'}"
        )
    for n in hw.notes:
        print(f"  Note: {n}")
    print("\n  Heavy AI models for this PC (install from Studio > Engines):")
    marks = {
        "fits": "[ YES ]",
        "fits-reduced": "[ YES ]",
        "cpu": "[ cpu ]",
        "tight": "[tight]",
        "too-big": "[ no  ]",
        "no-gpu": "[ no  ]",
    }
    for r in selector.recommendations(hw):
        mark = marks.get(r["status"], "[ no  ]")
        lic = {"yes": "commercial OK", "conditional": "check license", "no": "non-commercial"}[
            r["commercial"]
        ]
        need = (
            f"{r['min_vram_gb']:g}-{r['vram_full_gb']:g} GB"
            if r["vram_full_gb"] != r["min_vram_gb"]
            else f"{r['min_vram_gb']:g} GB"
        )
        label = "" if r["status"] in ("fits", "fits-reduced") else f"{r['label']}: "
        print(f"   {mark} {r['name']:<28} {need:<9} {lic:<15} {label}{r['reason']}")
    print(
        "\n  [ YES ] recommended   [tight] may run, close other GPU apps   [ no ] not recommended"
    )
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    for spec in registry.ENGINES:
        h = registry.health(spec)
        mark = "OK " if h["installed"] else "-- "
        print(f"  {mark} {spec.key:<20} {spec.tier:<9} {h['detail']}")
    return 0


def cmd_install(a: argparse.Namespace) -> int:
    keys: list[str] = []
    if a.core:
        keys += core_keys()
    for name in filter(None, (a.extras or "").split(",")):
        name = name.strip().lower()
        if name in EXTRAS:
            keys += EXTRAS[name]
        else:
            try:
                registry.get(name)
            except KeyError:
                print(f"  [WARN] Unknown extra '{name}'. Choices: {', '.join(EXTRAS)}")
                continue
            keys.append(name)
    failed = []
    for key in dict.fromkeys(keys):
        spec = registry.get(key)
        if registry.health(spec)["installed"] and not a.force:
            print(f"  [ OK ] {spec.name} already installed")
            continue
        print(f"  Installing {spec.name} ...")
        try:
            res = installer.install(key, log=(print if a.verbose else lambda _s: None))
        except FriendlyError as e:
            print(f"  [WARN] {e}")
            failed.append(spec.name)
            continue
        if res["installed"]:
            print(f"  [ OK ] {spec.name}")
        else:
            print(f"  [WARN] {spec.name} installed but its health check did not pass yet")
            failed.append(spec.name)
    if failed:
        print("  These can be retried later from Studio > Engines: " + ", ".join(failed))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="studio-engines", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hardware", help="detect hardware and recommend models").set_defaults(
        fn=cmd_hardware
    )
    sub.add_parser("status", help="show every engine and whether it is installed").set_defaults(
        fn=cmd_status
    )
    pi = sub.add_parser("install", help="install core tools and optional extras")
    pi.add_argument("--core", action="store_true", help="install the core tool set")
    pi.add_argument("--extras", default="", help="comma list: " + ", ".join(EXTRAS))
    pi.add_argument("--force", action="store_true")
    pi.add_argument("-v", "--verbose", action="store_true")
    pi.set_defaults(fn=cmd_install)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
