"""Stage setup: a deterministic script that pins every fact the review depends on.

Two rules here are load-bearing. The validation command comes from the BASE branch,
never the checked-out pull request, because `gh pr checkout` lands the author's tree
and a PR that edits CLAUDE.md would otherwise choose what this workflow executes.
And the pull request never becomes a branch in the operator's checkout: both the
reviewed tree and the base tree are detached worktrees, so nothing the author wrote
moves the operator's own HEAD.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from operator_driver.storage import Park, atomic, canonical, digest

from . import diffindex
from .proc import command, git, git_bytes, git_ok

PR_FIELDS = (
    "number,title,body,author,baseRefName,headRefName,headRefOid,isDraft,state,url,"
    "labels,commits,files,mergeable,reviewDecision"
)
# The check commands a project documents, in the order this workflow prefers them: an
# aggregate whole-tree recipe first, then lint, then types, then a test runner. A repo
# that documents several is normal - the first by this order is pinned and the rest are
# recorded in the provenance, so an operator can see what was not chosen.
GATE_PATTERNS = (
    r"just check",
    r"pnpm(?: run)? check",
    r"npm run check",
    r"yarn check",
    r"make check",
    r"cargo clippy[^\n`]*",
    r"uv run ruff check[^\n`#]*",
    r"ruff check[^\n`#]*",
    r"uv run mypy[^\n`#]*",
    r"uv run ty check[^\n`#]*",
    r"just test",
    r"uv run python scripts/run_tests\.py[^\n`#]*",
    r"python3? -m pytest[^\n`#]*",
    r"pytest[^\n`#]*",
    r"python3? -m unittest[^\n`#]*",
    r"go test \./\.\.\.",
)
BACKTICKED = re.compile(r"`([^`\n]+)`")
FAST_PATH_LINES = 50

CLAUDE_FAMILY = (
    "generated with claude",
    "co-authored-by: claude",
    "claude.ai/code",
    "claude code",
    "anthropic",
)
CODEX_FAMILY = ("generated with codex", "chatgpt.com/codex", "openai codex", "codex cli", "gpt-5")
GEMINI_FAMILY = ("antigravity", "gemini-", "generated with gemini")
# Escaped, so this file stays plain ASCII. A weak family marker on its own: the
# reason a hygiene denylist exists is that people write these characters too.
UNICODE_PROSE = re.compile(r"[\u2010-\u2015\u2018-\u201f\u2026]")


def facts(
    source: str, *, number: int | None, repo: str | None, descriptor: Path | None
) -> dict[str, Any]:
    """PR metadata from GitHub, or from a descriptor file so a fixture runs offline."""
    if source == "file":
        if descriptor is None:
            raise Park("--source file needs --facts <descriptor.json>")
        data = json.loads(descriptor.read_text())
        if not isinstance(data, dict) or "number" not in data:
            raise Park("PR descriptor must be an object carrying at least a number")
        return data
    if source != "gh":
        raise Park(f"unknown PR source: {source!r}")
    if number is None:
        raise Park("--source gh needs --pr <number>")
    argv = ["gh", "pr", "view", str(number), "--json", PR_FIELDS]
    if repo:
        argv += ["-R", repo]
    code, out, err = command(argv, Path.cwd(), timeout=120)
    if code:
        raise Park(f"gh pr view failed: {err.decode(errors='replace')[-500:]}")
    data = json.loads(out)
    data["repo"] = repo
    return data


def _documented(text: str) -> list[tuple[int, str]]:
    """Every command-shaped string in a project doc: inline in backticks, or in a fence.

    Fences matter: a project that lists its checks in a ``` block rather than inline is
    the common case, and the upstream repository this workflow was built for is one.
    """
    found: list[tuple[int, str]] = []
    fenced = False
    for index, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            candidate = line.split("#", 1)[0].strip().removeprefix("$ ").strip()
            if candidate:
                found.append((index, candidate))
            continue
        found.extend((index, value.strip()) for value in BACKTICKED.findall(line))
    return found


def gate_command(root: Path, base_ref: str) -> dict[str, Any]:
    """Read the pinned validation command out of the base branch's project doc."""
    for name in ("CLAUDE.md", "AGENTS.md"):
        if not git_ok(root, "cat-file", "-e", f"{base_ref}:{name}"):
            continue
        blob = git_bytes(root, "show", f"{base_ref}:{name}")
        matched: list[tuple[int, int, str]] = []
        for index, candidate in _documented(blob.decode(errors="replace")):
            for rank, pattern in enumerate(GATE_PATTERNS):
                if re.fullmatch(pattern, candidate):
                    matched.append((rank, index, candidate))
                    break
        if not matched:
            continue
        matched.sort()
        rank, index, command = matched[0]
        return {
            "source": "base-project-doc",
            "ref": base_ref,
            "commit": git(root, "rev-parse", base_ref),
            "path": name,
            "blob": digest(blob),
            "line": index,
            "command": command,
            "candidates": [value for _, _, value in matched[1:]],
        }
    raise Park(
        f"no validation command documented in {base_ref}:CLAUDE.md or AGENTS.md; "
        "pass --gate-cmd explicitly"
    )


def gate_edited(root: Path, provenance: dict[str, Any], head: str) -> bool:
    """A pull request that edits the command this workflow runs is itself a finding."""
    path = provenance.get("path")
    if not path or provenance["source"] != "base-project-doc":
        return False
    if not git_ok(root, "cat-file", "-e", f"{head}:{path}"):
        return True
    return digest(git_bytes(root, "show", f"{head}:{path}")) != provenance["blob"]


# Files that state what a project claims about itself: who owns what, what governs
# changes, what the project promises. The ground-truth replays measured that every
# missed finding lived in exactly this class of file - in scope for every lens, read
# end to end by none - so setup names them and the implementation lens is instructed
# to read each one whole.
# Rare words match as a word segment (review-charter.md, quorum-roster.toml); ubiquitous
# ones match only as the whole stem, because "security" names eval scenarios and test
# fixtures all over a tree. Segments join with - or _ only, so an extension is never
# swallowed and test_governance.py stays out.
# "requirements" is deliberately absent: requirements.txt is a dependency manifest, and
# it would outrank real authority docs under the root-first cap in most Python trees.
AUTHORITY_NAMES = re.compile(
    r"(?i)^(?:"
    r"(?:[a-z0-9_-]+[-_])?"
    r"(?:governance|charter|roster|maintainers|codeowners|contributing|code_of_conduct"
    r"|policy|standards|guidelines)"
    r"(?:[-_][a-z0-9_-]+)?"
    r"|owners|security"
    r")(\.(md|rst|txt|toml|ya?ml))?$"
)
AUTHORITY_CAP = 12


def authority_files(root: Path, head: str) -> list[str]:
    """Repository-relative authority docs present at the reviewed head, root first."""
    listed = git(root, "ls-tree", "-r", "--name-only", head).splitlines()
    matched = [path for path in listed if AUTHORITY_NAMES.match(Path(path).name)]
    matched.sort(key=lambda path: (len(Path(path).parts), path))
    return matched[:AUTHORITY_CAP]


def author_family(pr: dict[str, Any]) -> dict[str, Any]:
    """Route by author family. Ambiguity falls back to the default table, never a guess."""
    author = pr.get("author") or {}
    haystack = " ".join(
        [
            str(pr.get("body") or ""),
            str(pr.get("title") or ""),
            *[str(commit.get("messageBody", "")) for commit in pr.get("commits") or []],
            *[str(commit.get("messageHeadline", "")) for commit in pr.get("commits") or []],
        ]
    ).lower()
    markers: list[str] = []
    scores = {"claude": 0, "codex": 0, "gemini": 0}
    for family, needles in (
        ("claude", CLAUDE_FAMILY),
        ("codex", CODEX_FAMILY),
        ("gemini", GEMINI_FAMILY),
    ):
        for needle in needles:
            if needle in haystack:
                scores[family] += 2
                markers.append(f"disclosure:{needle}")
    if UNICODE_PROSE.search(str(pr.get("body") or "")):
        # Weak on its own: a hygiene denylist exists precisely because humans do this too.
        scores["claude"] += 1
        markers.append("unicode-punctuation-in-body")
    if author.get("is_bot"):
        markers.append("author:bot")
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    family, top = ranked[0]
    second = ranked[1][1]
    if top == 0 or top == second:
        return {"family": "unknown", "confidence": "none", "markers": markers, "scores": scores}
    return {
        "family": family,
        "confidence": "high" if top >= 2 else "low",
        "markers": markers,
        "scores": scores,
    }


def prepare(
    dest: Path,
    *,
    pr: dict[str, Any],
    repo_path: Path,
    gate_override: str | None = None,
    rules: str | None = None,
) -> dict[str, Any]:
    """Materialise the review workspace and write the sidecar every stage reads."""
    dest.mkdir(parents=True, exist_ok=True)
    root = repo_path.resolve()
    if git(root, "rev-parse", "--is-inside-work-tree") != "true":
        raise Park(f"not a Git checkout: {root}")
    number = int(pr["number"])
    base_branch = str(pr["baseRefName"])
    base_ref = (
        f"origin/{base_branch}"
        if git_ok(root, "rev-parse", f"origin/{base_branch}")
        else base_branch
    )
    head = str(pr.get("headRefOid") or "")
    if not head:
        git(root, "fetch", "--quiet", "origin", f"pull/{number}/head")
        head = git(root, "rev-parse", "FETCH_HEAD")
    if not git_ok(root, "cat-file", "-e", f"{head}^{{commit}}"):
        git(root, "fetch", "--quiet", "origin", f"pull/{number}/head")
    base = git(root, "merge-base", base_ref, head)
    tree = dest / "tree"
    base_tree = dest / "base"
    # A review workspace is disposable, and deleting one leaves its worktrees registered
    # in the reviewed repository. Prune first so a second review of the same pull
    # request is not blocked by the remains of the first.
    git(root, "worktree", "prune")
    for path, sha in ((tree, head), (base_tree, base)):
        if not path.exists():
            git(root, "worktree", "add", "--detach", "--quiet", str(path), sha)
        elif git(path, "rev-parse", "HEAD") != sha:
            raise Park(f"existing worktree {path} is not at {sha}")
    diff = git_bytes(root, "diff", "--no-color", "--no-renames", f"{base}...{head}")
    atomic(dest / "diff.patch", diff, mode=0o644)
    files = diffindex.parse(diff.decode(errors="replace"))
    reviewable = diffindex.reviewable(files)
    lines = diffindex.changed_lines(reviewable)
    provenance = (
        {"source": "operator", "command": gate_override}
        if gate_override
        else gate_command(root, base_ref)
    )
    sidecar: dict[str, Any] = {
        "number": number,
        "repo": pr.get("repo") or remote_slug(root),
        "url": pr.get("url"),
        "title": pr.get("title"),
        "author": (pr.get("author") or {}).get("login"),
        "state": pr.get("state", "OPEN"),
        "isDraft": bool(pr.get("isDraft")),
        "base_branch": base_branch,
        "base_ref": base_ref,
        "base": base,
        "head": head,
        "repo_path": str(root),
        "tree": str(tree),
        "base_tree": str(base_tree),
        "scratch": str(dest / "scratch"),
        "diff": "diff.patch",
        "diff_digest": digest(diff),
        "changed_lines": lines,
        "reviewable_files": sorted(reviewable),
        "excluded_files": sorted(set(files) - set(reviewable)),
        "test_files": diffindex.test_paths(reviewable),
        "gate": provenance,
        "gate_edited": gate_edited(root, provenance, head),
        "authority_files": authority_files(root, head),
        "author_family": author_family(pr),
        "rules": rules or rule_set(pr.get("repo") or remote_slug(root)),
        "fast_path": lines < FAST_PATH_LINES,
        "fast_path_threshold": FAST_PATH_LINES,
    }
    atomic(dest / "pr.json", canonical(pr), mode=0o644)
    atomic(
        dest / "review.json",
        json.dumps(sidecar, indent=2, sort_keys=True).encode() + b"\n",
        mode=0o644,
    )
    (dest / "reports").mkdir(exist_ok=True)
    (dest / "scratch").mkdir(exist_ok=True)
    return sidecar


def remote_slug(root: Path) -> str | None:
    code, out, _ = command(["git", "remote", "get-url", "origin"], root, timeout=30)
    if code:
        return None
    url = out.decode(errors="replace").strip().removesuffix(".git")
    match = re.search(r"[:/]([^/:]+/[^/]+)$", url)
    return match.group(1) if match else None


def rule_set(slug: str | None) -> str:
    """Stage 0 loads per-repo rules; everything outside Bernstein gets the generic set."""
    return "bernstein" if slug and slug.endswith("/bernstein") else "generic"


def sidecar(dest: Path) -> dict[str, Any]:
    path = dest / "review.json"
    if not path.is_file():
        raise Park(f"no review sidecar at {path}; run `review-pr setup` first")
    data = json.loads(path.read_text())
    if data["gate"]["source"] not in ("base-project-doc", "operator"):
        raise Park("validation command provenance is not the base branch or the operator")
    return data
