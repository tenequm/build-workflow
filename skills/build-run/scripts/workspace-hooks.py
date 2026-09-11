#!/usr/bin/env python3
"""Capture, disable and restore local Git hooks without overwriting later configuration."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def config(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "config", "--local", *args], cwd=root, capture_output=True, text=True, timeout=30
    )
    if result.returncode not in (0, 1, 5):
        raise RuntimeError(result.stderr)
    return result.stdout.splitlines()


def configure(root: Path, run: Path, action: str) -> None:
    root, run = root.resolve(), run.resolve()
    if not run.is_relative_to(root / ".agents/build/runs"):
        raise RuntimeError("hook receipt must belong to this workspace")
    path = run / "hooks.json"
    empty = root / ".agents/build/nohooks"
    values = config(root, "--get-all", "core.hooksPath")
    if path.exists():
        receipt = json.loads(path.read_text())
        if receipt["workspace"] != str(root) or receipt["disabled"] != str(empty):
            raise RuntimeError("hook receipt belongs to another workspace")
    else:
        if action != "disable":
            raise RuntimeError("original hooks configuration was not recorded")
        if any(".agents/build/nohooks" in value for value in values):
            raise RuntimeError("another build owns the shared hooks configuration")
        receipt = {"workspace": str(root), "disabled": str(empty), "original": values}
        run.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    original = receipt["original"]
    if values not in (original, [str(empty)]):
        raise RuntimeError("hooks configuration changed outside this build; preserve it")
    desired = [str(empty)] if action == "disable" else original
    if action == "disable":
        empty.mkdir(parents=True, exist_ok=True)
        if any(empty.iterdir()):
            raise RuntimeError("disabled hook directory is not empty")
    if values != desired:
        config(root, "--unset-all", "core.hooksPath")
        for value in desired:
            config(root, "--add", "core.hooksPath", value)
    if config(root, "--get-all", "core.hooksPath") != desired:
        raise RuntimeError("hooks configuration did not persist")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("disable", "restore"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    configure(args.root, args.run, args.action)
