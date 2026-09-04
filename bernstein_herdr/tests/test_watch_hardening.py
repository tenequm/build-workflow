"""Watcher hardening (H11): disk thresholds, ORCH-DEAD pacing, spawner-event rows.

    uv run --with pytest pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path

from bernstein_herdr.watch import disk_events, orch_dead_due, record_spawner_event

GB = 1024**3


def tags(events: list[tuple[str, str]]) -> list[str]:
    return [t for t, _ in events]


def test_disk_warn_once_per_crossing() -> None:
    state: dict = {}
    assert tags(disk_events(50 * GB, state)) == []
    assert tags(disk_events(9 * GB, state)) == ["DISK"]
    assert tags(disk_events(8 * GB, state)) == []          # already warned
    assert tags(disk_events(50 * GB, state)) == []         # recovered, resets
    assert tags(disk_events(9 * GB, state)) == ["DISK"]    # warns again


def test_disk_critical_below_2gb() -> None:
    state: dict = {}
    assert tags(disk_events(1 * GB, state)) == ["DISK-CRITICAL"]
    assert tags(disk_events(1 * GB, state)) == []          # said once
    _, detail = disk_events(1 * GB, {"critical": False, "warned": True})[0]
    assert "kill" in detail


def test_orch_dead_pacing() -> None:
    assert orch_dead_due(None, 1000.0, None) is False
    assert orch_dead_due(500.0, 1000.0, None) is False       # under 10 minutes
    assert orch_dead_due(0.0, 601.0, None) is True           # due
    assert orch_dead_due(0.0, 700.0, 650.0) is False         # said 50s ago
    assert orch_dead_due(0.0, 650.0 + 1800.0, 650.0) is True  # 30m later, again


def test_spawner_event_row_lands_in_runs_jsonl(tmp_path: Path) -> None:
    record_spawner_event(tmp_path, "SIGTERM sent to agent-xyz after liveness_judgment")
    rows = [json.loads(l) for l in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "watch" and row["kind"] == "spawner_event"
    assert "SIGTERM" in row["line"] and row["ts"]


def test_trouble_regex_catches_branch_rename() -> None:
    from bernstein_herdr.watch import TROUBLE

    assert TROUBLE.search("Branch: renamed refs/heads/build/x to refs/heads/salvage/a1")
    assert not TROUBLE.search("merged task phase-1 cleanly")
