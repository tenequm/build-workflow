#!/usr/bin/env python3
"""Deterministic plan checks that otherwise cost a critic round.

    plan-check.py <plan dir> [--repo <root>]

facts: every `| claim | path:line | needle |` row in facts.md must still hold: the
file exists, the line exists, and the needle is on that line. A NOTE says HEAD moved
past `pinned: <sha>`; a FAIL is a stale or wrong fact.

surface: every line of the fenced `surface` block in plan.md,
`<phase> :: <allowlist globs> :: <rg regex>`, is run as `rg -l` over the repo; a hit
outside the phase's globs is a FAIL, because that phase's gate cannot pass inside its
allowlist. Only source files count: paths under the plan directory, `.agents/`,
`.sdd/` and `docs/` are ignored.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROW = re.compile(r"^\|\s*(?P<claim>[^|]+?)\s*\|\s*(?P<path>[^|:]+):(?P<line>\d+)\s*\|\s*(?P<needle>.+?)\s*\|\s*$")
SURFACE = re.compile(r"```surface\n(.*?)```", re.S)
IGNORED = (".agents/", ".sdd/", "docs/", ".claude/")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    plan_dir = Path(args[0]).resolve()
    repo = Path(args[args.index("--repo") + 1]).resolve() if "--repo" in args else git_root(plan_dir)
    fail = 0
    fail += check_facts(plan_dir / "facts.md", repo)
    fail += check_surface(plan_dir / "plan.md", repo)
    print("plan-check: clean" if not fail else f"plan-check: {fail} FAIL")
    return 1 if fail else 0


def git_root(start: Path) -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start, capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def check_facts(facts: Path, repo: Path) -> int:
    if not facts.exists():
        print(f"NOTE no {facts.name}; facts verifier skipped")
        return 0
    text = facts.read_text()
    m = re.search(r"^pinned:\s*([0-9a-f]{7,40})", text, re.M)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False).stdout.strip()
    if not m:
        print("FAIL facts.md has no `pinned: <sha>` first line")
        return 1
    if not head.startswith(m.group(1)):
        print(f"NOTE HEAD {head[:12]} is not the pinned {m.group(1)[:12]}; facts may be stale")
    rows = [ROW.match(line) for line in text.splitlines()]
    rows = [r for r in rows if r and r.group("path") not in ("path", "where", "---")]
    fail = 0
    for r in rows:
        path = repo / r.group("path").strip()
        n = int(r.group("line"))
        if not path.exists():
            print(f"FAIL fact `{r.group('claim')}`: {r.group('path')} does not exist")
            fail += 1
            continue
        lines = path.read_text(errors="replace").splitlines()
        if n > len(lines):
            print(f"FAIL fact `{r.group('claim')}`: {r.group('path')} has {len(lines)} lines, no line {n}")
            fail += 1
        elif r.group("needle") not in lines[n - 1]:
            print(f"FAIL fact `{r.group('claim')}`: {r.group('path')}:{n} does not contain `{r.group('needle')}`")
            fail += 1
    print(f"{'PASS' if not fail else 'FAIL'} facts: {len(rows)} rows, {fail} stale")
    return fail


def check_surface(plan: Path, repo: Path) -> int:
    if not plan.exists():
        print(f"FAIL {plan} missing")
        return 1
    m = SURFACE.search(plan.read_text())
    if not m:
        print("NOTE plan.md has no fenced `surface` block; surface check skipped")
        return 0
    fail = 0
    for raw in m.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in raw.split("::")]
        if len(parts) != 3:
            print(f"FAIL surface line is not `<phase> :: <globs> :: <regex>`: {raw}")
            fail += 1
            continue
        phase, globs, regex = parts
        globs = globs.split()
        r = subprocess.run(["rg", "-l", "-e", regex, "."], cwd=repo, capture_output=True, text=True, check=False)
        hits = [h[2:] if h.startswith("./") else h for h in r.stdout.splitlines()]
        hits = [h for h in hits if not h.startswith(IGNORED)]
        outside = [h for h in hits if not any(fnmatch.fnmatch(h, g) or fnmatch.fnmatch(h, g.rstrip("*") + "*") for g in globs)]
        if outside:
            print(f"FAIL surface {phase}: `{regex}` matches outside its allowlist: {', '.join(outside[:8])}"
                  + (f" (+{len(outside) - 8})" if len(outside) > 8 else ""))
            fail += 1
        else:
            print(f"PASS surface {phase}: {len(hits)} file(s), all inside allowlist")
    return fail


if __name__ == "__main__":
    sys.exit(main())
