"""The gate's already-merged short-circuit, both directions (finding J, 2026-09-03).

    uv run --no-project --with pytest --with pyyaml python -m pytest bernstein_herdr/tests -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bernstein_herdr.cli import merged_ahead, short_circuit_sha  # noqa: E402


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


def test_branch_tip_with_no_commits_of_its_own_is_scored(repo: Path, tmp_path: Path) -> None:
    """Finding S: the retry that sits at the branch tip having committed nothing.

    Everything `merged_ahead` looks at is TRUE of that HEAD -- it is strictly ahead of the
    frozen base and on the integration branch -- so the sha predicate alone cannot save it.
    What saves it is that the gate only ever short-circuits on the sha in a PASS memo, and a
    blocked attempt writes no PASS memo. The step is scored, where `commits == 0` blocks it.
    """
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("an earlier step's merged work\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "an earlier step merged")
    tip = git(repo, "rev-parse", "HEAD")
    assert merged_ahead(repo, tip, base, "build/x") is True             # the sha test passes...
    assert git(repo, "rev-list", "--count", f"build/x..{tip}") == "0"   # ...having done nothing

    memo = tmp_path / "gate-memo"
    memo.mkdir()
    (memo / f"t1-{tip[:12]}.json").write_text(
        json.dumps({"ts": "x", "head": tip, "rc": 1, "row": {"blocked": True}}))   # a BLOCKING memo
    assert short_circuit_sha(repo, memo, "t1", base, "build/x") == ""


def test_pass_memo_short_circuits_on_its_own_sha(repo: Path, tmp_path: Path) -> None:
    """The other direction: a task that passed and merged is not re-scored."""
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("the step's work\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "the step's work")
    done = git(repo, "rev-parse", "HEAD")
    memo = tmp_path / "gate-memo"
    memo.mkdir()
    (memo / "t1-merged.json").write_text(json.dumps({"ts": "x", "head": done, "rc": 0, "row": {}}))
    assert short_circuit_sha(repo, memo, "t1", base, "build/x") == done
    assert short_circuit_sha(repo, memo, "t2", base, "build/x") == ""   # another task's memo is not this one's


def test_pass_memo_not_yet_on_the_branch_is_rescored(repo: Path, tmp_path: Path) -> None:
    """Passed the gate but the merge never landed: there is still something to score."""
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "agent/s")
    (repo / "a.txt").write_text("the step's work\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "the step's work")
    memo = tmp_path / "gate-memo"
    memo.mkdir()
    (memo / "t1-merged.json").write_text(
        json.dumps({"ts": "x", "head": git(repo, "rev-parse", "HEAD"), "rc": 0, "row": {}}))
    assert short_circuit_sha(repo, memo, "t1", base, "build/x") == ""
