"""Stage 3: who verifies what, and how a verdict is reached.

The two rules this pins are the ones the research says matter most: a verifier is
never the claim's own family, and a correctness claim confirms on a demonstration that
survives the gold gate, not on prose.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest
from operator_driver.storage import Park
from review_pr import claims, config, dualfamily, findings, readiness, verify


def finding(**over):
    lens = over.pop("lens", "gating")
    producer = over.pop("producer", "claude")
    base = {
        "file": "a.py",
        "line": 3,
        "category": "correctness",
        "claim": "The charge runs before its gate.",
        "evidence": "a.py:3 charge()",
    }
    return findings.normalize({**base, **over}, lens=lens, producer=producer)


def observed(passed=True, ran=True, **over):
    return {"ran": ran, "passed": passed, **over}


def session(**over):
    return {
        "operation": "verify-x",
        "family": "codex",
        "model": "gpt-5.6-terra",
        "ok": True,
        "problems": [],
        "cost_usd": 0.1,
        "acp": {"session_id": "s"},
        **over,
    }


def _with_families(plan, *names):
    """The same plan with extra registered families, as a new lane would add them."""
    for name in names:
        plan["families"][name] = {"transport": "acp", "adapter_argv": ["adapter", name]}
        plan["roles"]["verifier"]["models"][name] = f"{name}-model"
    return plan


class TestRouting:
    def test_a_verifier_is_never_the_producing_family(self):
        plan = config.load()
        for producer in ("claude", "codex", "gemini"):
            assert verify.opposite(plan, producer)[0] != producer

    def test_a_family_beyond_the_declared_table_still_gets_a_different_verifier(self):
        """The law is cross-family verification, not a two-family flip. A lane added to
        the registry with no entry in routing.opposite must still be verified by
        someone else, and by the same someone else on every run."""
        plan = _with_families(config.load(), "pi", "zeta")
        for producer in sorted(plan["roles"]["verifier"]["models"]):
            family, reason = verify.opposite(plan, producer)
            assert family != producer
            assert family in plan["roles"]["verifier"]["models"]
            assert verify.opposite(plan, producer) == (family, reason), "not deterministic"
        assert verify.opposite(plan, "pi")[0] == "claude"
        assert verify.opposite(plan, "claude")[0] == "codex", "a declared opposite still wins"

    def test_the_reason_a_verifier_family_was_chosen_reaches_the_receipt(self):
        """With more than two families registered, which one judged is a fact about the
        run that the routing table alone no longer explains."""
        plan = _with_families(config.load(), "pi")
        row = finding(producer="pi", category="correctness")
        seen = {}

        def launch(tasks):
            seen.update({task.operation: task for task in tasks})
            return {
                task.operation: session(
                    operation=task.operation,
                    family=task.family,
                    ok=False,
                    problems=["no provider in this test"],
                )
                for task in tasks
            }

        verify.verify(
            [row],
            {"base_tree": "beef"},
            plan,
            _ledger(),
            {"diff": Path("/tmp/diff.patch")},
            tier="none",
            launch=launch,
        )
        task = seen[f"verify-{row['id']}"]
        assert task.family == "claude" and task.meta["producer"] == "pi"
        assert "no opposite is declared for pi" in task.meta["verifier_reason"]

    def test_a_template_with_one_verifiable_family_parks_rather_than_self_verifies(self):
        plan = config.load()
        plan["roles"]["verifier"]["models"] = {"gemini": "gemini-3.7-flash-medium"}
        plan["routing"]["opposite"] = {}
        with pytest.raises(Park, match="no family available to verify"):
            verify.opposite(plan, "gemini")

    def test_correctness_and_impact_take_the_budget_first(self):
        rows = [
            finding(id="a", category="cleanliness", lens="cleanliness"),
            finding(category="correctness", impact="data_loss"),
            finding(file="b.py", category="correctness"),
        ]
        ordered = sorted(rows, key=verify.priority)
        assert ordered[0]["impact"] == "data_loss"
        assert ordered[-1]["category"] == "cleanliness"

    def test_a_passing_rubric_settles_a_claim_without_spending_a_session(self):
        cheap = finding(category="cleanliness", lens="cleanliness")
        queued, settled = verify.select([cheap], {cheap["id"]: observed()}, cap=10)
        assert queued == [] and settled == [cheap]

    def test_a_correctness_claim_queues_even_when_its_rubric_passed(self):
        claim = finding()
        queued, settled = verify.select([claim], {claim["id"]: observed()}, cap=10)
        assert queued == [claim] and settled == []

    def test_a_claim_spanning_two_artifacts_always_gets_a_reader(self):
        """Its rubric can only execute against the code; the statement it contradicts is
        the other half, and nothing mechanical reads that."""
        row = finding(lens="implementation", category="correctness")
        queued, settled = verify.select([row], {row["id"]: observed(passed=True)}, cap=10)
        assert queued == [row] and settled == []
        cheap = finding(lens="implementation", category="design")
        _q2, s2 = verify.select([cheap], {cheap["id"]: observed(passed=True)}, cap=10)
        assert s2 == [cheap], "a design-category note settles on its rubric as before"

    def test_past_the_cap_a_two_sided_claim_is_plausible_not_confirmed(self):
        row = finding(lens="implementation", category="correctness")
        settled = verify.settle(row, observed(passed=True), None, {}, tier="none")
        assert settled["verdict"] == "PLAUSIBLE"
        assert "implementation side only" in settled["verify"]["reason"]

    def test_the_cap_is_a_ceiling_and_the_overflow_settles_on_its_rubric(self):
        rows = [
            finding(file=f"f{i}.py", category="cleanliness", lens="cleanliness") for i in range(4)
        ]
        seen = {row["id"]: observed(passed=False) for row in rows}
        queued, settled = verify.select(rows, seen, cap=2)
        assert len(queued) == 2 and len(settled) == 2


class TestSettle:
    def test_a_rubric_alone_confirms_a_claim_that_needs_no_demonstration(self):
        row = finding(category="cleanliness", lens="cleanliness")
        assert verify.settle(row, observed(), None, {}, tier="none")["verdict"] == "CONFIRMED"

    def test_a_correctness_claim_with_no_proof_of_concept_is_demoted(self):
        settled = verify.settle(finding(), observed(), None, {}, tier="none")
        assert settled["verdict"] == "PLAUSIBLE"
        assert "no proof of concept" in settled["verify"]["reason"]

    def test_a_verifier_that_drops_a_claim_drops_it(self):
        report = {
            "verdict": "DROPPED",
            "reason": "the code does the opposite",
            "repro": None,
            "rubric": None,
        }
        settled = verify.settle(
            finding(), observed(passed=False), session(verification=report), {}, tier="none"
        )
        assert settled["verdict"] == "DROPPED"
        assert settled["verify"]["verifier"] == "codex"

    def test_a_verifier_session_that_produced_nothing_never_confirms(self):
        settled = verify.settle(
            finding(),
            observed(),
            session(ok=False, problems=["declared report is missing"]),
            {},
            tier="none",
        )
        assert settled["verdict"] == "PLAUSIBLE"
        assert "no usable report" in settled["verify"]["reason"]

    def test_a_claim_without_a_rubric_is_plausible_at_best(self):
        row = finding(category="design", lens="design", rubric=None)
        settled = verify.settle(
            row, observed(ran=False, passed=False, reason="none stated"), None, {}, tier="none"
        )
        assert settled["verdict"] == "PLAUSIBLE" and settled["unverifiable"] is True

    def test_an_unreadable_verification_report_parks_rather_than_counting(self, tmp_path):
        path = tmp_path / "verify-x.json"
        path.write_text("{not json")
        with pytest.raises(Park, match="unreadable"):
            verify._report(path, "x")
        path.write_text(
            json.dumps({"verification": "other", "verdict": "CONFIRMED", "reason": "r"})
        )
        with pytest.raises(Park, match="another finding"):
            verify._report(path, "x")
        path.write_text(json.dumps({"verification": "x", "verdict": "MAYBE", "reason": "r"}))
        with pytest.raises(Park, match="verdict must be"):
            verify._report(path, "x")
        path.write_text(json.dumps({"verification": "x", "verdict": "CONFIRMED", "reason": " "}))
        with pytest.raises(Park, match="states no reason"):
            verify._report(path, "x")

    def test_a_malformed_replacement_rubric_is_dropped_not_fatal(self, tmp_path):
        """The verdict and the reason decide; a sharper rubric is an optimisation.
        Measured 2026-09-11: one bad `expect` value parked an entire run."""
        path = tmp_path / "verify-x.json"
        path.write_text(
            json.dumps(
                {
                    "verification": "x",
                    "verdict": "CONFIRMED",
                    "reason": "it holds at a.py:3",
                    "repro": None,
                    "rubric": {"kind": "command", "run": "x", "expect": "hoping"},
                }
            )
        )
        report = verify._report(path, "x")
        assert report["verdict"] == "CONFIRMED"
        assert report["rubric"] is None
        assert "expect must be one of" in report["rejected_rubric"]

    def test_a_replacement_rubric_naming_a_scratch_file_is_dropped_and_recorded(self, tmp_path):
        """A session may write its demonstration under scratch/, but that worktree is
        removed at settle and rubrics execute against the shared tree. So a replacement
        that runs a scratch file cannot run at all - and a command that cannot run must
        never reach a verdict. Dropped and recorded, like any other bad replacement."""
        tree = tmp_path / "tree"
        (tree / "src").mkdir(parents=True)
        (tree / "src/app.py").write_text("x = 1\n")
        path = tmp_path / "verify-x.json"
        path.write_text(
            json.dumps(
                {
                    "verification": "x",
                    "verdict": "CONFIRMED",
                    "reason": "it holds at a.py:3",
                    "repro": "exit 1",
                    "rubric": {
                        "kind": "command",
                        "run": "sh scratch/repro-678dfdbdda79.sh",
                        "expect": "exit_nonzero",
                    },
                }
            )
        )
        report = verify._report(path, "x", str(tree))
        assert report["verdict"] == "CONFIRMED", "the verdict and the reason still decide"
        assert report["rubric"] is None
        assert "does not exist in the tree" in report["rejected_rubric"]

    def test_a_replacement_rubric_naming_a_real_path_survives(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "check.sh").write_text("exit 1\n")
        path = tmp_path / "verify-x.json"
        path.write_text(
            json.dumps(
                {
                    "verification": "x",
                    "verdict": "CONFIRMED",
                    "reason": "it holds at a.py:3",
                    "repro": None,
                    "rubric": {
                        "kind": "command",
                        "run": "sh check.sh",
                        "expect": "exit_nonzero",
                    },
                }
            )
        )
        report = verify._report(path, "x", str(tree))
        assert report["rubric"]["run"] == "sh check.sh"
        assert report["rejected_rubric"] is None

    def test_a_follow_up_is_reported_but_never_verified(self):
        row = finding(tags=["pre-existing"])
        result = verify.verify(
            [row],
            {},
            config.load(),
            _ledger(),
            {},
            tier="none",
            launch=lambda tasks: pytest.fail("a follow-up must not be verified"),
        )
        assert result["sessions"] == 0
        assert result["findings"][0]["verdict"] == "UNVERIFIED"


class _Ledger:
    directory = Path("/nonexistent")


def _ledger():
    return _Ledger()


class TestBlinding:
    def test_the_verifier_brief_never_carries_the_body_lens_or_producer(self):
        from review_pr import briefs

        side = {"number": 1, "tree": "/t", "base_tree": "/b", "reviewable_files": ["a.py"]}
        paths = {
            "diff": Path("/w/diff.patch"),
            "body": Path("/w/pr-body.md"),
            "files": Path("/w/files.txt"),
        }
        brief, _, _ = briefs.verifier(finding(), side, paths)
        assert "pr-body.md" not in brief
        assert "gating" not in brief.lower().split("## the claim")[0].replace("judging", "")
        assert "claude" not in brief.lower()
        assert "proof of concept" in brief.lower()


class TestWriteTargets:
    """Where a brief tells a model to write is the difference between a review and a
    session that exits clean having produced nothing. Measured on the first paid run:
    the brief named the shared tree, all seven sessions obeyed it, and every report
    landed where nothing collects it."""

    side: ClassVar[dict] = {
        "number": 1,
        "tree": "/w/tree",
        "base_tree": "/w/base",
        "reviewable_files": ["a.py"],
        "repo": "o/r",
    }
    paths: ClassVar[dict] = {
        "diff": Path("/w/inputs/diff.patch"),
        "body": Path("/w/inputs/pr-body.md"),
        "files": Path("/w/inputs/changed-files.txt"),
    }

    def briefs_for(self):
        from review_pr import briefs

        made = [
            briefs.reviewer(lens, self.side, self.paths)
            for lens in ("cleanliness", "design", "efficiency", "gating", "implementation")
        ]
        made.append(briefs.verifier(finding(), self.side, self.paths))
        made.append(briefs.claims(self.side, self.paths))
        return made

    def test_a_brief_that_names_the_shared_tree_is_refused(self):
        from review_pr import briefs

        with pytest.raises(Park, match="shared reviewed tree"):
            briefs.guard("write your report to /w/tree/reports/x.json", self.side)
        assert briefs.guard("write it to reports/x.json", self.side)


class TestAuthorityBriefs:
    """The implementation lens is told to extract each authority file's claims before
    it reads a hunk. The flat list it replaced was read as context and skipped, so the
    per-file directives are assembled in code and not left to the brief's prose."""

    side: ClassVar[dict] = {
        "number": 1,
        "tree": "/w/tree",
        "base_tree": "/w/base",
        "reviewable_files": ["a.py"],
        "repo": "o/r",
    }
    paths: ClassVar[dict] = {
        "diff": Path("/w/inputs/diff.patch"),
        "body": Path("/w/inputs/pr-body.md"),
        "files": Path("/w/inputs/changed-files.txt"),
    }

    def brief(self, lens, authority):
        from review_pr import briefs

        side = {**self.side, "authority_files": authority}
        return briefs.reviewer(lens, side, self.paths)[0]

    def test_every_authority_file_gets_its_own_addressed_block(self):
        found = ["GOVERNANCE.md", "docs/retention-policy.md", "STANDARDS.md"]
        brief = self.brief("implementation", found)
        for path in found:
            assert f"### `{path}`" in brief, f"{path} was named but not addressed"
        assert brief.count("Read this file whole before any hunk") == len(found)

    def test_extraction_is_ordered_before_the_hunk_audit(self):
        brief = self.brief("implementation", ["GOVERNANCE.md"])
        first = brief.index("### Phase 1")
        assert first < brief.index("### `GOVERNANCE.md`") < brief.index("### Phase 2")
        assert "quorums and numeric floors" in brief.lower()
        assert "carve-outs and invariants" in brief.lower()

    def test_a_repo_with_no_authority_files_still_audits_the_diff(self):
        """Nothing to extract must not read as nothing to check: the lens owns claim
        against implementation, and most repositories have no governance document."""
        brief = self.brief("implementation", [])
        assert "{{" not in brief
        assert "No authority file was found" in brief
        assert "Phase 2 runs anyway" in brief
        assert "###" not in brief.split("### Phase 1")[1].split("### Phase 2")[0]

    def test_the_lens_still_hunts_plain_code_defects(self):
        """The mandatory two-phase audit crowded correctness out: in the 2026-09-11 eval
        the lens named an off-by-one in its reasoning and dropped it as out of scope.
        No other lens a review runs hunts those, so the duty is pinned here."""
        brief = self.brief("implementation", ["GOVERNANCE.md"])
        assert "coequal duties" in brief
        assert "off-by-one" in brief

    def test_the_listed_versions_are_declared_to_be_the_base_branch_ones(self):
        """The pull request never supplies its own ground truth, and the brief has to
        say so: the head's copy of an authority file is a hunk, not an authority."""
        brief = self.brief("implementation", ["GOVERNANCE.md"])
        assert "BASE branch" in brief
        assert "hunks to audit" in brief

    def test_a_full_cap_of_long_paths_stays_inside_the_brief_cap(self):
        """AUTHORITY_CAP blocks times their size is what keeps this section under
        BRIEF_CAP; nothing else bounds it, so the two caps are pinned together."""
        from review_pr import briefs, checkout

        long = "docs/knowledge/decisions/" + "g" * 55 + ".md"
        brief = self.brief("implementation", [long] * checkout.AUTHORITY_CAP)
        assert len(brief) <= briefs.BRIEF_CAP

    def test_only_the_implementation_lens_carries_the_section(self):
        for lens in ("cleanliness", "design", "efficiency", "gating"):
            brief = self.brief(lens, ["GOVERNANCE.md"])
            assert "### `GOVERNANCE.md`" not in brief
            assert "{{" not in brief


