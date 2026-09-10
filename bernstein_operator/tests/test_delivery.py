from __future__ import annotations

import json

import pytest
from bernstein.core.agents.spawner_merge import merge_worktree_branch
from bernstein.core.persistence.wal import WALRecovery, WALWriter
from bernstein.core.replay.journal import EventJournal
from bernstein.core.replay.review_board import record_task_merged
from operator_driver.reconcile import (
    archive_native,
    close_proven_wal,
    native_events,
    prove_delivery,
)
from operator_driver.storage import Park
from test_scorer_contract import git

from bernstein_operator.scorer import score


@pytest.fixture
def delivered(attempt):
    root, wt = attempt
    run_id = "native-one"
    start = git(root, "rev-parse", "HEAD")
    assert score(wt, "Owned step")["status"] == "pass"
    result = merge_worktree_branch("test", root)
    assert result.success and result.merge_commit
    journal = EventJournal(run_id, root / ".sdd")
    journal.record("agent_spawned", agent_id="test", task_ids=["task-one"])
    record_task_merged(
        journal, task_id="task-one", agent_id="test", merge_commit=result.merge_commit
    )
    journal.record("run_completed", outcome="completed")
    journal.record("run_quiescence", verified=True, residual=[])
    tasks = [{"id": "task-one", "title": "Owned step", "status": "done", "metadata": {}}]
    writer = WALWriter(run_id, root / ".sdd")
    writer.write_entry("tick_start", {}, {}, "orchestrator")
    writer.write_entry(
        "task_claimed", {"task_id": "task-one"}, {}, "task_lifecycle", committed=False
    )
    writer.write_entry(
        "claim_confirmed",
        {"task_id": "task-one", "agent_id": "test"},
        {},
        "task_lifecycle",
        committed=False,
    )
    writer.write_entry(
        "task_spawn_confirmed", {"task_id": "task-one", "agent_id": "test"}, {}, "task_lifecycle"
    )
    return root, run_id, start, result.merge_commit, tasks, journal, writer


def prove(fixture, events=None, tasks=None):
    root, run_id, start, tip, stored, journal, _ = fixture
    return prove_delivery(
        root,
        root / ".agents/build/runs/demo",
        run_id,
        start,
        tip,
        {"Owned step": "task-one"},
        stored if tasks is None else tasks,
        native_events(journal.path, closed=True) if events is None else events,
    )


def test_real_native_merge_and_journal_prove_delivery_and_seal_paired_wal(delivered):
    root, run_id, _, _, tasks, journal, _ = delivered
    assert prove(delivered)[0]["scorer_attempt"]
    assert WALRecovery.scan_all_uncommitted(root / ".sdd")
    archive_native(root, root / ".agents/build/runs/demo", run_id, tasks, b"{}")
    close_proven_wal(root, run_id, tasks, native_events(journal.path, closed=True))
    assert not WALRecovery.scan_all_uncommitted(root / ".sdd")


@pytest.mark.parametrize("missing", ["run_quiescence", "run_completed", "agent_spawned"])
def test_completed_status_never_replaces_missing_delivery_links(delivered, missing):
    events = [row for row in native_events(delivered[5].path) if row["event"] != missing]
    with pytest.raises(Park):
        prove(delivered, events=events)


def test_dead_agent_merge_requires_exact_scored_second_parent(delivered):
    events = [row for row in native_events(delivered[5].path) if row["event"] != "task_merged"]
    assert prove(delivered, events=events)[0]["source"] == "git_merge_parents"
    root = delivered[0]
    receipt_path = next((root / ".agents/build/runs/demo/reports").glob("*/*/receipt.json"))
    receipt = json.loads(receipt_path.read_text())
    receipt["status"] = "fail"
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(Park, match="no unique scored"):
        prove(delivered, events=events)


