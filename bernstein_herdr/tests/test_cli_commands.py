"""CLI hardening: fix-noop (H8), resume classification (H9), triage classification (H10).

    uv run --with pytest pytest -q
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from bernstein_herdr.cli import classify, completed_steps, fix_noop

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


# --- H9: completed_steps classification ------------------------------------

def row(**kv: object) -> dict:
    return {"gate": "scorer", "evidence": "verified", "blocked": False, "step": "phase-1", **kv}


def test_completed_steps_basic(tmp_path: Path) -> None:
    rows = [row(archive="reports/phase-1/t1-abc123abc123")]
    assert completed_steps(rows, tmp_path, lambda sha: True) == {"phase-1"}
    assert completed_steps(rows, tmp_path, lambda sha: False) == set()


def test_completed_steps_blocked_or_unverified_rows_do_not_count(tmp_path: Path) -> None:
    rows = [row(blocked=True), row(evidence="claimed"), row(gate="judge"),
            row(step=""), {"gate": "scorer"}]
    assert completed_steps(rows, tmp_path, lambda sha: True) == set()


def test_completed_steps_judge_rows_mark_the_judge_not_the_phase(tmp_path: Path) -> None:
    rows = [{"gate": "judge_step", "evidence": "verified", "block": False, "step": "phase-1"}]
    assert completed_steps(rows, tmp_path, lambda sha: True) == {"judge:phase-1"}
    rows[0]["block"] = True
    assert completed_steps(rows, tmp_path, lambda sha: True) == set()


def test_completed_steps_sha_from_reports_dir(tmp_path: Path) -> None:
    d = tmp_path / "phase-1" / "t1-deadbeef1234"
    d.mkdir(parents=True)
    rows = [row()]  # no archive key on the row itself
    assert completed_steps(rows, tmp_path, lambda sha: sha == "deadbeef1234") == {"phase-1"}
    assert completed_steps(rows, tmp_path, lambda sha: False) == set()


def test_completed_steps_no_sha_anywhere_completes_without_ancestry(tmp_path: Path) -> None:
    hits: list[str] = []
    assert completed_steps([row()], tmp_path, hits.append) == {"phase-1"}
    assert hits == []


# --- H10: triage classification ---------------------------------------------

PIDS = [(123, "bernstein run ...")]


def test_classify_branch_loss_takes_precedence() -> None:
    verdict, reasons = classify({
        "renames": ["abc123 HEAD@{0}: Branch: renamed refs/heads/build/x to refs/heads/salvage/a1"],
        "spawner": ["retry_or_fail_task verdict=retry attempt=1/3"],
        "refused": ["{}"], "pids": PIDS})
    assert verdict == "BRANCH-LOSS"
    assert any("renamed refs/heads" in r for r in reasons)


def test_classify_retrying() -> None:
    verdict, reasons = classify({
        "spawner": ["retry_or_fail_task verdict=retry attempt=2/3"],
        "refused": ["{}"], "pids": PIDS})
    assert verdict == "RETRYING"
    assert any("retry scheduled" in r for r in reasons)


def test_classify_dispatch_fix() -> None:
    verdict, reasons = classify({
        "refused": ['{"task": "t1", "reason": "allowlist violation src/evil.go"}'],
        "spawner": ["retry_or_fail_task verdict=permanent_fail"],
        "graveyard": ["abc refs/graveyard/a1-123"], "pids": []})
    assert verdict == "DISPATCH-FIX"
    assert any("allowlist violation" in r for r in reasons)
    assert any("no retry pending" in r for r in reasons)


def test_classify_terminal() -> None:
    verdict, reasons = classify({"rows": [{"step": "s", "blocked": False}], "pids": []})
    assert verdict == "TERMINAL"
    assert any("no live bernstein process" in r for r in reasons)


def test_classify_running() -> None:
    verdict, reasons = classify({"pids": PIDS})
    assert verdict == "RUNNING"
    assert any("live bernstein process" in r for r in reasons)
