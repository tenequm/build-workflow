"""Vendor admission helpers so independently installed skills are self-contained."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ("__init__", "admission", "spec", "storage", "processes", "readiness")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name in FILES:
        source = ROOT / "skills/build-run/scripts/operator_driver" / f"{name}.py"
        dest = ROOT / "skills/build-plan/scripts/operator_driver" / f"{name}.py"
        if args.check:
            if not dest.exists() or dest.read_bytes() != source.read_bytes():
                raise SystemExit(f"vendored skill code diverged: {name}; run just fix")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
    source = ROOT / "skills/build-run/scripts/workspace-hooks.py"
    for skill in ("build-plan", "build-close"):
        dest = ROOT / "skills" / skill / "scripts/workspace-hooks.py"
        if args.check:
            if not dest.exists() or dest.read_bytes() != source.read_bytes():
                raise SystemExit(f"vendored hook helper diverged: {skill}; run just fix")
        else:
            dest.write_bytes(source.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
