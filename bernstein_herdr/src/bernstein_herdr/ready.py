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

import yaml

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
    base = plan.sidecar.get("defaults", {}).get("base", "HEAD")

    def fail(msg: str) -> None:
        nonlocal ok
        ok = False
        lines.append(f"FAIL {msg}")

    # A symlinked agent-instruction file at the root makes Bernstein's
    # `validate_worktree_isolation` refuse the repo ("points into parent repo mutable
    # state") even when the target is inside the same worktree. The refusal is silent:
    # `spawner_core.py:4489` falls back to running EVERY executor at the ROOT on an
    # `agent/<session>` branch, where the merge target is that same branch and nothing
    # ever lands on the integration branch (measured, gopost 1a replay). The adapter
    # refuses that spawn per step; this catches the whole run before a token is spent.
    for name in ("CLAUDE.md", "AGENTS.md"):
        f = plan.root / name
        if f.is_symlink():
            fail(f"{name} at the repo root is a symlink -> {f.readlink()}; Bernstein refuses worktree "
                 f"isolation for it and silently runs every executor at the root on an agent branch, "
                 f"with no merge back. Make it a real file (`cp --remove-destination` the target over it, "
                 f"or copy the content and drop the link) and commit.")
        elif f.exists():
            lines.append(f"PASS {name} is a regular file")

    # Codex takes no reasoning-effort flag: `codex exec` reads `model_reasoning_effort`
    # from ~/.codex/config.toml (adapters/codex.py:105-125, argv measured 2026-09-02), so
    # the effort lock lives in a per-machine file OUTSIDE the repo and another machine
    # silently runs the whole plan at `medium`.
    codex_cfg = Path.home() / ".codex" / "config.toml"
    codex_text = codex_cfg.read_text() if codex_cfg.exists() else ""
    if re.search(r'^\s*model_reasoning_effort\s*=\s*"high"', codex_text, re.M):
        lines.append(f"PASS {codex_cfg}: model_reasoning_effort = \"high\"")
    else:
        fail(f'{codex_cfg} does not set model_reasoning_effort = "high"; codex exec takes no effort flag and '
             f"every codex step in this plan would run at the default effort. Add the line and rerun.")

    # Role is the durable dispatch key: a per-step `cli:` is not in Bernstein's plan schema
    # and was measured losing to the role policy on the first retry, while the role policy
    # resolved correctly on every spawn. A role with no policy entry falls back to the
    # seed's top-level `cli:` and whatever model that adapter defaults to.
    seed_path = plan.root / "bernstein.yaml"
    policy = (yaml.safe_load(seed_path.read_text()) or {}).get("role_model_policy") or {} if seed_path.exists() else {}
    roles = {s.get("role") for s in plan.steps() if s.get("role")}
    for role in sorted(roles):
        if role in policy:
            lines.append(f"PASS role_model_policy[{role}] = {policy[role]}")
        else:
            fail(f"plan uses role {role!r} with no role_model_policy entry in bernstein.yaml; "
                 f"its cli, model and effort would fall back to the seed default")
    if not roles:
        fail("no step in the plan declares a `role:`; dispatch has nothing to resolve")

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
    # Bernstein content-addresses plan-level `context_files` against the worker's
    # WORKTREE at spawn, before the adapter writes anything into it -- measured
    # 2026-09-02: a brief listed here came back `{"reason_code": "missing"}` in the run
    # journal's context.files_attached for both workers. Only a path in the base tree
    # reaches a worker, so anything else is a silent no-op and fails here.
    for c in plan.data.get("context_files") or []:
        in_base = subprocess.run(["git", "cat-file", "-e", f"{base}:{c}"], cwd=plan.root, capture_output=True, check=False).returncode == 0
        if in_base:
            lines.append(f"PASS context_files: {c}")
        else:
            fail(f"context_files: {c} is not in base {base}; every worker records it `missing` (run-dir briefs included)")
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
