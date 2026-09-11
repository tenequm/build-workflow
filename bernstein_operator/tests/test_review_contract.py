"""The findings contract, the diff index, anchors, and the verdict table.

Nothing here spawns a model: this is the deterministic spine, and it is tested cold.
"""

from __future__ import annotations

import pytest
from operator_driver.storage import Park
from review_pr import anchors, diffindex, findings, verdictcalc

DIFF = """diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,6 +10,8 @@ def handler(request):
     validate(request)
-    charge(request)
+    receipt = charge(request)
+    audit(receipt)
     return receipt
@@ -40,3 +42,4 @@ def other():
     pass
+    # added
diff --git a/pnpm-lock.yaml b/pnpm-lock.yaml
index 3333333..4444444 100644
--- a/pnpm-lock.yaml
+++ b/pnpm-lock.yaml
@@ -1,2 +1,3 @@
 lockfileVersion: 9
+  added: true
diff --git a/tests/test_app.py b/tests/test_app.py
new file mode 100644
index 0000000..5555555
--- /dev/null
+++ b/tests/test_app.py
@@ -0,0 +1,3 @@
+def test_handler():
+    assert True
+
diff --git a/old.py b/old.py
deleted file mode 100644
index 6666666..0000000
--- a/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-gone = 1
-also = 2
"""


def finding(**over):
    base = {
        "file": "src/app.py",
        "line": 12,
        "category": "correctness",
        "claim": "The charge runs before its gate.",
        "evidence": "src/app.py:12 charge()",
    }
    return findings.normalize(
        {**base, **over}, lens=over.pop("lens", "gating"), producer=over.pop("producer", "claude")
    )


class TestFindingsSchema:
    def test_a_finding_without_a_rubric_is_marked_unverifiable(self):
        assert finding(rubric=None)["unverifiable"] is True
        checked = finding(
            rubric={"kind": "grep", "pattern": "charge", "path": "src", "expect": "nonempty"}
        )
        assert checked["unverifiable"] is False

    @pytest.mark.parametrize(
        "rubric",
        [
            {"kind": "wishing", "expect": "exit_zero"},
            {"kind": "command", "expect": "hoping", "run": "x"},
            {"kind": "command", "expect": "contains", "run": "x"},
            {"kind": "grep", "pattern": "x", "expect": "exit_zero"},
            {"kind": "revert_test", "test": "x", "hunk": "src/app.py", "expect": "exit_nonzero"},
            {"kind": "revert_test", "test": "x", "hunk": "src/app.py:1-2", "expect": "exit_zero"},
        ],
    )
    def test_a_rubric_that_cannot_be_executed_is_refused(self, rubric):
        with pytest.raises(Park):
            finding(rubric=rubric)

    def test_a_revert_test_rubric_must_name_a_hunk_and_expect_a_flip(self):
        ok = finding(
            rubric={
                "kind": "revert_test",
                "test": "pytest",
                "hunk": "src/app.py:10-12",
                "expect": "exit_nonzero",
            }
        )
        assert ok["rubric"]["hunk"] == "src/app.py:10-12"

    def test_a_claim_must_be_a_sentence_and_a_path_must_be_relative(self):
        with pytest.raises(Park, match="sentence"):
            finding(claim="bug")
        with pytest.raises(Park, match="relative"):
            finding(file="/etc/passwd")
        with pytest.raises(Park, match="relative"):
            finding(file="../outside.py")

    def test_a_meta_finding_names_a_known_surface(self):
        assert finding(scope="meta", file="PR:body")["scope"] == "meta"
        with pytest.raises(Park, match="PR:<part>"):
            finding(scope="meta", file="somewhere")

    def test_a_credential_is_named_and_never_reproduced(self):
        assert findings.redact("token ghp_abcdefghijklmnopqrst here") == "token ghp_**** here"
        assert (
            "AKIAABCDEFGH1234"
            not in finding(claim="The key AKIAABCDEFGH1234 is hardcoded.", evidence="x y z")[
                "claim"
            ]
        )

    def test_a_suggestion_stays_small_enough_to_stage(self):
        with pytest.raises(Park, match="12 replacement lines"):
            finding(suggestion={"line": 12, "replacement": "\n".join("x" * 13)})
        with pytest.raises(Park, match="start_line"):
            finding(suggestion={"start_line": 9, "line": 5, "replacement": "x"})

    def test_merging_keeps_the_rubric_and_the_strongest_impact(self):
        weak = finding(lens="cleanliness", producer="codex", tags=["pre-existing"])
        strong = finding(
            rubric={"kind": "command", "run": "x", "expect": "exit_zero"}, impact="irreversible"
        )
        merged = findings.merge([weak, strong])
        assert len(merged) == 1
        assert merged[0]["rubric"] is not None and merged[0]["unverifiable"] is False
        assert merged[0]["impact"] == "irreversible"
        assert merged[0]["follow_up"] is False

    def test_a_finding_this_workflow_produced_needs_no_proof_of_concept(self):
        assert findings.needs_poc(finding(producer="script")) is False
        assert findings.needs_poc(finding(producer="claude")) is True
        settled = findings.presettle(finding(producer="script"), "the grep matched")
        assert settled["verdict"] == "CONFIRMED"