class TestChangedFileSection:
    """What the list of files in scope costs the brief. It is the only section sized by
    the pull request rather than by the repository, and every brief carries it."""

    side: ClassVar[dict] = dict(TestAuthorityBriefs.side)
    paths: ClassVar[dict] = dict(TestAuthorityBriefs.paths)

    def test_a_pathological_changed_file_list_truncates_instead_of_parking(self):
        """The changed-file list is the only section that scales with the pull request,
        and the tool reviews arbitrary ones. A count cap said nothing about path length,
        so a wide enough change parked the brief before any lens launched."""
        from review_pr import briefs, checkout

        side = {
            **self.side,
            "reviewable_files": ["src/" + "d" * 60 + f"/module_{i}.py" for i in range(5000)],
            "authority_files": ["docs/knowledge/decisions/" + "g" * 55 + ".md"]
            * checkout.AUTHORITY_CAP,
        }
        brief = briefs.reviewer("implementation", side, self.paths)[0]
        assert len(brief) <= briefs.BRIEF_CAP
        marker = [line for line in brief.splitlines() if "list truncated" in line]
        assert len(marker) == 1, "a list cut short in silence reads as a complete one"
        assert str(self.paths["files"]) in marker[0], "the full list must stay reachable"

    def test_a_list_that_fits_is_never_truncated(self):
        from review_pr import briefs

        side = {**self.side, "reviewable_files": ["src/a.py", "src/b.py"]}
        brief = briefs.reviewer("implementation", side, self.paths)[0]
        assert "- `src/a.py`" in brief and "- `src/b.py`" in brief
        assert "list truncated" not in brief


