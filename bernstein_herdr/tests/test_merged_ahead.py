"""The gate's already-merged short-circuit, both directions (finding J, 2026-09-03).

    uv run --no-project --with pytest --with pyyaml python -m pytest bernstein_herdr/tests -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bernstein_herdr.cli import merged_ahead  # noqa: E402


def git(wt: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=wt, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    wt = tmp_path / "r"
    wt.mkdir()
    git(wt, "init", "-q", "-b", "build/x")
    git(wt, "config", "user.email", "t@t"); git(wt, "config", "user.name", "t")
    (wt / "a.txt").write_text("base\n")
    git(wt, "add", "-A"); git(wt, "commit", "-qm", "base")
    return wt


def test_head_at_base_is_scored(repo: Path) -> None:
    """The executor was killed before committing: HEAD is still the frozen base."""
    base = git(repo, "rev-parse", "HEAD")
    assert merged_ahead(repo, base, base, "build/x") is False


def test_head_behind_base_is_scored(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("more\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "advance the branch")
    later = git(repo, "rev-parse", "HEAD")
    assert merged_ahead(repo, base, later, "build/x") is False


def test_head_merged_ahead_short_circuits(repo: Path) -> None:
    """The step committed and its work is on the integration branch."""
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("work\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "the step's work")
    assert merged_ahead(repo, git(repo, "rev-parse", "HEAD"), base, "build/x") is True


def test_unmerged_work_is_scored(repo: Path) -> None:
    """Committed but not yet on the integration branch: the normal first gate call."""
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "agent/s")
    (repo / "a.txt").write_text("work\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "the step's work")
    assert merged_ahead(repo, git(repo, "rev-parse", "HEAD"), base, "build/x") is False


def test_no_base_sha_disables_the_short_circuit(repo: Path) -> None:
    assert merged_ahead(repo, git(repo, "rev-parse", "HEAD"), "", "build/x") is False