def test_local_only_native_push_skips_all_git_io(monkeypatch, tmp_path):
    from bernstein.core.git import git_basic

    monkeypatch.setenv("BERNSTEIN_OPERATOR_LOCAL_ONLY", "1")

    def unexpected(*args, **kwargs):
        pytest.fail("operator merge-back attempted Git I/O through safe_push")

    monkeypatch.setattr(git_basic, "run_git", unexpected)
    assert git_basic.safe_push(tmp_path, "integration").returncode == 0


def test_parked_task_or_residual_process_blocks_boundary(delivered):
    tasks = [{**delivered[4][0], "status": "blocked_by_failed_dep"}]
    with pytest.raises(Park, match="task obligation"):
        prove(delivered, tasks=tasks)
    # A claimed retry of a step this run delivered is not an obligation: it was
    # dispatched after the work landed, so the scorer refuses it a content-bound PASS.
    stranded = [
        *delivered[4],
        {
            "id": "task-two",
            "title": "Owned step",
            "status": "claimed",
            "metadata": {"retry_of": "task-one"},
        },
    ]
    assert prove(delivered, tasks=stranded)[0]["task_id"] == "task-one"
    events = native_events(delivered[5].path)
    events[-1]["residual"] = [{"pid": 123}]
    with pytest.raises(Park, match="quiescence"):
        prove(delivered, events=events)


def test_unpaired_wal_intent_is_never_hidden_by_a_closed_marker(delivered):
    root, run_id, _, _, tasks, journal, writer = delivered
    writer.write_entry(
        "task_claimed", {"task_id": "unknown"}, {}, "task_lifecycle", committed=False
    )
    with pytest.raises(Park, match="unresolved WAL"):
        close_proven_wal(root, run_id, tasks, native_events(journal.path))
    assert not WALRecovery.is_wal_closed(run_id, root / ".sdd")


def test_native_refusal_cannot_be_hidden_by_later_status_or_pass(delivered):
    path = delivered[0] / ".sdd/runtime/refused_merges.jsonl"
    path.write_text(json.dumps({"session_id": "previous-run-agent", "reason": "old"}) + "\n")
    assert prove(delivered)
    with path.open("a") as stream:
        stream.write(json.dumps({"session_id": "test", "reason": "file-scope-refused"}) + "\n")
    with pytest.raises(Park, match="native merge refusal"):
        prove(delivered)


def test_refusal_of_an_attempt_a_later_one_superseded_does_not_park_the_step(delivered):
    """Native retries stay enabled, so a first attempt whose branch the gates refused is
    resolved once a DIFFERENT attempt delivers that step. Measured on the first real
    build: a misdispatched attempt was refused and its retry landed the scored work."""
    root, _, _, _, _, journal, _ = delivered
    path = root / ".sdd/runtime/refused_merges.jsonl"
    path.write_text(
        json.dumps({"session_id": "first-try", "reason": "quality-gates-blocked"}) + "\n"
    )
    events = native_events(journal.path, closed=True)
    events.insert(0, {"event": "agent_spawned", "agent_id": "first-try", "task_ids": ["task-one"]})
    assert prove(delivered, events=events)[0]["agent_id"] == "test"
    # Only the gates blocking an attempt is explained by a later delivery. Scope,
    # blast radius and a merge aimed at the default branch are not.
    for reason in ("allowed-files-scope", "target-is-default-branch", None):
        row = {"session_id": "first-try"} | ({"reason": reason} if reason else {})
        path.write_text(json.dumps(row) + "\n")
        with pytest.raises(Park, match="native merge refusal"):
            prove(delivered, events=events)


