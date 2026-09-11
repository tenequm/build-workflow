"""Tests for pondcost token accounting and cost calculation with rate registry.

Verifies per-harness SQL dispatch, Anthropic deduplication and model normalization,
Codex cache subset semantics and OpenAI pricing, agy summation and Google model
effort-suffix normalization, registry missing/malformed resilience, and totals aggregation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from review_pr.pondcost import METHOD_TEXT, usage

REGISTRY_FIXTURE_DATA = {
    "providers": {
        "anthropic": {
            "claude-fable-5": {
                "input": 10.0,
                "output": 50.0,
                "cache_read": 1.0,
                "cache_write_5m": 12.5,
                "cache_write_1h": 20.0,
            },
            "claude-opus-5": {
                "input": 5.0,
                "output": 25.0,
                "cache_read": 0.5,
                "cache_write_5m": 6.25,
                "cache_write_1h": 10.0,
            },
            "claude-opus-4-8": {
                "input": 5.0,
                "output": 25.0,
                "cache_read": 0.5,
                "cache_write_5m": 6.25,
                "cache_write_1h": 10.0,
            },
            "claude-sonnet-5": {
                "input": 2.0,
                "output": 10.0,
                "cache_read": 0.2,
                "cache_write_5m": 2.5,
                "cache_write_1h": 4.0,
            },
            "claude-haiku-4-5": {
                "input": 1.0,
                "output": 5.0,
                "cache_read": 0.1,
                "cache_write_5m": 1.25,
                "cache_write_1h": 2.0,
            },
        },
        "openai": {
            "gpt-5.6": {"input": 4.0, "output": 20.0, "cache_read": 0.4},
            "gpt-5.6-sol": {"input": 4.0, "output": 20.0, "cache_read": 0.4},
            "gpt-5.6-terra": {"input": 2.0, "output": 12.0, "cache_read": 0.2},
            "gpt-5.6-luna": {"input": 0.2, "output": 1.2, "cache_read": 0.02},
        },
        "google": {
            "gemini-3.7-flash": {"input": 0.75, "output": 3.75, "cache_read": 0.075},
            "gemini-3.8-flash": {"input": 0.75, "output": 3.75, "cache_read": 0.075},
        },
    }
}


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    """Create a temporary rate registry JSON file for test isolation."""
    reg_file = tmp_path / "registry.json"
    reg_file.write_text(json.dumps(REGISTRY_FIXTURE_DATA), encoding="utf-8")
    return reg_file


def make_fake_runner(responses: dict[str, tuple[int, bytes, bytes]]) -> Any:
    """Construct a fake run callable that dispatches on SQL substrings."""
    calls: list[list[str]] = []

    def fake_run(argv: list[str], cwd: Path, timeout: float = 120.0) -> tuple[int, bytes, bytes]:
        calls.append(argv)
        sql = argv[-1] if argv else ""
        for pattern, response in responses.items():
            if pattern in sql:
                return response
        return 0, b"", b""

    fake_run.calls = calls  # type: ignore[attr-defined]
    return fake_run


def test_anthropic_session_priced_hand_computed(registry_path: Path) -> None:
    """Anthropic session with claude-sonnet-5 must match hand-computed USD list price.

    Rates for claude-sonnet-5:
    - Input: $2.00 / Mtok
    - Output: $10.00 / Mtok
    - Cache read: $0.20 / Mtok
    - Cache write 5m: $2.50 / Mtok
    - Cache write 1h: $4.00 / Mtok

    Tokens:
    - 1,000,000 input -> $2.00
    - 500,000 output -> $5.00
    - 2,000,000 cache read -> $0.40
    - 100,000 cache write 5m -> $0.25
    - 50,000 cache write 1h -> $0.20
    Expected sum: $7.85 exactly.
    """
    row = {
        "turn_id": "msg_sonnet_001",
        "model": "claude-sonnet-5",
        "input_tokens": 1_000_000,
        "output_tokens": 500_000,
        "cache_read": 2_000_000,
        "cache_write_5m": 100_000,
        "cache_write_1h": 50_000,
    }
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-sonnet'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-sonnet", "source_agent": "claude-code"}]
    result = usage(sessions, registry=registry_path, run=runner)

    assert result["method"] == METHOD_TEXT
    assert len(result["sessions"]) == 1

    sess = result["sessions"][0]
    assert sess["session_id"] == "sess-sonnet"
    assert sess["source_agent"] == "claude-code"
    assert sess["model"] == "claude-sonnet-5"
    assert sess["note"] is None
    assert sess["tokens"] == {
        "input": 1_000_000,
        "output": 500_000,
        "cache_read": 2_000_000,
        "cache_write_5m": 100_000,
        "cache_write_1h": 50_000,
    }
    assert sess["usd_list_price"] == pytest.approx(7.85, rel=1e-6)

    totals = result["totals"]
    assert totals["usd_list_price"] == pytest.approx(7.85, rel=1e-6)
    assert totals["input_tokens"] == 1_000_000
    assert totals["output_tokens"] == 500_000


def test_anthropic_date_stamp_strip(registry_path: Path) -> None:
    """Anthropic model with trailing date stamp must strip date before registry lookup."""
    row = {
        "turn_id": "msg_haiku_date",
        "model": "claude-haiku-4-5-20251001",
        "input_tokens": 1_000_000,
        "output_tokens": 200_000,
        "cache_read": 500_000,
        "cache_write_5m": 40_000,
        "cache_write_1h": 25_000,
    }
    # Rates for claude-haiku-4-5: in: 1.0, out: 5.0, cr: 0.1, cw5m: 1.25, cw1h: 2.0
    # Cost = 1M*1.0 + 0.2M*5.0 + 0.5M*0.1 + 0.04M*1.25 + 0.025M*2.0
    #      = 1.00 + 1.00 + 0.05 + 0.05 + 0.05 = 2.15 USD
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-haiku'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-haiku", "source_agent": "nanoclaw"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["model"] == "claude-haiku-4-5-20251001"
    assert sess["note"] is None
    assert sess["usd_list_price"] == pytest.approx(2.15, rel=1e-6)


def test_anthropic_1m_strip(registry_path: Path) -> None:
    """Anthropic model with [1m] context suffix must strip suffix before lookup."""
    row = {
        "turn_id": "msg_opus_1m",
        "model": "claude-opus-5[1m]",
        "input_tokens": 200_000,
        "output_tokens": 40_000,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    # Rates for claude-opus-5: in: 5.0, out: 25.0
    # Cost = 0.2M * 5.0 + 0.04M * 25.0 = 1.00 + 1.00 = 2.00 USD
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-opus'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-opus", "source_agent": "claude-desktop-app"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["model"] == "claude-opus-5[1m]"
    assert sess["note"] is None
    assert sess["usd_list_price"] == pytest.approx(2.00, rel=1e-6)


def test_anthropic_dedup_max_per_group(registry_path: Path) -> None:
    """Multiple assistant snapshots for the same turn ID must take MAX of each field."""
    rows = [
        {
            "turn_id": "msg_dup",
            "model": "claude-sonnet-5",
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read": 50,
            "cache_write_5m": 10,
            "cache_write_1h": 0,
        },
        {
            "turn_id": "msg_dup",
            "model": "claude-sonnet-5",
            "input_tokens": 150,
            "output_tokens": 60,
            "cache_read": 40,
            "cache_write_5m": 12,
            "cache_write_1h": 5,
        },
        {
            "turn_id": "msg_single",
            "model": "claude-sonnet-5",
            "input_tokens": 50,
            "output_tokens": 20,
            "cache_read": 10,
            "cache_write_5m": 0,
            "cache_write_1h": 0,
        },
    ]
    ndjson = b"\n".join(json.dumps(r).encode("utf-8") for r in rows) + b"\n"
    runner = make_fake_runner({"session_id = 'sess-dedup'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-dedup", "source_agent": "nanoclaw"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["tokens"] == {
        "input": 200,
        "output": 80,
        "cache_read": 60,
        "cache_write_5m": 12,
        "cache_write_1h": 5,
    }


def test_codex_subset_cache_and_hand_computed_pricing(registry_path: Path) -> None:
    """Codex session inverts cached input and prices via the openai registry table."""
    row = {
        "total_token_usage": json.dumps(
            {
                "input_tokens": 10_000,
                "cached_input_tokens": 8_000,
                "output_tokens": 500,
            }
        ),
        "model": "gpt-5.6",
    }
    # Rates for gpt-5.6: in: 4.0, out: 20.0, cr: 0.4
    # Uncached in: 2,000 -> 0.008 USD
    # Cached in: 8,000 -> 0.0032 USD
    # Output: 500 -> 0.010 USD
    # Total = 0.008 + 0.0032 + 0.010 = 0.0212 USD
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-codex'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-codex", "source_agent": "codex-cli"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["session_id"] == "sess-codex"
    assert sess["source_agent"] == "codex-cli"
    assert sess["model"] == "gpt-5.6"
    assert sess["tokens"] == {
        "input": 2_000,
        "output": 500,
        "cache_read": 8_000,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    assert sess["usd_list_price"] == pytest.approx(0.0212, rel=1e-6)
    assert sess["note"] is None

    assert result["totals"]["usd_list_price"] == pytest.approx(0.0212, rel=1e-6)
    assert result["totals"]["input_tokens"] == 2_000
    assert result["totals"]["output_tokens"] == 500


def test_agy_session_summed_and_priced_with_model(registry_path: Path) -> None:
    """agy usage is summed across assistant rows and priced when model is supplied."""
    rows = [
        {
            "model": None,
            "input_tokens": 5_000,
            "output_tokens": 300,
            "turn_count": None,
        },
        {
            "model": None,
            "input_tokens": 7_000,
            "output_tokens": 450,
            "turn_count": None,
        },
    ]
    # Total in: 12,000, total out: 750
    # Rates for gemini-3.7-flash: in: 0.75, out: 3.75
    # Cost = 0.012M * 0.75 + 0.00075M * 3.75 = 0.009 + 0.0028125 = 0.0118125 USD
    ndjson = b"\n".join(json.dumps(r).encode("utf-8") for r in rows) + b"\n"
    runner = make_fake_runner({"session_id = 'sess-agy'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-agy", "source_agent": "agy", "model": "gemini-3.7-flash"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["session_id"] == "sess-agy"
    assert sess["source_agent"] == "agy"
    assert sess["model"] == "gemini-3.7-flash"
    assert sess["tokens"] == {
        "input": 12_000,
        "output": 750,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    assert sess["usd_list_price"] == pytest.approx(0.0118125, rel=1e-6)
    assert sess["note"] is None


def test_agy_effort_suffix_strip(registry_path: Path) -> None:
    """agy model with effort suffix (-low, -medium, -high) must strip before lookup."""
    row = {
        "model": None,
        "input_tokens": 1_000_000,
        "output_tokens": 100_000,
        "turn_count": 1,
    }
    # Rates for gemini-3.7-flash: in: 0.75, out: 3.75
    # Cost = 1M * 0.75 + 0.1M * 3.75 = 0.75 + 0.375 = 1.125 USD
    ndjson = json.dumps(row).encode("utf-8") + b"\n"

    for suffix in ("-low", "-medium", "-high"):
        model_name = f"gemini-3.7-flash{suffix}"
        runner = make_fake_runner({f"sess-agy{suffix}": (0, ndjson, b"")})
        sessions = [{"session_id": f"sess-agy{suffix}", "source_agent": "agy", "model": model_name}]
        result = usage(sessions, registry=registry_path, run=runner)

        sess = result["sessions"][0]
        assert sess["model"] == model_name
        assert sess["note"] is None
        assert sess["usd_list_price"] == pytest.approx(1.125, rel=1e-6)


def test_agy_unpriced_when_no_model(registry_path: Path) -> None:
    """agy session without model supplied is marked unpriced (None)."""
    row = {
        "model": None,
        "input_tokens": 10_000,
        "output_tokens": 500,
        "turn_count": 1,
    }
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-agy-nomodel'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-agy-nomodel", "source_agent": "agy"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["model"] is None
    assert sess["tokens"] == {
        "input": 10_000,
        "output": 500,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    assert sess["usd_list_price"] is None
    assert sess["note"] == "unpriced (None)"


def test_registry_none_skips_pricing() -> None:
    """When registry is None, pricing is skipped and note records missing registry."""
    row = {
        "turn_id": "msg_sonnet",
        "model": "claude-sonnet-5",
        "input_tokens": 100_000,
        "output_tokens": 20_000,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-noreg'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-noreg", "source_agent": "claude-code"}]
    result = usage(sessions, registry=None, run=runner)

    sess = result["sessions"][0]
    assert sess["tokens"] == {
        "input": 100_000,
        "output": 20_000,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    assert sess["usd_list_price"] is None
    assert sess["note"] == "no rate registry provided"

    assert result["totals"]["usd_list_price"] is None
    assert result["totals"]["input_tokens"] == 100_000
    assert result["totals"]["output_tokens"] == 20_000


def test_malformed_registry_file_produces_notes(tmp_path: Path) -> None:
    """Malformed rate registry file produces session notes without raising exceptions."""
    bad_registry = tmp_path / "bad_registry.json"
    bad_registry.write_text("{invalid_json: 123", encoding="utf-8")

    row = {
        "turn_id": "msg_badreg",
        "model": "claude-sonnet-5",
        "input_tokens": 50_000,
        "output_tokens": 10_000,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-badreg'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-badreg", "source_agent": "claude-code"}]
    result = usage(sessions, registry=bad_registry, run=runner)

    sess = result["sessions"][0]
    assert sess["tokens"] is not None
    assert sess["usd_list_price"] is None
    assert sess["note"] is not None
    assert "malformed rate registry" in sess["note"]


def test_missing_registry_file_produces_notes(tmp_path: Path) -> None:
    """Non-existent registry path produces informative note without raising."""
    missing_path = tmp_path / "does_not_exist.json"
    row = {
        "turn_id": "msg_miss",
        "model": "claude-sonnet-5",
        "input_tokens": 10_000,
        "output_tokens": 2_000,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    ndjson = json.dumps(row).encode("utf-8") + b"\n"
    runner = make_fake_runner({"session_id = 'sess-miss'": (0, ndjson, b"")})

    sessions = [{"session_id": "sess-miss", "source_agent": "claude-code"}]
    result = usage(sessions, registry=missing_path, run=runner)

    sess = result["sessions"][0]
    assert sess["tokens"] is not None
    assert sess["usd_list_price"] is None
    assert sess["note"] is not None
    assert "rate registry file not found" in sess["note"]


def test_unknown_model_prices_to_none(registry_path: Path) -> None:
    """Unrecognized model names in registry must yield usd_list_price: None with model name."""
    anthropic_row = {
        "turn_id": "msg_unk_anthropic",
        "model": "claude-experimental-future",
        "input_tokens": 100_000,
        "output_tokens": 20_000,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    codex_row = {
        "total_token_usage": json.dumps(
            {"input_tokens": 5_000, "cached_input_tokens": 0, "output_tokens": 100}
        ),
        "model": "gpt-4o",
    }
    agy_row = {
        "model": None,
        "input_tokens": 2_000,
        "output_tokens": 50,
        "turn_count": 1,
    }

    responses = {
        "sess-unk-ant": (0, json.dumps(anthropic_row).encode("utf-8") + b"\n", b""),
        "sess-unk-cdx": (0, json.dumps(codex_row).encode("utf-8") + b"\n", b""),
        "sess-unk-agy": (0, json.dumps(agy_row).encode("utf-8") + b"\n", b""),
    }
    runner = make_fake_runner(responses)

    sessions = [
        {"session_id": "sess-unk-ant", "source_agent": "claude-code"},
        {"session_id": "sess-unk-cdx", "source_agent": "codex-cli"},
        {"session_id": "sess-unk-agy", "source_agent": "agy", "model": "gemini-unknown-medium"},
    ]
    result = usage(sessions, registry=registry_path, run=runner)

    assert result["sessions"][0]["usd_list_price"] is None
    assert result["sessions"][0]["note"] == "unpriced (claude-experimental-future)"

    assert result["sessions"][1]["usd_list_price"] is None
    assert result["sessions"][1]["note"] == "unpriced (gpt-4o)"

    assert result["sessions"][2]["usd_list_price"] is None
    assert result["sessions"][2]["note"] == "unpriced (gemini-unknown-medium)"


def test_unknown_harness(registry_path: Path) -> None:
    """Unknown harnesses return None tokens and informative note without querying."""
    runner = make_fake_runner({})
    sessions = [{"session_id": "sess-unk", "source_agent": "opencode"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["session_id"] == "sess-unk"
    assert sess["source_agent"] == "opencode"
    assert sess["model"] is None
    assert sess["tokens"] is None
    assert sess["usd_list_price"] is None
    assert sess["note"] == "no known usage path for this harness"

    assert result["totals"]["usd_list_price"] is None
    assert result["totals"]["input_tokens"] == 0
    assert result["totals"]["output_tokens"] == 0
    assert len(runner.calls) == 0


def test_failing_query_produces_note_not_exception(registry_path: Path) -> None:
    """Non-zero query return code records note on session without raising."""
    runner = make_fake_runner(
        {"session_id = 'sess-fail'": (1, b"", b"database locked: disk I/O error")}
    )
    sessions = [{"session_id": "sess-fail", "source_agent": "claude-code"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["tokens"] is None
    assert sess["usd_list_price"] is None
    assert sess["note"] is not None
    assert "query failed (code 1)" in sess["note"]
    assert "database locked" in sess["note"]

    assert result["totals"]["usd_list_price"] is None
    assert result["totals"]["input_tokens"] == 0
    assert result["totals"]["output_tokens"] == 0


def test_runner_exception_produces_note(registry_path: Path) -> None:
    """Exceptions raised by the run callable are trapped and recorded as notes."""

    def crash_run(argv: list[str], cwd: Path, timeout: float = 120.0) -> tuple[int, bytes, bytes]:
        raise OSError("connection refused by pond daemon")

    sessions = [{"session_id": "sess-crash", "source_agent": "claude-code"}]
    result = usage(sessions, registry=registry_path, run=crash_run)

    sess = result["sessions"][0]
    assert sess["tokens"] is None
    assert sess["usd_list_price"] is None
    assert sess["note"] is not None
    assert "query runner exception" in sess["note"]
    assert "connection refused" in sess["note"]


def test_storage_path_argument_passed(registry_path: Path) -> None:
    """When store is provided, --storage-path must be included in pond argv."""
    runner = make_fake_runner({})
    sessions = [{"session_id": "sess-store", "source_agent": "claude-code"}]
    usage(sessions, store="/data/custom_pond", registry=registry_path, run=runner)

    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert argv[0] == "pond"
    assert argv[1] == "--storage-path"
    assert argv[2] == "/data/custom_pond"
    assert argv[3] == "sql"


def test_mixed_sessions_totals_aggregation(registry_path: Path) -> None:
    """Totals should aggregate token sums and sum usd_list_price across priced sessions."""
    sonnet_row = {
        "turn_id": "msg_sonnet",
        "model": "claude-sonnet-5",
        "input_tokens": 500_000,
        "output_tokens": 100_000,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    # Sonnet cost: 500k * 2.0 / 1e6 + 100k * 10.0 / 1e6 = 1.00 + 1.00 = 2.00 USD
    codex_row = {
        "total_token_usage": json.dumps(
            {"input_tokens": 3_000, "cached_input_tokens": 1_000, "output_tokens": 200}
        ),
        "model": "gpt-5.6",
    }
    # Codex cost: 2k in * 4.0 / 1e6 + 1k cr * 0.4 / 1e6 + 200 out * 20.0 / 1e6 = 0.0124 USD
    agy_row = {
        "model": None,
        "input_tokens": 4_000,
        "output_tokens": 300,
        "turn_count": 1,
    }
    # Agy cost: 4k in * 0.75 / 1e6 ($0.003) + 300 out * 3.75 / 1e6 ($0.001125) = 0.004125 USD

    responses = {
        "sess-1": (0, json.dumps(sonnet_row).encode("utf-8") + b"\n", b""),
        "sess-2": (0, json.dumps(codex_row).encode("utf-8") + b"\n", b""),
        "sess-3": (0, json.dumps(agy_row).encode("utf-8") + b"\n", b""),
    }
    runner = make_fake_runner(responses)

    sessions = [
        {"session_id": "sess-1", "source_agent": "claude-code"},
        {"session_id": "sess-2", "source_agent": "codex-cli"},
        {"session_id": "sess-3", "source_agent": "agy", "model": "gemini-3.7-flash"},
        {"session_id": "sess-4", "source_agent": "other-agent"},
    ]
    result = usage(sessions, registry=registry_path, run=runner)

    assert len(result["sessions"]) == 4
    totals = result["totals"]
    # Sum of priced: 2.00 + 0.0124 + 0.004125 = 2.016525 USD
    assert totals["usd_list_price"] == pytest.approx(2.016525, rel=1e-6)
    # Total input: 500_000 (sess-1) + 2_000 (sess-2) + 4_000 (sess-3) + 0 (sess-4) = 506_000
    assert totals["input_tokens"] == 506_000
    # Total output: 100_000 + 200 + 300 + 0 = 100_500
    assert totals["output_tokens"] == 100_500


def test_empty_sessions_list(registry_path: Path) -> None:
    """Empty sessions input produces empty output and zeroed totals."""
    runner = make_fake_runner({})
    result = usage([], registry=registry_path, run=runner)
    assert result["sessions"] == []
    assert result["totals"] == {
        "usd_list_price": None,
        "priced_sessions": 0,
        "unpriced_sessions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    assert result["method"] == METHOD_TEXT


def test_empty_query_result_produces_note(registry_path: Path) -> None:
    """When query yields zero rows, session records missing usage note."""
    runner = make_fake_runner({"sess-empty": (0, b"", b"")})
    sessions = [{"session_id": "sess-empty", "source_agent": "claude-code"}]
    result = usage(sessions, registry=registry_path, run=runner)

    sess = result["sessions"][0]
    assert sess["tokens"] is None
    assert sess["usd_list_price"] is None
    assert sess["note"] == "no usage recorded for session"
