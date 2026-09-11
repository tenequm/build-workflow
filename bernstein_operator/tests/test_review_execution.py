"""Everything that runs untrusted code: the sandbox, the rubrics, the gold gate, the
gate itself, and a suggestion that is applied for real before it is offered.

These are the parts that make a finding evidence rather than an opinion, so they are
tested by executing, never by mocking the execution.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from operator_driver.storage import Park
from review_pr import findings, gate, rubric, sandbox, suggestions

BASE_BILLING = (
    "def validate(order):\n"
    "    if not order['items']:\n"
    "        raise ValueError('empty')\n\n\n"
    "def charge(order):\n"
    "    CHARGES.append(order)\n"
    "    return 'ok'\n\n\n"
    "CHARGES = []\n\n\n"
    "def charge_order(order):\n"
    "    validate(order)\n"
    "    return charge(order)\n"
)
HEAD_BILLING = BASE_BILLING.replace(
    "def charge_order(order):\n    validate(order)\n    return charge(order)\n",
    "def charge_order(order):\n    receipt = charge(order)\n    validate(order)\n"
    "    return receipt\n",
)
# A real proof of concept: it charges nothing on the base tree and charges an invalid
# order on the head tree, which is exactly the defect the reordering introduced.
REPRO = """python3 - <<'PY'
import billing
try:
    billing.charge_order({'items': []})
except ValueError:
    pass
