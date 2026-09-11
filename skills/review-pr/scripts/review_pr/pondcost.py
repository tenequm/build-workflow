"""Token accounting and list-price equivalent cost calculation for pond sessions.

Queries assistant usage snapshots from a pond database across different agent harnesses
(Claude Code, Codex CLI, agy) and normalizes them into token counts and list-price USD
derived from a rate registry JSON file. All calculations provide an informative floor
rather than billing truth, keeping failed queries non-fatal to preserve review pipeline flow.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import pondsync
from .proc import command

METHOD_TEXT = (
    "pond-derived list-price equivalent; an informative floor, not billing - "
    "subscription-backed lanes are billed nothing"
)


def _normalize_anthropic_model(model: str | None) -> str | None:
    """Normalize Anthropic model ID by stripping [1m] suffix and trailing date stamp.

    Examples:
    - claude-haiku-4-5-20251001 -> claude-haiku-4-5
    - claude-opus-5[1m] -> claude-opus-5
    """
    if not model:
        return None
    clean = model.removesuffix("[1m]").strip()
    clean = re.sub(r"-20\d{6,}$", "", clean)
    return clean or None


def _normalize_google_model(model: str | None) -> str | None:
    """Normalize Google model ID by stripping trailing effort suffixes.

    Examples:
    - gemini-3.7-flash-medium -> gemini-3.7-flash
    - gemini-3.7-flash-high -> gemini-3.7-flash
    """
    if not model:
        return None
    for suffix in ("-low", "-medium", "-high"):
        if model.endswith(suffix):
            return model[: -len(suffix)]
    return model


def _load_registry(
    registry: str | Path | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Load and parse the rate registry JSON file once per usage call.

    Returns (providers_dict, error_note). When registry is None, pricing is skipped.
    Missing or malformed files produce an error note without raising exceptions.
    """
    if registry is None:
        return None, "no rate registry provided"

    try:
        path = Path(registry)
        if not path.is_file():
            return None, f"rate registry file not found: {registry}"
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return None, f"malformed rate registry ({exc})"

    if not isinstance(data, dict):
        return None, "malformed rate registry (expected JSON object)"

    providers = data.get("providers")
    if not isinstance(providers, dict):
        return None, "malformed rate registry (missing 'providers' mapping)"

    return providers, None