class TestDiffIndex:
    def test_hunks_new_files_and_deletions_are_read_correctly(self):
        files = diffindex.parse(DIFF)
        assert set(files) == {"src/app.py", "pnpm-lock.yaml", "tests/test_app.py", "old.py"}
        assert files["tests/test_app.py"].new_file is True
        assert files["old.py"].deleted is True
        assert [(h.start, h.end) for h in files["src/app.py"].hunks] == [(10, 17), (42, 45)]

    def test_generated_outputs_are_not_authored_code(self):
        reviewable = diffindex.reviewable(diffindex.parse(DIFF))
        assert "pnpm-lock.yaml" not in reviewable
        assert diffindex.excluded("a/b/Cargo.lock") and diffindex.excluded("x.snap")
        assert not diffindex.excluded("src/app.py")

    def test_test_paths_are_recognised_for_the_fail_on_base_check(self):
        assert diffindex.test_paths(diffindex.reviewable(diffindex.parse(DIFF))) == [
            "tests/test_app.py"
        ]


class TestAnchors:
    def test_a_deliberately_misanchored_finding_is_caught_by_the_script(self):
        """GitHub rejects a whole review atomically on one bad anchor - catch it here."""
        files = diffindex.reviewable(diffindex.parse(DIFF))
        good = finding(line=12)
        outside_a_hunk = finding(line=300, claim="This line is nowhere near a hunk.")
        absent_file = finding(file="src/never.py", claim="This file is not in the diff.")
        deleted = finding(file="old.py", line=1, claim="This file is deleted by the change.")
        problems = anchors.violations([good, outside_a_hunk, absent_file, deleted], files)
        assert {p["reason"] for p in problems} == {
            "line does not sit inside a diff hunk",
            "file is not in this pull request's diff",
            "file is deleted by this pull request",
        }
        assert [
            f["id"] for f in anchors.anchored([good, outside_a_hunk, absent_file, deleted], files)
        ] == [good["id"]]

    def test_a_new_file_anchors_anywhere_and_a_meta_finding_never_anchors(self):
        files = diffindex.reviewable(diffindex.parse(DIFF))
        assert files["tests/test_app.py"].anchorable(3) is True
        assert files["src/app.py"].anchorable(41) is False
        meta = finding(scope="meta", file="PR:body", line=1)
        assert anchors.violations([meta], files) == []
        assert anchors.anchored([meta], files) == []

    def test_a_multi_line_anchor_checks_both_ends(self):
        files = diffindex.reviewable(diffindex.parse(DIFF))
        straddling = finding(start_line=5, line=12, claim="This range starts outside a hunk.")
        assert any(
            p["reason"].startswith("start_line") for p in anchors.violations([straddling], files)
        )


class TestVerdictTable:
    def graded(self, **over):
        return {
            "id": "x",
            "file": "a",
            "line": 1,
            "follow_up": False,
            "unverifiable": False,
            "category": "correctness",
            "lens": "gating",
            "impact": "none",
            "verdict": "CONFIRMED",
            **over,
        }

    def test_the_strictest_surviving_finding_decides(self):
        assert verdictcalc.verdict([self.graded(impact="security")]) == "request-changes"
        assert verdictcalc.verdict([self.graded()]) == "comment-only"
        assert verdictcalc.verdict([self.graded(verdict="PLAUSIBLE")]) == "comment-only"
        assert (
            verdictcalc.verdict([self.graded(category="cleanliness", lens="cleanliness")])
            == "approve-with-comments"
        )
        assert verdictcalc.verdict([]) == "approve"

    def test_follow_ups_and_dropped_findings_never_enter_the_verdict(self):
        assert verdictcalc.verdict([self.graded(follow_up=True, impact="security")]) == "approve"
        assert verdictcalc.verdict([self.graded(verdict="DROPPED", impact="security")]) == "approve"

    def test_an_unverifiable_finding_can_never_block_a_merge(self):
        assert (
            verdictcalc.verdict([self.graded(unverifiable=True, impact="security")])
            == "approve-with-comments"
        )

    def test_a_convention_finding_asks_for_a_commit_but_is_never_severe(self):
        convention = self.graded(category="convention", lens="house-rules", impact="security")
        assert verdictcalc.severity(convention) == "BLOCKING_FIX"
        assert verdictcalc.verdict([convention]) == "comment-only"

    def test_the_state_gate_is_reached_only_from_state(self):
        for state in (
            {"isDraft": True},
            {"state": "MERGED"},
            {"state": "CLOSED"},
            {"withdrawn": True},
        ):
            assert verdictcalc.verdict([self.graded()], state) == "skip"
        assert verdictcalc.verdict([self.graded()], {"state": "OPEN"}) == "comment-only"

    def test_an_unverified_finding_cannot_reach_synthesis(self):
        with pytest.raises(Park, match="unverified"):
            verdictcalc.severity(self.graded(verdict="UNVERIFIED"))
        assert verdictcalc.severity(self.graded(verdict="UNVERIFIED", follow_up=True)) is None

    def test_an_approve_whose_comments_ask_for_changes_is_inconsistent(self):
        assert verdictcalc.consistency(
            "approve-with-comments", [{"path": "a", "line": 1, "body": "Fix before merge."}]
        )
        assert (
            verdictcalc.consistency(
                "comment-only", [{"path": "a", "line": 1, "body": "Fix before merge."}]
            )
            == []
        )

    def test_split_orders_asks_by_severity(self):
        rows = [
            self.graded(id="s", category="cleanliness", lens="cleanliness"),
            self.graded(id="b", impact="data_loss"),
            self.graded(id="f", follow_up=True),
        ]
        asks, follow = verdictcalc.split(rows)
        assert [row["id"] for row in asks] == ["b", "s"]
        assert [row["id"] for row in follow] == ["f"]
