"""Identified processes with a receipt written before the native program executes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .storage import Ledger, Park, atomic, canonical


def identity(pid: int) -> dict:
    process = psutil.Process(pid)
    return {"pid": pid, "created": process.create_time(), "pgid": os.getpgid(pid)}


def alive(receipt: dict) -> bool:
    try:
        process = psutil.Process(receipt["pid"])
        return (
            process.create_time() == receipt["created"] and process.status() != psutil.STATUS_ZOMBIE
        )
    except psutil.NoSuchProcess:
        return False


def owned_processes(
    root: Path, *, exclude: set[int] | None = None, all_commands: bool = False
) -> list[dict]:
    found = []
    for process in psutil.process_iter(["pid", "cmdline", "name"]):
        if process.pid <= 0 or process.pid in (exclude or set()) or process.pid == os.getpid():
            continue
        try:
            argv = process.info["cmdline"] or []
            command = " ".join(argv)
            name = process.info["name"] or ""
            relevant = (
                all_commands
                or name in {"bernstein", "codex", "claude", "agy", "acpx"}
                or any(arg.startswith(("bernstein.", "operator_driver.")) for arg in argv)
                or any("/acpx/" in arg or "claude-agent-acp" in arg for arg in argv)
            )
            if relevant and Path(process.cwd()).resolve().is_relative_to(root.resolve()):
                if process.status() != psutil.STATUS_ZOMBIE:
                    found.append({**identity(process.pid), "command": command})
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            continue
    return found


def terminate(receipt: dict, timeout: float = 10) -> None:
    """No native drain: signals only, guarded against PID reuse."""
    if not alive(receipt):
        return
    process = psutil.Process(receipt["pid"])
    descendants = [
        identity(child.pid) for child in process.children(recursive=True) if child.is_running()
    ]
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except psutil.TimeoutExpired:
        if alive(receipt):
            process.kill()
            process.wait(timeout=timeout)
    for child in descendants:
        if alive(child):
            psutil.Process(child["pid"]).kill()
    if any(alive(child) for child in descendants):
        _, survivors = psutil.wait_procs(
            [psutil.Process(child["pid"]) for child in descendants if alive(child)], timeout=timeout
        )
        if survivors:
            raise Park("process descendants survived teardown")


def cancel_acp(receipt: dict, timeout: float = 10) -> None:
    """Interrupt acpx itself so it sends session/cancel before forced teardown."""
    if not alive(receipt):
        return
    wrapper = psutil.Process(receipt["pid"])
    for child in wrapper.children():
        try:
            child.send_signal(signal.SIGINT)
        except psutil.NoSuchProcess:
            pass
    deadline = time.monotonic() + timeout
    while alive(receipt) and time.monotonic() < deadline:
        time.sleep(0.05)
    terminate(receipt, timeout)


def launch_once(
    ledger: Ledger,
    operation: str,
    argv: list[str],
    cwd: Path,
    env: dict[str, str | None],
    *,
    native_pid: Path | None = None,
    stdin: Path | None = None,
) -> dict:
    receipt_path = ledger.directory / "processes" / f"{operation}.json"
    record = ledger.last("launch_intent", operation=operation)
    if record and record["argv"] != argv:
        raise Park("launch intent changed")
    if receipt_path.exists():
        return json.loads(receipt_path.read_text())
    if record:
        raise Park("launch has no process receipt; investigate before relaunch")
    ledger.append(
        "launch_intent", operation=operation, argv=argv, cwd=str(cwd), receipt=str(receipt_path)
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper = [
        sys.executable,
        "-m",
        "operator_driver.processes",
        str(receipt_path),
        str(native_pid) if native_pid else "-",
        *argv,
    ]
    scripts = str(Path(__file__).resolve().parents[1])
    launch_env = dict(os.environ)
    for key, value in env.items():
        if value is None:
            launch_env.pop(key, None)
        else:
            launch_env[key] = value
    launch_env["PYTHONPATH"] = scripts + os.pathsep + launch_env.get("PYTHONPATH", "")
    with (receipt_path.with_suffix(".log")).open("ab") as output:
        with (stdin or Path(os.devnull)).open("rb") as input_stream:
            proc = subprocess.Popen(
                wrapper,
                cwd=cwd,
                env=launch_env,
                stdin=input_stream,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    deadline = time.monotonic() + 15
    while not receipt_path.exists():
        if proc.poll() is not None or time.monotonic() > deadline:
            raise Park(f"launcher did not establish a process receipt: {operation}")
        time.sleep(0.05)
    receipt = json.loads(receipt_path.read_text())
    ledger.append("launch_receipt", operation=operation, process=receipt)
    return receipt


def child() -> None:
    path, native_pid, *argv = sys.argv[1:]
    if not argv:
        raise SystemExit("missing child command")
    record = {**identity(os.getpid()), "argv": argv, "cwd": str(Path.cwd())}
    atomic(Path(path), canonical(record))
    proc = subprocess.Popen(argv)
    if native_pid != "-":
        atomic(Path(native_pid), str(proc.pid).encode())
    code = proc.wait()
    residual = []
    for process in psutil.process_iter(["pid", "status"]):
        try:
            if (
                process.pid > 0
                and process.pid != os.getpid()
                and process.info["status"] != psutil.STATUS_ZOMBIE
                and os.getpgid(process.pid) == record["pgid"]
            ):
                residual.append(identity(process.pid))
                process.kill()
        except (ProcessLookupError, psutil.NoSuchProcess):
            continue
    atomic(
        Path(path).with_suffix(".exit.json"), canonical({"returncode": code, "residual": residual})
    )
    raise SystemExit(code)


if __name__ == "__main__":
    child()
