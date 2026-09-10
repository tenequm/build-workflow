from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from bernstein_operator.scorer import ScorerGate, score


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def attempt(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q", "-b", "integration")
    git(root, "config", "user.name", "Scorer test")
    git(root, "config", "user.email", "test@example.invalid")
    plans = root / ".agents/build/plans"
    plans.mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src/code.py").write_text("VALUE = 0\n")
    (root / "src/unowned.py").write_text("VALUE = 0\n")
    (root / "src/test_code.py").write_text("def test_code(): pass\n")
    (root / ".gitignore").write_text(".sdd/\n.agents/build/runs/\n")
    (plans / "brief.md").write_text("Change the owned file.\n")
    (plans / "demo.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "demo",
                "stages": [
                    {
                        "name": "step",
                        "steps": [
                            {"title": "Owned step", "files": ["src/code.py", "src/test_code.py"]}
                        ],
                    }
                ],
            }
        )
    )
    (plans / "demo.steps.yaml").write_text(
        yaml.safe_dump(
            {
                "defaults": {"doc": "docs/plans/demo/plan.md"},
                "steps": {
                    "Owned step": {
                        "brief": ".agents/build/plans/brief.md",
                        "report": ".agents/report.md",
                        "gate_cmd": "true",
                    }
                },
            }
        )
    )
    (root / "bernstein.yaml").write_text(
        "goal: test\nquality_gates:\n  enabled: true\n  base_ref: integration\n  pipeline:\n    - name: scorer\n      condition: always\n      required: true\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/build/base/demo", base)
    wt = root / ".sdd/worktrees/test"
    git(root, "worktree", "add", "-qb", "agent/test", str(wt))
    (wt / "src/code.py").write_text("VALUE = 1\n")
    (wt / ".agents/report.md").write_text("Validation: exit 0\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "owned change")
    for key, value in {
        "BERNSTEIN_OPERATOR_ROOT": root,
        "BERNSTEIN_OPERATOR_PLAN": ".agents/build/plans/demo.yaml",
        "BERNSTEIN_OPERATOR_BASE": base,
        "BERNSTEIN_OPERATOR_BRANCH": "integration",
        "BERNSTEIN_RUN_ID": "native-one",
    }.items():
        monkeypatch.setenv(key, str(value))
    return root, wt


def test_native_changed_files_cannot_hide_unowned_change(attempt):
    _, wt = attempt
    (wt / "src/unowned.py").write_text("VALUE = 2\n")
    git(wt, "commit", "-qam", "unowned")
    result = ScorerGate().run(["src/code.py"], wt, "Owned step", "")
    assert result.blocked
    assert result.metadata["allowlist_violations"] == ["src/unowned.py"]


def test_memo_requires_clean_content_and_archives_each_call(attempt):
    root, wt = attempt
    first = score(wt, "Owned step")
    second = score(wt, "Owned step")
    assert first["status"] == second["status"] == "pass"
    assert second["memo_of"] == first["attempt_id"]
    assert first["attempt_id"] != second["attempt_id"]
    (wt / "src/code.py").write_text("VALUE = 9\n")
    changed = score(wt, "Owned step")
    assert changed["status"] == "fail"
    assert changed["memo_of"] is None
    receipts = list((root / ".agents/build/runs/demo/reports").glob("*/*/receipt.json"))
    assert len(receipts) == 3
    assert {json.loads(p.read_text())["attempt_id"] for p in receipts} == {
        first["attempt_id"],
        second["attempt_id"],
        changed["attempt_id"],
    }


@pytest.mark.parametrize(
    "refusal", ["scope_exceeded", "underspecified", "blocked_on_dependency", "awaiting_operator"]
)
def test_changed_report_cannot_reuse_pass(attempt, refusal):
    _, wt = attempt
    first = score(wt, "Owned step")
    (wt / ".agents/report.md").write_text(f"{refusal}: cannot complete\n")
    changed = score(wt, "Owned step")
    assert changed["status"] == "fail"
    assert changed["refusal"] == refusal
    assert changed["evidence"] != first["evidence"]


def test_landed_pass_survives_integration_advancing(attempt):
    root, wt = attempt
    first = score(wt, "Owned step")
    git(root, "merge", "--ff-only", "agent/test")
    (root / "later.txt").write_text("later\n")
    git(root, "add", "later.txt")
    git(root, "commit", "-qm", "later work")
    again = score(wt, "Owned step")
    assert again["deduplicated_landing"]
    assert again["memo_of"] == first["attempt_id"]


def test_no_commit_unknown_title_root_and_pin_drift_fail_closed(attempt):
    root, wt = attempt
    gate = ScorerGate()
    assert gate.condition == "always"
    assert gate.run([], wt, "Unknown step", "").blocked
    assert gate.run([], root, "Owned step", "").blocked
    git(wt, "reset", "--hard", "HEAD~1")
    assert gate.run([], wt, "Owned step", "").blocked
    (root / ".agents/build/plans/brief.md").write_text("soften the policy\n")
    assert "pin drift" in gate.run([], wt, "Owned step", "").details


def test_deleted_test_is_seen_even_with_empty_native_hint(attempt):
    _, wt = attempt
    git(wt, "rm", "src/test_code.py")
    git(wt, "commit", "-qm", "delete test")
    result = ScorerGate().run([], wt, "Owned step", "")
    assert result.blocked
    assert result.metadata["deleted_tests"] == ["src/test_code.py"]


def test_human_plan_doc_is_protected_even_outside_machine_plan_directory(attempt):
    _, wt = attempt
    doc = wt / "docs/plans/demo/plan.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("Weaken acceptance\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "docs: change acceptance")
    result = score(wt, "Owned step")
    assert result["policy_edits"] == ["docs/plans/demo/plan.md"]


