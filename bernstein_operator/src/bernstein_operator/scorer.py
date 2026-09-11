"""Score the observed attempt and archive its content identity before merge."""

from __future__ import annotations

import fcntl
import fnmatch
import json
import re
import time
import uuid
from pathlib import Path

from bernstein.core.quality.gate_plugins import GatePlugin
from bernstein.core.quality.gate_runner import GateResult

from .shared import ancestor, atomic, canonical, command, digest, dirty_paths, evidence, git, policy

TEST = re.compile(r"(^|/)(test[^/]*\.(py|rs)|tests?/)|_test\.go$|\.(test|spec)\.[cm]?[jt]sx?$")
REFUSAL = re.compile(
    r"^[\s>*#`-]*(scope_exceeded|underspecified|blocked_on_dependency|awaiting_operator)\b",
    re.MULTILINE,
)
SUPPRESSION = re.compile(
    r"^\+(?!\+\+).*?(nolint|noqa|type:\s*ignore|eslint-disable|allow\(clippy)", re.MULTILINE
)


def runtime(path: str) -> bool:
    return path == "CLAUDE.md" or path.startswith((".sdd/", ".claude/"))


def score(worktree: Path, title: str) -> dict:
    selected = policy(worktree, title)
    lock_dir = selected["run_dir"] / "scorer-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / digest(str(worktree.resolve()).encode())).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _score(worktree, selected)


def _score(worktree: Path, selected: dict) -> dict:
    head = git(worktree, "rev-parse", "HEAD").decode().strip()
    tree = git(worktree, "rev-parse", "HEAD^{tree}").decode().strip()
    report = selected["report"]
    evidence_before = evidence(worktree, report)
    dirty = [path for path in dirty_paths(worktree) if path != report and not runtime(path)]
    identity = {
        "title": selected["title"],
        "head": head,
        "tree": tree,
        "agent_branch": git(worktree, "symbolic-ref", "--short", "HEAD").decode().strip(),
        "policy_hash": selected["policy_hash"],
        "evidence": evidence_before,
    }
    memo_dir = selected["run_dir"] / "scorer-memos"
    memo_path = memo_dir / f"{digest(canonical(identity))}.json"
    previous = json.loads(memo_path.read_text()) if memo_path.exists() else None
    landed = ancestor(worktree, head, selected["branch"])
    base = git(worktree, "merge-base", "HEAD", selected["branch"]).decode().strip()
    if (
        not dirty
        and previous
        and previous["status"] == "pass"
        and (landed or previous["base"] == base)
    ):
        return _archive(
            worktree,
            selected,
            {**previous, "memo_of": previous["attempt_id"], "deduplicated_landing": landed},
        )
    if landed:
        raise ValueError("landed or no-commit HEAD has no matching content-bound PASS")
    changed = [
        p.decode()
        for p in git(worktree, "diff", "--name-only", "--no-renames", "-z", base, "HEAD").split(
            b"\0"
        )
        if p
    ]
    changed = sorted(set(changed + dirty_paths(worktree)))
    unauthorized = [
        p
        for p in changed
        if p != report
        and not runtime(p)
        and not any(fnmatch.fnmatchcase(p, glob) for glob in selected["files"])
    ]
    protected = [
        p for p in changed if p.startswith(".agents/build/plans/") or p in selected["protected"]
    ]
    diff = git(worktree, "diff", "--binary", "--no-ext-diff", base, "HEAD")
    diff_text = diff.decode(errors="replace")
    deleted = [
        p.decode()
        for p in git(
            worktree, "diff", "--diff-filter=D", "--name-only", "--no-renames", "-z", base, "HEAD"
        ).split(b"\0")
        if p and TEST.search(p.decode())
    ]
    suppressions = [
        m.group(0)
        for m in SUPPRESSION.finditer(diff_text)
        if not re.search(
            r"(?:--|//|#)\s*\S.{5,}", m.group(0)[m.group(0).find(m.group(1)) + len(m.group(1)) :]
        )
    ]
    commits = int(git(worktree, "rev-list", "--count", f"{base}..HEAD"))
    spec = selected["spec"]
    cache = selected["run_dir"] / "lintcache" / selected["native_run"]
    cache.mkdir(parents=True, exist_ok=True)
    code, out, err = command(
        ["bash", "-c", spec["gate_cmd"]],
        worktree,
        timeout=float(spec.get("gate_timeout_s", 600)),
        env={"GOLANGCI_LINT_CACHE": str(cache)},
    )
    output = (out + err).decode(errors="replace")
    report_path = worktree / report
    claims = report_path.read_text() if report_path.is_file() else ""
    refusal = REFUSAL.search(claims)
    exits = re.findall(r"[Ee]xit(?: code)?[:=]?\s*(\d+)", claims)
    measured = re.findall(r"(\d+) issues?\.", output)
    claimed = re.findall(r"(\d+) issues?\.", claims)
    mismatch = []
    if code and exits and all(int(x) == 0 for x in exits):
        mismatch.append("report claims clean exits while measured gate failed")
    if measured and int(measured[-1]) and claimed and all(int(x) == 0 for x in claimed):
        mismatch.append("report claims zero issues while measured gate found issues")
    if (
        claims
        and (
            (worktree / "go.mod").exists()
            or re.search(r"golangci|\bruff\b|eslint|clippy|\blint", output, re.IGNORECASE)
        )
        and not re.search(r"golangci|\bruff\b|eslint|clippy|\blint", claims, re.IGNORECASE)
    ):
        mismatch.append("report omits the lint result")
    dirty_after = [p for p in dirty_paths(worktree) if p != report and not runtime(p)]
    drift = (
        git(worktree, "rev-parse", "HEAD").decode().strip() != head
        or evidence(worktree, report) != evidence_before
    )
    blocked = bool(
        code
        or unauthorized
        or protected
        or deleted
        or suppressions
        or not commits
        or dirty
        or dirty_after
        or drift
        or refusal
        or mismatch
    )
    receipt = {
        **identity,
        "base": base,
        "native_run": selected["native_run"],
        "status": "fail" if blocked else "pass",
        "gate_rc": code,
        "gate_tail": output[-6000:],
        "commits": commits,
        "changed_files": changed,
        "allowlist_violations": unauthorized,
        "policy_edits": protected,
        "deleted_tests": deleted,
        "unjustified_suppressions": suppressions,
        "dirty": sorted(set(dirty + dirty_after)),
        "content_drift": drift,
        "refusal": refusal.group(1) if refusal else None,
        "report_mismatch": mismatch,
        "report_present": bool(claims),
        "diff_sha256": digest(diff),
        "memo_of": None,
    }
    result = _archive(worktree, selected, receipt, diff)
    if not blocked:
        atomic(memo_path, canonical(result))
    return result


