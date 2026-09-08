"""Frozen admission checks and detached validation replay before any paid work."""

from __future__ import annotations

import fnmatch
import importlib.metadata
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from bernstein_operator.shared import command

from .admission import clean_root, disk_check, no_ingress, prerequisites
from .processes import owned_processes
from .spec import Build, git
from .storage import Ledger, Park, canonical, contained, digest, immutable

SECTION_CITE = re.compile(r"\b(PLAN|DESIGN|SPEC|spec)\s+(\d+(?:\.\d+)*)\b")
FAST_PATH = re.compile(
    r"\b(format|formatting|auto-?format|black|prettier|lint|linting|ruff fix|fix lint|autofix|sort imports?|isort|import order)\b|\brename\s+['\"]?\w+['\"]?\s+(?:to|->|=>)\s+['\"]?\w+['\"]?"
)


def runtime_identity() -> dict:
    from bernstein.core.config import seed_parser
    from bernstein.core.git import git_basic
    from bernstein.core.orchestration import orchestrator

    from bernstein_operator import scorer, shared

    modules = (orchestrator, seed_parser, git_basic, scorer, shared)
    files = {
        module.__name__: digest(Path(inspect.getfile(module)).read_bytes()) for module in modules
    }
    files.update(
        {
            f"driver/{name}.py": digest(Path(__file__).with_name(f"{name}.py").read_bytes())
            for name in ("admission", "spec", "storage", "processes", "readiness")
        }
    )
    versions = {}
    for cli in ("acpx", "claude", "codex"):
        code, out, err = command([cli, "--version"], cwd=Path.cwd(), timeout=15)
        if code:
            raise Park(f"required CLI is unavailable: {cli}")
        versions[cli] = (out + err).decode(errors="replace").strip()
    return {"code": files, "versions": versions}


def globs_overlap(a: str, b: str) -> bool:
    if a == b or fnmatch.fnmatchcase(a, b) or fnmatch.fnmatchcase(b, a):
        return True

    def prefix(pattern):
        result = []
        for part in pattern.split("/"):
            if re.search(r"[*?\[]", part):
                return result, True
            result.append(part)
        return result, False

    left, wild_left = prefix(a)
    right, wild_right = prefix(b)
    short, long, wildcard = (
        (left, right, wild_left) if len(left) <= len(right) else (right, left, wild_right)
    )
    # Empty prefixes are not proof of separation: broad wildcards are conservative.
    return wildcard and (not short or long[: len(short)] == short)


