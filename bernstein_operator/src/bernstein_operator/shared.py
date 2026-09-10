"""Frozen policy, bounded subprocesses, and immutable scorer evidence."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

import yaml

POLICY_VERSION = 1


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def contained(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"expected a contained relative path: {value!r}")
    result = root / path
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"path escapes root: {value!r}")
    return result


def command(
    argv: list[str], cwd: Path, *, timeout: float = 30, env: dict[str, str] | None = None
) -> tuple[int, bytes, bytes]:
    """Own the process group, including children that outlive their wrapper."""
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **(env or {})},
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except BaseException:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise
    try:
        os.killpg(proc.pid, 0)
    except ProcessLookupError:
        return proc.returncode, out, err
    os.killpg(proc.pid, signal.SIGKILL)
    raise RuntimeError(f"command left a live child process group: {argv[0]}")


def git(root: Path, *args: str) -> bytes:
    code, out, err = command(["git", *args], root, env={"GIT_OPTIONAL_LOCKS": "0"})
    if code:
        raise RuntimeError(f"git {args[0]} failed: {err.decode(errors='replace')[-1000:]}")
    return out


def ancestor(root: Path, older: str, newer: str) -> bool:
    code, _, err = command(["git", "merge-base", "--is-ancestor", older, newer], root)
    if code not in (0, 1):
        raise RuntimeError(f"ancestry check failed: {err.decode(errors='replace')}")
    return code == 0


def atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def policy(worktree: Path, title: str) -> dict:
    """Require driver identity; never fall back to executor-editable policy."""
    root = Path(os.environ["BERNSTEIN_OPERATOR_ROOT"]).resolve()
    plan_rel = os.environ["BERNSTEIN_OPERATOR_PLAN"]
    base = os.environ["BERNSTEIN_OPERATOR_BASE"]
    branch = os.environ["BERNSTEIN_OPERATOR_BRANCH"]
    native_run = os.environ["BERNSTEIN_RUN_ID"]
    if Path(git(worktree, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root:
        raise ValueError("root-worktree refusal")
    if not ancestor(root, base, branch):
        raise ValueError("frozen build base is not an ancestor of integration")
    sidecar_rel = str(Path(plan_rel).with_suffix(".steps.yaml"))
    raw = {}
    for key, rel in (("plan", plan_rel), ("sidecar", sidecar_rel), ("seed", "bernstein.yaml")):
        path = contained(root, rel)
        data = git(root, "show", f"{base}:{rel}")
        if path.read_bytes() != data:
            raise ValueError(f"frozen policy drift: {rel}")
        raw[key] = yaml.safe_load(data)
    plan, sidecar = raw["plan"], raw["sidecar"]
    protected = {plan_rel, sidecar_rel, "bernstein.yaml", *plan.get("context_files", [])}
    protected.update(spec["brief"] for spec in sidecar["steps"].values())
    protected.update(phase["judge"]["brief"] for phase in sidecar.get("phases", []))
    protected.update(
        value
        for key in ("doc", "spec", "design")
        if (value := sidecar.get("defaults", {}).get(key))
    )
    steps = [step for stage in plan["stages"] for step in stage["steps"]]
    if title not in {step["title"] for step in steps}:
        # The merge call site constructs a surrogate Task whose title is its ID.
        # Resolve only against this run's admitted IDs and scope-preserving retry
        # chain. Never guess a step from a branch name or similarly named title.
        run_dir = contained(root, f".agents/build/runs/{plan['name']}")
        admitted_path = run_dir / "admitted" / f"{native_run}.json"
        if not admitted_path.exists():
            raise ValueError(f"unknown or ambiguous task title: {title!r}")
        admitted = json.loads(admitted_path.read_text())
        tasks_path = root / ".sdd/runtime/tasks.jsonl"
        task_bytes = tasks_path.read_bytes()
        if not task_bytes.endswith(b"\n"):
            raise ValueError("task identity snapshot has a torn tail")
        tasks = {
            row["id"]: row
            for line in task_bytes.splitlines()
            if (row := json.loads(line)).get("id")
        }
        requested = title
        seen = set()
        while requested not in admitted:
            if requested in seen or requested not in tasks:
                raise ValueError("merge task ID has no admitted lineage")
            seen.add(requested)
            requested = tasks[requested].get("metadata", {}).get("retry_of")
        title = admitted[requested]
        declaration = next(step for step in steps if step["title"] == title)
        for task_id in seen | {requested}:
            row = tasks[task_id]
            owned = row.get("owned_files")
            # The admitted task carries the frozen ownership. A native retry of it
            # drops the field (measured 2026-09-10: a retry of a three-file step
            # carried []), and this gate scores against the frozen declaration
            # regardless, so only a DIFFERENT list is a scope nobody admitted.
            dropped = task_id != requested and owned in ([], None)
            if (
                row["title"] != title
                or (owned != declaration["files"] and not dropped)
                or row.get("metadata", {}).get("operator_run") != native_run
            ):
                raise ValueError("merge task identity or scope differs from admission")
    matches = [step for step in steps if step["title"] == title]
    if len(matches) != 1 or title not in sidecar["steps"]:
        raise ValueError(f"unknown or ambiguous task title: {title!r}")
    spec = {**sidecar.get("defaults", {}), **sidecar["steps"][title]}
    brief_rel = spec["brief"]
    brief = git(root, "show", f"{base}:{brief_rel}")
    if contained(root, brief_rel).read_bytes() != brief:
        raise ValueError("brief pin drift")
    slug = plan["name"]
    if git(root, "rev-parse", f"refs/build/base/{slug}").decode().strip() != base:
        raise ValueError("frozen base ref drift")
    files = matches[0].get("files", [])
    if not files or not all(
        isinstance(path, str) and not Path(path).is_absolute() and ".." not in Path(path).parts
        for path in files
    ):
        raise ValueError("missing or unsafe ownership declaration")
    report = spec["report"]
    contained(worktree, report)
    run_dir = contained(root, f".agents/build/runs/{slug}")
    key = digest(
        canonical(
            {
                "version": POLICY_VERSION,
                "task": matches[0],
                "policy": spec,
                "brief": digest(brief),
                "seed": raw["seed"],
                "build_base": base,
            }
        )
    )
    return {
        "root": root,
        "run_dir": run_dir,
        "branch": branch,
        "build_base": base,
        "native_run": native_run,
        "title": title,
        "policy_hash": key,
        "files": files,
        "protected": sorted(protected),
        "report": report,
        "spec": spec,
    }


def evidence(worktree: Path, report: str) -> dict[str, str]:
    path = contained(worktree, report)
    return {report: digest(path.read_bytes()) if path.is_file() else "missing"}


def dirty_paths(worktree: Path) -> list[str]:
    tracked = git(worktree, "diff", "--name-only", "--no-renames", "-z", "HEAD")
    untracked = git(worktree, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted({path.decode() for path in (tracked + untracked).split(b"\0") if path})
