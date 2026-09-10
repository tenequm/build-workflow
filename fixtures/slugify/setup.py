#!/usr/bin/env python3
"""Materialize the slugify fixture as a ready-to-run build workspace.

    setup.py <target dir> [--analyst-model M] [--resolver-model M] [--judge agy|claude]

Produces what /build-plan's WORKSPACE and CUT stages produce by hand: a primary
checkout, a linked workspace on `feat/slugify`, a committed seed, a sign-off
commit whose sha is pinned into the sidecar, disabled Git hooks, and a
workspace.json. Prints the readiness and run commands. Nothing here is a skill;
it exists so a workflow change can be verified end to end in one command.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent
SLUG = "slugify"
BRANCH = f"feat/{SLUG}"
RUN = f".agents/build/runs/{SLUG}"


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--analyst-model", default="claude-sonnet-5")
    parser.add_argument("--resolver-model", default="gpt-5.6-terra")
    parser.add_argument("--role", choices=("analyst", "resolver"), default="analyst")
    parser.add_argument("--judge", choices=("claude", "agy"), default="claude")
    parser.add_argument("--judge-adapter", help="argv for --judge agy, space separated")
    args = parser.parse_args()

    target = args.target.resolve()
    if target.exists():
        raise SystemExit(f"refusing to overwrite an existing path: {target}")
    if args.judge == "agy" and not args.judge_adapter:
        raise SystemExit("--judge agy needs --judge-adapter '<path to the ACP server>'")

    shutil.copytree(FIXTURE / "tree", target)
    git(target, "init", "-q", "-b", "main")

    seed = target / "bernstein.yaml"
    seed.write_text(
        seed.read_text()
        .replace("model: gpt-5.6-terra", f"model: {args.resolver_model}")
        .replace("model: gpt-5.6-luna", f"model: {args.resolver_model}")
        .replace("model: claude-sonnet-5", f"model: {args.analyst_model}")
    )
    # Swap the executor step's role only. Its pinned fix keeps the other role, so a
    # phase never carries two steps on one role, and a plain replace would hit both.
    plan = target / f".agents/build/plans/{SLUG}.yaml"
    executor, fix = ("analyst", "resolver") if args.role == "analyst" else ("resolver", "analyst")
    text, swapped = re.subn(
        r"(- title: 'implement: slugify'\n(?:.*\n)*?\s+role: )\w+",
        lambda m: m.group(1) + executor,
        plan.read_text(),
        count=1,
    )
    text, fixed = re.subn(
        r"(- title: 'fix-implement: repair verified findings'\n(?:.*\n)*?\s+role: )\w+",
        lambda m: m.group(1) + fix,
        text,
        count=1,
    )
    if (swapped, fixed) != (1, 1):
        raise SystemExit("fixture plan does not have the expected step/fix role lines")
    plan.write_text(text)

    git(target, "add", "-A")
    git(target, "commit", "-qm", "chore: textkit fixture")
    signoff = git(target, "rev-parse", "HEAD")

    workspace = target / ".claude/worktrees" / SLUG
    git(target, "worktree", "add", "-q", "-b", BRANCH, str(workspace), signoff)

    sidecar = workspace / f".agents/build/plans/{SLUG}.steps.yaml"
    text = sidecar.read_text().replace("<SIGNOFF>", signoff)
    if args.judge == "agy":
        argv = json.dumps(args.judge_adapter.split())
        text = text.replace("    transport: claude\n", "    transport: acp\n")
        text = text.replace(
            "    adapter_argv:\n    - npx\n    - --yes\n"
            "    - '@agentclientprotocol/claude-agent-acp@0.60.0'\n",
            f"    adapter_argv: {argv}\n",
        )
        text = text.replace("    model: claude-sonnet-5\n", "    model: gemini-3.7-flash-low\n")
    sidecar.write_text(text)
    doc = workspace / f"docs/plans/2609-10-{SLUG}/plan.md"
    doc.write_text(doc.read_text().replace("<SIGNOFF>", signoff).replace("<ROLE>", args.role))

    (workspace / RUN).mkdir(parents=True, exist_ok=True)
    (workspace / RUN / "workspace.json").write_text(
        json.dumps(
            {
                "path": str(workspace),
                "branch": BRANCH,
                "base": signoff,
                "base_branch": "main",
                "primary": str(target),
            }
        )
    )
    hooks = FIXTURE.parents[1] / "skills/build-plan/scripts/workspace-hooks.py"
    subprocess.run(
        [sys.executable, str(hooks), "disable", "--root", str(workspace), "--run", str(workspace / RUN)],
        check=True,
    )
    git(workspace, "add", "-A")
    git(workspace, "commit", "-qm", "chore(build): pin the fixture sign-off")

    plans = FIXTURE.parents[1] / "skills/build-plan/scripts/plan-check.py"
    runner = FIXTURE.parents[1] / "skills/build-run/scripts/build-operator.py"
    print(
        f"workspace: {workspace}\n"
        f"signoff:   {signoff}\n\n"
        "Run these with the interpreter from the installed Bernstein uv tool\n"
        "(`uv tool dir` then bernstein/bin/python):\n\n"
        f"  PYTHONPATH={plans.parent} <python> {plans} \\\n"
        f"    {workspace}/docs/plans/2609-10-{SLUG} --repo {workspace} \\\n"
        f"    --machine {workspace}/.agents/build/plans/{SLUG}.yaml\n\n"
        f"  <python> {runner} run --root {workspace} \\\n"
        f"    --plan {workspace}/.agents/build/plans/{SLUG}.yaml\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
