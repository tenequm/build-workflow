"""CLI hardening: fix-noop (H8), resume classification (H9), triage classification (H10).

    uv run --with pytest pytest -q
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from bernstein_herdr.cli import fix_noop

FIX_TITLE = "fix-1: judge findings on phase-1"

PLAN_YAML = """\
name: t
stages:
  - name: "phase-1: work"
    steps:
      - title: "phase-1: work"
        files: ["src/**"]
  - name: "fix-1: judge findings on phase-1"
    depends_on: ["phase-1: work"]
    steps:
      - title: "fix-1: judge findings on phase-1"
        files: ["src/**"]
"""

SIDECAR_YAML = """\
defaults:
  base: build/x
  gate_cmd: "true"
steps:
  "fix-1: judge findings on phase-1":
    report: .agents/fix-1.md
    fixes: "phase-1: work"
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def ws(tmp_path: Path) -> Path:
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


def verdict(root: Path, **kv: object) -> Path:
    d = root / ".agents" / "build" / "runs" / "t" / "judge" / "phase-1-work"
    d.mkdir(parents=True, exist_ok=True)
    v = {"verdict": "merge as-is", "certain": 0, "plausible": 1, "counts_declared": True, **kv}
    (d / "verdict.json").write_text(json.dumps(v))
    return d / "verdict.json"


def worktree(root: Path) -> Path:
    wt = root / ".sdd" / "worktrees" / "fx"
    git(root, "worktree", "add", "-q", "-b", "agent/fx", str(wt), "build/x")
    return wt


def test_fix_noop_writes_and_commits_the_report(ws: Path, capsys) -> None:
    verdict(ws)
    wt = worktree(ws)
    assert fix_noop(wt, FIX_TITLE) == 0
    assert "DONE" in capsys.readouterr().out
    report = (wt / ".agents" / "fix-1.md").read_text()
    assert "Verdict: merge as-is" in report
    assert "Certain: 0" in report and "Plausible: 1" in report
    assert "## Deviations\n\nnone" in report
    assert "no-op" in git(wt, "log", "-1", "--format=%s")


def test_fix_noop_refuses_certain_defects(ws: Path, capsys) -> None:
    verdict(ws, certain=2)
    wt = worktree(ws)
    assert fix_noop(wt, FIX_TITLE) == 1
    assert "take the fix path" in capsys.readouterr().out
    assert not (wt / ".agents" / "fix-1.md").exists()


def test_fix_noop_refuses_undeclared_counts(ws: Path, capsys) -> None:
    verdict(ws, counts_declared=False)
    wt = worktree(ws)
    assert fix_noop(wt, FIX_TITLE) == 1
    assert "refusal path" in capsys.readouterr().out
    assert not (wt / ".agents" / "fix-1.md").exists()


def test_fix_noop_refuses_illegal_verdict_and_missing_file(ws: Path, capsys) -> None:
    wt = worktree(ws)
    assert fix_noop(wt, FIX_TITLE) == 1
    assert "no judge verdict" in capsys.readouterr().out
    verdict(ws, verdict="unclear")
    assert fix_noop(wt, FIX_TITLE) == 1
    assert "legal strings" in capsys.readouterr().out
    assert not (wt / ".agents" / "fix-1.md").exists()


def test_fix_noop_refuses_a_non_fix_step(ws: Path, capsys) -> None:
    verdict(ws)
    wt = worktree(ws)
    assert fix_noop(wt, "phase-1: work") == 1
    assert "declares no `fixes:`" in capsys.readouterr().out