def _run_pond_query(
    sql: str,
    store: str | None,
    run: Callable[..., tuple[int, bytes, bytes]],
) -> tuple[int, list[dict[str, Any]], str | None]:
    """Execute a SQL query against pond CLI and parse ndjson output.

    Catches execution and parsing failures gracefully to guarantee observability semantics.
    """
    # The pinned binary, resolved the same way capture resolves it: a bare "pond"
    # from PATH would price with whatever the host has, which is exactly the drift
    # the pin exists to prevent - and fails outright where pond lives only in the
    # operator venv (cross-family review, 2026-09-11).
    try:
        pond = str(pondsync.binary())
    except Exception:
        pond = "pond"
    if store is not None:
        argv = [pond, "--storage-path", store, "sql", "--format", "ndjson", "--timeout", "120", sql]
    else:
        argv = [pond, "sql", "--format", "ndjson", "--timeout", "120", sql]

    try:
        code, out_bytes, err_bytes = run(argv, Path.cwd(), 120)
    except Exception as exc:
        return -1, [], f"query runner exception: {exc}"

    if code != 0:
        err_msg = err_bytes.decode(errors="replace").strip()
        return code, [], f"query failed (code {code}): {err_msg or 'unknown error'}"

    rows: list[dict[str, Any]] = []
    text = out_bytes.decode(errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return 0, rows, None


def _process_anthropic_session(
    session_id: str,
    source_agent: str,
    store: str | None,
    run: Callable[..., tuple[int, bytes, bytes]],
    providers: dict[str, Any] | None,
    registry_note: str | None,
) -> dict[str, Any]:
    """Process Claude Code / nanoclaw / claude-desktop-app session.

    Groups assistant snapshots by anthropic message ID, takes MAX of each cumulative
    usage snapshot, and applies registry absolute rates for input, output, cache read,
    and ephemeral cache writes.
    """
    escaped_sid = session_id.replace("'", "''")
    sql = (
        "SELECT "
        "json_get_string(options, 'anthropic', 'id') AS turn_id, "
        "any_value(json_get_string(options, 'anthropic', 'model')) AS model, "
        "MAX(json_get_int(options, 'anthropic', 'usage', 'input_tokens')) AS input_tokens, "
        "MAX(json_get_int(options, 'anthropic', 'usage', 'output_tokens')) AS output_tokens, "
        "MAX(json_get_int(options, 'anthropic', 'usage', 'cache_read_input_tokens')) "
        "AS cache_read, "
        "MAX(json_get_int(options, 'anthropic', 'usage', 'cache_creation', "
        "'ephemeral_5m_input_tokens')) AS cache_write_5m, "
        "MAX(json_get_int(options, 'anthropic', 'usage', 'cache_creation', "
        "'ephemeral_1h_input_tokens')) AS cache_write_1h "
        "FROM messages "
        f"WHERE session_id = '{escaped_sid}' "
        "AND role = 'assistant' "
        "AND json_get_string(options, 'anthropic', 'id') IS NOT NULL "
        "GROUP BY turn_id"
    )

    code, rows, err = _run_pond_query(sql, store, run)
    if err is not None:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": None,
            "tokens": None,
            "usd_list_price": None,
            "note": err,
        }

    if not rows:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": None,
            "tokens": None,
            "usd_list_price": None,
            "note": "no usage recorded for session",
        }

    turns: dict[str, dict[str, Any]] = {}
    for row in rows:
        tid = row.get("turn_id")
        if not tid:
            continue
        if tid not in turns:
            turns[tid] = {
                "model": row.get("model"),
                "input_tokens": int(row.get("input_tokens") or 0),
                "output_tokens": int(row.get("output_tokens") or 0),
                "cache_read": int(row.get("cache_read") or 0),
                "cache_write_5m": int(row.get("cache_write_5m") or 0),
                "cache_write_1h": int(row.get("cache_write_1h") or 0),
            }
        else:
            t = turns[tid]
            if row.get("model") and not t["model"]:
                t["model"] = row.get("model")
            t["input_tokens"] = max(t["input_tokens"], int(row.get("input_tokens") or 0))
            t["output_tokens"] = max(t["output_tokens"], int(row.get("output_tokens") or 0))
            t["cache_read"] = max(t["cache_read"], int(row.get("cache_read") or 0))
            t["cache_write_5m"] = max(t["cache_write_5m"], int(row.get("cache_write_5m") or 0))
            t["cache_write_1h"] = max(t["cache_write_1h"], int(row.get("cache_write_1h") or 0))

    if not turns:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": None,
            "tokens": None,
            "usd_list_price": None,
            "note": "no usage recorded for session",
        }

    total_in = sum(t["input_tokens"] for t in turns.values())
    total_out = sum(t["output_tokens"] for t in turns.values())
    total_cr = sum(t["cache_read"] for t in turns.values())
    total_cw5m = sum(t["cache_write_5m"] for t in turns.values())
    total_cw1h = sum(t["cache_write_1h"] for t in turns.values())

    tokens = {
        "input": total_in,
        "output": total_out,
        "cache_read": total_cr,
        "cache_write_5m": total_cw5m,
        "cache_write_1h": total_cw1h,
    }

    models = [t["model"] for t in turns.values() if t.get("model")]
    session_model = models[0] if models else None

    if providers is None:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": session_model,
            "tokens": tokens,
            "usd_list_price": None,
            "note": registry_note,
        }

    anthropic_rates = providers.get("anthropic")
    if not isinstance(anthropic_rates, dict):
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": session_model,
            "tokens": tokens,
            "usd_list_price": None,
            "note": f"unpriced ({session_model})",
        }

    turn_costs: list[float] = []
    all_priced = True
    unpriced_model = session_model

    for t in turns.values():
        raw_model = t.get("model")
        norm_model = _normalize_anthropic_model(raw_model)
        rate = anthropic_rates.get(norm_model) if norm_model else None
        if rate is None or not isinstance(rate, dict):
            all_priced = False
            unpriced_model = raw_model
            break

        inp_rate = float(rate.get("input", 0.0))
        out_rate = float(rate.get("output", 0.0))
        cr_rate = float(rate.get("cache_read", 0.0))
        cw5m_rate = float(rate.get("cache_write_5m", 0.0))
        cw1h_rate = float(rate.get("cache_write_1h", 0.0))

        cost = (
            t["input_tokens"] * inp_rate
            + t["output_tokens"] * out_rate
            + t["cache_read"] * cr_rate
            + t["cache_write_5m"] * cw5m_rate
            + t["cache_write_1h"] * cw1h_rate
        ) / 1_000_000.0
        turn_costs.append(cost)

    usd_price = sum(turn_costs) if all_priced and turn_costs else None
    note = None if all_priced else f"unpriced ({unpriced_model})"

    return {
        "session_id": session_id,
        "source_agent": source_agent,
        "model": session_model,
        "tokens": tokens,
        "usd_list_price": usd_price,
        "note": note,
    }


