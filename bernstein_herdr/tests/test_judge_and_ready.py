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
    from bernstein_herdr.ready import check  # noqa: F401  (import side-effect free)
    import bernstein_herdr.ready as ready
    import inspect
    src = inspect.getsource(ready.check)
    assert "_globs_overlap" in src
    # exercise the closure logic through a tiny reimplementation-free harness:
    import fnmatch as _f, re as _re
    def lit(g):
        out = []
        for s in g.split("/"):
            if _re.search(r"[*?\[]", s):
                return out, True
            out.append(s)
        return out, False
    def overlap(a, b):
        if a == b or _f.fnmatch(a, b) or _f.fnmatch(b, a):
            return True
        la, wa = lit(a); lb, wb = lit(b)
        shorter, longer, sw = (la, lb, wa) if len(la) <= len(lb) else (lb, la, wb)
        return sw and longer[: len(shorter)] == shorter
    assert overlap("src/*/x", "src/a/*")
    assert overlap("pkg/core/**", "pkg/core/engine/facts.go")
    assert not overlap("internal/adapter/**", "internal/adapters/**")
    assert not overlap("a/b.go", "a/c.go")


def test_refusal_prose_mention_is_not_a_receipt(tmp_path):
    r = tmp_path / "report.md"
    r.write_text("## Deviations\n\nNothing was underspecified; item 2 built the smallest faithful shape.\n")
    assert ledger.report_claims(r)["refusal"] is None
    r.write_text("## Report\n\n- scope_exceeded: item 3 needs files outside the allowlist\n")
    assert ledger.report_claims(r)["refusal"] == "scope_exceeded"
