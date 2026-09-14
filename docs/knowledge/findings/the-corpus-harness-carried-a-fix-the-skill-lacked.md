---
type: Finding
title: A corpus that passes proves the harness's invocation, not the skill's, and the two had silently diverged
description: /review-pr's first real run died six seconds in on "FATAL: no adapter configured" while four green-ish corpus runs the same afternoon proved nothing about it. The eval harness set BERNSTEIN_SEED_PATH and the skill's documented invocation did not; the detached orchestrator re-resolves its seed and falls back to a file that only exists for the harness. An eval harness that reimplements the invocation instead of calling it tests a second implementation.
tags: [review-pr, bernstein, evaluation, corpus, invocation]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-14T16:35:00Z" }
sources:
  - id: failure
    resource: "the first pond#237 launch, 2026-09-14T16:22Z in /tmp/pond-237, run from the SKILL.md invocation verbatim. `.sdd/runtime/orchestrator-debug.log` records six identical cycles about five seconds apart: `resolved seed_path=/tmp/pond-237/bernstein.yaml (from --seed-path=None, exists=False)` followed by `FATAL: no adapter configured`. The run log showed only the banner, the adapter list, and a summary of one declared task with zero agents."
    title: the launch that failed on a message naming the wrong problem
  - id: harness
    resource: /fixtures/review-pr-cases/harness.py
    title: the eval harness, which sets the variable the skill did not
  - id: skill
    resource: /skills/review-pr/SKILL.md
    title: the invocation, now carrying the variable and the failure signature
---

# What happened

Four four-case corpus runs passed their plumbing checks that afternoon - nine agents
under nine custom roles, zero ERROR, reports at the contract path. The first run against
a real pull request, launched from `SKILL.md` verbatim, produced no agents at all and
exited in six seconds.

`--seed` reaches the `bernstein run` CLI, but the CLI hands off to a detached
orchestrator that re-resolves the seed on its own. Its only other source is
`<workdir>/bernstein.yaml`. With the seed living in the skill directory that file does
not exist, so the orchestrator started with no `role_model_policy`, could not name an
adapter, and died on a message that reads like a missing CLI installation.[^failure]

The harness had never hit it because of one line it carries and the skill did not:

```python
env = {**os.environ, "BERNSTEIN_SEED_PATH": str(Path(options.seed).resolve())}
```

Its comment already explained the hop - "the orchestrator detaches and re-reads its seed
from the environment" - so the knowledge existed. It just lived in the wrong artifact,
in the one place no consumer of the skill ever reads.[^harness]

# The general lesson

**An eval harness that reimplements the thing it evaluates is testing a second
implementation.** The corpus was built to be the regression signal for /review-pr, and it
faithfully was - for `harness.py`'s invocation. Every step the harness and the skill share
was proven all afternoon; the one step where they differed was proven by neither, and it
was the step that decides whether any agent runs.

Two properties made the divergence invisible:

- The harness constructs its argv in code rather than executing the documented command,
  so the two can drift without any check failing.
- The failure surfaces only in `.sdd/runtime/orchestrator-debug.log`. The run log shows a
  clean banner, a correct adapter list, and a summary - nothing that reads as broken. A
  reader watching the run log would conclude the lane was healthy.

The fix was to state the variable and its failure signature in the invocation.[^skill]
The durable form of the fix is narrower: where an eval harness must diverge from the
documented invocation, the divergence is the thing to write down, because it is by
definition the part the corpus cannot prove.

# What the message means when it appears

`FATAL: no adapter configured` from the orchestrator is a seed that never arrived, not a
CLI that is missing. Check `.sdd/runtime/orchestrator-debug.log` for the resolved
`seed_path` before touching adapters, `~/.codex/config.toml`, or PATH.

[^failure]: the launch that failed on a message naming the wrong problem
[^harness]: the eval harness, which sets the variable the skill did not
[^skill]: the invocation, now carrying the variable and the failure signature
