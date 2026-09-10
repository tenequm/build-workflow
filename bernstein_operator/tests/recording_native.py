"""Real native CLI boot with only the paid adapter spawn replaced for acceptance."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import httpx
from bernstein.adapters.base import SpawnResult
from bernstein.adapters.codex import CodexAdapter


def spawn(self, *, workdir, **kwargs):
    log = workdir / ".sdd/runtime/recording.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as output:
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "worker"],
            cwd=workdir,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    return SpawnResult(pid=proc.pid, log_path=log, proc=proc)


def worker():
    import yaml
    from operator_driver.transport import Server

    root = Path(os.environ["BERNSTEIN_OPERATOR_ROOT"])
    client = Server(os.environ["BERNSTEIN_SERVER_URL"], os.environ["BERNSTEIN_AUTH_TOKEN"])
    tasks = [task for task in client.tasks() if task["status"] == "claimed"]
    assert len(tasks) == 1, tasks
    task = tasks[0]
    sidecar = yaml.safe_load(
        (root / os.environ["BERNSTEIN_OPERATOR_PLAN"]).with_suffix(".steps.yaml").read_text()
    )
    source = Path(task["owned_files"][0])
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n")
    report = Path(sidecar["steps"][task["title"]]["report"])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("Validation: exit 0\n## Deviations\nNone.\n")
    subprocess.run(["git", "add", "-f", str(source), str(report)], check=True)
    subprocess.run(["git", "commit", "-m", "feat(test): recorded executor change"], check=True)
    response = client.client.post(
        f"/tasks/{task['id']}/complete",
        json={
            "result_summary": "Implemented the owned behavior and committed its measured validation report."
        },
    )
    response.raise_for_status()
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}))
    client.close()


if __name__ == "__main__":
    if sys.argv[1:] == ["worker"]:
        worker()
    else:
        CodexAdapter.spawn = spawn
        # The seed disables internal LLM work; refuse any accidentally attempted
        # external network request in this recording process.
        original_send = httpx.Client.send

        def local_only(self, request, *args, **kwargs):
            if request.url.host not in {"127.0.0.1", "localhost", "testserver"}:
                raise RuntimeError("acceptance forbids external requests")
            return original_send(self, request, *args, **kwargs)

        httpx.Client.send = local_only
        runpy.run_module("bernstein.core.orchestration.orchestrator", run_name="__main__")