def check(build: Build, *, replay: bool = True) -> dict:
    common = (build.root / git(build.root, "rev-parse", "--git-common-dir")).resolve()
    directory = (build.root / git(build.root, "rev-parse", "--git-dir")).resolve()
    if common == directory or git(build.root, "rev-parse", "--show-superproject-working-tree"):
        raise Park("admission requires a linked workspace outside any superproject")
    workspace = json.loads((build.run_dir / "workspace.json").read_text())
    if (
        set(workspace) != {"path", "branch", "base", "base_branch", "primary"}
        or workspace["path"] != str(build.root)
        or workspace["branch"] != build.branch
    ):
        raise Park("workspace identity does not match the current checkout")
    clean_root(build)
    if owned_processes(build.root):
        raise Park("native or judge processes remain before admission")
    disk_check(build.root)
    no_ingress(build.root)
    prerequisites(build)
    base = git(build.root, "rev-parse", "HEAD")
    build.verify_pins(base)
    defaults = build.sidecar["defaults"]
    if not defaults.get("signoff") or not defaults.get("spec"):
        raise Park("readiness requires a signed-off build specification")
    signed = subprocess.run(
        ["git", "show", f"{defaults['signoff']}:{defaults['spec']}"],
        cwd=build.root,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    if signed != contained(build.root, defaults["spec"]).read_bytes():
        raise Park("build specification differs from its sign-off commit")
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=build.root,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    hooks = build.root / (configured or git(build.root, "rev-parse", "--git-common-dir") + "/hooks")
    if any(
        (hooks / name).is_file() and os.access(hooks / name, os.X_OK)
        for name in (
            "pre-commit",
            "commit-msg",
            "prepare-commit-msg",
            "post-commit",
            "post-checkout",
            "post-merge",
            "pre-push",
        )
    ):
        raise Park("active Git hooks can alter worktrees; configure an empty core.hooksPath")
    sections = {}
    for label, key in (("PLAN", "doc"), ("SPEC", "spec"), ("DESIGN", "design"), ("spec", "design")):
        rel = defaults.get(key)
        sections[label] = (
            set(
                re.findall(r"^#+\s*(\d+(?:\.\d+)*)\b", contained(build.root, rel).read_text(), re.M)
            )
            if rel
            else set()
        )
    checks = []
    commands = set()
    for title, task in build.tasks.items():
        text = contained(build.root, build.sidecar["steps"][title]["brief"]).read_text()
        if len(text) > 16000 or not re.search(r"^##\s*Items\b", text, re.M):
            raise Park(f"brief exceeds 16k characters or lacks Items: {title}")
        for label, section in SECTION_CITE.findall(text):
            if section not in sections[label] and section.split(".")[0] not in sections[label]:
                raise Park(f"unresolvable brief citation: {title}: {label} {section}")
        if FAST_PATH.search(f"{title} {task.description}".lower()):
            raise Park(f"title or description selects an unexecuted native fast path: {title}")
        validation = re.search(r"^##\s*Validation[^\n]*\n.*?```[^\n]*\n(.*?)```", text, re.M | re.S)
        if not validation:
            raise Park(f"brief has no fenced Validation command: {title}")
        commands.add(validation[1])
        checks.append(
            f"PASS {title}: frozen brief, citations, ownership, dispatch and loaded witnesses"
        )
    for phase in build.phases:
        for index, left in enumerate(phase["steps"]):
            for right in phase["steps"][index + 1 :]:
                if any(
                    globs_overlap(a, b)
                    for a in build.tasks[left].owned_files
                    for b in build.tasks[right].owned_files
                ):
                    raise Park(f"phase has overlapping executor ownership: {left} and {right}")
    policy = build.seed["role_model_policy"]
    codex_config = Path.home() / ".codex/config.toml"
    if any(policy[task.role]["cli"] == "codex" for task in build.tasks.values()):
        raw = codex_config.read_text() if codex_config.exists() else ""
        if not re.search(r'^\s*model_reasoning_effort\s*=\s*"high"', raw, re.M):
            raise Park(
                "Codex dispatch requires model_reasoning_effort = high in the machine config"
            )
    code, out, err = command(
        [sys.executable, "-m", "bernstein", "plan", "validate", str(build.path)],
        cwd=build.root,
        timeout=60,
    )
    if code:
        raise Park("native plan validation failed: " + (out + err).decode(errors="replace")[-1500:])
    replay_results = []
    if replay:
        with tempfile.TemporaryDirectory(prefix="operator-ready-") as tmp:
            worktree = Path(tmp) / "base"
            git(build.root, "worktree", "add", "--detach", str(worktree), base)
            try:
                for cmd in sorted(commands):
                    code, out, err = command(["bash", "-c", cmd], cwd=worktree, timeout=600)
                    replay_results.append(
                        {
                            "command": cmd,
                            "returncode": code,
                            "stdout_sha256": digest(out),
                            "stderr_sha256": digest(err),
                            "output_tail": (out + err).decode(errors="replace")[-3000:],
                        }
                    )
                    # A formatter/generator in one validation must not change the
                    # baseline used by another command's readiness measurement.
                    if git(worktree, "diff", "--name-only", "HEAD"):
                        raise Park("readiness validation modified the frozen tracked input")
            finally:
                git(build.root, "worktree", "remove", "--force", str(worktree))
    distribution = importlib.metadata.distribution("bernstein")
    source = json.loads(distribution.read_text("direct_url.json") or "{}")
    if not (source.get("dir_info") is not None or source.get("vcs_info")):
        raise Park("installed engine has no source-build provenance")
    return {
        "base": base,
        "fingerprint": build.fingerprint,
        "pins": build.pins,
        "checks": checks,
        "validation": replay_results,
        "validated": replay,
        "role_model_policy": policy,
        "judge_configs": [phase["judge"] for phase in build.phases],
        "engine_version": importlib.metadata.version("bernstein"),
        "engine_source": source,
        "operator_version": importlib.metadata.version("bernstein-operator"),
        "codex_config_sha256": digest(codex_config.read_bytes()) if codex_config.exists() else None,
        "runtime": runtime_identity(),
    }


def freeze(build: Build, ledger: Ledger) -> dict:
    started = ledger.last("build_started")
    execution_hash = digest(
        canonical(
            {path.name: digest(path.read_bytes()) for path in Path(__file__).parent.glob("*.py")}
        )
    )
    if started:
        receipt = json.loads((build.run_dir / "readiness/receipt.json").read_text())
        if (
            digest(canonical(receipt)) != started["readiness_sha256"]
            or receipt["runtime"] != runtime_identity()
            or execution_hash != started["execution_hash"]
        ):
            raise Park("admitted runtime or readiness evidence changed")
        return started
    receipt_path = build.run_dir / "readiness/receipt.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if (
            receipt["base"] != git(build.root, "rev-parse", "HEAD")
            or receipt["fingerprint"] != build.fingerprint
            or not receipt["validated"]
            or receipt["runtime"] != runtime_identity()
        ):
            raise Park("readiness receipt is stale")
        clean_root(build)
        prerequisites(build)
        build.verify_pins(receipt["base"])
    else:
        receipt = check(build)
        immutable(receipt_path, canonical(receipt))
    intent = ledger.last("freeze_intent")
    if intent and intent["base"] != receipt["base"]:
        raise Park("base changed during interrupted admission")
    if not intent:
        ledger.append("freeze_intent", base=receipt["base"], fingerprint=build.fingerprint)
    ref = f"refs/build/base/{build.slug}"
    existing = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=build.root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if existing.returncode == 0:
        if existing.stdout.strip() != receipt["base"]:
            raise Park("write-once build base already names another commit")
    else:
        git(build.root, "update-ref", ref, receipt["base"], "0" * 40)
    immutable(build.run_dir / "readiness/pins.json", canonical(build.pins))
    return ledger.append(
        "build_started",
        base=receipt["base"],
        branch=build.branch,
        fingerprint=build.fingerprint,
        readiness_sha256=digest(canonical(receipt)),
        execution_hash=execution_hash,
    )
