"""Anchored verdict parsing, refusal receipts, and glob-overlap semantics."""
from pathlib import Path

from bernstein_herdr import ledger
from bernstein_herdr.judge import parse_verdict


def _write(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "blind-review.md"
    f.write_text(body)
    return f


def test_wellformed_review_routes(tmp_path):
    v = parse_verdict(_write(tmp_path, "prose about certain things\n\nCertain: 2\nPlausible: 1\nVerdict: merge after listed fixes\n"))
    assert v == {"review_present": True, "verdict": "merge after listed fixes", "certain": 2,
                 "plausible": 1, "counts_declared": True, "do_not_merge": False,
                 "merge_as_is": False, "block": False}


def test_do_not_merge_blocks(tmp_path):
    v = parse_verdict(_write(tmp_path, "Certain: 1\nPlausible: 0\nVerdict: do not merge\n"))
    assert v["block"] and v["do_not_merge"]


def test_verdict_outside_last_three_lines_blocks(tmp_path):
    v = parse_verdict(_write(tmp_path, "Verdict: merge as-is\nCertain: 0\nPlausible: 0\nlate discussion\nmore prose\nfinal words\n"))
    assert v["block"] and not v["counts_declared"] and "last three lines" in v["reason"]


def test_duplicate_counts_block(tmp_path):
    v = parse_verdict(_write(tmp_path, "Certain: 3\nnotes\nCertain: 0\nPlausible: 0\nVerdict: merge as-is\n"))
    assert v["block"] and "2 `Certain:` lines" in v["reason"]


def test_prose_words_do_not_count(tmp_path):
    body = "No defect, certain or plausible, is attributable to this diff.\n\nCertain: 0\nPlausible: 0\nVerdict: merge as-is\n"
    v = parse_verdict(_write(tmp_path, body))
    assert v["certain"] == 0 and v["counts_declared"] and not v["block"]


def test_missing_review_blocks(tmp_path):
    v = parse_verdict(tmp_path / "absent.md")
    assert v["block"] and v["verdict"] == "missing"


def test_report_claims_refusal(tmp_path):
    r = tmp_path / "report.md"
    r.write_text("## Report\n\nblocked_on_dependency: the judge must be re-run\n")
    assert ledger.report_claims(r)["refusal"] == "blocked_on_dependency"
    r.write_text("## Report\n\nall DONE\n## Deviations\n\nnone\n")
    assert ledger.report_claims(r)["refusal"] is None


def test_glob_overlap_predicate():
    from bernstein_herdr.ready import globs_overlap

    assert globs_overlap("src/*/x", "src/a/*")
    assert globs_overlap("pkg/core/**", "pkg/core/engine/facts.go")
    assert globs_overlap("a/b/**", "a/b/c/*.go")
    assert not globs_overlap("internal/adapter/**", "internal/adapters/**")
    assert not globs_overlap("a/b.go", "a/c.go")
    # an empty literal prefix proves nothing: these must NOT overlap everything
    assert not globs_overlap("*.go", "docs/**")
    assert not globs_overlap("**/testdata/**", "internal/api/api.go")
    assert globs_overlap("x.go", "x.go")


def test_fenced_declarations_do_not_count(tmp_path):
    body = (
        "The required format is:\n\n```\nCertain: <n>\nPlausible: <n>\nVerdict: ...\n```\n\n"
        "and a diff hunk:\n\n```\n+Certain: 9\n```\n\n"
        "Certain: 1\nPlausible: 0\nVerdict: merge after listed fixes\n"
    )
    f = tmp_path / "blind-review.md"
    f.write_text(body)
    v = parse_verdict(f)
    assert v["counts_declared"] and v["certain"] == 1 and not v["block"]


def test_refusal_prose_mention_is_not_a_receipt(tmp_path):
    r = tmp_path / "report.md"
    r.write_text("## Deviations\n\nNothing was underspecified; item 2 built the smallest faithful shape.\n")
    assert ledger.report_claims(r)["refusal"] is None
    r.write_text("## Report\n\n- scope_exceeded: item 3 needs files outside the allowlist\n")
    assert ledger.report_claims(r)["refusal"] == "scope_exceeded"
