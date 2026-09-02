"""Readiness gate: mechanical checks over a plan before any executor starts.

Writes <run>/readiness/ledger.md and <run>/readiness/pins.json (spec, plan, brief
hashes the adapter refuses to start without). Critic rounds are the skill's job;
this file is the part that is a command.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import tempfile
from pathlib import Path

from bernstein_herdr import ledger
from bernstein_herdr.plan import Plan, load_plan, pinned_hashes

SECTION_CITE = re.compile(r"\b(?:DESIGN|spec)\s+(\d+(?:\.\d+)*)\b")
CODE_BLOCK = re.compile(r"```\n(.*?)```", re.S)


def _spec_sections(spec: Path) -> set[str]:
    if not spec.exists():
        return set()
    return {m.group(1) for m in re.finditer(r"^#+\s*(\d+(?:\.\d+)*)\b", spec.read_text(), re.M)}


def check(plan: Plan, run_validation: bool = True) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True

    def fail(msg: str) -> None:
        nonlocal ok
        ok = False
        lines.append(f"FAIL {msg}")

    v = subprocess.run(["bernstein", "plan", "validate", str(plan.path)], capture_output=True, text=True, check=False)
    lines.append(f"{'PASS' if v.returncode == 0 else 'FAIL'} bernstein plan validate: {v.stdout.strip()[-200:] or v.stderr.strip()[-200:]}")
    ok &= v.returncode == 0

    sections = _spec_sections(plan.root / "docs" / "spec.md")
    for stage in plan.data.get("stages", []):
        owned: dict[str, str] = {}
        for raw in stage.get("steps", []):
            step = plan.step(raw["title"])
            if not step.brief.exists():
                fail(f"{step.slug}: brief missing at {step.brief}")
                continue
            text = step.brief.read_text()
            for g in step.files:
                if not any(True for _ in plan.root.glob(g)) and not re.search(r"[*?\[]", g) and not (plan.root / g).exists():
                    lines.append(f"NOTE {step.slug}: allowlisted path does not exist yet (new file?): {g}")
            for g in step.files:
                for other_title, other_g in owned.items():
                    if g == other_g or fnmatch.fnmatch(g, other_g) or fnmatch.fnmatch(other_g, g):
                        fail(f"{step.slug}: owns {g} which sibling step {other_title!r} also owns ({other_g})")
                owned[step.title] = g
            for sec in SECTION_CITE.findall(text):
                if sections and sec not in sections and sec.split(".")[0] not in sections:
                    fail(f"{step.slug}: cites spec section {sec} which does not exist")
            if not re.search(r"^##\s*Report", text, re.M) or "Deviations" not in text:
                fail(f"{step.slug}: brief lacks a Report section with a Deviations rule")
            if not re.search(r"^##\s*Items", text, re.M):
                fail(f"{step.slug}: brief lacks an Items section")
            if len(text) > 16000:
                fail(f"{step.slug}: brief is {len(text)} chars; over the 16k cap (length hurts resolve rate)")
            if run_validation:
                m = re.search(r"##\s*Validation.*?```\n(.*?)```", text, re.S)
                if not m:
                    fail(f"{step.slug}: brief has no Validation code block")
                else:
                    with tempfile.TemporaryDirectory() as tmp:
                        wt = Path(tmp) / "base"
                        subprocess.run(["git", "worktree", "add", "--detach", str(wt), step.base], cwd=plan.root, capture_output=True, check=True)
                        try:
                            for cmd in [c for c in m.group(1).splitlines() if c.strip() and not c.startswith("#")]:
                                r = subprocess.run(["bash", "-lc", cmd], cwd=wt, capture_output=True, text=True, check=False)
                                lines.append(f"{'PASS' if r.returncode == 0 else 'RED '} {step.slug} on base {step.base}: `{cmd[:80]}` rc={r.returncode}")
                        finally:
                            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=plan.root, capture_output=True, check=False)
            if step.judges and step.judges not in {s["title"] for s in plan.steps()}:
                fail(f"{step.slug}: judges {step.judges!r} which is not a step")
    for s in plan.steps():
        if plan.step(s["title"]).judge == "required" and not s.get("completion_signals"):
            lines.append(f"NOTE {s['title']}: judge required but no completion_signals (the judge gate runs from bernstein.yaml pipeline)")
    return ok, lines


def write(plan: Plan, ok: bool, lines: list[str]) -> Path:
    rd = plan.run_dir / "readiness"
    rd.mkdir(parents=True, exist_ok=True)
    pins = pinned_hashes(plan)
    (rd / "pins.json").write_text(json.dumps(pins, indent=2))
    (rd / "ledger.md").write_text(f"# Readiness {ledger.now()} plan={plan.path.name} ok={ok}\n\n" + "\n".join(f"- {l}" for l in lines) + "\n\nPins:\n" + "\n".join(f"- {k}: {v}" for k, v in pins.items()) + "\n")
    ledger.note(plan.run_dir, f"readiness ok={ok} checks={len(lines)} pins={len(pins)}")
    return rd / "ledger.md"


def main(argv: list[str]) -> int:
    plan_path = Path(argv[argv.index("--plan") + 1]) if "--plan" in argv else None
    plan = load_plan(plan_path)
    ok, lines = check(plan, run_validation="--no-validate" not in argv)
    out = write(plan, ok, lines)
    print("\n".join(lines))
    print(f"\n{'READY' if ok else 'NOT READY'} -> {out}")
    return 0 if ok else 1