class TestDualFamily:
    def row(self, file, line, producer, rubric=None, suggestion=None):
        return {
            "file": file,
            "line": line,
            "category": "design",
            "producer": producer,
            "rubric": rubric,
            "unverifiable": rubric is None,
            "suggestion": suggestion,
            "impact": "none",
        }

    def test_agreement_and_disagreement_are_counted_per_claim(self):
        result = dualfamily.diff_sets(
            {
                "claude": [self.row("a.py", 10, "claude"), self.row("b.py", 5, "claude")],
                "codex": [self.row("a.py", 12, "codex"), self.row("c.py", 1, "codex")],
            }
        )
        assert result["agreed"] == 1 and result["disagreed"] == 2
        agreed = next(r for r in result["findings"] if r["file"] == "a.py")
        assert agreed["agreement"] == ["claude", "codex"]

    def test_the_surviving_row_keeps_whatever_either_family_could_state(self):
        rubric = {"kind": "command", "run": "x", "expect": "exit_zero"}
        suggestion = {"line": 10, "replacement": "fixed"}
        result = dualfamily.diff_sets(
            {
                "claude": [self.row("a.py", 10, "claude")],
                "codex": [self.row("a.py", 10, "codex", rubric=rubric, suggestion=suggestion)],
            }
        )
        kept = result["findings"][0]
        assert kept["rubric"] == rubric and kept["unverifiable"] is False
        assert kept["suggestion"] == suggestion

    def test_one_family_is_a_legitimate_answer(self):
        result = dualfamily.diff_sets({"claude": [self.row("a.py", 1, "claude")]})
        assert result["agreed"] == 0 and result["findings"][0]["agreement"] == ["claude"]


