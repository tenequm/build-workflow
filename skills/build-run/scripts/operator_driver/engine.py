"""Launch, observe, and seal one native run. No bootstrap or soft-drain path."""

from __future__ import annotations

import json
import math
import os
import secrets
import socket
import sys
import time
import uuid
from pathlib import Path

import httpx
import psutil
from bernstein.core.persistence.runs_report import list_finished_runs
from bernstein.core.persistence.wal import WALRecovery
from bernstein.core.security.quarantine import QuarantineStore

from .admission import clean_root, disk_check, no_ingress, prerequisites
from .processes import alive, launch_once, owned_processes, terminate
from .reconcile import archive_native, close_proven_wal, native_events, prove_delivery
from .spec import Build, git
from .storage import Ledger, Park, atomic, canonical, digest, immutable, post_once
from .transport import Server, admitted_inventory


def cost_for(root: Path, run_id: str) -> float:
    path = root / ".sdd/cost/ledger.jsonl"
    total = 0.0
    if not path.exists():
        return total
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise Park("cost ledger has a torn tail")
    for line in raw.splitlines():
        row = json.loads(line)
        if row.get("run_id") != run_id:
            continue
        amount = row.get("cost_usd")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise Park("invalid native spend evidence")
        total += amount
    return total


def run_env(build: Build, run: dict, base: str) -> dict:
    # Provider credentials remain inherited. Native ambient overrides do not.
    env = {key: None for key in os.environ if key.startswith("BERNSTEIN_")}
    env.update(
        {
            "BERNSTEIN_RUN_ID": run["run_id"],
            "BERNSTEIN_AUTH_TOKEN": run["token"],
            "BERNSTEIN_SERVER_URL": run["url"],
            "BERNSTEIN_RESPONSE_CACHE": "0",
            "BERNSTEIN_OPERATOR_LOCAL_ONLY": "1",
            "BERNSTEIN_OPERATOR_ROOT": str(build.root),
            "BERNSTEIN_OPERATOR_PLAN": build.rel,
            "BERNSTEIN_OPERATOR_BASE": base,
            "BERNSTEIN_OPERATOR_BRANCH": build.branch,
            "BERNSTEIN_OPERATOR_PORT": str(run["port"]),
            "BERNSTEIN_WORKERS": "1",
            "BERNSTEIN_HARD_BUDGET_USD": str(build.bounds["run_budget_usd"]),
            "WEB_CONCURRENCY": "1",
        }
    )
    return env


def server_identity(client: Server, build: Build, run: dict, receipt: dict):
    if not alive(receipt):
        raise Park("identified task-server process died")
    response = client.client.get("/operator/identity")
    response.raise_for_status()
    info = response.json()
    if info.get("run_id") != run["run_id"] or info.get("root") != str(build.root):
        raise Park("port belongs to a different server")
    child = psutil.Process(info["pid"])
    if child not in psutil.Process(receipt["pid"]).children(recursive=True):
        raise Park("server identity is not a child of the recorded launcher")
    with httpx.Client(timeout=5) as anonymous:
        if anonymous.get(run["url"] + "/operator/identity").status_code not in (401, 403):
            raise Park("task server does not enforce authentication")


def seal(
    build: Build,
    ledger: Ledger,
    run: dict,
    expected: dict,
    client: Server,
    server_proc: dict,
    spawn_proc: dict,
) -> dict:
    if alive(spawn_proc):
        raise Park("cannot seal a running scheduler")
    operation = run["operation"]
    exit_path = ledger.directory / "processes" / f"{operation}-spawner.exit.json"
    if not exit_path.exists():
        raise Park("scheduler exited without a process completion receipt")
    exit_record = json.loads(exit_path.read_text())
    if exit_record["returncode"] or exit_record["residual"]:
        raise Park("scheduler failed or left residual child processes")
    tasks_path = build.run_dir / "closure" / run["run_id"] / "tasks.json"
    if tasks_path.exists():
        tasks = json.loads(tasks_path.read_text())
    else:
        server_identity(client, build, run, server_proc)
        tasks = client.tasks()
        immutable(tasks_path, canonical(tasks))
    events = native_events(build.root / ".sdd/runs" / run["run_id"] / "journal.jsonl", closed=True)
    terminate(server_proc)
    if owned_processes(build.root):
        raise Park("native processes survived the phase boundary")
    clean_root(build)
    if git(build.root, "symbolic-ref", "--short", "HEAD") != build.branch:
        raise Park("workspace branch was displaced")
    tip = git(build.root, "rev-parse", build.branch)
    report = canonical({"runs": [row.to_dict() for row in list_finished_runs(build.root / ".sdd")]})
    archive_native(build.root, build.run_dir, run["run_id"], tasks, report)
    proofs = prove_delivery(
        build.root, build.run_dir, run["run_id"], run["start"], tip, expected, tasks, events
    )
    close_proven_wal(build.root, run["run_id"], tasks, events)
    cost = cost_for(build.root, run["run_id"])
    if cost > build.bounds["run_budget_usd"]:
        raise Park("native run exceeded its spend reservation at closure")
    return ledger.append(
        "native_closed",
        operation=operation,
        run_id=run["run_id"],
        start=run["start"],
        tip=tip,
        proofs=proofs,
        cost_usd=cost,
    )