def _process_codex_session(
    session_id: str,
    source_agent: str,
    input_model: str | None,
    store: str | None,
    run: Callable[..., tuple[int, bytes, bytes]],
    providers: dict[str, Any] | None,
    registry_note: str | None,
) -> dict[str, Any]:
    """Process codex-cli session.

    Reads cumulative total_token_usage from the final record. Inverts cached
    tokens out of input_tokens since Codex records cached as an input subset.
    Prices against the openai registry table.
    """
    escaped_sid = session_id.replace("'", "''")
    sql = (
        "SELECT "
        "json_extract(options, '$.source.raw_record.payload.info.total_token_usage') "
        "AS total_token_usage, "
        "json_get_string(options, 'source', 'raw_record', 'payload', 'info', 'model') "
        "AS model "
        "FROM messages "
        f"WHERE session_id = '{escaped_sid}' "
        "AND json_extract(options, '$.source.raw_record.payload.info.total_token_usage') "
        "IS NOT NULL "
        'ORDER BY "timestamp" DESC '
        "LIMIT 1"
    )

    code, rows, err = _run_pond_query(sql, store, run)
    if err is not None:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": None,
            "tokens": None,
            "usd_list_price": None,
            "note": err,
        }

    if not rows:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": None,
            "tokens": None,
            "usd_list_price": None,
            "note": "no usage recorded for session",
        }

    row = rows[0]
    usage_raw = row.get("total_token_usage")
    if isinstance(usage_raw, str):
        try:
            usage_data = json.loads(usage_raw)
        except json.JSONDecodeError:
            usage_data = {}
    elif isinstance(usage_raw, dict):
        usage_data = usage_raw
    else:
        usage_data = {}

    if usage_data:
        raw_input = int(usage_data.get("input_tokens") or 0)
        cached = int(usage_data.get("cached_input_tokens") or 0)
        output = int(usage_data.get("output_tokens") or 0)
        model = row.get("model") or usage_data.get("model") or input_model
    else:
        raw_input = int(row.get("input_tokens") or 0)
        cached = int(row.get("cached_input_tokens") or 0)
        output = int(row.get("output_tokens") or 0)
        model = row.get("model") or input_model

    uncached_input = max(0, raw_input - cached)
    tokens = {
        "input": uncached_input,
        "output": output,
        "cache_read": cached,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }

    if providers is None:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": model,
            "tokens": tokens,
            "usd_list_price": None,
            "note": registry_note,
        }

    openai_rates = providers.get("openai")
    rate = None
    if isinstance(openai_rates, dict) and model:
        rate = openai_rates.get(model)

    if rate is not None and isinstance(rate, dict):
        inp_rate = float(rate.get("input", 0.0))
        out_rate = float(rate.get("output", 0.0))
        cr_rate = float(rate.get("cache_read", 0.0))
        cost = (uncached_input * inp_rate + output * out_rate + cached * cr_rate) / 1_000_000.0
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": model,
            "tokens": tokens,
            "usd_list_price": cost,
            "note": None,
        }

    return {
        "session_id": session_id,
        "source_agent": source_agent,
        "model": model,
        "tokens": tokens,
        "usd_list_price": None,
        "note": f"unpriced ({model})",
    }


