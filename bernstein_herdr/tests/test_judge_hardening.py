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


PROSE = "found a bug at pkg/a.go:12\n\nCertain: 1\nPlausible: 2\nVerdict: merge after listed fixes\n"


def _review(tmp_path: Path, body: str = PROSE, vj: dict | str | None = None) -> Path:
    d = tmp_path / "a"
    d.mkdir(exist_ok=True)
    f = d / "blind-review.md"
    f.write_text(body)
    if vj is not None:
        (d / "verdict.json").write_text(vj if isinstance(vj, str) else json.dumps(vj))
    return f


def test_json_and_prose_agree(tmp_path: Path) -> None:
    v = parse_verdict(_review(tmp_path, vj={
        "verdict": "merge after listed fixes", "certain": 1, "plausible": 2,
        "evidence": [{"file": "pkg/a.go", "line": 12, "note": "nil deref"}]}))
    assert not v["block"]
    assert v["verdict_json"] is True
    assert v["evidence"] == [{"file": "pkg/a.go", "line": 12, "note": "nil deref"}]
    assert v["certain"] == 1 and v["verdict"] == "merge after listed fixes"


def test_json_prose_disagreement_blocks(tmp_path: Path) -> None:
    v = parse_verdict(_review(tmp_path, vj={
        "verdict": "merge as-is", "certain": 0, "plausible": 2, "evidence": []}))
    assert v["block"] and v["verdict_json"] is False
    assert "disagrees with the prose block" in v["reason"]


def test_json_invalid_schema_blocks(tmp_path: Path) -> None:
    v = parse_verdict(_review(tmp_path, vj={
        "verdict": "merge after listed fixes", "certain": 1, "plausible": 2, "evidence": []}))
    assert v["block"] and "invalid verdict.json" in v["reason"]
    v = parse_verdict(_review(tmp_path, vj="not json at all"))
    assert v["block"] and "invalid verdict.json" in v["reason"]
    v = parse_verdict(_review(tmp_path, vj={
        "verdict": "ship it", "certain": 1, "plausible": 2,
        "evidence": [{"file": "a.go", "line": 1, "note": "x"}]}))
    assert v["block"] and "legal strings" in v["reason"]


def test_json_with_malformed_prose_blocks(tmp_path: Path) -> None:
    v = parse_verdict(_review(
        tmp_path,
        body="Verdict: merge as-is\nCertain: 0\nPlausible: 0\nlate\nprose\ntail\n",
        vj={"verdict": "merge as-is", "certain": 0, "plausible": 0, "evidence": []}))
    assert v["block"] and "prose verdict block is malformed" in v["reason"]


def test_prose_only_certain_without_evidence_blocks(tmp_path: Path) -> None:
    v = parse_verdict(_review(
        tmp_path, body="two real bugs, trust me\n\nCertain: 2\nPlausible: 0\nVerdict: merge after listed fixes\n"))
    assert v["block"] and "counted defects without evidence" in v["reason"]


def test_prose_only_with_enough_references_passes(tmp_path: Path) -> None:
    v = parse_verdict(_review(
        tmp_path, body="bugs at pkg/a.go:12 and cmd/b.py:9\n\nCertain: 2\nPlausible: 0\nVerdict: merge after listed fixes\n"))
    assert not v["block"] and v["certain"] == 2
