from __future__ import annotations

import copy
import sys

import pytest
from operator_driver.processes import launch_once
from operator_driver.storage import Ledger, Park, driver_lock, post_once
from operator_driver.transport import Server, admitted_inventory


class MemoryServer:
    verify_task = staticmethod(Server.verify_task)

    def __init__(self):
        self.rows = []
        self.posts = 0
        self.lose_response = False

    def tasks(self):
        return copy.deepcopy(self.rows)

    def post_task(self, body):
        self.posts += 1
        row = {**copy.deepcopy(body), "id": f"server-{self.posts}"}
        self.rows.append(row)
        if self.lose_response:
            raise ConnectionError("response lost after server commit")
        return row


def payload():
    return {
        "title": "Execute phase",
        "description": "frozen brief",
        "role": "resolver",
        "owned_files": ["src/a.py"],
        "depends_on": [],
        "completion_signals": [{"type": "file_contains", "value": "receipt.txt :: PASS"}],
        "metadata": {"operator_run": "phase-unique"},
    }


def test_lost_post_response_recovers_without_a_second_post(tmp_path):
    server = MemoryServer()
    server.lose_response = True
    ledger = Ledger(tmp_path)
    with pytest.raises(ConnectionError):
        post_once(ledger, server, payload(), "unique-op")
    task_id = post_once(Ledger(tmp_path), server, payload(), "unique-op")
    assert task_id == "server-1"
    assert server.posts == 1
    assert server.rows[0]["completion_signals"] == payload()["completion_signals"]
    assert Ledger(tmp_path).last("post_receipt", operation="unique-op")["task_id"] == task_id


def test_missing_task_after_intent_is_not_reposted(tmp_path):
    server = MemoryServer()
    ledger = Ledger(tmp_path)
    post_once(ledger, server, payload(), "unique-op")
    server.rows.clear()
    with pytest.raises(Park, match="uncertain"):
        post_once(Ledger(tmp_path), server, payload(), "unique-op")
    assert server.posts == 1


def test_payload_drift_and_duplicate_metadata_park(tmp_path):
    server = MemoryServer()
    ledger = Ledger(tmp_path)
    post_once(ledger, server, payload(), "unique-op")
    with pytest.raises(Park, match="drift"):
        post_once(ledger, server, {**payload(), "description": "changed"}, "unique-op")
    server.rows.append({**server.rows[0], "id": "duplicate"})
    with pytest.raises(Park, match="duplicate"):
        post_once(ledger, server, payload(), "unique-op")


def test_stored_signal_loss_fails_admission(tmp_path):
    server = MemoryServer()
    ledger = Ledger(tmp_path)
    post_once(ledger, server, payload(), "unique-op")
    server.rows[0]["completion_signals"] = []
    with pytest.raises(Park, match="completion_signals"):
        post_once(ledger, server, payload(), "unique-op")


def test_engine_test_followup_is_not_an_admitted_retry():
    tasks = [
        {"id": "a", "title": "executor"},
        {"id": "b", "title": "executor", "metadata": {"retry_of": "a"}},
    ]
    admitted_inventory(tasks, {"a"})
    tasks.append({"id": "c", "title": "unplanned QA", "metadata": {"origin": "test_followup"}})
    with pytest.raises(Park, match="unplanned QA"):
        admitted_inventory(tasks, {"a"})


@pytest.mark.parametrize("status", ["claimed", "done", "closed"])
def test_post_recovery_uses_original_identity_despite_an_active_retry(tmp_path, status):
    server = MemoryServer()
    ledger = Ledger(tmp_path)
    task_id = post_once(ledger, server, payload(), "fix-op")
    original = server.rows[0]
    server.rows.append(
        {
            **copy.deepcopy(original),
            "id": "retry-id",
            "status": status,
            "metadata": {**original["metadata"], "retry_of": task_id},
        }
    )
    admitted_inventory(server.tasks(), {task_id})
    assert post_once(Ledger(tmp_path), server, payload(), "fix-op") == task_id
    assert server.posts == 1
    server.rows[1]["completion_signals"] = []
    with pytest.raises(Park, match="completion_signals"):
        admitted_inventory(server.tasks(), {task_id})


def test_journal_torn_tail_and_tamper_fail_closed(tmp_path):
    ledger = Ledger(tmp_path)
    ledger.append("launch_intent", operation="one")
    raw = ledger.path.read_bytes()
    ledger.path.write_bytes(raw[:-1])
    with pytest.raises(Park, match="torn"):
        Ledger(tmp_path)
    ledger.path.write_bytes(raw.replace(b'"one"', b'"two"'))
    with pytest.raises(Park, match="chain"):
        Ledger(tmp_path)


def test_driver_lock_spans_the_ceremony(tmp_path):
    with driver_lock(tmp_path):
        with pytest.raises(Park, match="another driver"):
            with driver_lock(tmp_path):
                pass


def test_process_receipt_precedes_exec_and_recovery_does_not_relaunch(tmp_path):
    ledger = Ledger(tmp_path / "run")
    argv = [sys.executable, "-c", "print('executed once')"]
    first = launch_once(ledger, "native-one", argv, tmp_path, {})
    second = launch_once(Ledger(tmp_path / "run"), "native-one", argv, tmp_path, {})
    assert first == second
    assert first["argv"] == argv
    assert (
        len([row for row in Ledger(tmp_path / "run").events if row["event"] == "launch_intent"])
        == 1
    )