def execute(
    build: Build,
    ledger: Ledger,
    titles: list[str],
    operation: str,
    base: str,
    *,
    reserve,
    check_bounds,
    fix_input: dict | None = None,
) -> dict:
    closed = ledger.last("native_closed", operation=operation)
    if closed:
        archive_native(build.root, build.run_dir, closed["run_id"], [], b"")
        return closed
    run = ledger.last("native_intent", operation=operation)
    if run is None:
        if owned_processes(build.root):
            raise Park("workspace has live native or judge processes")
        no_ingress(build.root)
        disk_check(build.root)
        if WALRecovery.scan_all_uncommitted(build.root / ".sdd"):
            raise Park("prior WAL intents remain; preserve and reconcile before a fresh run")
        quarantine_path = build.root / ".sdd/runtime/quarantine.json"
        if quarantine_path.exists():
            json.loads(
                quarantine_path.read_text()
            )  # Do not accept native permissive malformed-file fallback.
        quarantine = QuarantineStore(quarantine_path)
        if any(quarantine.is_quarantined(title) for title in titles):
            raise Park("an expected step is quarantined")
        build.verify_pins(base)
        prerequisites(build)
        tasks_path = build.root / ".sdd/runtime/tasks.jsonl"
        if tasks_path.exists() and tasks_path.stat().st_size and not ledger.last("native_closed"):
            raise Park("preexisting task state has no reconciled workflow run")
        reserve(operation, build.bounds["run_budget_usd"])
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        run_id = f"operator-{uuid.uuid4().hex}"
        run = ledger.append(
            "native_intent",
            operation=operation,
            run_id=run_id,
            titles=titles,
            start=git(build.root, "rev-parse", build.branch),
            port=port,
            url=f"http://127.0.0.1:{port}",
            token=secrets.token_urlsafe(32),
            fix_hash=digest(canonical(fix_input)),
        )
    if run["titles"] != titles or run["fix_hash"] != digest(canonical(fix_input)):
        raise Park("native launch inputs changed during recovery")
    env = run_env(build, run, base)
    server_op, spawn_op = operation + "-server", operation + "-spawner"
    server_proc = spawn_proc = None
    client = Server(run["url"], run["token"])
    try:
        saved_spawn = ledger.directory / "processes" / f"{spawn_op}.json"
        saved_server = ledger.directory / "processes" / f"{server_op}.json"
        if saved_spawn.exists() and saved_server.exists():
            spawn_proc, server_proc = (
                json.loads(saved_spawn.read_text()),
                json.loads(saved_server.read_text()),
            )
            if not alive(spawn_proc):
                expected = {}
                for index, (title, _) in enumerate(
                    build.payloads(titles, run["run_id"], fix_input)
                ):
                    posted = ledger.last("post_receipt", operation=f"{operation}-task-{index}")
                    if not posted:
                        raise Park("scheduler started without a complete task admission receipt")
                    expected[title] = posted["task_id"]
                return seal(build, ledger, run, expected, client, server_proc, spawn_proc)
        if not ledger.last("launch_intent", operation=server_op):
            if owned_processes(build.root):
                raise Park("another writer appeared during launch")
            tasks_path = build.root / ".sdd/runtime/tasks.jsonl"
            if tasks_path.exists():
                immutable(
                    build.run_dir / "prelaunch" / run["run_id"] / "tasks.jsonl",
                    tasks_path.read_bytes(),
                )
                tasks_path.unlink()
            atomic(
                build.root / ".sdd/runtime/run_config.json",
                canonical(
                    {"merge_strategy": "direct", "budget_usd": build.bounds["run_budget_usd"]}
                ),
            )
        server_proc = launch_once(
            ledger,
            server_op,
            [sys.executable, "-m", "operator_driver.server_worker"],
            build.root,
            env,
            native_pid=build.root / ".sdd/runtime/server.pid",
        )
        deadline = time.monotonic() + 45
        while True:
            try:
                server_identity(client, build, run, server_proc)
                break
            except httpx.TransportError:
                if not alive(server_proc) or time.monotonic() > deadline:
                    raise Park("server did not become ready on its reserved port") from None
                time.sleep(0.2)
        expected = {}
        for index, (title, payload) in enumerate(build.payloads(titles, run["run_id"], fix_input)):
            payload["depends_on"] = [
                expected[name] for name in payload["metadata"]["operator_dependencies"]
            ]
            expected[title] = post_once(ledger, client, payload, f"{operation}-task-{index}")
        admitted_inventory(client.tasks(), set(expected.values()))
        immutable(
            build.run_dir / "admitted" / f"{run['run_id']}.json",
            canonical({task_id: title for title, task_id in expected.items()}),
        )
        spawn_proc = launch_once(
            ledger,
            spawn_op,
            [
                sys.executable,
                "-m",
                "bernstein.core.orchestration.orchestrator",
                "--port",
                str(run["port"]),
                "--cells",
                "1",
                "--seed-path",
                str(build.root / "bernstein.yaml"),
            ],
            build.root,
            env,
            native_pid=build.root / ".sdd/runtime/spawner.pid",
        )
        journal = build.root / ".sdd/runs" / run["run_id"] / "journal.jsonl"
        while alive(spawn_proc):
            check_bounds()
            disk_check(build.root)
            no_ingress(build.root)
            server_identity(client, build, run, server_proc)
            admitted_inventory(client.tasks(), set(expected.values()))
            events = native_events(journal)
            if time.time() - run["time"] > 120 and not any(
                row.get("event") == "agent_spawned" for row in events
            ):
                raise Park("no executor started within 120 seconds")
            if cost_for(build.root, run["run_id"]) > build.bounds["run_budget_usd"]:
                raise Park("native run exceeded its spend reservation")
            time.sleep(1)
        return seal(build, ledger, run, expected, client, server_proc, spawn_proc)
    finally:
        client.close()
        # Never ask Bernstein to drain: rejected branches must not be auto-merged.
        if spawn_proc is not None:
            terminate(spawn_proc)
        if server_proc is not None:
            terminate(server_proc)
