from __future__ import annotations

import inspect
import json
import runpy
import shutil
from pathlib import Path

import pytest
import yaml
from operator_driver import admission, readiness
from operator_driver.spec import Build
from operator_driver.storage import Ledger, Park, driver_lock
from test_scorer_contract import git

HOOKS = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "skills/build-run/scripts/workspace-hooks.py")
)["configure"]


def test_hooks_restore_exact_original_and_refuse_unrelated_changes(authored):
    root, _ = authored
    run = root / ".agents/build/runs/demo"
    git(root, "config", "core.hooksPath", "original-hooks")
    HOOKS(root, run, "disable")
    HOOKS(root, run, "disable")
    assert git(root, "config", "--get", "core.hooksPath") == str(root / ".agents/build/nohooks")
    HOOKS(root, run, "restore")
    assert git(root, "config", "--get", "core.hooksPath") == "original-hooks"
    HOOKS(root, run, "disable")
    git(root, "config", "core.hooksPath", "someone-elses-hooks")
    with pytest.raises(RuntimeError, match="changed outside"):
        HOOKS(root, run, "restore")
    assert git(root, "config", "--get", "core.hooksPath") == "someone-elses-hooks"


def test_linked_workspace_admission_and_write_once_freeze(authored, monkeypatch, tmp_path):
    primary, path = authored
    (primary / ".gitignore").write_text(".sdd/\n.agents/build/runs/\n.agents/build/nohooks/\n")
    (primary / "spec.md").write_text("# 1 Intent\nImplement the measured behavior.\n")
    (primary / "plan.md").write_text("# 1 Work\nExecute the declared tasks.\n")
    git(primary, "add", "-A")
    git(primary, "commit", "-qm", "docs: sign off specification")
    signoff = git(primary, "rev-parse", "HEAD")
    sidecar_path = path.with_suffix(".steps.yaml")
    sidecar = yaml.safe_load(sidecar_path.read_text())
    sidecar["defaults"].update(doc="plan.md", spec="spec.md", signoff=signoff)
    sidecar_path.write_text(yaml.safe_dump(sidecar))
    seed_path = primary / "bernstein.yaml"
    seed = yaml.safe_load(seed_path.read_text())
    seed.update(
        goal="readiness fixture",
        gate_repair_enabled=False,
        evolution_enabled=False,
        orchestration={"test_followup": False},
    )
    seed["quality_gates"].update(
        base_ref="feat/ready",
        enabled=True,
        cache_enabled=False,
        flaky_detection=False,
        pipeline=[{"name": "scorer", "required": True, "condition": "always"}],
    )
    # This fixture exercises the actual role policy without depending on a
    # developer's global Codex configuration. CLI versions make no model calls.
    for policy in seed["role_model_policy"].values():
        policy.update(cli="claude", model="claude-opus-5")
    seed_path.write_text(yaml.safe_dump(seed))
    git(primary, "add", "-A")
    git(primary, "commit", "-qm", "chore: freeze readiness fixture")
    root = tmp_path / "workspace"
    git(primary, "worktree", "add", "-qb", "feat/ready", str(root))
    build = Build(root, root / path.name)
    build.run_dir.mkdir(parents=True)
    (build.run_dir / "workspace.json").write_text(
        json.dumps(
            {
                "path": str(root.resolve()),
                "branch": build.branch,
                "base": signoff,
                "base_branch": "integration",
                "primary": str(primary),
            }
        )
    )
    HOOKS(root, build.run_dir, "disable")
    monkeypatch.chdir(root)
    with driver_lock(root):
        receipt = readiness.check(build)
        assert receipt["validated"] and receipt["validation"][0]["returncode"] == 0
        assert receipt["runtime"]["code"]["bernstein.core.git.git_basic"]
        ledger = Ledger(build.run_dir)
        frozen = readiness.freeze(build, ledger)
        assert readiness.freeze(build, ledger) == frozen
        assert git(root, "rev-parse", "refs/build/base/demo") == frozen["base"]
        git(root, "commit", "--allow-empty", "-qm", "chore: later phase tip")
        assert readiness.freeze(build, ledger)["base"] == frozen["base"]
        (root / "TODO.md").write_text("Unplanned work\n")
        with pytest.raises(Park, match="importable"):
            admission.no_ingress(root)
    HOOKS(root, build.run_dir, "restore")


def test_missing_required_scorer_switch_fails_before_launch(authored):
    root, path = authored
    build = Build(root, path)
    with pytest.raises(Park, match="quality gates must be enabled"):
        admission.prerequisites(build)


def test_engine_without_the_closed_quiescence_patch_fails_admission(
    authored, monkeypatch, tmp_path
):
    """A merged task is archived to CLOSED; an engine whose terminal check omits that
    status never self-stops, so the phase boundary it journals never arrives."""
    from bernstein.core.orchestration import orchestrator

    patched = Path(inspect.getfile(orchestrator)).read_text()
    marker = 'or fetch_all_tasks(self._client, base, ["closed"])["closed"]\n'
    assert marker in patched, "the installed acceptance engine is unpatched"
    stock = tmp_path / "orchestrator.py"
    stock.write_text(patched.replace(marker, ""))
    real = admission.inspect.getfile
    monkeypatch.setattr(
        admission.inspect,
        "getfile",
        lambda module: str(stock) if module is orchestrator else real(module),
    )
    with pytest.raises(Park, match="closed-task quiescence patch"):
        admission.prerequisites(Build(*authored))


def test_prepare_engine_applies_every_patch_once_to_the_pinned_source(tmp_path):
    import bernstein

    prepare = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "skills/build-run/scripts/prepare-engine.py")
    )["prepare"]
    source = tmp_path / "src/bernstein"
    shutil.copytree(
        Path(bernstein.__file__).parent, source, ignore=shutil.ignore_patterns("__pycache__")
    )
    # The acceptance engine is already patched, so reverting one proves the patcher
    # reapplies exactly it, and that a second pass is the no-op the checker accepts.
    orchestrator = source / "core/orchestration/orchestrator.py"
    orchestrator.write_text(
        orchestrator.read_text().replace(
            "            _had_any_terminal_task = bool(\n"
            '                refreshed_tasks_by_status["done"]\n'
            '                or refreshed_tasks_by_status["failed"]\n'
            '                or fetch_all_tasks(self._client, base, ["closed"])["closed"]\n'
            "            )",
            '            _had_any_terminal_task = bool(refreshed_tasks_by_status["done"] '
            'or refreshed_tasks_by_status["failed"])',
        )
    )
    with pytest.raises(RuntimeError, match="prerequisite patches"):
        prepare(tmp_path, check=True)
    assert prepare(tmp_path) == ["src/bernstein/core/orchestration/orchestrator.py"]
    assert prepare(tmp_path) == []
    prepare(tmp_path, check=True)


def test_missing_installed_plugin_fails_admission(authored, monkeypatch):
    from bernstein.core.quality.gate_plugins import GatePluginRegistry

    root, path = authored
    monkeypatch.setattr(GatePluginRegistry, "get", lambda *args: None)
    with pytest.raises(Park, match="entry point is absent"):
        admission.prerequisites(Build(root, path))
