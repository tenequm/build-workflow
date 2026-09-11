"""Review sessions over the real acpx transport, and the template that pins them.

No provider is called: a recording ACP agent answers instead, so the launch, the
worktree allowlist, the report-witness law, the retry, the cost evidence and the
teardown are all exercised for real while the judgment is canned.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from operator_driver.storage import Ledger, Park
from review_pr import config, pondsync, readiness, runner

pytestmark = pytest.mark.skipif(shutil.which("acpx") is None, reason="acpx executable unavailable")

WRITES_ITS_REPORT = """
import json, re, sys
from pathlib import Path
REPORT = re.compile(r"Write exactly one file and no others: `([^`]+)`")
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    request = json.loads(line)
    method = request.get("method")
    result = {}
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {}, "authMethods": []}
    elif method == "session/new":
        result = {"sessionId": "recorded", "models": {"currentModelId": "m",
                  "availableModels": [{"modelId": "m", "name": "m"}]}}
    elif method == "session/prompt":
        text = "\\n".join(b.get("text", "") for b in request["params"].get("prompt", []))
        match = REPORT.search(text)
        if match and "MODE" != "silent":
            path = Path(match.group(1))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"lens": "cleanliness", "findings": []}))
        EXTRA
        print(json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": "recorded", "update": {"sessionUpdate": "usage_update", "used": 1,
            "size": 10, "cost": {"amount": COST, "currency": "USD"}}}}), flush=True)
        result = {"stopReason": "end_turn"}
    if "id" in request:
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def agent(tmp_path: Path, *, mode: str = "writes", extra: str = "pass", cost: float = 0.01) -> Path:
    source = (
        WRITES_ITS_REPORT.replace('"MODE" != "silent"', "True" if mode == "writes" else "False")
        .replace("EXTRA", extra)
        .replace("COST", repr(cost))
    )
    path = tmp_path / f"agent_{mode}_{abs(hash(extra + str(cost))) % 9999}.py"
    path.write_text(source)
    return path


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    head = git(root, "rev-parse", "HEAD")
    ledger_dir = tmp_path / "review"
    ledger_dir.mkdir()
    return {
        "sidecar": {"repo_path": str(root), "head": head},
        "ledger": Ledger(ledger_dir),
        "dir": ledger_dir,
    }


def task(path: Path, **over) -> runner.Task:
    spec = {
        "transport": "acp",
        "adapter_argv": [sys.executable, str(path)],
        "model": "m",
        "budget_usd": 1.0,
        "max_turns": 4,
        "timeout_s": 120,
    }
    return runner.Task(
        operation=over.pop("operation", "review-cleanliness-gemini"),
        key="review-cleanliness-gemini",
        brief="Write exactly one file and no others: `reports/findings-cleanliness.json`\n",
        report="reports/findings-cleanliness.json",
        witness='"lens": "cleanliness"',
        spec={**spec, **over.pop("spec", {})},
        lens="cleanliness",
        family="gemini",
        **over,
    )


class TestReportWitnessLaw:
    def test_a_session_that_writes_its_witnessed_report_succeeds(self, workspace, tmp_path):
        receipts = runner.run_batch(
            [task(agent(tmp_path))],
            workspace["sidecar"],
            workspace["ledger"],
            attempts=2,
            wall_cap=300,
        )
        receipt = receipts["review-cleanliness-gemini"]
        assert receipt["ok"] is True and receipt["problems"] == []
        assert receipt["cost_usd"] == 0.01
        assert receipt["signal"] == 'reports/findings-cleanliness.json :: "lens": "cleanliness"'

    def test_a_clean_exit_with_no_report_is_a_failed_attempt_and_is_retried(
        self, workspace, tmp_path
    ):
        """The luna failure shape: exit 0, nothing written. Without the witness this
        reads as success; with it, it is a retry and then an honest failure."""
        receipts = runner.run_batch(
            [task(agent(tmp_path, mode="silent"))],
            workspace["sidecar"],
            workspace["ledger"],
            attempts=2,
            wall_cap=300,
        )
        receipt = receipts["review-cleanliness-gemini"]
        assert receipt["ok"] is False
        assert any("declared report is missing" in problem for problem in receipt["problems"])
        operations = {row.get("operation") for row in workspace["ledger"].events}
        assert "review-cleanliness-gemini#2" in operations, "the failed attempt must be retried"

    def test_a_report_that_does_not_witness_itself_fails(self, workspace, tmp_path):
        writes_wrong_lens = agent(tmp_path)
        writes_wrong_lens.write_text(
            writes_wrong_lens.read_text().replace('"lens": "cleanliness"', '"lens": "design"')
        )
        receipts = runner.run_batch(
            [task(writes_wrong_lens)],
            workspace["sidecar"],
            workspace["ledger"],
            attempts=1,
            wall_cap=300,
        )
        receipt = receipts["review-cleanliness-gemini"]
        assert receipt["ok"] is False
        assert any("does not witness" in problem for problem in receipt["problems"])


