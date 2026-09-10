from __future__ import annotations

import sys

import pytest
import yaml
from bernstein.core.quality.janitor import _check_file_contains
from operator_driver.spec import Build
from operator_driver.storage import Park
from test_scorer_contract import git


@pytest.fixture
def authored(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q", "-b", "integration")
    git(root, "config", "user.name", "Plan test")
    git(root, "config", "user.email", "test@example.invalid")
    declarations = [
        ("a", [], "resolver"),
        ("b", ["a"], "analyst"),
        ("repair-first", ["a", "b"], "resolver"),
        ("c", ["a", "b"], "resolver"),
        ("repair-final", ["c"], "analyst"),
    ]
    stages = [
        {
            "name": name,
            "depends_on": dependencies,
            "steps": [
                {
                    "title": name,
                    "role": role,
                    "description": f"Implement {name} from its pinned brief",
                    "files": [f"src/{name}.py"],
                    "completion_signals": [
                        {"type": "file_contains", "value": f"src/{name}.py :: VALUE"}
                    ],
                }
            ],
        }
        for name, dependencies, role in declarations
    ]
    path = root / "build.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "demo",
                "max_agents": 2,
                "stages": stages,
                "constraints": ["Never push or change the integration ref."],
            }
        )
    )
    sidecar = {
        "defaults": {"gate_cmd": "true"},
        "bounds": {"max_attempts": 10, "max_wall_s": 300, "max_spend_usd": 10, "run_budget_usd": 1},
        "phases": [
            {"name": "first", "steps": ["b", "a"], "fix": "repair-first"},
            {"name": "final", "steps": ["c"], "fix": "repair-final", "final_regression": True},
        ],
        "steps": {
            name: {"brief": f"briefs/{name}.md", "report": f".agents/{name}.md"}
            for name, _, _ in declarations
        },
    }
    for phase in sidecar["phases"]:
        phase["judge"] = {
            "brief": "briefs/judge.md",
            "adapter_argv": [sys.executable, "-m", "claude_agent_acp"],
            "model": "claude-opus-5",
            "max_turns": 4,
            "timeout_s": 20,
            "budget_usd": 1,
        }
    (root / "build.steps.yaml").write_text(yaml.safe_dump(sidecar))
    (root / "briefs").mkdir()
    for name in ["judge", *(name for name, _, _ in declarations)]:
        (root / "briefs" / f"{name}.md").write_text(
            "## Items\nDo the work.\n## Validation\n```\ntrue\n```\n"
        )
    (root / "bernstein.yaml").write_text(
        yaml.safe_dump(
            {
                "max_agents": 2,
                "quality_gates": {"base_ref": "integration"},
                "role_model_policy": {
                    "resolver": {"cli": "codex", "model": "gpt-5.6-sol", "effort": "high"},
                    "analyst": {"cli": "claude", "model": "claude-opus-5", "effort": "high"},
                },
            }
        )
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "frozen inputs")
    return root, path


def test_real_loader_dependency_titles_survive_phase_compilation(authored):
    root, path = authored
    build = Build(root, path)
    payloads = build.payloads(["b", "a"], "unique-native-run")
    assert [title for title, _ in payloads] == ["a", "b"]
    assert payloads[1][1]["metadata"]["operator_dependencies"] == ["a"]
    assert payloads[0][1]["completion_signals"] == [
        {"type": "file_contains", "value": "src/a.py :: VALUE"}
    ]
    assert "Never push or change the integration ref." in payloads[0][1]["description"]
    assert "id" not in payloads[0][1]
    (root / "src").mkdir()
    (root / "src/a.py").write_text("VALUE = 1\n")
    assert _check_file_contains(payloads[0][1]["completion_signals"][0]["value"], root)
    (root / "src/a.py").write_text("WRONG = 1\n")
    assert not _check_file_contains(payloads[0][1]["completion_signals"][0]["value"], root)
    # Prior phases are verified outside the engine, so their IDs cannot leak
    # into the fresh task store used by the next phase or a fix mini-run.
    assert build.payloads(["c"], "later")[0][1]["metadata"]["operator_dependencies"] == []
    assert build.payloads(["repair-first"], "fix")[0][1]["metadata"]["operator_dependencies"] == []


def test_broken_completion_signal_shape_fails_before_any_post(authored):
    root, path = authored
    raw = yaml.safe_load(path.read_text())
    raw["stages"][0]["steps"][0]["completion_signals"] = [
        {"type": "file_contains", "path": "src/a.py", "contains": "VALUE"}
    ]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(Park, match="signals differ"):
        Build(root, path)


def test_judge_transport_selects_its_required_limits(authored):
    root, path = authored
    sidecar_path = path.with_suffix(".steps.yaml")
    sidecar = yaml.safe_load(sidecar_path.read_text())
    for phase in sidecar["phases"]:
        phase["judge"].update(transport="acp", model="gemini-3.7-flash-low")
    sidecar_path.write_text(yaml.safe_dump(sidecar))
    Build(root, path)
    # Every transport is turn-bounded: the bridge binds it in session metadata, acpx
    # binds it with --max-turns, and neither may be left to the agent.
    del sidecar["phases"][0]["judge"]["max_turns"]
    sidecar_path.write_text(yaml.safe_dump(sidecar))
    with pytest.raises(Park, match="max_turns"):
        Build(root, path)
    sidecar["phases"][0]["judge"]["max_turns"] = 4
    sidecar["phases"][0]["judge"]["transport"] = "herdr"
    sidecar_path.write_text(yaml.safe_dump(sidecar))
    with pytest.raises(Park, match="transport"):
        Build(root, path)


def test_codex_role_effort_must_state_the_machine_config(authored, tmp_path):
    from operator_driver.readiness import codex_effort

    build = Build(*authored)
    config = tmp_path / "config.toml"
    with pytest.raises(Park, match=r"\['high'\].*= default"):
        codex_effort(build, config)
    config.write_text('model_reasoning_effort = "high"\n[features]\nhooks = true\n')
    codex_effort(build, config)
    build.seed["role_model_policy"]["resolver"]["effort"] = "default"
    with pytest.raises(Park, match="= high"):
        codex_effort(build, config)
    config.write_text("")
    codex_effort(build, config)
    config.write_text("model_reasoning_effort = high\n")
    with pytest.raises(Park, match="cannot be read"):
        codex_effort(build, config)


def test_future_stage_dependency_cannot_be_silently_dropped_by_native_loader(authored):
    root, path = authored
    raw = yaml.safe_load(path.read_text())
    raw["stages"][0]["depends_on"] = ["c"]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(Park, match="earlier declared stages"):
        Build(root, path)
