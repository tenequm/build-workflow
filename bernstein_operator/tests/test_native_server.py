from __future__ import annotations

import secrets
import socket
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
from operator_driver.engine import no_ingress, server_identity
from operator_driver.processes import alive, launch_once, terminate
from operator_driver.storage import Ledger, Park, post_once
from operator_driver.transport import Server


def test_native_server_only_retains_driver_post_fields_and_does_not_inject_manager(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    run = {
        "run_id": "test-identity",
        "token": secrets.token_urlsafe(32),
        "url": f"http://127.0.0.1:{port}",
    }
    env = {
        "BERNSTEIN_RUN_ID": run["run_id"],
        "BERNSTEIN_AUTH_TOKEN": run["token"],
        "BERNSTEIN_OPERATOR_PORT": str(port),
        "BERNSTEIN_AUTH_DISABLED": None,
        "BERNSTEIN_WORKERS": "1",
        "WEB_CONCURRENCY": "1",
    }
    ledger = Ledger(tmp_path / "workflow")
    proc = launch_once(
        ledger, "server", [sys.executable, "-m", "operator_driver.server_worker"], tmp_path, env
    )
    client = Server(run["url"], run["token"])
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                server_identity(client, SimpleNamespace(root=tmp_path), run, proc)
                break
            except httpx.TransportError:
                assert alive(proc), (tmp_path / "workflow/processes/server.log").read_text()
                assert time.monotonic() < deadline
                time.sleep(0.1)
        assert client.tasks() == []
        body = {
            "title": "Frozen phase executor",
            "description": "Implement the pinned brief",
            "role": "resolver",
            "owned_files": ["src/component.py"],
            "depends_on": [],
            "completion_signals": [{"type": "file_contains", "value": "result.txt :: PASS"}],
            "metadata": {"operator_run": "test-identity", "context_files": ["brief.md"]},
        }
        first = post_once(ledger, client, body, "first")
        second = post_once(
            ledger, client, {**body, "title": "Next executor", "depends_on": [first]}, "second"
        )
        assert first != second
        rows = client.tasks()
        assert len(rows) == 2
        assert {row["title"] for row in rows} == {"Frozen phase executor", "Next executor"}
        assert rows[1]["depends_on"] == [first]
        assert post_once(ledger, client, body, "first") == first
        terminate(proc)
        with pytest.raises(Park, match="server process died"):
            server_identity(client, SimpleNamespace(root=tmp_path), run, proc)
    finally:
        client.close()
        terminate(proc)


@pytest.mark.parametrize(
    "relative",
    [
        "TODO.md",
        "TASKS.md",
        ".plan",
        ".sdd/backlog/open/task.md",
        ".sdd/backlog/issues/next.md",
        ".sdd/runtime/task-backlog.json",
    ],
)
def test_future_work_cannot_enter_through_native_imports(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("- [ ] Future phase work")
    with pytest.raises(Park):
        no_ingress(tmp_path)