def _archive(worktree: Path, selected: dict, receipt: dict, diff: bytes | None = None) -> dict:
    attempt = uuid.uuid4().hex
    result = {
        **receipt,
        "attempt_id": attempt,
        "native_run": selected["native_run"],
        "recorded_at": time.time(),
        "worktree": str(worktree.resolve()),
    }
    dest = selected["run_dir"] / "reports" / digest(selected["title"].encode())[:20] / attempt
    dest.mkdir(parents=True, exist_ok=False)
    if diff is not None:
        atomic(dest / "diff.patch", diff)
    report = worktree / selected["report"]
    if report.is_file():
        atomic(dest / "report.md", report.read_bytes())
    atomic(dest / "receipt.json", canonical(result))
    return result


class ScorerGate(GatePlugin):
    @property
    def name(self) -> str:
        return "scorer"

    @property
    def condition(self) -> str:
        return "always"

    def run(
        self, changed_files: list[str], run_dir: Path, task_title: str, task_description: str
    ) -> GateResult:
        started = time.monotonic()
        try:
            receipt = score(run_dir, task_title)
        except Exception as exc:
            receipt = {"status": "fail", "error": str(exc), "title": task_title}
        failed = receipt["status"] != "pass"
        return GateResult(
            name=self.name,
            status="fail" if failed else "pass",
            required=True,
            blocked=failed,
            cached=bool(receipt.get("memo_of")),
            duration_ms=int((time.monotonic() - started) * 1000),
            details=json.dumps(receipt),
            metadata=receipt,
        )
