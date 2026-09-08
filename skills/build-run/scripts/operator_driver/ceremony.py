"""Detached blind review bound to an exact staged input and immutable receipt."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .acp import judge_argv, transcript
from .processes import alive, cancel_acp, launch_once, owned_processes, terminate
from .spec import Build, git
from .storage import Ledger, Park, canonical, contained, digest, immutable
from .verdict import parse_verdict

ALLOWED = {".agents/blind-review.md", ".agents/verdict.json", ".agents/scorecard.md"}


def reaction(verdict: dict, malformed_attempts: int = 0) -> str:
    if verdict.get("integrity_error"):
        return "park"
    if verdict.get("do_not_merge"):
        return "park"
    if verdict.get("reason") or not verdict.get("counts_declared"):
        return "rejudge" if malformed_attempts == 0 else "park"
    return "fix" if verdict["certain"] > 0 else "accept"


def validate_tree(worktree: Path, staged: str, pinned_tree: str) -> None:
    if git(worktree, "rev-parse", "HEAD") != staged:
        raise Park("judge moved its detached HEAD")
    if git(worktree, "rev-parse", f"{staged}^{{tree}}") != pinned_tree:
        raise Park("judge staging tree differs from reviewed integration tip")
    changed = git(worktree, "diff", "--name-only", "--no-renames", staged).splitlines()
    changed += git(worktree, "ls-files", "--others", "--exclude-standard").splitlines()
    violations = sorted({path for path in changed if path not in ALLOWED})
    # Staged changes may differ from the working tree; inspect both layers.
    staged_paths = git(
        worktree, "diff", "--cached", "--name-only", "--no-renames", staged
    ).splitlines()
    violations += [path for path in staged_paths if path not in ALLOWED]
    if violations:
        raise Park(f"judge changed application inputs: {sorted(set(violations))}")
    for rel in ALLOWED:
        contained(worktree, rel)


def judge(
    build: Build, ledger: Ledger, phase: dict, base: str, tip: str, operation: str, *, timeout_check
) -> dict:
    spec = phase["judge"]
    dest = build.run_dir / "judge" / operation
    receipt_path = dest / "receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        receipt_hash = digest(canonical(receipt))
        recorded = ledger.last("judge_receipt", operation=operation)
        if recorded and recorded["receipt_hash"] != receipt_hash:
            raise Park("judge receipt differs from its journal binding")
        if receipt["base"] != base or receipt["tip"] != tip:
            raise Park("judge receipt is for another reviewed range")
        if receipt["operation"] != operation or receipt["phase"] != phase["name"]:
            raise Park("judge receipt is for another ceremony")
        for rel, expected in receipt["artifacts"].items():
            if digest(contained(dest, rel).read_bytes()) != expected:
                raise Park("judge archive was modified")
        wt = dest / "worktree"
        if wt.exists():
            if owned_processes(wt, all_commands=True):
                raise Park("judge process remains after its archived receipt")
            git(build.root, "worktree", "remove", "--force", str(wt))
        if not recorded:
            ledger.append(
                "judge_receipt",
                operation=operation,
                receipt_hash=receipt_hash,
                cost_usd=receipt["cost_usd"],
            )
        return receipt
    process_record = ledger.directory / "processes" / f"{operation}.json"
    known = json.loads(process_record.read_text()) if process_record.exists() else None
    # Recovery attaches to this ceremony; other live writers still prohibit review.
    unrelated = [
        p
        for p in owned_processes(build.root)
        if not (known and alive(known) and p["pgid"] == known["pgid"])
    ]
    if unrelated:
        raise Park("native processes remain before the judge ceremony")
    if git(build.root, "rev-parse", build.branch) != tip:
        raise Park("integration ref moved before review")
    brief = contained(build.root, spec["brief"]).read_bytes()
    prompt = (
        brief
        + f"\n\nReviewed range: {base}..{tip}\n"
        "The current tree is the exact staged implementation. Review the cumulative diff against "
        f"{base}. Write only .agents/blind-review.md, .agents/verdict.json, and .agents/scorecard.md. "
        "Do not change application files or repository refs. End the prose with exactly one each of "
        "Certain: N, Plausible: N, Verdict: <legal verdict>.\n".encode()
    )
    if not ledger.last("judge_intent", operation=operation):
        ledger.append(
            "judge_intent",
            operation=operation,
            phase=phase["name"],
            base=base,
            tip=tip,
            prompt_hash=digest(prompt),
            reserved_usd=spec["budget_usd"],
        )
    dest.mkdir(parents=True, exist_ok=True)
    immutable(dest / "prompt.md", prompt)
    wt = dest / "worktree"
    staged_record = ledger.last("judge_staged", operation=operation)
    if staged_record:
        staged = staged_record["commit"]
    else:
        if wt.exists():
            raise Park("judge staging was interrupted; preserve the worktree for reconciliation")
        git(build.root, "worktree", "add", "--detach", str(wt), base)
        git(wt, "read-tree", "--reset", "-u", tip)
        expected_tree = git(build.root, "rev-parse", f"{tip}^{{tree}}")
        if git(wt, "write-tree") != expected_tree:
            raise Park("staged input does not equal reviewed tip")
        git(wt, "commit", "--allow-empty", "-m", "chore(review): stage frozen blind-review input")
        staged = git(wt, "rev-parse", "HEAD")
        ledger.append("judge_staged", operation=operation, commit=staged, tree=expected_tree)
    tree = git(build.root, "rev-parse", f"{tip}^{{tree}}")
    validate_tree(wt, staged, tree)
    if not ledger.last("launch_intent", operation=operation):
        # A verdict tracked by an earlier build must not become this attempt's
        # output when the fresh agent produces nothing. Preserve then clear only
        # the declared evidence paths, leaving the staged input tree unchanged.
        for rel in sorted(ALLOWED):
            path = contained(wt, rel)
            if path.is_file():
                immutable(dest / "inherited-evidence" / Path(rel).name, path.read_bytes())
                path.unlink()
    argv = judge_argv(spec, wt, dest / "prompt.md")
    proc = launch_once(ledger, operation, argv, wt, {"ACPX_CLAUDE_INCLUDE_USER_SETTINGS": "0"})
    launch = ledger.last("launch_intent", operation=operation)
    if launch is None:
        raise Park("judge process has no launch intent")
    started = launch["time"]
    try:
        while alive(proc):
            timeout_check()
            if time.time() - started > spec["timeout_s"]:
                raise Park("judge exceeded its wall-clock bound")
            time.sleep(0.2)
    except BaseException:
        cancel_acp(proc)
        raise
    exit_path = ledger.directory / "processes" / f"{operation}.exit.json"
    if not exit_path.is_file():
        raise Park("judge exited without a completion receipt")
    exit_record = json.loads(exit_path.read_text())
    survivors = owned_processes(wt, all_commands=True)
    for survivor in survivors:
        terminate(survivor)
    if exit_record["residual"] or owned_processes(build.root) or survivors:
        raise Park("judge left surviving child processes")
    validate_tree(wt, staged, tree)
    if git(build.root, "rev-parse", build.branch) != tip:
        raise Park("integration ref moved while the judge was reviewing")
    verdict: dict = parse_verdict(wt / ".agents/blind-review.md")
    if exit_record["returncode"]:
        verdict = {**verdict, "reason": "judge command failed"}
    for item in verdict.get("evidence", []):
        file = contained(wt, item["file"])
        if (
            not file.is_file()
            or not 1 <= item["line"] <= len(file.read_text().splitlines())
            or not item["note"].strip()
        ):
            verdict = {
                **verdict,
                "reason": "judge evidence does not reference an existing file and line",
            }
    log = (ledger.directory / "processes" / f"{operation}.log").read_bytes()
    protocol = transcript(log)
    cost = protocol["cost_usd"]
    if protocol["stop_reason"] != "end_turn" or protocol["errors"]:
        verdict = {**verdict, "reason": "ACP prompt did not finish successfully"}
    if cost > spec["budget_usd"]:
        raise Park("judge exceeded its reserved spend")
    artifacts = {}
    for rel in sorted(ALLOWED):
        source = wt / rel
        if source.is_file():
            output = Path(rel).name
            data = source.read_bytes()
            immutable(dest / output, data)
            artifacts[output] = digest(data)
    immutable(dest / "process.log", log)
    artifacts["process.log"] = digest(log)
    receipt = {
        "operation": operation,
        "phase": phase["name"],
        "base": base,
        "tip": tip,
        "staged": staged,
        "tree": tree,
        "verdict": verdict,
        "cost_usd": cost,
        "acp": protocol,
        "artifacts": artifacts,
    }
    immutable(receipt_path, canonical(receipt))
    ledger.append(
        "judge_receipt", operation=operation, receipt_hash=digest(canonical(receipt)), cost_usd=cost
    )
    git(build.root, "worktree", "remove", "--force", str(wt))
    return receipt