class TestClaims:
    def test_shell_prompts_inside_fences_are_a_deterministic_floor(self):
        body = "Proof:\n\n```\n$ just check\ncheck: clean\n```\n"
        extracted = claims.extract(body)
        assert extracted[0]["run"] == "just check"
        assert extracted[0]["claimed_output"] == "check: clean"

    def test_a_claim_report_is_validated_at_the_boundary(self):
        with pytest.raises(Park, match="kind must be"):
            claims.normalize({"claims": [{"quote": "x", "kind": "vibes"}]})
        with pytest.raises(Park, match="expect must be"):
            claims.normalize(
                {"claims": [{"quote": "x", "kind": "command", "run": "x", "expect": "hoping"}]}
            )
        with pytest.raises(Park, match="must quote the body"):
            claims.normalize({"claims": [{"kind": "command", "run": "x"}]})
        with pytest.raises(Park, match="not a list"):
            claims.normalize({"claims": "everything passes"})

    def test_an_explicit_null_expect_takes_the_default(self):
        """Measured 2026-09-11 on the milestone run: the extractor filled every schema
        field, so its run-less number claims carried expect: null - and the boundary
        parked the whole run over a field nothing downstream could execute."""
        rows = claims.normalize(
            {
                "claims": [
                    {"quote": "four failures fixed", "kind": "number", "run": None, "expect": None},
                    {"quote": "$ x passes", "kind": "command", "run": "x", "expect": None},
                ]
            }
        )
        assert [row["expect"] for row in rows] == ["exit_zero", "exit_zero"]

    def test_a_blocked_network_refutes_nothing(self, tmp_path):
        """Measured 2026-09-11: sandboxed `uv run` dies downloading dependencies before
        the claimed check runs; that exit is environment, not the author over-claiming."""
        tree = tmp_path / "tree"
        tree.mkdir()
        rows = [
            {
                "id": "c1",
                "quote": "tests pass",
                "kind": "command",
                "run": "sh -c 'echo Network is unreachable >&2; exit 2'",
                "expect": "exit_zero",
                "contains": None,
                "claimed_output": None,
            }
        ]
        result = claims.check(rows, {"tree": str(tree)}, tier="none")
        assert result["mismatched"] == 0 and result["unchecked"] == 1
        assert result["claims"][0]["matched"] is None

    def test_a_body_whose_evidence_does_not_reproduce_is_a_finding(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        side = {"tree": str(tree)}
        rows = [
            {
                "id": "c1",
                "quote": "all tests pass",
                "kind": "command",
                "run": "echo 'Ran 3 tests'",
                "expect": "contains",
                "contains": "Ran 12 tests",
                "claimed_output": "Ran 12 tests",
            }
        ]
        result = claims.check(rows, side, tier="none")
        assert result["mismatched"] == 1 and result["reproduced"] == 0
        assert result["findings"][0]["category"] == "correctness"
        assert "permanent commit message" in result["findings"][0]["claim"]

    def test_a_command_that_cannot_run_here_refutes_nothing(self, tmp_path):
        """Measured on a paid replay: the body listed the tests it ran, the extractor
        made that `pytest ...`, the sandbox has no pytest, and exit 127 was reported as
        the author over-claiming."""
        tree = tmp_path / "tree"
        tree.mkdir()
        rows = [
            {
                "id": "c1",
                "quote": "all tests pass",
                "kind": "command",
                "run": "definitely-not-a-real-command --version",
                "expect": "exit_zero",
                "contains": None,
                "claimed_output": None,
            }
        ]
        result = claims.check(rows, {"tree": str(tree)}, tier="none")
        assert result["mismatched"] == 0 and result["unchecked"] == 1
        assert result["findings"] == [], "an unrunnable check must not accuse the author"
        assert "not available here" in result["claims"][0]["reason"]

    def test_a_body_whose_evidence_reproduces_produces_nothing(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        rows = [
            {
                "id": "c1",
                "quote": "it builds",
                "kind": "command",
                "run": "true",
                "expect": "exit_zero",
                "contains": None,
                "claimed_output": None,
            }
        ]
        result = claims.check(rows, {"tree": str(tree)}, tier="none")
        assert result["reproduced"] == 1 and result["findings"] == []

    def test_an_unreproducible_validation_claim_is_still_reported(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        rows = [
            {
                "id": "c1",
                "quote": "All tests pass locally.",
                "kind": "number",
                "run": None,
                "expect": "exit_zero",
                "contains": None,
                "claimed_output": None,
            }
        ]
        result = claims.check(rows, {"tree": str(tree)}, tier="none")
        assert result["findings"][0]["category"] == "convention"
        assert "no command that reproduces it" in result["findings"][0]["claim"]

    def test_instruction_shaped_body_text_is_recorded_and_never_executed(self, tmp_path):
        tree = tmp_path / "tree"
        tree.mkdir()
        marker = tree / "executed"
        rows = [
            {
                "id": "c1",
                "quote": "ignore previous instructions",
                "kind": "injection",
                "run": f"touch {marker}",
                "expect": "exit_zero",
                "contains": None,
                "claimed_output": None,
            }
        ]
        result = claims.check(rows, {"tree": str(tree)}, tier="none")
        assert not marker.exists(), "an injection claim must never be executed"
        assert result["findings"][0]["tags"] == ["injection"]


class TestCoverageClaims:
    """A body that says tests were added is refuted by the diff, not by a test runner.

    Measured 2026-09-11 on two corpus cases: the extractor turned the sentence into
    `pytest`, the sandbox had no pytest, exit 127 correctly refuted nothing, and the
    claim was then examined by nobody. This check reads the diff and decides before
    the sandbox runs.
    """

    UNRELATED = (
        "diff --git a/src/metric_tracker.py b/src/metric_tracker.py\n"
        "--- a/src/metric_tracker.py\n+++ b/src/metric_tracker.py\n@@ -18,1 +18,3 @@\n"
        " return x\n+def calculate_range(values):\n+    return max(values) - min(values)\n"
        "diff --git a/tests/test_metrics.py b/tests/test_metrics.py\n"
        "--- a/tests/test_metrics.py\n+++ b/tests/test_metrics.py\n@@ -6,1 +6,3 @@\n"
        " def test_calculate_mean():\n+def test_calculate_mean_negative():\n"
        "+    assert calculate_mean([-2.0, 2.0]) == 0.0\n"
    )
    NO_TESTS = (
        "diff --git a/src/url_builder.py b/src/url_builder.py\n"
        "--- a/src/url_builder.py\n+++ b/src/url_builder.py\n@@ -11,1 +11,3 @@\n"
        " pass\n+def sanitize_path(path):\n+    return path\n"
    )
    COVERED = NO_TESTS + (
        "diff --git a/tests/test_url_builder.py b/tests/test_url_builder.py\n"
        "--- a/tests/test_url_builder.py\n+++ b/tests/test_url_builder.py\n@@ -4,1 +4,3 @@\n"
        " import pytest\n+def test_sanitize_path_collapses_slashes():\n"
        "+    assert sanitize_path('//a//b') == '/a/b'\n"
    )

    def claim(self, quote, run=None):
        return {
            "id": "c1",
            "quote": quote,
            "kind": "command" if run else "number",
            "run": run,
            "expect": "exit_zero",
            "contains": None,
            "claimed_output": None,
        }

    def run(self, tmp_path, quote, diff, run=None):
        tree = tmp_path / "tree"
        tree.mkdir()
        return claims.check([self.claim(quote, run)], {"tree": str(tree)}, tier="none", diff=diff)

    def test_a_subject_no_added_test_mentions_is_a_finding(self, tmp_path):
        """The diff does change a test file - just not one that touches the subject."""
        result = self.run(
            tmp_path,
            "Ran pytest suite: 100% passing including new unit tests covering "
            "`calculate_range` for positive, negative, and empty lists.",
            self.UNRELATED,
            run="definitely-not-a-real-command",
        )
        assert result["unchecked"] == 1, "the sandbox leg is unchanged and still refutes nothing"
        assert len(result["findings"]) == 1
        finding = result["findings"][0]
        assert finding["category"] == "correctness" and finding["scope"] == "meta"
        assert "calculate_range" in finding["claim"] + finding["evidence"]

    def test_a_named_test_file_the_diff_never_touches_is_a_finding(self, tmp_path):
        result = self.run(
            tmp_path,
            "All unit tests in `tests/test_url_builder.py` pass, including new coverage "
            "for `sanitize_path` edge cases.",
            self.NO_TESTS,
        )
        assert len(result["findings"]) == 1
        assert "tests/test_url_builder.py" in result["findings"][0]["claim"]

    def test_a_claim_the_diff_backs_up_produces_nothing(self, tmp_path):
        result = self.run(
            tmp_path,
            "All unit tests in `tests/test_url_builder.py` pass, including new coverage "
            "for `sanitize_path` edge cases.",
            self.COVERED,
        )
        assert result["findings"] == []

    def test_with_no_diff_to_read_the_check_accuses_nobody(self, tmp_path):
        """The control leg: this check has not run, and one that cannot run refutes
        nothing - an absent diff is not evidence that a test is absent."""
        result = self.run(tmp_path, "Adds new tests for `sanitize_path`.", "")
        assert result["findings"] == []


class TestAgreementSettles:
    """Cross-family agreement is the second reading of a two-sided claim - the field
    used to be computed, written to the ledger, and read by nothing that decided."""

    def two_sided(self, **over):
        row = finding(
            lens="implementation",
            category="correctness",
            rubric={"kind": "grep", "expect": "empty", "pattern": "old_name", "path": "."},
            **over,
        )
        return row

    def test_a_two_family_claim_with_a_passing_rubric_settles_without_a_session(self):
        row = {**self.two_sided(), "agreement": ["claude", "codex"]}
        queued, settled = verify.select([row], {row["id"]: observed(passed=True)}, cap=10)
        assert queued == [] and settled == [row]
        done = verify.settle(row, observed(passed=True), None, {}, tier="none")
        assert done["verdict"] == "CONFIRMED"
        assert "two families" in done["verify"]["reason"]

    def test_a_single_family_claim_still_queues_even_with_a_passing_rubric(self):
        row = {**self.two_sided(), "agreement": ["claude"]}
        queued, settled = verify.select([row], {row["id"]: observed(passed=True)}, cap=10)
        assert queued == [row] and settled == []
        done = verify.settle(row, observed(passed=True), None, {}, tier="none")
        assert done["verdict"] == "PLAUSIBLE"

    def test_agreement_never_substitutes_for_a_proof_of_concept(self):
        row = {
            **finding(lens="gating", category="correctness"),
            "agreement": ["claude", "codex"],
        }
        queued, _settled = verify.select([row], {row["id"]: observed(passed=True)}, cap=10)
        assert queued == [row], "a PoC class always queues: agreement is opinions, not a demo"

    def test_a_verifier_that_did_not_confirm_is_never_overridden_by_the_rubric(self):
        """The rubric reaches only the implementation half of a two-sided claim, so a
        passing rubric plus a verifier's PLAUSIBLE settles PLAUSIBLE, not CONFIRMED."""
        row = {**self.two_sided(), "agreement": ["claude"]}
        report = {
            "verdict": "PLAUSIBLE",
            "reason": "the claim side did not hold up",
            "repro": None,
            "rubric": None,
            "rejected_rubric": None,
        }
        done = verify.settle(
            row, observed(passed=True), session(verification=report), {}, tier="none"
        )
        assert done["verdict"] == "PLAUSIBLE"
        assert "did not confirm the claim side" in done["verify"]["reason"]

    def test_a_verifier_confirmation_with_a_passing_rubric_confirms(self):
        row = {**self.two_sided(), "agreement": ["claude"]}
        report = {
            "verdict": "CONFIRMED",
            "reason": "the claim holds against the code",
            "repro": None,
            "rubric": None,
            "rejected_rubric": None,
        }
        done = verify.settle(
            row, observed(passed=True), session(verification=report), {}, tier="none"
        )
        assert done["verdict"] == "CONFIRMED"

    def test_contested_claims_outrank_agreed_ones_in_the_queue(self):
        alone = {**self.two_sided(claim="One family made this claim."), "agreement": ["claude"]}
        both = {
            **self.two_sided(claim="Two families made this claim."),
            "agreement": ["claude", "codex"],
        }
        assert verify.priority(alone) < verify.priority(both)


class TestFamilySwap:
    """One knob moves a whole run onto one declared family.

    Swapping used to mean authoring another near-copy of stages.yaml. The law that does
    not move with it: a finding is verified by a family other than its producer's.
    """

    def test_the_override_reroutes_every_lens_and_the_claims_role(self):
        from review_pr import pipeline

        plan = config.override_family(config.load(), "gemini")
        for lens in config.active_lenses(plan):
            spec = config.lens_spec(plan, lens)
            assert spec["family"] == "gemini"
            assert spec["model"].startswith("gemini-"), "a swapped lens must not keep the old model"
            assert pipeline.lens_families(plan, lens, {"family": "codex"}) == [
                ("gemini", "the whole-run --family gemini override")
            ]
        assert config.role_spec(plan, "claims")["family"] == "gemini"
        assert plan["dual_family"]["enabled"] is False
        assert plan["routing"]["reroute_lenses"] == []

    def test_the_swapped_run_is_still_verified_by_another_family(self):
        plan = config.override_family(config.load(), "gemini")
        family, _ = verify.opposite(plan, "gemini")
        assert family != "gemini"
        assert config.role_spec(plan, "verifier", family=family)["family"] == family

    def test_a_family_the_registry_alone_declares_can_run_the_whole_review(self):
        """The acceptance test for a new lane: a `families:` entry plus a verifier
        model, and nothing else - no fourth template, no Python."""
        plan = config.load()
        plan["families"]["pi"] = {"transport": "acp", "adapter_argv": ["pi-acp-server"]}
        plan["roles"]["verifier"]["models"]["pi"] = "pi-1"
        swapped = config.override_family(plan, "pi")
        for lens in config.active_lenses(swapped):
            spec = config.lens_spec(swapped, lens)
            assert (spec["family"], spec["model"]) == ("pi", "pi-1")
            assert spec["adapter_argv"] == ["pi-acp-server"]
        assert verify.opposite(swapped, "pi")[0] != "pi"
        assert "pi" in readiness.routed(swapped), "its adapter must block readiness now"

    def test_a_family_with_no_model_declared_parks_before_anything_spawns(self):
        """Never the previous family's model: that launches gpt-5.6-sol on the gemini
        adapter, which is a silent wrong answer rather than a refusal."""
        plan = config.load()
        plan["families"]["pi"] = {"transport": "acp", "adapter_argv": ["pi-acp-server"]}
        with pytest.raises(Park, match="no model for family pi"):
            config.override_family(plan, "pi")
        with pytest.raises(Park, match="no model for family pi"):
            config.lens_spec(plan, "design", family="pi")

    def test_the_override_refuses_a_family_a_lens_forbids(self):
        with pytest.raises(Park, match="must never run on codex"):
            config.override_family(config.load(), "codex")

    def test_the_override_refuses_an_undeclared_family(self):
        with pytest.raises(Park, match="not declared by this template"):
            config.override_family(config.load(), "pi")

    def test_a_verifier_only_family_still_blocks_readiness(self):
        """A one-family template declares its verifier on a family no lens names. An
        unresolvable adapter there is otherwise found after every lens has been paid."""
        plan = config.load(config.TEMPLATES / "stages-fast.yaml")
        assert {plan["lenses"][lens]["family"] for lens in config.active_lenses(plan)} == {"claude"}
        assert readiness.routed(plan) == {"claude", "codex"}

    @pytest.mark.parametrize(
        "mutate,message",
        [
            (lambda d: d["routing"].update(opposite={"claude": "claude"}), "with claude itself"),
            (lambda d: d["routing"].update(opposite={"claude": "pi"}), "undeclared family"),
            (lambda d: d["roles"]["verifier"]["models"].pop("codex"), "which has no model"),
        ],
    )
    def test_a_routing_table_that_cannot_be_honoured_parks_at_load(self, tmp_path, mutate, message):
        """These used to pass validation and fail a whole stage later, inside the
        session launcher, with a KeyError."""
        import yaml

        data = config.load()
        mutate(data)
        path = tmp_path / "stages.yaml"
        path.write_text(yaml.safe_dump(data))
        with pytest.raises(Park, match=message):
            config.load(path)


class TestActiveLenses:
    def test_the_shipped_template_parks_cleanliness_and_efficiency(self):
        plan = config.load()
        active = config.active_lenses(plan)
        assert active == ("design", "gating", "implementation")

    def test_a_parked_lens_is_reenabled_with_one_line(self):
        plan = config.load()
        plan["lenses"]["cleanliness"]["enabled"] = True
        assert "cleanliness" in config.active_lenses(plan)


class TestStageProducts:
    def test_a_product_computes_once_and_rereads_forever(self, tmp_path):
        from review_pr import pipeline

        calls = []

        def compute():
            calls.append(1)
            return {"result": 42}

        first = pipeline._product(tmp_path, "stage0-lint", compute)
        second = pipeline._product(tmp_path, "stage0-lint", compute)
        assert first == second == {"result": 42}
        assert len(calls) == 1, "a completed stage is re-read, never re-executed"
        assert (tmp_path / "products" / "stage0-lint.json").is_file()