def test_declared_witnesses_are_read_from_the_settled_tip(delivered):
    """The engine judges a completion signal against the delivered copy while the merge
    is still landing. The driver reads the same signals at the boundary, where the tip
    is settled: they resolve a failed status, and an unmet one parks the phase."""
    root, run_id, start, tip, tasks, journal, _ = delivered
    failed = [{"id": "task-one", "title": "Owned step", "status": "failed", "metadata": {}}]
    events = native_events(journal.path, closed=True)

    def prove_with(signals, stored):
        return prove_delivery(
            root,
            root / ".agents/build/runs/demo",
            run_id,
            start,
            tip,
            {"Owned step": "task-one"},
            stored,
            events,
            {"Owned step": signals},
        )

    held = [{"type": "file_contains", "value": "src/code.py :: VALUE = 1"}]
    assert prove_with(held, failed)[0]["task_id"] == "task-one"
    with pytest.raises(Park, match="declared witnesses"):
        prove_with([{"type": "file_contains", "value": "src/code.py :: NEVER WRITTEN"}], tasks)
    with pytest.raises(Park, match="declared witnesses"):
        prove_with([{"type": "path_exists", "value": "src/absent.py"}], tasks)


def test_landed_content_of_a_failed_attempt_needs_a_completed_retry(delivered):
    """Dead-agent reaping lands a scored attempt and still records it failed, then
    retries. Measured on the first real build: the landed content held a scorer PASS
    while its own task read failed. The step is resolved only by a completed retry."""
    failed = [{"id": "task-one", "title": "Owned step", "status": "failed", "metadata": {}}]
    with pytest.raises(Park, match="failed task obligation"):
        prove(delivered, tasks=failed)
    retried = [
        *failed,
        {
            "id": "task-two",
            "title": "Owned step",
            "status": "done",
            "metadata": {"retry_of": "task-one"},
        },
    ]
    assert prove(delivered, tasks=retried)[0]["task_id"] == "task-one"
    orphan = [*failed, {**retried[1], "status": "failed"}]
    with pytest.raises(Park, match="failed task obligation"):
        prove(delivered, tasks=orphan)


def test_a_step_lands_twice_when_its_retry_branches_from_the_first_landing(delivered):
    """An attempt whose completion signal cannot be verified fails and is retried after
    its work already merged, so the retry branches from the tip that carries it. Both
    landings are separately scored and sequential, so both are proven rather than
    ambiguous - measured on the first real builds."""
    root, run_id, start, _, tasks, journal, _ = delivered
    second = root / ".sdd/worktrees/retry"
    git(root, "worktree", "add", "-qb", "agent/retry", str(second))
    (second / "src/code.py").write_text("VALUE = 2\n")
    (second / ".agents/report.md").write_text("Validation: exit 0\n")
    git(second, "add", "-A")
    git(second, "commit", "-qm", "retry of the owned change")
    assert score(second, "Owned step")["status"] == "pass"
    result = merge_worktree_branch("retry", root)
    assert result.success and result.merge_commit
    journal.record("agent_spawned", agent_id="retry", task_ids=["task-two"])
    record_task_merged(
        journal, task_id="task-two", agent_id="retry", merge_commit=result.merge_commit
    )
    retried = [
        *tasks,
        {
            "id": "task-two",
            "title": "Owned step",
            "status": "done",
            "metadata": {"retry_of": "task-one"},
        },
    ]
    tip = git(root, "rev-parse", "integration")
    proofs = prove_delivery(
        root,
        root / ".agents/build/runs/demo",
        run_id,
        start,
        tip,
        {"Owned step": "task-one"},
        retried,
        native_events(journal.path, closed=True),
    )
    assert [proof["agent_id"] for proof in proofs] == ["test", "retry"]


def test_native_retention_cannot_prune_archived_build_evidence(delivered):
    root, run_id, _, _, tasks, _, _ = delivered
    dest = archive_native(root, root / ".agents/build/runs/demo", run_id, tasks, b"{}")
    manifest = json.loads((dest / "archive.json").read_text())
    for number in range(25):
        EventJournal(f"later-{number}", root / ".sdd").record("run_completed")
    assert archive_native(root, root / ".agents/build/runs/demo", run_id, [], b"") == dest
    assert json.loads((dest / "tasks.json").read_text()) == tasks
    assert f"state/runtime/wal/{run_id}.wal.jsonl" in manifest
