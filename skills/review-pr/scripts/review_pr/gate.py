"""Stage 1: the pinned validation command, run once, on a cold tool cache.

Cold matters. Codex over-claimed a clean lint twice against a warm golangci cache
(research overview, process findings), so the caches a linter consults are redirected
into this review's own workspace and the redirection is recorded. The build cache is
left alone: a stale lint verdict is the hazard, a slow rebuild is not.

Failures here are findings. Review mode never edits the tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import findings, sandbox

# Caches whose staleness has produced a wrong verdict, redirected per run.
COLD_CACHES = (
    "GOLANGCI_LINT_CACHE",
    "RUFF_CACHE_DIR",
    "MYPY_CACHE_DIR",
    "PYTEST_ADDOPTS",
    "ESLINT_CACHE_LOCATION",
    "BIOME_CACHE_DIR",
)


def cold_env(workspace: Path) -> dict[str, str]:
    cache = workspace / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    env = {name: str(cache / name.lower()) for name in COLD_CACHES if name != "PYTEST_ADDOPTS"}
    env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
    return env


def run(sidecar: dict[str, Any], *, tier: str) -> dict[str, Any]:
    """Execute the base-pinned command against the pull request tree."""
    workspace = Path(sidecar["scratch"]).parent
    result = sandbox.run(
        sidecar["gate"]["command"],
        Path(sidecar["tree"]),
        tier_name=tier,
        image=sidecar.get("sandbox_image"),
        timeout=float(sidecar.get("gate_timeout_s", 1800)),
        env=cold_env(workspace),
    )
    hits = []
    refused = bool(result["returncode"]) and sandbox.could_not_run(result)
    if result["returncode"] and not refused:
        tail = (result["stderr"] or result["stdout"]).strip().splitlines()[-12:]
        hits.append(
            findings.normalize(
                {
                    "scope": "meta",
                    "file": "CHECK:gate",
                    "line": 1,
                    "category": "correctness",
                    "claim": f"The project's own validation command fails on this pull "
                    f"request's head: {sidecar['gate']['command']!r} exited "
                    f"{result['returncode']}.",
                    "evidence": "\n".join(tail)[:2000] or "no output captured",
                    "rubric": {
                        "kind": "command",
                        "expect": "exit_zero",
                        "run": sidecar["gate"]["command"],
                    },
                },
                lens="house-rules",
                producer="script",
            )
        )
    return {
        "could_not_run": refused,
        "command": sidecar["gate"]["command"],
        "provenance": sidecar["gate"],
        "returncode": result["returncode"],
        "timed_out": result["timed_out"],
        "tier": result["tier"],
        "cold_caches": result["env"],
        "stdout_tail": result["stdout"][-4000:],
        "stderr_tail": result["stderr"][-4000:],
        "findings": hits,
    }
