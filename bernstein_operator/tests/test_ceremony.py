from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from operator_driver import ceremony
from operator_driver.processes import owned_processes
from operator_driver.storage import Ledger, Park
from test_scorer_contract import git


@pytest.fixture
def review(attempt, monkeypatch):
    root, wt = attempt
    base = git(root, "rev-parse", "refs/build/base/demo")
    git(root, "merge", "--ff-only", "agent/test")
    tip = git(root, "rev-parse", "HEAD")
    build = SimpleNamespace(
        root=root, branch="integration", run_dir=root / ".agents/build/runs/demo"
    )
    phase = {
        "name": "first",
        "judge": {"brief": ".agents/build/plans/brief.md", "timeout_s": 20, "budget_usd": 1},
    }
    ledger = Ledger(build.run_dir)
    mode = ["clean"]

    def argv(spec, worktree, prompt):
        program = f"""import json, subprocess, sys
from pathlib import Path
mode = {mode[0]!r}
Path(".agents").mkdir(exist_ok=True)
Path(".agents/blind-review.md").write_text("No defects.\\nCertain: 0\\nPlausible: 0\\nVerdict: merge as-is\\n")
Path(".agents/verdict.json").write_text(json.dumps({{"verdict": "merge as-is", "certain": 0, "plausible": 0, "evidence": []}}))
if mode == "mutate":
    Path("src/code.py").write_text("MUTATED = True\\n")
if mode == "move-ref":
    subprocess.run(["git", "update-ref", "refs/heads/integration", {base!r}], check=True)
if mode == "child":
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(json.dumps({{"method": "session/update", "params": {{"sessionId": "fresh", "update": {{"sessionUpdate": "usage_update", "used": 1, "size": 100, "cost": {{"currency": "USD", "amount": 0.1}}}}}}}}))
print(json.dumps({{"id": 1, "result": {{"stopReason": "end_turn"}}}}))
"""
        return [sys.executable, "-c", program]

    monkeypatch.setattr(ceremony, "judge_argv", argv)
    return SimpleNamespace(build=build, phase=phase, ledger=ledger, base=base, tip=tip, mode=mode)


def invoke(review):
    return ceremony.judge(
        review.build,
        review.ledger,
        review.phase,
        review.base,
        review.tip,
        "judge-one",
        timeout_check=lambda: None,
    )


def test_detached_review_binds_exact_tree_and_recovers_from_immutable_receipt(review):
    receipt = invoke(review)
    assert receipt["base"] == review.base and receipt["tip"] == review.tip
    assert receipt["tree"] == git(review.build.root, "rev-parse", f"{review.tip}^{{tree}}")
    assert receipt["verdict"]["certain"] == 0
    assert receipt["cost_usd"] == 0.1
    assert invoke(review) == receipt
    assert not (review.build.run_dir / "judge/judge-one/worktree").exists()
    assert not owned_processes(review.build.root)


@pytest.mark.parametrize(
    "mode, reason",
    [
        ("mutate", "application inputs"),
        ("move-ref", "integration ref moved"),
        ("child", "surviving child processes"),
    ],
)
def test_integrity_violations_invalidate_review_and_children_are_reaped(review, mode, reason):
    review.mode[0] = mode
    with pytest.raises(Park, match=reason):
        invoke(review)
    dest = review.build.run_dir / "judge/judge-one"
    assert not (dest / "receipt.json").exists()
    assert not owned_processes(dest / "worktree", all_commands=True)


def test_changed_archived_review_cannot_trigger_a_fix(review):
    invoke(review)
    path = review.build.run_dir / "judge/judge-one/blind-review.md"
    path.write_text("Changed after acceptance")
    with pytest.raises(Park, match="archive was modified"):
        invoke(review)


def test_changed_receipt_cannot_replace_the_journal_binding(review):
    invoke(review)
    path = review.build.run_dir / "judge/judge-one/receipt.json"
    data = json.loads(path.read_text())
    data["verdict"]["certain"] = 2
    path.write_text(json.dumps(data))
    with pytest.raises(Park, match="journal binding"):
        invoke(review)


def test_crash_after_receipt_before_journal_recovers_without_a_second_agent(review, monkeypatch):
    original = review.ledger.append

    def append(event, **data):
        if event == "judge_receipt":
            raise RuntimeError("simulated crash")
        return original(event, **data)

    monkeypatch.setattr(review.ledger, "append", append)
    with pytest.raises(RuntimeError, match="simulated crash"):
        invoke(review)
    monkeypatch.setattr(review.ledger, "append", original)
    before = len([row for row in review.ledger.events if row["event"] == "launch_intent"])
    invoke(review)
    assert review.ledger.last("judge_receipt", operation="judge-one")
    assert before == len([row for row in review.ledger.events if row["event"] == "launch_intent"])
    assert not (review.build.run_dir / "judge/judge-one/worktree").exists()
