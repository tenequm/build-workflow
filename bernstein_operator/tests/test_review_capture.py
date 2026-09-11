"""Which directories a run's session capture points pond at, per adapter.

The agy case is a regression: pond's agy adapter discovers sessions from the gemini
root and walks down to `antigravity-acp/conversations` itself, so the scoped sync this
workflow used to issue - straight at the conversations directory - matched nothing and
ingested zero sessions while reporting success. Every gemini-family finding lost its
transcript that way. The run now stages its own root holding only its own conversations,
which keeps the scope narrow without widening the source to the operator's whole
Antigravity history.
"""

from __future__ import annotations

import json
from pathlib import Path

from review_pr import pondsync


def conversation(root: Path, name: str, cwd: str, *, wal: bool = True) -> None:
    directory = root / ".gemini" / "antigravity-acp" / "conversations"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.db").write_bytes(b"SQLite format 3\x00")
    (directory / f"{name}.meta").write_text(json.dumps({"cwd": cwd}))
    if wal:
        (directory / f"{name}.db-wal").write_bytes(b"")
        (directory / f"{name}.db-shm").write_bytes(b"")


def receipts(ledger_dir: Path, *operations: tuple[str, str], adapter: str | None = None) -> dict:
    return {
        operation: {
            "operation": operation,
            "family": family,
            "pond_adapter": adapter,
            "started": 1.0,
            "finished": 2.0,
        }
        for operation, family in operations
    }