class TestProviderOutage:
    """A turn that ends on the provider's error, with the adapter still exiting 0 and
    the stream still closing `end_turn`. Measured on the first corpus run: 11 of 67
    sessions ended this way, and nothing in the receipt said so."""

    ERROR_CHUNK = (
        'print(json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": '
        '{"sessionId": "recorded", "update": {"sessionUpdate": "agent_message_chunk", '
        '"content": {"type": "text", "text": "Agent execution error: model unreachable: '
        'Error 429, Status: RESOURCE_EXHAUSTED"}}}}), flush=True)'
    )

    def test_a_report_written_before_a_provider_error_is_never_accepted(
        self, workspace, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(runner, "PROVIDER_BACKOFF_S", 0.0)
        stalled = agent(tmp_path, extra=self.ERROR_CHUNK)
        with pytest.raises(Park, match="provider error"):
            runner.run_batch(
                [task(stalled)],
                workspace["sidecar"],
                workspace["ledger"],
                attempts=2,
                wall_cap=300,
            )
        path = workspace["dir"] / "sessions/review-cleanliness-gemini/receipt.json"
        receipt = json.loads(path.read_text())
        assert receipt["ok"] is False
        assert any(runner.PROVIDER_PROBLEM in problem for problem in receipt["problems"])
        assert receipt["report"], "it did write a report - it is the stream that refuses it"
        operations = {row.get("operation") for row in workspace["ledger"].events}
        assert "review-cleanliness-gemini#2" in operations, "the failed attempt must be retried"


class TestIsolation:
    def test_a_session_that_writes_outside_its_allowlist_parks_the_stage(self, workspace, tmp_path):
        nosy = agent(tmp_path, extra='Path("app.py").write_text("tampered\\n")')
        with pytest.raises(Park, match="outside its allowlist"):
            runner.run_batch(
                [task(nosy)],
                workspace["sidecar"],
                workspace["ledger"],
                attempts=1,
                wall_cap=300,
            )

    def test_each_session_gets_its_own_worktree_and_it_is_removed_afterwards(
        self, workspace, tmp_path
    ):
        runner.run_batch(
            [task(agent(tmp_path))],
            workspace["sidecar"],
            workspace["ledger"],
            attempts=1,
            wall_cap=300,
        )
        assert not (workspace["dir"] / "sessions/review-cleanliness-gemini/worktree").exists()
        archived = workspace["dir"] / "sessions/review-cleanliness-gemini/findings-cleanliness.json"
        assert json.loads(archived.read_text())["lens"] == "cleanliness"

    def test_sessions_in_one_batch_run_concurrently(self, workspace, tmp_path):
        path = agent(tmp_path)
        tasks = [task(path, operation=f"review-lens-{index}") for index in range(3)]
        receipts = runner.run_batch(
            tasks, workspace["sidecar"], workspace["ledger"], attempts=1, wall_cap=300
        )
        assert all(receipt["ok"] for receipt in receipts.values())
        spans = [(r["started"], r["finished"]) for r in receipts.values()]
        latest_start = max(start for start, _ in spans)
        earliest_finish = min(finish for _, finish in spans)
        assert latest_start < earliest_finish, "the batch should overlap, not queue"


class TestStageTemplate:
    def test_the_gating_lens_can_never_be_routed_to_codex(self):
        plan = config.load()
        with pytest.raises(Park, match="must never run on codex"):
            config.lens_spec(plan, "gating", family="codex")

    def test_a_template_that_pins_a_forbidden_family_is_refused(self, tmp_path):
        import yaml

        data = config.load()
        data["lenses"]["gating"]["family"] = "codex"
        path = tmp_path / "stages.yaml"
        path.write_text(yaml.safe_dump(data))
        with pytest.raises(Park, match="forbids"):
            config.load(path)

    @pytest.mark.parametrize(
        "mutate,message",
        [
            (lambda d: d["lenses"].pop("efficiency"), "exactly the lenses"),
            (lambda d: d["families"].pop("codex"), "undeclared family"),
            (lambda d: d["bounds"].update(max_verifier_sessions=0), "positive integer"),
            (lambda d: d["bounds"].update(max_wall_s=0), "positive number"),
            (lambda d: d["roles"].pop("verifier"), "no verifier role"),
            (lambda d: d["lenses"]["design"].pop("model"), "explicit model"),
        ],
    )
    def test_an_incomplete_template_parks_before_anything_is_spawned(
        self, tmp_path, mutate, message
    ):
        import yaml

        data = config.load()
        mutate(data)
        path = tmp_path / "stages.yaml"
        path.write_text(yaml.safe_dump(data))
        with pytest.raises(Park, match=message):
            config.load(path)

    def test_a_review_session_persists_so_pond_can_ingest_it(self, tmp_path):
        """Measured 2026-09-11: codex and agy write their own rollouts and were captured,
        while every Claude review session was invisible to pond because the bridge
        defaults to not saving one."""
        plan = config.load()
        bridge = runner.session_argv(config.lens_spec(plan, "gating"), tmp_path, tmp_path / "p.md")
        assert "--persist" in bridge[bridge.index("--agent") + 1]
        from operator_driver.claude_acp import bind_session

        saved = bind_session({"method": "session/new"}, budget=1, model="m", turns=2, persist=True)
        assert saved["params"]["_meta"]["claudeCode"]["options"]["persistSession"] is True

    def test_a_blind_judge_still_leaves_no_session_behind(self):
        """The build judge's default must not move: it reviews blind and resumes never."""
        from operator_driver.acp import judge_argv
        from operator_driver.claude_acp import bind_session

        default = bind_session({"method": "session/new"}, budget=1, model="m", turns=2)
        assert default["params"]["_meta"]["claudeCode"]["options"]["persistSession"] is False
        spec = {
            "budget_usd": 1,
            "model": "m",
            "max_turns": 2,
            "timeout_s": 5,
            "adapter_argv": ["npx", "adapter"],
        }
        argv = judge_argv(spec, Path("/tmp"), Path("/tmp/p.md"))
        assert "--persist" not in argv[argv.index("--agent") + 1]


class TestReadiness:
    def test_a_lens_routed_to_an_unresolvable_adapter_blocks(self, tmp_path):
        import yaml

        data = config.load()
        data["families"]["gemini"]["adapter_argv"] = ["/nonexistent/agy-acp-server"]
        path = tmp_path / "stages.yaml"
        path.write_text(yaml.safe_dump(data))
        report = readiness.check(config.load(path), capture=False)
        adapter = next(row for row in report["checks"] if row["check"] == "adapter:gemini")
        assert adapter["ok"] is False and adapter["blocking"] is True
        assert report["ok"] is False
        with pytest.raises(Park, match="readiness refused"):
            readiness.require(report)


class TestPondPin:
    def test_the_pinned_binary_gates_on_exact_version(self, tmp_path, monkeypatch):
        """Pinned like the bernstein dep: a host pond ahead of the pin is as much
        drift as one behind it."""
        fake = tmp_path / "pond"
        fake.write_text("#!/bin/sh\necho pond 0.16.9\n")
        fake.chmod(0o755)
        monkeypatch.setenv("POND_BIN", str(fake))
        report = pondsync.current()
        assert report["ok"] is False
        assert report["version"] == "0.16.9" and report["pinned"] == "0.17.2"

    def test_the_exact_pin_passes(self, tmp_path, monkeypatch):
        fake = tmp_path / "pond"
        fake.write_text("#!/bin/sh\necho pond 0.17.2\n")
        fake.chmod(0o755)
        monkeypatch.setenv("POND_BIN", str(fake))
        assert pondsync.current()["ok"] is True


class TestCostEvidenceIsInformative:
    """Cost is observability: malformed or regressing figures never void a review
    session's transcript. The blind judge keeps the strict contract."""

    def lines(self, *costs):
        rows = [
            {
                "method": "session/update",
                "params": {
                    "sessionId": "s1",
                    "update": {
                        "sessionUpdate": "usage_update",
                        "cost": {"currency": "USD", "amount": amount},
                    },
                },
            }
            for amount in costs
        ]
        rows.append({"result": {"stopReason": "end_turn"}})
        return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()

    def test_a_backwards_cost_is_ignored_without_the_strict_contract(self):
        from operator_driver.acp import transcript

        evidence = transcript(self.lines(0.5, 0.2), require_cost=False)
        assert evidence["cost_usd"] == 0.5

    def test_the_strict_contract_still_parks_on_a_backwards_cost(self):
        from operator_driver.acp import transcript

        with pytest.raises(Park, match="moved backwards"):
            transcript(self.lines(0.5, 0.2), require_cost=True)

    def test_a_missing_cost_is_none_not_fatal(self):
        from operator_driver.acp import transcript

        rows = [{"result": {"stopReason": "end_turn"}}]
        rows.insert(
            0,
            {
                "method": "session/update",
                "params": {"sessionId": "s1", "update": {"sessionUpdate": "agent_message_chunk"}},
            },
        )
        log = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
        assert transcript(log, require_cost=False)["cost_usd"] is None
