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


def receipts(ledger_dir: Path, *operations: tuple[str, str]) -> dict[str, dict]:
    return {
        operation: {"operation": operation, "family": family, "started": 1.0, "finished": 2.0}
        for operation, family in operations
    }


class TestAgyStagedRoot:
    def test_the_agy_source_is_a_gemini_shaped_root_not_the_conversations_directory(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
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

    def test_a_run_with_no_agy_conversation_syncs_no_agy_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
        ledger_dir = tmp_path / "workspace"
        conversation(tmp_path / "home", "cccccccc-3333-3333-3333-333333333333", "/somewhere/else")
        sources = pondsync._sources(
            receipts(ledger_dir, ("review-design-gemini", "gemini")), ledger_dir
        )
        assert "agy" not in sources

    def test_the_other_two_families_keep_their_own_source_directories(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
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
