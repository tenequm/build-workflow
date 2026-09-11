"""The whole review, stage by stage, with the driver owning every boundary.

Stage 0 lints, stage 1 gates, stage 2 produces claims through four lenses, stage 3
verifies them, stage 4 synthesises. Each stage is a separate batch that returns only
when every one of its receipts is written, which is what makes the next stage's input
complete. Nothing here re-derives the plan: the shape is static and lives in
templates/stages.yaml.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from operator_driver.storage import Ledger, atomic, canonical

from . import (
    briefs,
    config,
    diffindex,
    dualfamily,
    houserules,
    pondcost,
    pondsync,
    suggestions,
    synthesize,
)
from . import (
    claims as claims_mod,
)
from . import (
    findings as findings_mod,
)
from . import (
    gate as gate_mod,
)
from . import (
    ledger as ledger_mod,
)
from . import (
    verify as verify_mod,
)
from .runner import Task, run_batch

Launcher = Callable[[list[Task]], dict[str, dict[str, Any]]]


def lens_families(plan: dict[str, Any], lens: str, author: dict[str, Any]) -> list[tuple[str, str]]:
    """Which families run this lens, and why. Never returns a forbidden pairing."""
    routing = plan.get("routing", {})
    default = plan["lenses"][lens]["family"]
    chosen: list[tuple[str, str]] = []
    family = default
    override = routing.get("override")
    reason = (
        f"the whole-run --family {override} override"
        if override
        else "the template's default family"
    )
    if lens in (routing.get("reroute_lenses") or []) and author.get("family") not in (
        None,
        "unknown",
    ):
        target = (routing.get("opposite") or {}).get(author["family"])
        forbidden = plan["lenses"][lens].get("forbid_families") or []
        if target and target in plan["families"] and target not in forbidden:
            family, reason = target, f"routed opposite the {author['family']} author"
        elif target in forbidden:
            reason = (
                f"kept on {default}: routing opposite the {author['family']} author would "
                f"have used {target}, which this lens forbids"
            )
    chosen.append((family, reason))
    dual = plan.get("dual_family") or {}
    if dual.get("enabled") and lens in (dual.get("lenses") or []):
        forbidden = set(plan["lenses"][lens].get("forbid_families") or []) | {family}
        alternate = next((name for name in sorted(plan["families"]) if name not in forbidden), None)
        if alternate:
            chosen.append((alternate, "the dual-family second opinion"))
    return chosen


def stage2(
    sidecar: dict[str, Any],
    plan: dict[str, Any],
    paths: dict[str, Path],
) -> tuple[list[Task], list[dict[str, Any]]]:
    tasks: list[Task] = []
    routing: list[dict[str, Any]] = []
    for lens in config.active_lenses(plan):
        for family, reason in lens_families(plan, lens, sidecar.get("author_family") or {}):
            spec = config.lens_spec(plan, lens, family=family)
            brief, report, witness = briefs.reviewer(lens, sidecar, paths)
            operation = f"review-{lens}-{family}"
            tasks.append(
                Task(
                    operation=operation,
                    key=operation,
                    brief=brief,
                    report=report,
                    witness=witness,
                    spec=spec,
                    lens=lens,
                    family=family,
                    meta={"lens": lens, "family": family, "reason": reason},
                )
            )
            routing.append(
                {
                    "lens": lens,
                    "family": family,
                    "model": spec["model"],
                    "reason": reason,
                    "operation": operation,
                }
            )
    brief, report, witness = briefs.claims(sidecar, paths)
    spec = config.role_spec(plan, "claims")
    # Extraction is production, not verification: it reads the body and writes a list,
    # it decides nothing. Executing that list is stage 3's job.
    tasks.append(
        Task(
            operation="claims-extract",
            key="claims-extract",
            brief=brief,
            report=report,
            witness=witness,
            spec=spec,
            lens="claims",
            family=spec["family"],
            meta={"role": "claims"},
        )
    )
    return tasks, routing


def collect(
    tasks: list[Task],
    receipts: dict[str, dict[str, Any]],
    ledger: Ledger,
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], list[dict[str, Any]], list[str]]:
    """Read every lens report. A task with no usable report is recorded, never guessed at."""
    per_lens: dict[str, dict[str, list[dict[str, Any]]]] = {}
    extracted: list[dict[str, Any]] = []
    missing: list[str] = []
    for task in tasks:
        receipt = receipts[task.operation]
        if not receipt["ok"]:
            missing.append(f"{task.operation}: {'; '.join(receipt['problems'])}")
            continue
        path = ledger.directory / "sessions" / receipt["operation"] / Path(task.report).name
        if task.lens == "claims":
            extracted = claims_mod.load(path)
            continue
        found = findings_mod.load(path, lens=task.lens or "", producer=task.family)
        per_lens.setdefault(task.lens or "", {})[task.family] = [
            {**finding, "producer_model": receipt["model"]} for finding in found
        ]
    return per_lens, extracted, missing


def fuse(
    per_lens: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-lens dual-family diff, then one row per claim across lenses."""
    produced: list[dict[str, Any]] = []
    report: dict[str, Any] = {}
    for lens, by_family in sorted(per_lens.items()):
        diffed = dualfamily.diff_sets(by_family)
        report[lens] = {
            "families": diffed["families"],
            "agreed": diffed["agreed"],
            "disagreed": diffed["disagreed"],
        }
        produced.extend(diffed["findings"])
    return findings_mod.merge(produced), report


