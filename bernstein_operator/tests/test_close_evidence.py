from __future__ import annotations

import runpy
from pathlib import Path

import pytest
from operator_driver.reconcile import archive_native
from operator_driver.storage import Ledger
from test_delivery import prove
from test_scorer_contract import git

PRESERVE = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "skills/build-close/scripts/preserve-evidence.py")
)["preserve"]


def completed(delivered):
    root, run_id, start, tip, tasks, _, _ = delivered
    run = root / ".agents/build/runs/demo"
    archive_native(root, run, run_id, tasks, b"{}")
    ledger = Ledger(run)
    ledger.append("build_started", base=start)
    ledger.append("native_closed", run_id=run_id, proofs=prove(delivered), tip=tip)
    ledger.append("phase_accepted", phase="phase-one", tip=tip)
    ledger.append("build_completed", base=start, tip=tip, phases=1)
    return root, run


def test_close_preserves_verified_evidence_and_portable_git_objects(delivered, tmp_path):
    root, run = completed(delivered)
    dest = tmp_path / "primary-archive"
    result = PRESERVE(root, run, dest)
    assert result["files"] > 5
    assert (dest / "objects.bundle").is_file()
    assert (dest / "preservation.json").is_file()
    (run / "handoff.md").write_text("## Outcome\nValidated\n")
    PRESERVE(root, run, dest)
    assert (dest / "handoff.md").read_text() == "## Outcome\nValidated\n"
    assert git(root, "for-each-ref", "refs/build/evidence/demo")


def test_close_refuses_tampering_or_application_changes_after_validation(delivered, tmp_path):
    root, run = completed(delivered)
    (root / "src/code.py").write_text("UNREVIEWED = True\n")
    git(root, "commit", "-qam", "unreviewed edit")
    with pytest.raises(ValueError, match="code changed"):
        PRESERVE(root, run, tmp_path / "archive")
    git(root, "reset", "--hard", "HEAD~1")
    receipt = next((run / "reports").glob("*/*/receipt.json"))
    receipt.write_text("{}")
    with pytest.raises(ValueError, match="scorer receipt changed"):
        PRESERVE(root, run, tmp_path / "archive")


def test_close_refuses_unresolved_workflow_obligations(delivered, tmp_path):
    root, run = completed(delivered)
    Ledger(run).append("parked", reason="unresolved")
    with pytest.raises(ValueError, match="parked"):
        PRESERVE(root, run, tmp_path / "archive")
