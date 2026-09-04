"""Judge hardening: worktree allowlist (H3) and structured verdict.json (H7).

    uv run --with pytest pytest -q
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from bernstein_herdr.judge import judge_worktree_violations, parse_verdict


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "build/x")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "code.py").write_text("print('base')\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "chore: base")
    git(r, "checkout", "-q", "-b", "agent/j")
    return r


def test_review_artifacts_only_is_clean(repo: Path) -> None:
    (repo / ".agents").mkdir()
    (repo / ".agents" / "blind-review.md").write_text("review\n")
    (repo / ".agents" / "scorecard.md").write_text("numbers\n")
    (repo / ".agents" / "verdict.json").write_text("{}\n")
    git(repo, "add", "-f", "-A")
    git(repo, "commit", "-qm", "docs(review): blind review")
    assert judge_worktree_violations(repo, "build/x") == []


def test_code_edit_is_a_violation(repo: Path) -> None:
    (repo / ".agents").mkdir()
    (repo / ".agents" / "blind-review.md").write_text("review\n")
    (repo / "code.py").write_text("print('the judge fixed it')\n")
    git(repo, "add", "-f", "-A")
    git(repo, "commit", "-qm", "docs(review): blind review plus a sneaky fix")
    assert judge_worktree_violations(repo, "build/x") == ["code.py"]


def test_uncommitted_tracked_edit_is_a_violation(repo: Path) -> None:
    (repo / "code.py").write_text("print('probe left behind')\n")
    assert judge_worktree_violations(repo, "build/x") == ["code.py"]
