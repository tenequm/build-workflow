"""Where untrusted PR code actually runs.

Two stages execute code the pull request author wrote: the tests-fail-on-base check
in stage 0 and every rubric, repro or gate in stage 3. Both run here. Readiness
resolves the tier BEFORE any run, because a sandbox that refuses everything reads
exactly like a model that had nothing to do - the 2026-09-10 two-hour symptom.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from operator_driver.storage import Park

from .proc import command

TIERS = ("container", "userns", "none")
USERNS_MAX = Path("/proc/sys/user/max_user_namespaces")


def capability() -> dict[str, Any]:
    """What this host can actually isolate, measured rather than assumed."""
    namespaces = 0
    if USERNS_MAX.is_file():
        try:
            namespaces = int(USERNS_MAX.read_text().strip())
        except (OSError, ValueError):
            namespaces = 0
    unshare = shutil.which("unshare")
    userns = bool(unshare) and namespaces > 0
    if userns:
        # Prove it rather than infer it from the sysctl: the mapping flag this needs
        # is newer than the namespace support, and a refusal here is the finding.
        code, _, _ = command(_userns(["true"], Path.cwd()), Path.cwd(), timeout=30)
        userns = code == 0
    runtime = next((name for name in ("podman", "docker") if shutil.which(name)), None)
    container = False
    if runtime:
        container = (
            command([runtime, "info", "--format", "{{.ServerVersion}}"], Path.cwd(), timeout=30)[0]
            == 0
        )
    return {
        "max_user_namespaces": namespaces,
        "unshare": unshare,
        "userns": userns,
        "container_runtime": runtime if container else None,
        "container": container,
    }


def tier(requested: str | None = None, *, image: str | None = None) -> str:
    """The strongest tier this host can honour, or the one the operator pinned."""
    found = capability()
    if requested == "container" or (requested is None and image and found["container"]):
        if not found["container"]:
            raise Park("sandbox=container requested but no container runtime answers")
        if not image:
            raise Park("sandbox=container needs a pinned image that can run the gate")
        return "container"
    if requested in (None, "userns"):
        if found["userns"]:
            return "userns"
        if requested == "userns":
            raise Park(
                "sandbox=userns requested but unprivileged user namespaces are unavailable; "
                "enable them or pin a container image"
            )
        return "none"
    if requested == "none":
        return "none"
    raise Park(f"unknown sandbox tier: {requested!r}")


def _userns(argv: list[str], cwd: Path) -> list[str]:
    # --map-current-user keeps the caller's uid, so the worktree stays readable while
    # the fresh network namespace leaves the command with nowhere to phone home.
    return ["unshare", "--user", "--map-current-user", "--net", "--", *argv]


def _container(argv: list[str], cwd: Path, image: str) -> list[str]:
    runtime = capability()["container_runtime"]
    if not runtime:
        raise Park("container tier lost its runtime between readiness and execution")
    return [
        runtime,
        "run",
        "--rm",
        "--network=none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--volume",
        f"{cwd}:{cwd}",
        "--workdir",
        str(cwd),
        image,
        *argv,
    ]


# A command that never ran refutes nothing. These are the measured shapes of "the
# environment refused" (2026-09-11: sandboxed `uv run` with blocked egress died
# downloading dependencies before the check itself started).
COULD_NOT_RUN = re.compile(
    r"command not found|No such file or directory|not recognized"
    r"|Network is unreachable|Failed to download|Temporary failure in name resolution",
    re.IGNORECASE,
)


def could_not_run(result: dict[str, Any]) -> bool:
    """Whether the command failed to execute at all, as opposed to running and failing."""
    if result.get("timed_out"):
        return True
    output = result.get("stdout", "") + result.get("stderr", "")
    return result.get("returncode") == 127 or bool(COULD_NOT_RUN.search(output))


def run(
    script: str,
    cwd: Path,
    *,
    tier_name: str,
    image: str | None = None,
    timeout: float = 900,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute one untrusted command string and report what happened, never raise on it."""
    argv = ["bash", "-c", script]
    if tier_name == "container":
        argv = _container(argv, cwd, image or "")
    elif tier_name == "userns":
        argv = _userns(argv, cwd)
    elif tier_name != "none":
        raise Park(f"unknown sandbox tier: {tier_name!r}")
    code, out, err = command(argv, cwd, timeout=timeout, env=env, isolate=True)
    return {
        "script": script,
        "tier": tier_name,
        "env": sorted(env or {}),
        "returncode": code,
        "timed_out": code == 124,
        "stdout": out.decode(errors="replace")[-8000:],
        "stderr": err.decode(errors="replace")[-8000:],
    }
