"""Scorer hardening: frozen-base plan resolution (H1), plans-dir edit block (H2),
report-mismatch block (H4), pin enforcement (H5), gate timing fields (H12).

    uv run --with pytest pytest -q
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bernstein_herdr.gates.scorer import score

TITLE = "phase-1: work"

PLAN_YAML = """\
name: t
stages:
  - name: "phase-1: work"
    steps:
      - title: "phase-1: work"
        files: ["src/**"]
"""

SIDECAR_YAML = """\
defaults:
  base: build/x
  gate_cmd: "true"
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """A workspace root on build/x with a committed plan, sidecar and one source file."""
    root = tmp_path / "ws"
    (root / ".agents" / "build" / "plans").mkdir(parents=True)
    (root / "src").mkdir()
    git(root, "init", "-q", "-b", "build/x")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / ".agents" / "build" / "plans" / "t.yaml").write_text(PLAN_YAML)
    (root / ".agents" / "build" / "plans" / "t.steps.yaml").write_text(SIDECAR_YAML)
    (root / "src" / "a.txt").write_text("base\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: base")
    return root


def worktree(root: Path, name: str = "w1") -> Path:
    wt = root / ".sdd" / "worktrees" / name
    git(root, "worktree", "add", "-q", "-b", f"agent/{name}", str(wt), "build/x")
    return wt


def commit_all(wt: Path, msg: str = "feat: work") -> None:
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", msg)


def test_frozen_ref_beats_worktree_allowlist_widening(ws: Path) -> None:
    """H1: an executor that widens the allowlist in its own tree is judged by the frozen one."""
    git(ws, "update-ref", "refs/build/base/t", git(ws, "rev-parse", "HEAD"))
    wt = worktree(ws)
    plan = wt / ".agents" / "build" / "plans" / "t.yaml"
    plan.write_text(plan.read_text().replace('["src/**"]', '["src/**", "evil/**"]'))
    (wt / "evil").mkdir()
    (wt / "evil" / "x.txt").write_text("out of scope\n")
    commit_all(wt)
    blocked, f = score(wt, TITLE)
    assert f["plan_source"] == "frozen_base"
    assert "evil/x.txt" in f["allowlist_violations"]
    assert blocked


def test_missing_ref_keeps_working_copy_plan(ws: Path) -> None:
    """H1: pre-run (no refs/build/base/<slug>) the root working-copy plan stands.

    The gate reads the plan from the workspace root, which merges (or a root-level
    edit) can rewrite; without the frozen ref a widened allowlist there is honored.
    """
    plan = ws / ".agents" / "build" / "plans" / "t.yaml"
    plan.write_text(plan.read_text().replace('["src/**"]', '["src/**", "evil/**"]'))
    wt = worktree(ws)
    (wt / "evil").mkdir()
    (wt / "evil" / "x.txt").write_text("in scope per the widened working copy\n")
    commit_all(wt)
    _, f = score(wt, TITLE)
    assert f["plan_source"] == "worktree"
    assert "evil/x.txt" not in f["allowlist_violations"]


def test_frozen_ref_beats_root_working_copy_widening(ws: Path) -> None:
    """H1: the same root-side widening is inert once the ref is frozen."""
    git(ws, "update-ref", "refs/build/base/t", git(ws, "rev-parse", "HEAD"))
    plan = ws / ".agents" / "build" / "plans" / "t.yaml"
    plan.write_text(plan.read_text().replace('["src/**"]', '["src/**", "evil/**"]'))
    wt = worktree(ws)
    (wt / "evil").mkdir()
    (wt / "evil" / "x.txt").write_text("out of scope per the frozen plan\n")
    commit_all(wt)
    blocked, f = score(wt, TITLE)
    assert f["plan_source"] == "frozen_base"
    assert "evil/x.txt" in f["allowlist_violations"]
    assert blocked