def _product(workspace: Path, name: str, compute: Callable[[], Any], *, guard: Any = None) -> Any:
    """A stage's output, durable the moment the stage finishes.

    Bernstein's restart law, at this workflow's scale: a rerun re-derives from what is
    on disk and never re-decides - or re-executes - a stage that already completed.
    Session receipts already make model work resumable; this makes the driver-side
    work (sandboxed test runs, rubric executions, suggestion proofs) resumable too.
    A stale product is invalidated by deleting the file or the workspace, which is
    also how a changed pull request head invalidates everything: setup refuses to
    reuse a workspace built for another head.
    """
    path = workspace / "products" / f"{name}.json"
    if path.is_file():
        data = json.loads(path.read_bytes())
        if isinstance(data, dict) and set(data) == {"guard", "result"}:
            if data["guard"] == guard:
                return data["result"]
            # A product computed under other conditions (a different sandbox tier) is
            # not this run's product: recompute rather than resume over it.
        else:
            return data
    result = compute()
    atomic(path, canonical({"guard": guard, "result": result}), mode=0o644)
    return result


def run(
    workspace: Path,
    sidecar: dict[str, Any],
    plan: dict[str, Any],
    ledger: Ledger,
    *,
    tier: str,
    launch: Launcher | None = None,
    capture: bool = True,
    run_id: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    run_id = run_id or f"{sidecar['repo'].replace('/', '-')}-{sidecar['number']}-{int(time.time())}"
    bounds = plan["bounds"]

    def default_launch(tasks: list[Task]) -> dict[str, dict[str, Any]]:
        return run_batch(
            tasks,
            sidecar,
            ledger,
            attempts=int(bounds["attempts_per_task"]),
            wall_cap=float(bounds["max_wall_s"]),
        )

    launcher: Launcher = launch or default_launch
    diff = (workspace / sidecar["diff"]).read_text(errors="replace")
    pr = json.loads((workspace / "pr.json").read_text())
    paths = briefs.inputs(workspace, sidecar, diff, str(pr.get("body") or ""))

    lint = _product(
        workspace,
        "stage0-lint",
        lambda: houserules.lint(sidecar, pr, diff, tier=tier),
        guard={"tier": tier},
    )
    ledger.append("stage_complete", operation="stage0", findings=len(lint["findings"]))
    gate = _product(
        workspace, "stage1-gate", lambda: gate_mod.run(sidecar, tier=tier), guard={"tier": tier}
    )
    ledger.append("stage_complete", operation="stage1", returncode=gate["returncode"])

    tasks, routing = stage2(sidecar, plan, paths)
    receipts = launcher(tasks)
    per_lens, extracted, missing = collect(tasks, receipts, ledger)
    produced, agreement = fuse(per_lens)
    ledger.append(
        "stage_complete", operation="stage2", produced=len(produced), missing=len(missing)
    )

    if not extracted:
        # A deterministic floor: shell prompts inside fenced blocks are claims whether
        # or not the extraction session came back.
        extracted = claims_mod.extract(str(pr.get("body") or ""))
    claim_results = _product(
        workspace,
        "stage2-claims",
        lambda: claims_mod.check(extracted, sidecar, tier=tier, diff=diff),
        guard={"tier": tier},
    )

    script_findings = [
        findings_mod.presettle(finding, "the check that produced it executed here")
        if not finding["follow_up"]
        else finding
        for finding in [*lint["findings"], *gate["findings"], *claim_results["findings"]]
    ]
    verified = _product(
        workspace,
        "stage3-verified",
        lambda: verify_mod.verify(
            [*produced, *script_findings],
            sidecar,
            plan,
            ledger,
            paths,
            tier=tier,
            launch=launcher,
        ),
        guard={"tier": tier},
    )
    ledger.append("stage_complete", operation="stage3", sessions=verified["sessions"])

    proofs = _product(
        workspace,
        "stage4-proofs",
        lambda: suggestions.prove_all(
            verified["findings"],
            sidecar,
            tier=tier,
            cap=int(bounds["max_proven_suggestions"]),
        ),
        guard={"tier": tier},
    )
    evidence = {
        "lint": lint,
        "gate": {key: gate[key] for key in ("command", "returncode", "tier", "cold_caches")},
        "verify": {key: verified[key] for key in ("sessions", "settled_by_rubric", "cap", "tier")},
        "routing": routing,
        "agreement": agreement,
        "gating_findings": sum(1 for f in produced if f["lens"] == "gating"),
        "claims_reproduced": claim_results["reproduced"],
        "claims_mismatched": claim_results["mismatched"],
        "claims_unchecked": claim_results["unchecked"],
        "missing_reports": missing,
        "suggestions": proofs,
        "tier": tier,
    }
    body = review_body(verified["findings"], evidence)
    evidence["wall_s"] = round(time.monotonic() - started, 1)
    # Every receipt on disk, retries included: a retry really was another session, and
    # a count derived from the task list silently omits the ones added after it.
    evidence["sessions"] = len(list((ledger.directory / "sessions").glob("*/receipt.json")))
    summary = synthesize.synthesize(
        workspace, sidecar, verified["findings"], body=body, evidence=evidence, proofs=proofs
    )
    sessions = pond_capture(workspace, ledger, summary, capture=capture)
    rows = ledger_mod.rows_for(summary, run_id, sessions)
    repo_root = Path(sidecar["repo_path"])
    ledger_mod.append(ledger_mod.path(repo_root), rows)
    summary["run"] = run_id
    summary["ledger"] = str(ledger_mod.path(repo_root))
    ledger.append("stage_complete", operation="stage4", action=summary["action"])
    atomic(workspace / "summary.json", canonical(summary), mode=0o644)
    return summary


def review_body(verified: list[dict[str, Any]], evidence: dict[str, Any]) -> str:
    """The review body, by code. It used to be a model session that wrote two
    sentences over a code-built draft, with this function as its fallback - a
    ceremony that could fail, cost a session, and never said more than the counts."""
    from . import verdictcalc

    asks, follow = verdictcalc.split(verified)
    counts = ", ".join(
        f"{sum(1 for f in asks if f['category'] == name)} {name}"
        for name in config.REPORT_CATEGORY_ORDER
        if any(f["category"] == name for f in asks)
    )
    if not asks:
        return "Nothing here blocks a merge; details of what was checked are in the report."
    tail = f" ({len(follow)} follow-up(s) noted, not part of the verdict)" if follow else ""
    return f"{counts} - details inline on the diff.{tail}"


def pond_capture(
    workspace: Path,
    ledger: Ledger,
    summary: dict[str, Any],
    *,
    capture: bool,
) -> dict[str, Any]:
    """Capture this run's sessions into a fresh per-run store, verified, then fold.

    The per-run store is the run's provenance artifact and the substrate every in-run
    query hits; the fold into the operator's corpus is pond's own row-verified copy.
    A session that does not resolve is a named gap in the summary, never a silent one.
    """
    if not capture:
        return {}
    receipts: dict[str, dict[str, Any]] = {}
    for directory in sorted((ledger.directory / "sessions").glob("*/receipt.json")):
        receipt = json.loads(directory.read_text())
        receipts[receipt["operation"]] = receipt
    store = workspace / "pond-store"
    synced = pondsync.sync_run_store(store, receipts, ledger.directory)
    resolved = pondsync.resolve(receipts, ledger.directory, store=store)
    missing = sorted(op for op, row in resolved.items() if not row["resolved"])
    rows = [
        {"session_id": s["session_id"], "source_agent": s["source_agent"], "model": row["model"]}
        for row in resolved.values()
        for s in row["sessions"]
    ]
    priced = pondcost.usage(
        rows, store=str(store), registry=str(config.TEMPLATES / "registry.json")
    )
    folded = pondsync.fold(store)
    archived = pondsync.archive(store, workspace / "provenance.pond")
    record = {
        "store": str(store),
        "synced": synced,
        "resolved": resolved,
        "missing": missing,
        "fold": folded,
        "archive": archived,
        "usage": priced,
    }
    atomic(workspace / "sessions.json", canonical(record), mode=0o644)
    summary["evidence"]["capture"] = {
        "store": str(store),
        "sessions_resolved": sum(1 for row in resolved.values() if row["resolved"]),
        "sessions_missing": missing,
        "folded": folded["ok"],
        "archived": archived["ok"],
        # Informative, never control flow: a pond-derived list-price equivalent, a
        # floor, and zero real dollars on subscription lanes.
        "usage_totals": priced.get("totals"),
    }

    def attempts(operation: str) -> list[dict[str, Any]]:
        # A retried session's receipt carries the attempt-suffixed operation name
        # (review-design-codex#2), so provenance matches on the base name or a
        # suffixed variant - otherwise every retried finding lost its sessions.
        return [
            session
            for op, row in resolved.items()
            if op == operation or op.startswith(operation + "#")
            for session in row.get("sessions", [])
        ]

    by_finding: dict[str, Any] = {}
    for finding in summary["findings"]:
        by_finding[finding["id"]] = {
            "produced_by": attempts(f"review-{finding['lens']}-{finding['producer']}"),
            "verified_by": attempts(f"verify-{finding['id']}"),
        }
    return by_finding


def diff_files(workspace: Path, sidecar: dict[str, Any]) -> dict[str, diffindex.FileDiff]:
    return diffindex.reviewable(
        diffindex.parse((workspace / sidecar["diff"]).read_text(errors="replace"))
    )
