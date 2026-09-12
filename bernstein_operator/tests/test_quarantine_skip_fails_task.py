from __future__ import annotations

from unittest.mock import MagicMock

import httpx
from bernstein.core.agents.spawner_core import AgentSpawner
from bernstein.core.models import OrchestratorConfig, Task
from bernstein.core.orchestration.orchestrator import Orchestrator, TickResult
from bernstein.core.security.quarantine import QUARANTINE_THRESHOLD, QuarantineStore
from bernstein.core.tasks import task_lifecycle


def test_quarantined_task_is_failed_rather_than_left_open(tmp_path, monkeypatch):
    """A skipped quarantined task must leave `open`, or the run never self-stops.

    8b quiescence needs a zero RAW open count, so a task the spawner refuses to claim
    and never fails makes the orchestrator tick forever with no agents - the wedge that
    took three of four eval cases on 2026-09-11.
    """
    task = Task(
        id="wedged-id",
        role="synthesizer",
        title="Synthesize review-report.md from all PR-review lens findings",
        description="Merge the lens findings into one report.",
        model="gpt-5.6-sol",
    )
    quarantine = QuarantineStore(tmp_path / "quarantine.json")
    for _ in range(QUARANTINE_THRESHOLD):
        quarantine.record_failure(task.title, "exhausted retries")
    assert quarantine.is_quarantined(task.title)

    adapter = MagicMock()
    adapter.name.return_value = "codex"
    adapter.is_rate_limited.return_value = False
    spawner = AgentSpawner(
        adapter, tmp_path / "templates/roles", tmp_path, default_model="gpt-5.6-sol"
    )
    requests: list[str] = []

    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={"id": task.id, "status": "failed"})

    client = httpx.Client(transport=httpx.MockTransport(respond), base_url="http://testserver")
    config = OrchestratorConfig(
        server_url="http://testserver", max_agents=1, evolution_enabled=False
    )
    orch = Orchestrator(config, spawner, tmp_path, client=client)
    orch._quarantine = quarantine
    orch._batch_api = None
    orch._convergence_guard = None

    def spawn(batch):
        raise AssertionError("a quarantined task must never be spawned")

    monkeypatch.setattr(spawner, "spawn_for_tasks", spawn)
    try:
        task_lifecycle.claim_and_spawn_batches(orch, [[task]], 0, set(), set(), TickResult())
        assert any(path.endswith(f"/tasks/{task.id}/fail") for path in requests), requests
        assert not any(path.endswith("/claim") for path in requests), requests
    finally:
        client.close()