def _process_agy_session(
    session_id: str,
    source_agent: str,
    input_model: str | None,
    store: str | None,
    run: Callable[..., tuple[int, bytes, bytes]],
    providers: dict[str, Any] | None,
    registry_note: str | None,
) -> dict[str, Any]:
    """Process agy session.

    Sums per-row assistant usage snapshots where each API call carries full context.
    Prices against google rate table after stripping effort suffixes.
    """
    escaped_sid = session_id.replace("'", "''")
    sql = (
        "SELECT "
        "any_value(json_get_string(options, 'agy', 'model')) AS model, "
        "SUM(json_get_int(options, 'agy', 'usage', 'input_tokens')) AS input_tokens, "
        "SUM(json_get_int(options, 'agy', 'usage', 'output_tokens')) AS output_tokens, "
        "COUNT(*) AS turn_count "
        "FROM messages "
        f"WHERE session_id = '{escaped_sid}' "
        "AND role = 'assistant' "
        "AND json_extract(options, '$.agy.usage') IS NOT NULL"
    )

    code, rows, err = _run_pond_query(sql, store, run)
    if err is not None:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": input_model,
            "tokens": None,
            "usd_list_price": None,
            "note": err,
        }

    if not rows:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": input_model,
            "tokens": None,
            "usd_list_price": None,
            "note": "no usage recorded for session",
        }

    total_in = 0
    total_out = 0
    db_model = None
    found_turns = 0

    for r in rows:
        if r.get("turn_count") is not None:
            if int(r.get("turn_count") or 0) > 0:
                total_in = int(r.get("input_tokens") or 0)
                total_out = int(r.get("output_tokens") or 0)
                db_model = r.get("model")
                found_turns = int(r["turn_count"])
        else:
            total_in += int(r.get("input_tokens") or 0)
            total_out += int(r.get("output_tokens") or 0)
            if r.get("model") and not db_model:
                db_model = r.get("model")
            found_turns += 1

    if found_turns == 0 and not total_in and not total_out:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": input_model,
            "tokens": None,
            "usd_list_price": None,
            "note": "no usage recorded for session",
        }

    tokens = {
        "input": total_in,
        "output": total_out,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }

    session_model = input_model if input_model is not None else db_model

    if providers is None:
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": session_model,
            "tokens": tokens,
            "usd_list_price": None,
            "note": registry_note,
        }

    google_rates = providers.get("google")
    norm_model = _normalize_google_model(session_model)
    rate = None
    if isinstance(google_rates, dict) and norm_model:
        rate = google_rates.get(norm_model)

    if rate is not None and isinstance(rate, dict):
        inp_rate = float(rate.get("input", 0.0))
        out_rate = float(rate.get("output", 0.0))
        cost = (total_in * inp_rate + total_out * out_rate) / 1_000_000.0
        return {
            "session_id": session_id,
            "source_agent": source_agent,
            "model": session_model,
            "tokens": tokens,
            "usd_list_price": cost,
            "note": None,
        }

    return {
        "session_id": session_id,
        "source_agent": source_agent,
        "model": session_model,
        "tokens": tokens,
        "usd_list_price": None,
        "note": f"unpriced ({session_model})",
    }


def usage(
    sessions: list[dict[str, Any]],
    *,
    store: str | None = None,
    registry: str | Path | None = None,
    run: Callable[..., tuple[int, bytes, bytes]] = command,
) -> dict[str, Any]:
    """Compute token usage and list-price cost for a collection of agent sessions.

    Dispatches on source_agent harness semantics, aggregates token buckets across
    valid queries, and produces list-price cost totals priced from a rate registry JSON file.
    """
    providers, registry_note = _load_registry(registry)
    session_results: list[dict[str, Any]] = []

    for item in sessions:
        sid = str(item.get("session_id", ""))
        agent = str(item.get("source_agent", ""))
        input_model = item.get("model")

        if (
            agent.startswith("claude-code")
            or agent.startswith("nanoclaw")
            or agent == "claude-desktop-app"
            or agent.startswith("claude-desktop-app")
        ):
            res = _process_anthropic_session(sid, agent, store, run, providers, registry_note)
        elif agent == "codex-cli" or agent.startswith("codex-cli"):
            res = _process_codex_session(
                sid, agent, input_model, store, run, providers, registry_note
            )
        elif agent == "agy" or agent.startswith("agy"):
            res = _process_agy_session(
                sid, agent, input_model, store, run, providers, registry_note
            )
        else:
            res = {
                "session_id": sid,
                "source_agent": agent,
                "model": input_model,
                "tokens": None,
                "usd_list_price": None,
                "note": "no known usage path for this harness",
            }

        session_results.append(res)

    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read = 0
    total_cache_write = 0
    priced_values: list[float] = []

    for s in session_results:
        toks = s.get("tokens")
        if toks:
            total_input_tokens += int(toks.get("input") or 0)
            total_output_tokens += int(toks.get("output") or 0)
            total_cache_read += int(toks.get("cache_read") or 0)
            total_cache_write += int(toks.get("cache_write_5m") or 0) + int(
                toks.get("cache_write_1h") or 0
            )
        price = s.get("usd_list_price")
        if price is not None:
            priced_values.append(price)

    total_usd = sum(priced_values) if priced_values else None

    return {
        "sessions": session_results,
        "totals": {
            # The floor is a floor over the PRICED sessions only; the counts beside it
            # say how much of the run that covers, so a partial sum never reads whole.
            "usd_list_price": total_usd,
            "priced_sessions": len(priced_values),
            "unpriced_sessions": len(session_results) - len(priced_values),
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cache_read_tokens": total_cache_read,
            "cache_write_tokens": total_cache_write,
        },
        "method": METHOD_TEXT,
    }
