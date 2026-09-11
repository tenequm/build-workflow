"""The unified diff as an index: which new-side lines a review may anchor to.

GitHub rejects a whole review atomically on one bad anchor, so anchorability is a
property this code computes rather than a property a reviewer asserts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# Outputs, not authored code. Excluded from the review scope, polish's own rule.
GENERATED = (
    "Cargo.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "go.sum",
    "composer.lock",
    "Gemfile.lock",
)
GENERATED_SUFFIX = (".snap", ".pb.go", "_pb2.py", ".generated.ts", ".gen.go", ".lock")


@dataclass
class Hunk:
    start: int
    count: int

    @property
    def end(self) -> int:
        return self.start + max(self.count, 1) - 1


@dataclass
class FileDiff:
    path: str
    old_path: str | None = None
    new_file: bool = False
    deleted: bool = False
    binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    added: list[tuple[int, str]] = field(default_factory=list)
    removed: list[tuple[int, str]] = field(default_factory=list)

    @property
    def changed_lines(self) -> int:
        return len(self.added) + len(self.removed)

    def anchorable(self, line: int) -> bool:
        """A new file anchors anywhere; a modified file only inside a hunk."""
        if self.deleted:
            return False
        if self.new_file:
            return line >= 1
        return any(hunk.start <= line <= hunk.end for hunk in self.hunks)


def excluded(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in GENERATED or path.endswith(GENERATED_SUFFIX)


def parse(diff: str) -> dict[str, FileDiff]:
    """Parse `git diff` output. Unknown trailing content is ignored, never guessed."""
    files: dict[str, FileDiff] = {}
    current: FileDiff | None = None
    new_line = 0
    old_line = 0
    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            current = None
            parts = raw.split(" b/", 1)
            if len(parts) == 2:
                current = FileDiff(path=parts[1].strip())
                files[current.path] = current
            continue
        if current is None:
            continue
        if raw.startswith("new file mode"):
            current.new_file = True
        elif raw.startswith("deleted file mode"):
            current.deleted = True
        elif raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            current.binary = True
        elif raw.startswith("rename from "):
            current.old_path = raw[len("rename from ") :].strip()
        elif raw.startswith("--- ") and raw[4:].strip() not in ("/dev/null",):
            current.old_path = current.old_path or raw[4:].strip().removeprefix("a/")
        elif raw.startswith("+++ b/"):
            current.path = raw[len("+++ b/") :].strip()
            files.pop(current.path, None)
            files[current.path] = current
        elif (match := HUNK.match(raw)) is not None:
            old_line = int(match.group(1))
            new_line = int(match.group(3))
            current.hunks.append(Hunk(start=new_line, count=int(match.group(4) or 1)))
        elif current.hunks:
            if raw.startswith("+"):
                current.added.append((new_line, raw[1:]))
                new_line += 1
            elif raw.startswith("-"):
                current.removed.append((old_line, raw[1:]))
                old_line += 1
            elif raw.startswith(" ") or raw == "":
                new_line += 1
                old_line += 1
    return files


def reviewable(files: dict[str, FileDiff]) -> dict[str, FileDiff]:
    return {path: fd for path, fd in files.items() if not excluded(path) and not fd.binary}


def changed_lines(files: dict[str, FileDiff]) -> int:
    return sum(fd.changed_lines for fd in files.values())


TEST_MARKS = ("test_", "_test.", "tests/", "test/", "spec/", ".spec.", ".test.", "Test.java")


def test_paths(files: dict[str, FileDiff]) -> list[str]:
    """Paths a project would recognise as tests, for the fail-on-base check."""
    return sorted(path for path in files if any(mark in path for mark in TEST_MARKS))
