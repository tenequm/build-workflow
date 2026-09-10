from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
import yaml
from operator_driver import engine
from operator_driver.processes import owned_processes
from operator_driver.spec import Build
from operator_driver.storage import Ledger, Park, driver_lock
from test_scorer_contract import git


def test_real_native_quiescence_then_fresh_phase_in_same_workspace(authored, monkeypatch):
    root, path = authored
    seed_path = root / "bernstein.yaml"
    seed = yaml.safe_load(seed_path.read_text())
    seed.update(
        goal="recording acceptance",
        cli="codex",
        evolution_enabled=False,
        gate_repair_enabled=False,
        internal_llm_provider="none",
        orchestration={"test_followup": False},
    )
    seed["quality_gates"].update(
        enabled=True,
        cache_enabled=False,
        flaky_detection=False,
        pipeline=[{"name": "scorer", "condition": "always", "required": True}],
    )
    seed_path.write_text(yaml.safe_dump(seed))
    (root / ".gitignore").write_text(
        ".sdd/\n.claude/\nCLAUDE.md\n.agents/build/runs/\n__pycache__/\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: freeze native fixture")
    base = git(root, "rev-parse", "HEAD")
    git(root, "branch", "main", base)
    git(root, "update-ref", "refs/build/base/demo", base)
    build = Build(root, path)
    ledger = Ledger(build.run_dir)
    actual_launch = engine.launch_once
    recording = str(Path(__file__).with_name("recording_native.py"))

    def launch(ledger, operation, argv, *args, **kwargs):
        if operation.endswith("-spawner"):
            assert argv[:3] == [sys.executable, "-m", "bernstein.core.orchestration.orchestrator"]
            argv = [sys.executable, recording, *argv[3:]]
        return actual_launch(ledger, operation, argv, *args, **kwargs)

    monkeypatch.setattr(engine, "launch_once", launch)
    deadline = time.monotonic() + 180

    def bound():
        if time.monotonic() > deadline:
            raise Park("native acceptance deadline")

    def execute(titles, operation):
        try:
            return engine.execute(
                build,
                ledger,
                titles,
                operation,
                base,
                reserve=lambda *args: None,
                check_bounds=bound,
            )
        except Exception:
            for log in (build.run_dir / "processes").glob("*.log"):
                print(log.name, log.read_text(errors="replace")[-10000:])
            raise

    with driver_lock(root):
        append = ledger.append

        def crash_at_closure(event, **data):
            if event == "native_closed":
                raise RuntimeError("driver died after teardown before closure receipt")
            return append(event, **data)

        monkeypatch.setattr(ledger, "append", crash_at_closure)
        with pytest.raises(RuntimeError, match="driver died"):
            execute(["a"], "phase-one")
        assert not owned_processes(root)
        launch_count = len([row for row in ledger.events if row["event"] == "launch_intent"])
        monkeypatch.setattr(ledger, "append", append)
        first = execute(["a"], "phase-one")
        assert launch_count == len(
            [row for row in ledger.events if row["event"] == "launch_intent"]
        )
        assert (root / "src/a.py").read_text() == "VALUE = 1\n"
        assert not (root / "src/c.py").exists()
        assert not owned_processes(root)
        second = execute(["c"], "phase-two")
        assert first["run_id"] != second["run_id"]
        assert first["tip"] == second["start"]
        assert (root / "src/c.py").read_text() == "VALUE = 1\n"
        intents = [row for row in ledger.events if row["event"] == "native_intent"]
        assert intents[0]["port"] != intents[1]["port"]
        for closed, title in ((first, "a"), (second, "c")):
            tasks = json.loads(
                (build.run_dir / "native" / closed["run_id"] / "tasks.json").read_text()
            )
            assert [task["title"] for task in tasks] == [title]
            assert closed["proofs"][0]["title"] == title
            # A run that needed no tolerance still journals the field, so a reader of
            # the receipt can tell "none exercised" from "an older row that never said".
            assert closed["waivers"] == []
        assert not owned_processes(root)
