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


def test_plans_dir_edit_blocks(ws: Path) -> None:
    """H2: a tracked change under .agents/build/plans/ vs the step base is a block."""
    wt = worktree(ws)
    brief = wt / ".agents" / "build" / "plans" / "t.steps.yaml"
    brief.write_text(brief.read_text() + "# widened\n")
    (wt / "src" / "a.txt").write_text("work\n")
    commit_all(wt)
    blocked, f = score(wt, TITLE)
    assert f["plans_dir_edit"] == [".agents/build/plans/t.steps.yaml"]
    assert blocked


def test_no_plans_dir_edit_passes(ws: Path) -> None:
    """H2: an ordinary step that leaves the plans dir alone is not blocked by it."""
    wt = worktree(ws)
    (wt / "src" / "a.txt").write_text("work\n")
    commit_all(wt)
    blocked, f = score(wt, TITLE)
    assert f["plans_dir_edit"] == []
    assert not blocked


def test_report_mismatch_blocks(ws: Path) -> None:
    """H4: a report that claims exit 0 against a measured red gate blocks."""
    side = ws / ".agents" / "build" / "plans" / "t.steps.yaml"
    side.write_text(side.read_text().replace('gate_cmd: "true"', 'gate_cmd: "false"'))
    git(ws, "add", "-A")
    git(ws, "commit", "-qm", "chore: red gate")
    wt = worktree(ws)
    (wt / "src" / "a.txt").write_text("work\n")
    (wt / ".agents").mkdir(exist_ok=True)
    (wt / ".agents" / "phase-1-work.md").write_text("## Validation\n\nExit: 0\n\n## Deviations\n\nnone\n")
    commit_all(wt)
    blocked, f = score(wt, TITLE)
    assert "report claims all commands exit 0; measured gate is red" in f["report_mismatch"]
    assert blocked


def test_report_mismatch_blocks_on_green_gate(ws: Path) -> None:
    """H4: the mismatch blocks on its own, not only when the gate is already red."""
    side = ws / ".agents" / "build" / "plans" / "t.steps.yaml"
    side.write_text(side.read_text().replace("gate_cmd: \"true\"", "gate_cmd: \"echo 'lint ran: 3 issues.'\""))
    git(ws, "add", "-A")
    git(ws, "commit", "-qm", "chore: lint-shaped gate")
    wt = worktree(ws)
    (wt / "src" / "a.txt").write_text("work\n")
    (wt / ".agents").mkdir(exist_ok=True)
    (wt / ".agents" / "phase-1-work.md").write_text("## Validation\n\nlint clean, 0 issues.\n\n## Deviations\n\nnone\n")
    commit_all(wt)
    blocked, f = score(wt, TITLE)
    assert f["gate"]["rc"] == 0
    assert "report claims 0 issues; measured 3" in f["report_mismatch"]
    assert blocked


def test_missing_report_alone_does_not_block(ws: Path) -> None:
    """H4: the sole entry "no report file" stays a non-blocking note."""
    wt = worktree(ws)
    (wt / "src" / "a.txt").write_text("work\n")
    commit_all(wt)
    blocked, f = score(wt, TITLE)
    assert f["report_mismatch"] == ["no report file"]
    assert not blocked
