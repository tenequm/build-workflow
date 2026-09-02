"""Thin herdr CLI wrapper plus the launch hygiene rules learned in the evals."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

DIALOG_MARKERS = ("Update available", "Do you trust the contents", "Skip until next version", "press enter to continue")


def call(*args: str) -> dict:
    out = subprocess.run(["herdr", *args], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)}: {out.stderr.strip() or out.stdout.strip()}")
    text = out.stdout.strip()
    return json.loads(text) if text.startswith("{") else {"raw": text}


def status(name: str) -> str:
    try:
        return call("agent", "get", name)["result"]["agent"]["agent_status"]
    except Exception:
        return "gone"


def screen(name: str, lines: int = 30) -> str:
    out = subprocess.run(["herdr", "agent", "read", name, "--source", "detection", "--lines", str(lines)], capture_output=True, text=True, check=False)
    return out.stdout


def workspace_for_run(run_dir: Path, label: str) -> str:
    """The run's herdr workspace id, created once by /build-run or here, recorded in <run>/herdr.json."""
    rec = run_dir / "herdr.json"
    if rec.exists():
        ws = json.loads(rec.read_text()).get("workspace")
        if ws:
            return ws
    res = call("workspace", "create", "--cwd", str(run_dir.parent.parent.parent), "--label", label, "--no-focus")["result"]
    ws = res["workspace"]["workspace_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps({"workspace": ws, "root_pane": res["root_pane"]["pane_id"]}))
    return ws


def open_tab(workspace: str, cwd: Path, label: str) -> str:
    return call("tab", "create", "--workspace", workspace, "--cwd", str(cwd), "--label", label)["result"]["root_pane"]["pane_id"]


def start_agent(name: str, kind: str, pane: str, args: list[str]) -> None:
    call("agent", "start", name, "--kind", kind, "--pane", pane, "--timeout", "120000", "--", *args)
    time.sleep(3)
    shot = screen(name)
    if any(m.lower() in shot.lower() for m in DIALOG_MARKERS):
        raise RuntimeError(f"agent {name} ({kind}) shows a dialog before the first prompt; refusing to send Enter blind:\n{shot[-600:]}")


def prompt(name: str, text: str) -> None:
    call("agent", "prompt", name, text)


def stop_agent(name: str) -> None:
    subprocess.run(["herdr", "agent", "send-keys", name, "ctrl+c"], capture_output=True, check=False)


def pretrust_agy(path: Path) -> None:
    """agy shows a workspace-trust prompt that herdr reports as idle (herdrdev/herdr#3419); trust the path first."""
    settings = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    if not settings.exists():
        return
    data = json.loads(settings.read_text())
    trusted = data.setdefault("trustedWorkspaces", [])
    if str(path) not in trusted:
        trusted.append(str(path))
        settings.write_text(json.dumps(data, indent=2) + "\n")
