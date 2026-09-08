---
type: Finding
title: Native merge-back can fetch, rebase and push the integration branch
description: A successful native merge calls safe_push, so a workflow promising local completion must disable that call before any Git I/O, not merely omit an explicit push command.
tags: [bernstein, git, release, compatibility]
status: stable
stale_after: "2026-10-08T00:00:00Z"
generated: { by: codex/gpt-6, at: "2026-09-08T13:40:15Z" }
sources:
  - id: merge
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/agents/spawner_merge.py
    title: merge_back calls safe_push after local merge success
  - id: push
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/git/git_basic.py
    title: safe_push fetches, may rebase, and pushes when origin exists
  - id: patch
    resource: ../../../skills/build-run/scripts/prepare-engine.py
    title: Verified operator source prerequisites
  - id: test
    resource: ../../../bernstein_operator/tests/test_delivery.py
    title: Local-only safe_push contract rejects any Git I/O
---

# Finding

Native merge-back invokes `safe_push` after landing the agent branch. With an
origin remote, that helper fetches and can rebase the integration branch before
pushing. A driver that never explicitly pushes can therefore still publish code
and change the identities of commits it intends to review.[^merge][^push]

The operator's source prerequisite short-circuits `safe_push` before any Git
operation when `BERNSTEIN_OPERATOR_LOCAL_ONLY=1`. Readiness verifies the patch;
the driver sets the variable for native runs. This protects the engine's own
merge-back path. Executor instructions still prohibit agent-authored pushes;
the patch is not a Git permission sandbox.[^patch][^test]

An upstream replacement must prove both that no remote write occurs and that
no fetch/rebase changes the reviewed commit range. Checking only that the final
push command is absent is insufficient.[^push][^test]

[^merge]: [Native merge-back](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/agents/spawner_merge.py).
[^push]: [safe_push](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/git/git_basic.py).
[^patch]: [Operator source preparation](../../../skills/build-run/scripts/prepare-engine.py).
[^test]: [Delivery contracts](../../../bernstein_operator/tests/test_delivery.py).
