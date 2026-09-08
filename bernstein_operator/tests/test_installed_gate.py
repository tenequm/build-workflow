from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest
from bernstein.core.agents.spawner_merge import _quality_gate_refusal
from bernstein.core.config import seed_parser
from bernstein.core.models import Task
from bernstein.core.quality.gate_plugins import GatePluginRegistry
from bernstein.core.quality.quality_gate_coalescer import QualityGateCoalescer
from bernstein.core.tasks.task_lifecycle import _run_quality_gates
from test_scorer_contract import git

pytestmark = pytest.mark.skipif(
    "GatePluginRegistry" not in inspect.getsource(seed_parser._parse_single_pipeline_step),
    reason="run this contract with the patched source engine and installed operator wheel",
)


def test_installed_plugin_is_reached_at_both_native_gate_callsites(attempt):
    root, wt = attempt
    registry = GatePluginRegistry(root)
    assert type(registry.get("scorer")).__module__ == "bernstein_operator.scorer"
    config = seed_parser.parse_seed(root / "bernstein.yaml").quality_gates
    task = Task(
        id="task-one",
        role="resolver",
        title="Owned step",
        description="Implement pinned brief",
        owned_files=["src/code.py", "src/test_code.py"],
    )
    session = SimpleNamespace(id="test", task_ids=[task.id], role=task.role)
    admitted = root / ".agents/build/runs/demo/admitted/native-one.json"
    admitted.parent.mkdir(parents=True)
    admitted.write_text(json.dumps({task.id: task.title}))
    snapshot = root / ".sdd/runtime/tasks.jsonl"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(
        json.dumps(
            {
                "id": task.id,
                "title": task.title,
                "owned_files": task.owned_files,
                "metadata": {"operator_run": "native-one"},
            }
        )
        + "\n"
    )
    orch = SimpleNamespace(
        _quality_gate_config=config,
        _workdir=root,
        _spawner=SimpleNamespace(get_worktree_path=lambda session_id: wt),
        _gate_coalescer=QualityGateCoalescer(),
    )
    tick = SimpleNamespace(verified=[task.id], verification_failures=[])
    passed, _ = _run_quality_gates(orch, task, session, tick)
    assert passed
    assert _quality_gate_refusal(session, root, "agent/test", quality_gate_config=config) is None
    receipts = [
        json.loads(path.read_text())
        for path in (root / ".agents/build/runs/demo/reports").glob("*/*/receipt.json")
    ]
    assert len(receipts) == 2
    assert all(row["status"] == "pass" for row in receipts)
    assert sum(row["memo_of"] is not None for row in receipts) == 1
    (wt / "src/unowned.py").write_text("UNOWNED = True\n")
    git(wt, "commit", "-qam", "unowned work")
    assert not _run_quality_gates(orch, task, session, tick)[0]
    refusal = _quality_gate_refusal(session, root, "agent/test", quality_gate_config=config)
    assert refusal is not None and not refusal.success
    assert tick.verification_failures == [(task.id, ["quality_gate:scorer"])]
