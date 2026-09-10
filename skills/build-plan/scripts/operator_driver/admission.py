"""Read-only native launch prerequisites, shared as vendored skill-local code."""

from __future__ import annotations

import inspect
import shutil
from pathlib import Path

from .spec import Build, git
from .storage import Park


def no_ingress(root: Path):
    for name in ("TODO.md", "TASKS.md", ".plan"):
        if (root / name).exists():
            raise Park(f"importable root input must be removed before execution: {name}")
    for directory in (root / ".sdd/backlog/open", root / ".sdd/backlog/issues"):
        if any(path.is_file() for path in directory.rglob("*")):
            raise Park(f"native task backlog is not empty: {directory}")
    for path in (root / ".sdd/runtime/task-backlog.json", root / ".sdd/task-backlog.json"):
        if path.is_file():
            # The driver never consumes backlog. Even a nonempty schema wrapper
            # requires explicit inspection instead of guessing which items are live.
            if path.read_text().strip() not in {"", "[]", "{}"}:
                raise Park(f"backlog is not empty: {path}")


def disk_check(root: Path):
    if shutil.disk_usage(root).free < 40 * 1024**3:
        raise Park("free disk fell below the 40 GiB workflow floor")


def prerequisites(build: Build):
    from bernstein.core.git import git_basic
    from bernstein.core.orchestration import orchestrator
    from bernstein.core.quality.gate_plugins import GatePluginRegistry

    source = Path(inspect.getfile(orchestrator)).read_text()
    marker = 'None if os.environ.get("BERNSTEIN_RESPONSE_CACHE", "1") == "0"'
    if marker not in source:
        raise Park(
            "installed engine lacks the verified response-cache disable patch; run prepare-engine.py and rebuild"
        )
    if 'fetch_all_tasks(self._client, base, ["closed"])["closed"]' not in source:
        raise Park(
            "installed engine lacks the closed-task quiescence patch; a merged run would "
            "never self-stop or journal its phase boundary"
        )
    if 'os.environ.get("BERNSTEIN_OPERATOR_LOCAL_ONLY") == "1"' not in inspect.getsource(
        git_basic.safe_push
    ):
        raise Park("installed engine lacks the local-only safe_push patch")
    gate = GatePluginRegistry(build.root).get("scorer")
    if gate is None or type(gate).__module__ != "bernstein_operator.scorer":
        raise Park("installed bernstein.gates scorer entry point is absent or shadowed")
    quality = build.seed["quality_gates"]
    if quality.get("enabled") is not True or quality.get("cache_enabled") is not False:
        raise Park("quality gates must be enabled and their cache explicitly disabled")
    if (
        build.seed.get("gate_repair_enabled") is not False
        or quality.get("flaky_detection") is not False
    ):
        raise Park("gate repair and flaky deselection must be explicitly disabled")
    if build.seed.get("orchestration", {}).get("test_followup") is not False:
        raise Park("test_followup must be explicitly disabled")
    if build.seed.get("evolution_enabled") is not False:
        raise Park("evolution must be explicitly disabled")
    steps = quality.get("pipeline", [])
    if not any(
        step.get("name") == "scorer"
        and step.get("condition") == "always"
        and step.get("required", True) is True
        for step in steps
    ):
        raise Park("required scorer with condition: always is missing")
    # Execute the installed parser, which formerly rejected plugin gate names.
    from bernstein.core.config.seed_parser import parse_seed

    parse_seed(build.root / "bernstein.yaml")


def clean_root(build: Build):
    if git(build.root, "diff", "--name-only", "HEAD"):
        raise Park("integration has uncommitted tracked changes")
    for rel in git(build.root, "ls-files", "--others", "--exclude-standard").splitlines():
        if not rel.startswith((".sdd/", ".agents/build/runs/", ".agents/build/nohooks/")):
            raise Park(f"integration has an untracked authored file: {rel}")
