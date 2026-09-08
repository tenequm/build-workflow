from __future__ import annotations

import sys
import time
from types import SimpleNamespace

import pytest
from bernstein.core.security.quarantine import QUARANTINE_THRESHOLD, QuarantineStore
from operator_driver import admission, engine
from operator_driver.processes import owned_processes
from operator_driver.spec import Build
from operator_driver.storage import Ledger, Park
from test_scorer_contract import git


def test_quarantine_blocks_before_a_new_server_or_post(authored):
    root, path = authored
    build = Build(root, path)
    store = QuarantineStore(root / ".sdd/runtime/quarantine.json")
    for _ in range(QUARANTINE_THRESHOLD):
        store.record_failure("a", "repeated failure")
    ledger = Ledger(build.run_dir)
    with pytest.raises(Park, match="quarantined"):
        engine.execute(
            build,
            ledger,
            ["a"],
            "phase",
            git(root, "rev-parse", "HEAD"),
            reserve=lambda *args: None,
            check_bounds=lambda: None,
        )
    assert not ledger.last("native_intent")
    assert not owned_processes(root)


def test_low_disk_blocks_before_admission(authored, monkeypatch):
    root, path = authored
    monkeypatch.setattr(admission.shutil, "disk_usage", lambda path: SimpleNamespace(free=1))
    ledger = Ledger(Build(root, path).run_dir)
    with pytest.raises(Park, match="40 GiB"):
        engine.execute(
            Build(root, path),
            ledger,
            ["a"],
            "phase",
            git(root, "rev-parse", "HEAD"),
            reserve=lambda *args: None,
            check_bounds=lambda: None,
        )
    assert not ledger.events


def test_no_start_parks_and_tears_down_identified_server(authored, monkeypatch):
    root, path = authored
    build = Build(root, path)
    ledger = Ledger(build.run_dir)
    actual_launch = engine.launch_once

    def launch(ledger, operation, argv, *args, **kwargs):
        if operation.endswith("-spawner"):
            # Simulate a scheduler that lives but never starts an executor.
            argv = [sys.executable, "-c", "import time; time.sleep(60)"]
        return actual_launch(ledger, operation, argv, *args, **kwargs)

    monkeypatch.setattr(engine, "launch_once", launch)
    monkeypatch.setattr(engine, "prerequisites", lambda build: None)
    monkeypatch.setattr(
        engine,
        "time",
        SimpleNamespace(
            time=lambda: time.time() + 121,
            monotonic=time.monotonic,
            sleep=time.sleep,
        ),
    )
    with pytest.raises(Park, match="no executor started"):
        engine.execute(
            build,
            ledger,
            ["a"],
            "phase",
            git(root, "rev-parse", "HEAD"),
            reserve=lambda *args: None,
            check_bounds=lambda: None,
        )
    assert not ledger.last("native_closed")
    assert not owned_processes(root)
