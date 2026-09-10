"""Positive delivery proofs over a closed native run and immutable scorer receipts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from bernstein.core.persistence.wal import WALReader, WALRecovery
from bernstein.core.replay.journal import load_events, verify_journal

from .spec import git
from .storage import Park, canonical, contained, digest, immutable
from .transport import admitted_inventory


def close_proven_wal(root: Path, run_id: str, tasks: list[dict], events: list[dict]) -> None:
    """Seal paired claim intents only after positive delivery and evidence archival.

    Native claims remain committed=False even after task_spawn_confirmed. Letting
    the next boot replay those against a fresh task store is not safe.
    """
    path = root / ".sdd/runtime/wal" / f"{run_id}.wal.jsonl"
    if not path.exists():
        raise Park("completed run has no WAL evidence")
    reader = WALReader(run_id, root / ".sdd")
    valid, errors = reader.verify_chain()
    if not valid or errors or (path.stat().st_size and not path.read_bytes().endswith(b"\n")):
        raise Park("native WAL evidence is incomplete or inconsistent")
    entries = list(reader.iter_verified_entries())
    confirmed = {
        (row.inputs.get("task_id"), row.inputs.get("agent_id"))
        for row in entries
        if row.decision_type == "task_spawn_confirmed" and row.committed
    }
    spawned = {
        (task_id, row.get("agent_id"))
        for row in events
        if row.get("event") == "agent_spawned"
        for task_id in row.get("task_ids", [])
    }
    terminal = {row["id"] for row in tasks if row.get("status") in {"done", "closed", "failed"}}
    pending = [row for row in entries if not row.committed]
    for row in pending:
        task_id, agent_id = row.inputs.get("task_id"), row.inputs.get("agent_id")
        matched = any(
            t == task_id and (agent_id is None or a == agent_id) for t, a in confirmed & spawned
        )
        if (
            row.decision_type not in {"task_claimed", "claim_confirmed"}
            or task_id not in terminal
            or not matched
        ):
            raise Park("unresolved WAL intent remains after run closure")
    WALRecovery.close_wal(
        run_id, root / ".sdd", reason="operator_proven_delivery", uncommitted_count=len(pending)
    )


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=root,
        capture_output=True,
        timeout=30,
    )
    if result.returncode not in (0, 1):
        raise Park("Git ancestry cannot be established")
    return result.returncode == 0


def native_events(path: Path, *, closed: bool = False) -> list[dict]:
    if not path.is_file():
        if closed:
            raise Park("closed run has no journal")
        return []
    if closed:
        verification = verify_journal(path)
        if not verification.chain_consistent or verification.discarded_line_indices:
            raise Park("native journal has incomplete or inconsistent evidence")
        if not path.read_bytes().endswith(b"\n"):
            raise Park("native journal has an unfinished final line")
    return load_events(path).events


def retried_to_completion(tasks: list[dict], task_id: str | None) -> bool:
    """Whether a native retry of this attempt reached a terminal, non-failed status.

    Dead-agent reaping lands an attempt's scored content and still records that
    attempt failed, then retries it. The landed content is proven by its own scorer
    PASS and merge ancestry; the failed status is engine bookkeeping about the
    session, so it is only unresolved when no retry of it ever completed.
    """
    frontier, seen = [task_id], set()
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        for task in tasks:
            if task.get("metadata", {}).get("retry_of") != current:
                continue
            if task.get("status") in {"done", "closed"}:
                return True
            frontier.append(task["id"])
    return False


def prove_delivery(
    root: Path,
    run_dir: Path,
    run_id: str,
    start: str,
    tip: str,
    expected: dict[str, str],
    tasks: list[dict],
    events: list[dict],
) -> list[dict]:
    admitted_inventory(tasks, set(expected.values()))
    if not is_ancestor(root, start, tip):
        raise Park("integration moved outside the phase start ancestry")
    quiescence = [row for row in events if row.get("event") == "run_quiescence"]
    if not quiescence or not quiescence[-1].get("verified") or quiescence[-1].get("residual"):
        raise Park("native process quiescence was not verified")
    completions = [row for row in events if row.get("event") == "run_completed"]
    if not completions:
        raise Park("native scheduler closure is missing")
    if completions[-1].get("outcome") != "completed":
        raise Park("native scheduler closure was not successful")
    task_map = {task["id"]: task for task in tasks}
    logical = {task_id: title for title, task_id in expected.items()}
    while True:
        previous = len(logical)
        for task in tasks:
            parent = task.get("metadata", {}).get("retry_of")
            if parent in logical:
                logical[task["id"]] = logical[parent]
        if previous == len(logical):
            break
    receipts: list[dict] = [
        {**json.loads(path.read_text()), "_receipt_path": path}
        for path in (run_dir / "reports").glob("*/*/receipt.json")
    ]
    receipts = [row for row in receipts if row.get("native_run") == run_id]
    refusals = [row for row in receipts if row.get("refusal")]
    if refusals:
        raise Park("scorer refusal: " + ", ".join(sorted({row["refusal"] for row in refusals})))
    spawned = {
        (row["agent_id"], task_id)
        for row in events
        if row.get("event") == "agent_spawned"
        for task_id in row.get("task_ids", [])
    }
    refusal_path = root / ".sdd/runtime/refused_merges.jsonl"
    refused: list[dict] = []
    if refusal_path.exists():
        raw = refusal_path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise Park("merge refusal journal has a torn tail")
        agent_ids = {agent_id for agent_id, _ in spawned}
        refused = [
            row
            for row in (json.loads(line) for line in raw.splitlines())
            if row.get("session_id") in agent_ids
        ]
    merges = [row for row in events if row.get("event") == "task_merged"]
    recorded_commits = {row.get("merge_commit") for row in merges}
    # Native dead-agent reaping can merge without a task_merged journal event.
    # A two-parent integration merge whose second parent is EXACTLY the scored
    # head is independent positive delivery evidence. Do not infer from a
    # commit message, tree similarity or task status.
    for commit in git(
        root, "rev-list", "--first-parent", "--merges", f"{start}..{tip}"
    ).splitlines():
        if commit in recorded_commits:
            continue
        parents = git(root, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        if len(parents) != 2:
            raise Park("integration has an unattributable non-binary merge")
        candidates = {
            (agent_id, task_id)
            for agent_id, task_id in spawned
            if task_id in logical
            for receipt in receipts
            if receipt.get("head") == parents[1]
            and receipt.get("agent_branch") == f"agent/{agent_id}"
            and receipt.get("title") == logical[task_id]
            and receipt.get("status") == "pass"
            and not receipt.get("memo_of")
        }
        if len(candidates) != 1:
            raise Park("merge parents have no unique scored task attempt")
        agent_id, task_id = candidates.pop()
        merges.append(
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "merge_commit": commit,
                "source": "git_merge_parents",
            }
        )
    proofs = []
    explained = set()
    delivered = set()
    for row in merges:
        task_id, agent_id = row.get("task_id"), row.get("agent_id")
        title = logical.get(task_id)
        commit = row.get("merge_commit")
        if not title or not commit or (agent_id, task_id) not in spawned:
            raise Park("merge has no attributable executed task attempt")
        task = task_map[task_id]
        if task.get("status") not in {"done", "closed"} and not retried_to_completion(
            tasks, task_id
        ):
            raise Park("landed work still has a failed task obligation")
        matching = [
            receipt
            for receipt in receipts
            if receipt.get("status") == "pass"
            and receipt.get("title") == task["title"]
            and receipt.get("agent_branch") == f"agent/{agent_id}"
            and not receipt.get("memo_of")
        ]
        matching = [
            receipt
            for receipt in matching
            if is_ancestor(root, receipt["head"], commit) and is_ancestor(root, commit, tip)
        ]
        if not matching:
            raise Park(f"delivered task has no scorer PASS for its landed content: {title}")
        receipt = matching[-1]
        receipt_path = receipt["_receipt_path"]
        if digest(receipt_path.with_name("diff.patch").read_bytes()) != receipt["diff_sha256"]:
            raise Park("scorer diff archive changed")
        report = receipt_path.with_name("report.md")
        if report.exists() and digest(report.read_bytes()) not in receipt["evidence"].values():
            raise Park("scorer report archive changed")
        if git(root, "rev-parse", f"{receipt['head']}^{{tree}}") != receipt["tree"]:
            raise Park("scorer receipt tree differs from its Git object")
        if title in delivered:
            raise Park(f"multiple delivered attempts for one logical step: {title}")
        delivered.add(title)
        explained.add(commit)
        explained.update(
            git(root, "rev-list", f"{receipt['base']}..{receipt['head']}").splitlines()
        )
        proofs.append(
            {
                "title": title,
                "source": row.get("source", "native_task_merged"),
                "task_id": task_id,
                "agent_id": agent_id,
                "scorer_attempt": receipt["attempt_id"],
                "scorer_receipt": receipt_path.relative_to(run_dir).as_posix(),
                "scorer_receipt_sha256": digest(receipt_path.read_bytes()),
                "head": receipt["head"],
                "merge_commit": commit,
                "tip": tip,
            }
        )
    if delivered != set(expected):
        raise Park(f"expected steps lack delivery proof: {sorted(set(expected) - delivered)}")
    # A task left claimed at closure is not a separate obligation: nothing runs after
    # the scheduler exits, every admitted task and retry maps to an expected step, and
    # each of those steps has just been proven delivered above. The native janitor
    # reopens a step whose report is missing, and a retry dispatched after the work
    # landed is refused by the scorer for having no content-bound PASS, so it can
    # never merge (measured 2026-09-10). An undelivered step parks above instead.
    # Native retries stay enabled, so an attempt the gates blocked is resolved
    # evidence once a DIFFERENT attempt delivered its step - that is the scorer doing
    # its job, then a retry succeeding. Every other refusal reason still parks
    # (scope, blast radius, unreadable diffs, a merge aimed at the default branch),
    # and so does a refusal naming the attempt whose content actually landed: a later
    # status or PASS never explains away the refusal of the work in the branch.
    landed = {(proof["agent_id"], proof["task_id"]) for proof in proofs}
    for row in refused:
        attempts = {(agent, task) for agent, task in spawned if agent == row["session_id"]}
        titles = {logical.get(task) for _, task in attempts}
        if (
            row.get("reason") != "quality-gates-blocked"
            or attempts & landed
            or not titles
            or not titles <= delivered
        ):
            raise Park(
                "native merge refusal remains in this run's evidence: "
                f"{row['session_id']} ({row.get('reason', 'no reason recorded')})"
            )
    unexplained = set(git(root, "rev-list", f"{start}..{tip}").splitlines()) - explained
    if unexplained:
        raise Park(f"unexpected integration commits: {sorted(unexplained)}")
    return proofs


def archive_native(
    root: Path, run_dir: Path, run_id: str, tasks: list[dict], report: bytes
) -> Path:
    dest = run_dir / "native" / run_id
    complete = dest / "archive.json"
    if complete.exists():
        manifest = json.loads(complete.read_text())
        for rel, expected in manifest.items():
            if digest(contained(dest, rel).read_bytes()) != expected:
                raise Park("archived native evidence changed")
        return dest
    source = root / ".sdd/runs" / run_id
    if not source.is_dir():
        raise Park("native run directory vanished before archival")
    if dest.exists():
        # A partial copy has no acceptance receipt; rebuilding from the stopped
        # source preserves the same run identity and performs no engine action.
        shutil.rmtree(dest)
    shutil.copytree(source, dest / "run", symlinks=True)
    for name in ("gates", "refused_merges.jsonl", "run_config.json", "quarantine.json"):
        path = root / ".sdd/runtime" / name
        if path.is_dir():
            shutil.copytree(path, dest / "runtime" / name, symlinks=True)
        elif path.is_file():
            immutable(dest / "runtime" / name, path.read_bytes())
    immutable(dest / "tasks.json", canonical(tasks))
    immutable(dest / "runs-report.json", report)
    for rel in (f"runtime/wal/{run_id}.wal.jsonl", "runtime/tasks.jsonl", "cost/ledger.jsonl"):
        path = root / ".sdd" / rel
        if path.is_file():
            immutable(dest / "state" / rel, path.read_bytes())
    manifest = {}
    for path in dest.rglob("*"):
        if path.is_symlink():
            raise Park("native evidence archive contains a symlink")
        if path.is_file():
            manifest[path.relative_to(dest).as_posix()] = digest(path.read_bytes())
    immutable(complete, canonical(manifest))
    return dest
