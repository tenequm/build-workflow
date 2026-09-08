from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from operator_driver import driver
from operator_driver.ceremony import reaction
from operator_driver.storage import Ledger, Park, canonical, digest, immutable


def verdict(certain=0, **extra):
    return {
        "certain": certain,
        "plausible": 0,
        "counts_declared": True,
        "evidence": [{"file": "src/a.py", "line": 1, "note": "broken"}] if certain else [],
        **extra,
    }


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    tip = ["base"]
    monkeypatch.setattr(
        driver, "git", lambda root, *args: "base" if "refs/build/base/demo" in args else tip[0]
    )
    build = SimpleNamespace(
        root=tmp_path,
        run_dir=tmp_path,
        branch="integration",
        slug="demo",
        fingerprint="pins",
        bounds={"max_wall_s": 60, "max_spend_usd": 50, "max_attempts": 20, "run_budget_usd": 2},
        phases=[
            {
                "name": name,
                "steps": [name + "-step"],
                "fix": name + "-repair",
                "judge": {"budget_usd": 1},
            }
            for name in ("phase-1", "phase-2")
        ],
        verify_pins=lambda base: None,
        fix_scope_covers=lambda phase, evidence: True,
    )
    ledger = Ledger(tmp_path)
    ledger.append("build_started", base="base", fingerprint="pins", branch="integration")
    launches, reviews = [], []
    judgments = {}
    crash = [None]

    def native(build, ledger, titles, operation, base, *, reserve, check_bounds, fix_input=None):
        closed = ledger.last("native_closed", operation=operation)
        if closed:
            return closed
        reserve(operation, 2)
        if not ledger.last("native_intent", operation=operation):
            ledger.append("native_intent", operation=operation)
            launches.append(operation)
        if crash[0] == operation:
            raise RuntimeError("simulated driver death after launch")
        if fix_input:
            assert fix_input["receipt_sha256"] == digest(canonical(fix_input["receipt"]))
            for artifact in fix_input["artifacts"].values():
                assert artifact["sha256"] == digest(artifact["utf8"].encode())
        tip[0] = operation + "-tip"
        return ledger.append("native_closed", operation=operation, tip=tip[0], cost_usd=0.25)

    def judge(build, ledger, phase, base, reviewed, operation, **kwargs):
        path = tmp_path / "judge" / operation / "receipt.json"
        if path.exists():
            return json.loads(path.read_text())
        assert tip[0] == reviewed
        reviews.append(operation)
        raw = b"Immutable review evidence.\n"
        immutable(path.parent / "blind-review.md", raw)
        receipt = {
            "operation": operation,
            "base": base,
            "tip": reviewed,
            "verdict": judgments.get(operation, verdict()),
            "cost_usd": 0.1,
            "artifacts": {"blind-review.md": digest(raw)},
        }
        immutable(path, canonical(receipt))
        ledger.append("judge_receipt", operation=operation, cost_usd=0.1)
        return receipt

    return SimpleNamespace(
        build=build,
        ledger=ledger,
        tip=tip,
        launches=launches,
        reviews=reviews,
        judgments=judgments,
        crash=crash,
        native=native,
        judge=judge,
    )


def run(w):
    return driver.run_build(
        w.build, Ledger(w.ledger.directory), execute_run=w.native, judge_run=w.judge
    )


def test_pending_fix_survives_crash_without_releasing_next_phase_or_duplicate_launch(workflow):
    w = workflow
    w.judgments["phase-1-judge-0"] = verdict(1)
    w.crash[0] = "phase-1-fix-0"
    with pytest.raises(RuntimeError, match="driver death"):
        run(w)
    assert w.launches == ["phase-1", "phase-1-fix-0"]
    assert w.reviews == ["phase-1-judge-0"]
    w.crash[0] = None
    assert run(w)["event"] == "build_completed"
    assert w.launches == ["phase-1", "phase-1-fix-0", "phase-2"]
    assert w.reviews == ["phase-1-judge-0", "phase-1-judge-1", "phase-2-judge-0"]
    run(w)
    assert len(w.launches) == 3 and len(w.reviews) == 3


def test_do_not_merge_and_missing_verdict_hold_phase_boundary(workflow):
    w = workflow
    w.judgments["phase-1-judge-0"] = verdict(1, do_not_merge=True)
    with pytest.raises(Park, match="operator resolution"):
        run(w)
    assert w.launches == ["phase-1"]
    assert reaction(verdict(1, do_not_merge=True)) == "park"
    assert reaction({"reason": "missing"}) == "rejudge"
    assert reaction({"reason": "missing"}, 1) == "park"


def test_malformed_verdict_rejudges_once_then_parks(workflow):
    w = workflow
    w.judgments.update(
        {"phase-1-judge-0": {"reason": "missing"}, "phase-1-judge-1": {"reason": "malformed"}}
    )
    with pytest.raises(Park):
        run(w)
    assert w.launches == ["phase-1"]
    assert len(w.reviews) == 2


def test_cumulative_out_of_scope_finding_cannot_widen_fix(workflow):
    w = workflow
    w.judgments["phase-1-judge-0"] = verdict(1)
    w.build.fix_scope_covers = lambda phase, evidence: False
    with pytest.raises(Park, match="pinned fix scope"):
        run(w)
    assert w.launches == ["phase-1"]


def test_whole_build_reservation_blocks_unbounded_repair(workflow):
    w = workflow
    w.build.bounds["max_attempts"] = 2
    w.judgments["phase-1-judge-0"] = verdict(1)
    with pytest.raises(Park, match="attempt limit"):
        run(w)
    assert w.launches == ["phase-1"]


def test_unresolved_spend_is_reserved_across_restart(workflow):
    w = workflow
    w.build.bounds["max_spend_usd"] = 3
    bounds = driver.Bounds(w.build, w.ledger)
    bounds.reserve("lost-launch", 2)
    with pytest.raises(Park, match="spend limit"):
        driver.Bounds(w.build, Ledger(w.ledger.directory)).reserve("new-launch", 2)
