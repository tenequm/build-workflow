"""Each skill is installed alone, so a skill that reaches into a sibling breaks.

AGENTS.md states the law; this is the check. A skill's own files may never name
another skill's directory - templates are copied into both, and shared helpers are
vendored by `bernstein_operator/scripts/sync-skill-code.py`, not imported across.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".toml"}


def violations() -> list[str]:
    names = sorted(path.name for path in SKILLS.iterdir() if path.is_dir())
    found = []
    for skill in names:
        others = re.compile(r"skills/(" + "|".join(re.escape(n) for n in names if n != skill) + ")/")
        for path in sorted((SKILLS / skill).rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                match = others.search(line)
                if match:
                    rel = path.relative_to(ROOT)
                    found.append(f"{rel}:{number} reads a sibling skill: {match.group(0)}")
    return found


def main() -> int:
    found = violations()
    for line in found:
        print(line, file=sys.stderr)
    if found:
        print(f"{len(found)} cross-skill reference(s); copy the file instead", file=sys.stderr)
        return 1
    print("skill isolation: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