def test_git_failure_is_not_an_empty_diff(attempt, monkeypatch):
    _, wt = attempt
    monkeypatch.setenv("BERNSTEIN_OPERATOR_BRANCH", "missing-branch")
    result = ScorerGate().run([], wt, "Owned step", "")
    assert result.blocked
    assert "failed" in result.details


def test_merge_surrogate_id_resolves_only_scope_preserving_admitted_retries(attempt):
    root, wt = attempt
    admitted = root / ".agents/build/runs/demo/admitted/native-one.json"
    admitted.parent.mkdir(parents=True)
    admitted.write_text(json.dumps({"task-root": "Owned step"}))
    task = {
        "id": "task-root",
        "title": "Owned step",
        "owned_files": ["src/code.py", "src/test_code.py"],
        "metadata": {"operator_run": "native-one"},
    }
    retry = {**task, "id": "task-retry", "metadata": {**task["metadata"], "retry_of": "task-root"}}
    path = root / ".sdd/runtime/tasks.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    def write():
        path.write_text(json.dumps(task) + "\n" + json.dumps(retry) + "\n")

    write()
    assert score(wt, "task-root")["title"] == "Owned step"
    assert score(wt, "task-retry")["status"] == "pass"
    # A native retry drops owned_files (measured 2026-09-10). Ownership is scored from
    # the frozen declaration, so an emptied retry still resolves, while the admitted
    # task itself must always carry the frozen list.
    retry["owned_files"] = []
    write()
    assert score(wt, "task-retry")["status"] == "pass"
    task["owned_files"] = []
    write()
    assert ScorerGate().run([], wt, "task-retry", "").blocked
    task["owned_files"] = ["src/code.py", "src/test_code.py"]
    retry["owned_files"] = ["src/unowned.py"]
    write()
    assert ScorerGate().run([], wt, "task-retry", "").blocked
    retry["owned_files"] = task["owned_files"]
    retry["metadata"]["operator_run"] = "another-run"
    write()
    assert ScorerGate().run([], wt, "task-retry", "").blocked
    assert ScorerGate().run([], wt, "unknown-id", "").blocked
