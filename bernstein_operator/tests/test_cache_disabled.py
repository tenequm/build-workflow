from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from bernstein.core.agents.spawner_core import AgentSpawner
from bernstein.core.knowledge.semantic_cache import ResponseCacheManager
from bernstein.core.models import OrchestratorConfig, Task
from bernstein.core.orchestration.orchestrator import Orchestrator, TickResult
from bernstein.core.tasks import task_lifecycle
from test_scorer_contract import git

from bernstein_operator.scorer import ScorerGate


class ReachedExecutor(BaseException):
    pass


@pytest.mark.parametrize("scenario", ["preloaded", "during-run", "restart", "merge-reopen"])
def test_native_claim_path_cannot_reuse_semantic_responses(attempt, monkeypatch, scenario):
    root, wt = attempt
    # A real native boot sweeps old .sdd/worktrees entries. Keep this recording
    # executor fixture outside that boot-owned tree, as the ceremony does.
    isolated = root / ".agents/build/runs/demo/recording-executor"
    isolated.parent.mkdir(parents=True)
    git(root, "worktree", "move", str(wt), str(isolated))
    wt = isolated
    monkeypatch.setenv("BERNSTEIN_RESPONSE_CACHE", "0")
    task = Task(
        id="fresh-id",
        role="resolver",
        title="Owned step",
        description="Implement the owned behavior. Attempt identity: fresh.",
        model="gpt-5.6-sol",
        owned_files=["src/code.py"],
    )
    cache = ResponseCacheManager(root)
    key = cache.task_key(task.role, task.title, task.description)
    cache.store(key, "Old verified answer", verified=True, git_diff_lines=10)
    cache.save()
    assert cache.lookup_entry(key)[0].verified
    adapter = MagicMock()
    adapter.name.return_value = "codex"
    adapter.is_rate_limited.return_value = False
    spawner = AgentSpawner(adapter, root / "templates/roles", root, default_model="gpt-5.6-sol")
    requests = []

    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={"id": task.id, "status": "claimed"})

    client = httpx.Client(transport=httpx.MockTransport(respond), base_url="http://testserver")
    config = OrchestratorConfig(
        server_url="http://testserver", max_agents=1, evolution_enabled=False
    )
    orch = Orchestrator(config, spawner, root, client=client)
    assert orch._response_cache is None
    if scenario in {"during-run", "merge-reopen"}:
        cache.store(key, "New answer populated after startup", verified=True, git_diff_lines=11)
        cache.save()
    if scenario == "restart":
        monkeypatch.setenv("BERNSTEIN_RUN_ID", "fresh-restart")
        orch = Orchestrator(config, spawner, root, client=client)
        assert orch._response_cache is None
    if scenario == "merge-reopen":
        task.metadata["retry_of"] = "failed-merge"
    scored = []

    def spawn(batch):
        scored.append(ScorerGate().run([], wt, batch[0].title, batch[0].description))
        raise ReachedExecutor

    monkeypatch.setattr(spawner, "spawn_for_tasks", spawn)
    # Disable unrelated provider batch scheduling; the actual two semantic-cache
    # branches, HTTP claim and native spawn dispatch remain intact.
    orch._batch_api = None
    orch._convergence_guard = None
    try:
        with pytest.raises(ReachedExecutor):
            task_lifecycle.claim_and_spawn_batches(orch, [[task]], 0, set(), set(), TickResult())
        assert any(path.endswith("/claim") for path in requests)
        assert not any(path.endswith("/complete") for path in requests)
        assert len(scored) == 1 and not scored[0].blocked
    finally:
        client.close()