class TestAgyStagedRoot:
    def test_the_agy_source_is_a_gemini_shaped_root_not_the_conversations_directory(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        ledger_dir = tmp_path / "workspace"
        operation = "review-gating-gemini"
        worktree = str(ledger_dir / "sessions" / operation / "worktree")
        conversation(tmp_path / "home", "11111111-1111-1111-1111-111111111111", worktree)
        sources = pondsync._sources(receipts(ledger_dir, (operation, "gemini")), ledger_dir)
        assert set(sources) == {"agy"}
        staged = next(iter(sources["agy"]))
        assert (staged / "antigravity-acp" / "conversations").is_dir()
        assert staged.name != "conversations", "pond discovers from the root, not from below it"

    def test_only_this_run_s_conversations_are_staged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        ledger_dir = tmp_path / "workspace"
        operation = "review-design-gemini"
        worktree = str(ledger_dir / "sessions" / operation / "worktree")
        conversation(tmp_path / "home", "aaaaaaaa-1111-1111-1111-111111111111", worktree)
        conversation(tmp_path / "home", "bbbbbbbb-2222-2222-2222-222222222222", "/somewhere/else")
        staged = pondsync.stage_agy_root({worktree}, ledger_dir / "agy-root")
        assert staged is not None
        names = sorted(p.name for p in (staged / "antigravity-acp/conversations").iterdir())
        # The database plus its write-ahead siblings: a copy without them loses whatever
        # the adapter had not checkpointed.
        assert names == [
            "aaaaaaaa-1111-1111-1111-111111111111.db",
            "aaaaaaaa-1111-1111-1111-111111111111.db-shm",
            "aaaaaaaa-1111-1111-1111-111111111111.db-wal",
            "aaaaaaaa-1111-1111-1111-111111111111.meta",
        ]

    def test_gemini_home_redirects_the_staging_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.setenv("GEMINI_HOME", str(tmp_path / "api-lane" / ".gemini"))
        ledger_dir = tmp_path / "workspace"
        operation = "review-design-gemini"
        worktree = str(ledger_dir / "sessions" / operation / "worktree")
        conversation(tmp_path / "api-lane", "dddddddd-4444-4444-4444-444444444444", worktree)
        conversation(tmp_path / "home", "eeeeeeee-5555-5555-5555-555555555555", worktree)
        staged = pondsync.stage_agy_root({worktree}, ledger_dir / "agy-root")
        assert staged is not None
        names = {p.name for p in (staged / "antigravity-acp/conversations").iterdir()}
        assert "dddddddd-4444-4444-4444-444444444444.meta" in names
        assert "eeeeeeee-5555-5555-5555-555555555555.meta" not in names

    def test_a_run_with_no_agy_conversation_syncs_no_agy_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        ledger_dir = tmp_path / "workspace"
        conversation(tmp_path / "home", "cccccccc-3333-3333-3333-333333333333", "/somewhere/else")
        sources = pondsync._sources(
            receipts(ledger_dir, ("review-design-gemini", "gemini")), ledger_dir
        )
        assert "agy" not in sources

    def test_the_other_two_families_keep_their_own_source_directories(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        ledger_dir = tmp_path / "workspace"
        worktree = str(ledger_dir / "sessions" / "review-gating-claude" / "worktree")
        claude_dir = pondsync._claude_project_dir(worktree)
        claude_dir.mkdir(parents=True)
        codex_dir = tmp_path / "home" / ".codex" / "sessions" / "1970/01/01"
        codex_dir.mkdir(parents=True)
        sources = pondsync._sources(
            receipts(
                ledger_dir, ("review-gating-claude", "claude"), ("review-design-codex", "codex")
            ),
            ledger_dir,
        )
        assert sources == {"claude-code": {claude_dir}, "codex-cli": {codex_dir}}


class TestOpencodeSource:
    """opencode keeps one global SQLite store for every session it has ever run, so
    the narrow source is manufactured, not found: the family redirects XDG_DATA_HOME
    per session and capture reads the store that leaves behind."""

    def test_the_opencode_source_is_the_session_s_own_redirected_store(self, tmp_path):
        ledger_dir = tmp_path / "workspace"
        operation = "review-implementation-opencode"
        store = ledger_dir / "sessions" / operation / "env" / "xdg_data_home" / "opencode"
        store.mkdir(parents=True)
        (store / "opencode.db").write_bytes(b"SQLite format 3\x00")
        sources = pondsync._sources(receipts(ledger_dir, (operation, "opencode")), ledger_dir)
        assert sources == {"opencode": {store}}

    def test_the_operator_s_own_opencode_history_is_never_a_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        globaldb = tmp_path / "home" / ".local/share/opencode"
        globaldb.mkdir(parents=True)
        (globaldb / "opencode.db").write_bytes(b"SQLite format 3\x00")
        ledger_dir = tmp_path / "workspace"
        sources = pondsync._sources(
            receipts(ledger_dir, ("review-design-opencode", "opencode")), ledger_dir
        )
        assert sources == {}, "a session that wrote no store of its own contributes none"

    def test_an_unknown_family_is_not_swallowed_by_the_agy_branch(self, tmp_path, monkeypatch):
        """The branch used to be an `else`, so any family added without touching this
        file was staged as agy - which meant captured as nothing, silently."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        ledger_dir = tmp_path / "workspace"
        worktree = str(ledger_dir / "sessions" / "review-design-mystery" / "worktree")
        conversation(tmp_path / "home", "dddddddd-4444-4444-4444-444444444444", worktree)
        sources = pondsync._sources(
            receipts(ledger_dir, ("review-design-mystery", "mystery")), ledger_dir
        )
        assert sources == {}

    def test_a_new_family_names_its_pond_adapter_in_the_registry(self, tmp_path, monkeypatch):
        """A new lane is usually a new model on a harness pond already reads, so it
        declares `pond_adapter` in its `families:` entry and is captured with no code
        change here. Without that its transcripts are captured as nothing."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        ledger_dir = tmp_path / "workspace"
        operation = "review-gating-pi"
        worktree = str(ledger_dir / "sessions" / operation / "worktree")
        conversation(tmp_path / "home", "eeeeeeee-5555-5555-5555-555555555555", worktree)
        sources = pondsync._sources(
            receipts(ledger_dir, (operation, "pi"), adapter="agy"), ledger_dir
        )
        assert set(sources) == {"agy"}

    def test_readiness_asks_pond_about_the_adapters_this_plan_actually_writes(self):
        """The check used to name agy whatever the template routed to. A lane whose
        adapter is disabled captures nothing, and the report-witness law would surface
        that at the end of a run, after every session had been paid for."""
        from review_pr import config

        plan = config.load()
        assert pondsync.plan_adapters(plan) == {"claude-code", "codex-cli", "opencode"}
        # The production gemini lane is Zen-served, so its sessions are opencode's: the
        # family name is a model family and the adapter is what the template declares.
        assert plan["families"]["gemini"]["pond_adapter"] == "opencode"
        fast = config.load(config.TEMPLATES / "stages-fast.yaml")
        assert pondsync.plan_adapters(fast) == {"codex-cli", "opencode"}


class TestPiSource:
    """pi keeps one sessions root for every project it has ever run in, so the narrow
    source is manufactured the same way opencode's is: the family redirects
    PI_CODING_AGENT_SESSION_DIR per session and capture reads the root that leaves."""

    def test_the_pi_source_is_the_session_s_own_redirected_root(self, tmp_path):
        ledger_dir = tmp_path / "workspace"
        operation = "review-implementation-pi"
        root = ledger_dir / "sessions" / operation / "env" / "pi_coding_agent_session_dir"
        root.mkdir(parents=True)
        # pond's pi-coding-agent adapter reads a sessions root, not the config root above
        # it: its configured default is `~/.pi/agent/sessions`, which is exactly what the
        # redirect replaces, so the redirected directory is handed over as it stands.
        (root / "2026-09-11T13-41-01-776Z_01a090b3-40cf-7665-9ea1-235dd0c422a4.jsonl").write_text(
            '{"type": "session", "version": 3}\n'
        )
        sources = pondsync._sources(receipts(ledger_dir, (operation, "pi")), ledger_dir)
        assert sources == {"pi-coding-agent": {root}}

    def test_the_operator_s_own_pi_history_is_never_a_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        monkeypatch.delenv("GEMINI_HOME", raising=False)
        history = tmp_path / "home" / ".pi/agent/sessions/--home-tenequm--"
        history.mkdir(parents=True)
        (history / "session.jsonl").write_text('{"type": "session", "version": 3}\n')
        ledger_dir = tmp_path / "workspace"
        sources = pondsync._sources(receipts(ledger_dir, ("review-design-pi", "pi")), ledger_dir)
        assert sources == {}, "a session that wrote no root of its own contributes none"