raise SystemExit(1 if billing.CHARGES else 0)
PY
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def review(tmp_path):
    """A checkout, its two detached trees, and the sidecar the stages read."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "billing.py").write_text(BASE_BILLING)
    (root / "CLAUDE.md").write_text("check with `python3 -m unittest discover -s tests -t .`\n")
    (root / "tests").mkdir()
    (root / "tests/__init__.py").write_text("")
    (root / "tests/test_billing.py").write_text(
        "import unittest\n\nimport billing\n\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_valid_order_charges(self):\n"
        "        billing.CHARGES.clear()\n"
        "        self.assertEqual(billing.charge_order({'items': ['x']}), 'ok')\n"
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-q", "-c", "feat/x")
    (root / "billing.py").write_text(HEAD_BILLING)
    git(root, "commit", "-qam", "feat: reorder")
    head = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-q", "main")
    workspace = tmp_path / "review"
    workspace.mkdir()
    tree, base_tree, scratch = workspace / "tree", workspace / "base", workspace / "scratch"
    scratch.mkdir()
    git(root, "worktree", "add", "--detach", "--quiet", str(tree), head)
    git(root, "worktree", "add", "--detach", "--quiet", str(base_tree), base)
    return {
        "repo_path": str(root),
        "tree": str(tree),
        "base_tree": str(base_tree),
        "scratch": str(scratch),
        "base": base,
        "head": head,
        "gate": {
            "command": "python3 -m unittest discover -s tests -t .",
            "source": "base-project-doc",
        },
    }


class TestSandbox:
    @pytest.mark.skipif(
        not sandbox.capability()["userns"], reason="this host has no unprivileged user namespaces"
    )
    def test_untrusted_code_gets_no_network(self, tmp_path):
        script = (
            'python3 -c "import socket\n'
            "try:\n socket.create_connection(('1.1.1.1', 80), timeout=2)\n"
            " print('REACHABLE')\n"
            "except OSError:\n print('blocked')\""
        )
        assert "blocked" in sandbox.run(script, tmp_path, tier_name="userns", timeout=60)["stdout"]

    def test_a_tier_this_host_cannot_honour_is_refused_rather_than_downgraded(self):
        with pytest.raises(Park, match="pinned image"):
            sandbox.tier("container", image=None)
        with pytest.raises(Park, match="unknown sandbox tier"):
            sandbox.tier("wishful")

    def test_the_credential_allowlist_is_a_keep_list(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_not_for_the_reviewer")
        result = sandbox.run("env", tmp_path, tier_name="none", timeout=30)
        assert "GITHUB_TOKEN" not in result["stdout"]
        assert "ghp_not_for_the_reviewer" not in result["stdout"]


class TestRubrics:
    def finding(self, **over):
        return findings.normalize(
            {
                "file": "billing.py",
                "line": 12,
                "category": "correctness",
                "claim": "The charge runs before its gate.",
                "evidence": "billing.py:12",
                **over,
            },
            lens="gating",
            producer="claude",
        )

    def test_a_command_rubric_is_decided_by_its_exit_code(self, review):
        passing = rubric.execute(
            self.finding(rubric={"kind": "command", "run": "true", "expect": "exit_zero"}),
            review,
            tier=sandbox.tier(),
        )
        assert passing == {
            "ran": True,
            "passed": True,
            "kind": "command",
            "expect": "exit_zero",
            "legs": passing["legs"],
        }
        failing = rubric.execute(
            self.finding(rubric={"kind": "command", "run": "false", "expect": "exit_zero"}),
            review,
            tier=sandbox.tier(),
        )
        assert failing["passed"] is False

    def test_a_command_rubric_that_runs_a_missing_script_never_passes(self, review):
        """Measured 2026-09-11 on floor/case-04: a verifier wrote its repro into its own
        worktree and named it in a rubric. Rubrics run against the shared tree, `sh` on
        a missing file exits non-zero, and `exit_nonzero` read that as the claim proved.
        A check that could not run refutes nothing, and it confirms nothing either."""
        result = rubric.execute(
            self.finding(
                rubric={
                    "kind": "command",
                    "run": "sh scratch/repro-678dfdbdda79.sh",
                    "expect": "exit_nonzero",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert result["ran"] is False and result["passed"] is False
        assert "does not exist in the tree" in result["reason"]

    def test_an_absence_proof_is_still_allowed_to_run(self, review):
        """`test -f gone.md` expecting non-zero is a legitimate check on a missing file;
        the guard polices the interpreter's target, not every path in the line."""
        result = rubric.execute(
            self.finding(
                rubric={"kind": "command", "run": "test -f nothing.md", "expect": "exit_nonzero"}
            ),
            review,
            tier=sandbox.tier(),
        )
        assert result["ran"] is True and result["passed"] is True

    def test_a_grep_rubric_decides_on_presence(self, review):
        present = rubric.execute(
            self.finding(
                rubric={
                    "kind": "grep",
                    "pattern": "receipt = charge",
                    "path": "billing.py",
                    "expect": "nonempty",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert present["passed"] is True
        absent = rubric.execute(
            self.finding(
                rubric={
                    "kind": "grep",
                    "pattern": "receipt = charge",
                    "path": "billing.py",
                    "expect": "empty",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert absent["passed"] is False

    def test_a_grep_rubric_cannot_escape_the_tree(self, review):
        result = rubric.execute(
            self.finding(
                rubric={"kind": "grep", "pattern": "x", "path": "../../etc", "expect": "nonempty"}
            ),
            review,
            tier=sandbox.tier(),
        )
        assert result["ran"] is False and "unsafe grep path" in result["reason"]

    def test_a_revert_test_rubric_needs_the_test_to_pass_at_the_head_first(self, review):
        broken = rubric.execute(
            self.finding(
                rubric={
                    "kind": "revert_test",
                    "hunk": "billing.py:11-14",
                    "test": "false",
                    "expect": "exit_nonzero",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert broken["passed"] is False
        assert "cannot flip" in broken["reason"]

    def test_a_revert_test_rubric_reverts_only_the_hunk_it_names(self, review):
        """Here the test passes both ways, which is exactly why this rubric must fail:
        no test witnesses the reordering, so the claim needs a proof of concept."""
        result = rubric.execute(
            self.finding(
                rubric={
                    "kind": "revert_test",
                    "hunk": "billing.py:11-14",
                    "test": "python3 -m unittest discover -s tests -t .",
                    "expect": "exit_nonzero",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert result["ran"] is True and result["passed"] is False
        assert [leg["leg"] for leg in result["legs"]] == ["head", "reverted"]
        assert result["legs"][0]["returncode"] == 0

    def test_a_hunk_outside_the_diff_parks_the_rubric_not_the_run(self, review):
        result = rubric.execute(
            self.finding(
                rubric={
                    "kind": "revert_test",
                    "hunk": "billing.py:900-901",
                    "test": "true",
                    "expect": "exit_nonzero",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert result["ran"] is False and "no hunk" in result["reason"]


class TestGoldGate:
    def test_a_repro_confirms_only_when_it_fails_on_head_and_passes_on_base(self, review):
        result = rubric.gold_gate(REPRO, review, tier=sandbox.tier())
        assert result["passed"] is True
        assert result["fails_on_head"] is True and result["passes_on_base"] is True

    def test_a_repro_that_fails_both_ways_proves_nothing(self, review):
        result = rubric.gold_gate("exit 1", review, tier=sandbox.tier())
        assert result["passed"] is False
        assert "fails on base as well" in result["reason"]

    def test_a_repro_that_passes_on_head_demonstrates_nothing(self, review):
        result = rubric.gold_gate("true", review, tier=sandbox.tier())
        assert result["passed"] is False
        assert "passes on the pull request head" in result["reason"]


class TestGate:
    def test_a_green_gate_produces_no_finding_and_records_its_cold_caches(self, review):
        result = gate.run({**review, "scratch": review["scratch"]}, tier=sandbox.tier())
        assert result["returncode"] == 0 and result["findings"] == []
        assert "GOLANGCI_LINT_CACHE" in result["cold_caches"]
        assert result["provenance"]["source"] == "base-project-doc"

    def test_a_red_gate_is_a_finding_and_never_a_fix(self, review):
        result = gate.run(
            {**review, "gate": {"command": "exit 3", "source": "operator"}}, tier=sandbox.tier()
        )
        assert result["returncode"] == 3
        assert result["findings"][0]["category"] == "correctness"
        assert result["findings"][0]["rubric"]["run"] == "exit 3"


class TestProvenSuggestions:
    def finding(self, **over):
        return {
            "id": "s1",
            "file": "billing.py",
            "line": 12,
            "verdict": "CONFIRMED",
            "category": "correctness",
            **over,
        }

    def test_a_suggestion_that_keeps_the_gate_green_is_proven(self, review):
        proof = suggestions.prove(
            self.finding(
                suggestion={
                    "start_line": 1,
                    "line": 1,
                    "replacement": "def validate(order):  # renamed nothing",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert proof["applied"] is True and proof["proven"] is True

    def test_a_suggestion_that_breaks_the_gate_is_downgraded_not_posted(self, review):
        proof = suggestions.prove(
            self.finding(
                suggestion={
                    "start_line": 1,
                    "line": 1,
                    "replacement": "def validate(order:  # syntax error",
                }
            ),
            review,
            tier=sandbox.tier(),
        )
        assert proof["applied"] is True and proof["proven"] is False
        assert "exited" in proof["reason"]

    def test_a_suggestion_outside_the_file_is_refused(self, review):
        proof = suggestions.prove(
            self.finding(file="nowhere.py", suggestion={"line": 1, "replacement": "x"}),
            review,
            tier=sandbox.tier(),
        )
        assert proof["applied"] is False and "not in the tree" in proof["reason"]
        span = suggestions.prove(
            self.finding(suggestion={"start_line": 400, "line": 900, "replacement": "x"}),
            review,
            tier=sandbox.tier(),
        )
        assert span["applied"] is False and "outside" in span["reason"]

    def test_the_proof_budget_is_bounded_and_the_rest_say_so(self, review):
        rows = [
            self.finding(id=f"s{i}", suggestion={"line": 1, "replacement": "# noop"})
            for i in range(3)
        ]
        proofs = suggestions.prove_all(rows, review, tier=sandbox.tier(), cap=1)
        assert sum(1 for p in proofs.values() if p["applied"]) == 1
        assert any("budget" in p["reason"] for p in proofs.values())

    def test_a_dropped_finding_is_never_proven(self, review):
        rows = [self.finding(verdict="DROPPED", suggestion={"line": 1, "replacement": "# noop"})]
        assert suggestions.prove_all(rows, review, tier=sandbox.tier(), cap=5) == {}

    def test_a_style_suggestion_is_never_gated_and_says_why(self, review):
        """The gate is the most expensive thing this workflow runs; a cleanliness
        suggestion posts as prose either way, so it never earns a full gate run."""
        rows = [
            self.finding(
                id="s9", category="cleanliness", suggestion={"line": 1, "replacement": "# noop"}
            )
        ]
        proofs = suggestions.prove_all(rows, review, tier=sandbox.tier(), cap=5)
        assert proofs["s9"]["applied"] is False and proofs["s9"]["proven"] is False
        assert "only correctness suggestions" in proofs["s9"]["reason"]
