"""Readiness hardening: run manifest and sign-off enforcement (H6).

    uv run --with pytest pytest -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bernstein_herdr.plan import Plan
from bernstein_herdr.ready import manifest_data, signoff_check


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def make_plan(root: Path, sidecar: dict) -> Plan:
    return Plan(path=root / ".agents" / "build" / "plans" / "t.yaml", slug="t",
                root=root, data={}, sidecar=sidecar)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "r"
    (r / "docs" / "plans" / "p").mkdir(parents=True)
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "docs" / "plans" / "p" / "spec.md").write_text("## 1. Problem\n\nsigned-off text\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "docs: sign off spec")
    return r


def test_signoff_matching_spec_passes(repo: Path) -> None:
    sha = git(repo, "rev-parse", "HEAD")
    plan = make_plan(repo, {"defaults": {"signoff": sha, "spec": "docs/plans/p/spec.md"}})
    status, msg = signoff_check(plan)
    assert status == "pass" and sha in msg


def test_signoff_edited_spec_fails(repo: Path) -> None:
    sha = git(repo, "rev-parse", "HEAD")
    (repo / "docs" / "plans" / "p" / "spec.md").write_text("## 1. Problem\n\nquietly re-scoped\n")
    plan = make_plan(repo, {"defaults": {"signoff": sha, "spec": "docs/plans/p/spec.md"}})
    status, msg = signoff_check(plan)
    assert status == "fail" and "edited after sign-off" in msg


def test_signoff_bad_sha_fails(repo: Path) -> None:
    plan = make_plan(repo, {"defaults": {"signoff": "0" * 40, "spec": "docs/plans/p/spec.md"}})
    status, msg = signoff_check(plan)
    assert status == "fail" and "cannot show" in msg


def test_signoff_absent_keys_skip(repo: Path) -> None:
    sha = git(repo, "rev-parse", "HEAD")
    assert signoff_check(make_plan(repo, {}))[0] == "skip"
    assert signoff_check(make_plan(repo, {"defaults": {"signoff": sha}}))[0] == "skip"
    assert signoff_check(make_plan(repo, {"defaults": {"spec": "docs/plans/p/spec.md"}}))[0] == "skip"


def test_manifest_shape(repo: Path) -> None:
    (repo / "bernstein.yaml").write_text(
        "role_model_policy:\n  resolver: {cli: codex, model: gpt-5.6-sol}\n")
    m = manifest_data(make_plan(repo, {}))
    assert set(m) == {"ts", "engine", "codex_version", "claude_version",
                      "codex_config_sha256", "role_model_policy"}
    assert set(m["engine"]) == {"receipt", "source", "head"}
    assert m["role_model_policy"] == {"resolver": {"cli": "codex", "model": "gpt-5.6-sol"}}


def test_manifest_tolerates_missing_seed(repo: Path) -> None:
    m = manifest_data(make_plan(repo, {}))
    assert m["role_model_policy"] is None
