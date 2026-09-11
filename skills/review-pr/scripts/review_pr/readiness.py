"""Everything that must be true before a paid review starts.

The expensive failure this prevents is the one measured on 2026-09-10: a vendor
sandbox refusing every command reads exactly like a model that had nothing to do, and
costs hours. So the sandbox tier is resolved here, by executing in it, before any
session is launched.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

from operator_driver.storage import Park

from . import config, pondsync, sandbox
from .proc import command

TOOLS = ("git", "gh", "acpx", "rg")
MODULES = ("yaml", "psutil")
DISK_FLOOR_GB = 10


def _check(name: str, ok: bool, detail: str, *, blocking: bool = True) -> dict[str, Any]:
    return {"check": name, "ok": ok, "blocking": blocking, "detail": detail}


def tools() -> list[dict[str, Any]]:
    results = []
    for name in TOOLS:
        found = shutil.which(name)
        if not found:
            results.append(_check(f"tool:{name}", False, "not on PATH"))
            continue
        code, out, err = command([name, "--version"], Path.cwd(), timeout=30)
        version = (out + err).decode(errors="replace").strip().splitlines()
        results.append(_check(f"tool:{name}", code == 0, version[0] if version else found))
    for name in MODULES:
        results.append(
            _check(
                f"module:{name}",
                importlib.util.find_spec(name) is not None,
                "importable" if importlib.util.find_spec(name) else "missing",
            )
        )
    return results


def routed(plan: dict[str, Any]) -> set[str]:
    """Every family this run can launch a session on, lenses and roles alike.

    Lens routing alone is not the answer: a one-family template declares its verifier
    on a second family that no lens names, and an unresolvable adapter there is found
    only after every lens session has been paid for.
    """
    used = {plan["lenses"][lens]["family"] for lens in config.active_lenses(plan)}
    used |= set(plan["roles"]["verifier"].get("models") or {})
    used.add(plan["roles"]["claims"]["family"])
    return used


def adapters(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """A family whose adapter cannot be resolved must not be routed to."""
    results = []
    reachable = routed(plan)
    for name, family in sorted(plan["families"].items()):
        head = family["adapter_argv"][0]
        resolved = shutil.which(head) or (head if Path(head).is_file() else None)
        results.append(
            _check(
                f"adapter:{name}",
                resolved is not None,
                f"{head} -> {resolved}" if resolved else f"{head} is neither on PATH nor a file",
                # A family nothing routes to is advisory; one this run can spawn is not.
                blocking=name in reachable,
            )
        )
    return results


def check(
    plan: dict[str, Any] | None = None,
    *,
    sidecar: dict[str, Any] | None = None,
    capture: bool = True,
    requested_tier: str | None = None,
) -> dict[str, Any]:
    plan = plan or config.load()
    results = [*tools(), *adapters(plan)]
    capability = sandbox.capability()
    try:
        tier = sandbox.tier(
            requested_tier or (plan.get("sandbox") or {}).get("tier"),
            image=(plan.get("sandbox") or {}).get("image"),
        )
        results.append(
            _check(
                "sandbox",
                tier != "none",
                f"tier {tier}; user namespaces "
                f"{'available' if capability['userns'] else 'unavailable'}, "
                f"container runtime {capability['container_runtime'] or 'none'}",
            )
        )
    except Park as exc:
        tier = "none"
        results.append(_check("sandbox", False, str(exc)))
    free_gb = shutil.disk_usage(Path.cwd()).free / (1 << 30)
    results.append(
        _check(
            "disk", free_gb >= DISK_FLOOR_GB, f"{free_gb:.1f} GB free (floor {DISK_FLOOR_GB} GB)"
        )
    )
    pond = pondsync.current()
    results.append(
        _check(
            "pond",
            pond["ok"],
            f"pond {pond['version'] or 'absent'} at {pond['binary']}; pinned exactly "
            f"{pond['pinned']} like the bernstein dep - `just install-pond` provisions it",
            blocking=capture,
        )
    )
    if capture and pond["ok"]:
        found = pondsync.adapters()
        results.append(
            _check(
                "pond:agy",
                found["agy"],
                "run `pond adapters enable agy` once on a host that synced before 0.17.2",
                blocking=False,
            )
        )
    if sidecar is not None:
        provenance = sidecar["gate"]
        results.append(
            _check(
                "gate-provenance",
                provenance["source"] in ("base-project-doc", "operator"),
                f"{provenance['command']!r} from {provenance['source']}",
            )
        )
        results.append(
            _check(
                "gate-not-from-pr",
                provenance["source"] != "pr-tree",
                "the validation command is never read from the pull request tree",
            )
        )
        if sidecar.get("fast_path"):
            results.append(
                _check(
                    "fast-path",
                    False,
                    f"{sidecar['changed_lines']} changed lines is under the "
                    f"{sidecar['fast_path_threshold']}-line floor; the driver overhead loses to "
                    "the interactive skill here - use /polish",
                    blocking=False,
                )
            )
    blocking = [row for row in results if row["blocking"] and not row["ok"]]
    return {
        "tier": tier,
        "checks": results,
        "ok": not blocking,
        "blocking": [row["check"] for row in blocking],
    }


def require(report: dict[str, Any]) -> None:
    if not report["ok"]:
        detail = "; ".join(
            f"{row['check']}: {row['detail']}"
            for row in report["checks"]
            if row["blocking"] and not row["ok"]
        )
        raise Park(f"review readiness refused: {detail}")
