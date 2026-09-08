import json

import pytest
from operator_driver.ceremony import reaction
from operator_driver.verdict import parse_verdict


@pytest.mark.parametrize("certain", ["missing", True, -1])
def test_do_not_merge_remains_terminal_even_with_malformed_json(tmp_path, certain):
    review = tmp_path / "blind-review.md"
    review.write_text("No defects.\nCertain: 0\nPlausible: 0\nVerdict: merge as-is\n")
    review.with_name("verdict.json").write_text(
        json.dumps(
            {
                "verdict": "do not merge",
                "certain": certain,
                "plausible": 0,
                "evidence": [],
            }
        )
    )
    assert reaction(parse_verdict(review)) == "park"


def test_disagreement_rejudges_once_and_cannot_accept_stale_json(tmp_path):
    review = tmp_path / "blind-review.md"
    review.write_text(
        "Defect at src/a.py:1\nCertain: 1\nPlausible: 0\nVerdict: merge after listed fixes\n"
    )
    review.with_name("verdict.json").write_text(
        json.dumps(
            {
                "verdict": "merge as-is",
                "certain": 0,
                "plausible": 0,
                "evidence": [],
            }
        )
    )
    verdict = parse_verdict(review)
    assert reaction(verdict) == "rejudge"
    assert reaction(verdict, 1) == "park"
