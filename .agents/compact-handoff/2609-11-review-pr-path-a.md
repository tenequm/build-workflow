# /review-pr path A - compact handoff (updated 2026-09-12)

Read this before trusting a conversation summary. Plan: `docs/plans/2609-11-review-v3.md`.

## Where this landed

/review-pr is on stock bernstein. The skill owns no orchestrator and ships no Python:
`templates/review-goal.md` carries the doctrine, `templates/review-seed.yaml` the routing,
and a stock `bernstein run` does the rest. The driver-owned design is deleted; git history
holds it, and `docs/knowledge/references/retired-driver-owned-review-design.md` records
what it was.

```
929787c  feat(review-pr)!: the cutover to stock bernstein, on a free local lane
4d0d2a0  feat(review-pr): an eval harness that can observe a run to its end
c6b3845  fix(build-run): two engine patches for wedged runs and host-local personas
```
plus the purge commit that follows 929787c.

## The gate, and why it did not gate

The plan's step 3 set a bar of 13/14 RECOVERED on the frozen corpus before the purge could
land. **The operator cleared that bar on 2026-09-12** - it was blocking forward motion for
a number the corpus cannot honestly produce - and authorised the purge directly. The
evidence that exists is one partial ledger row: **7 RECOVERED, 1 MISFILED, 1 ERROR of 9**
on the free pi lane, re-scored from the surviving workspaces after the remaining five bar
cases were cancelled mid-run. Do not describe the purge as gate-proven; describe it as
operator-authorised on that evidence.

Two of the nine are corpus defects, not model failures, and a case audit confirmed both:

- **floor/case-04 is ambiguous.** Its expected category `authority-file contradiction`
  maps to `correctness` only, but the defect is a flake8 `max-line-length` mismatch where
  `convention` is at least as defensible. Do not use it in a lane comparison, and do NOT
  widen `CATEGORY_ALIASES` to absorb it - editing the corpus to pass your own run destroys
  the only regression signal this skill has.
- **floor/case-06 has a bad anchor window.** `src/item_cache.py:14-16` excludes the
  rewritten docstring at line 13, so a reviewer that anchors the broken promise where the
  goal tells it to scores MISSED.

Also from that audit, and it changes how the ledger reads: **every bar case carries a
second objectively defensible finding** (an undocumented flag, a missing requirements.txt,
a command that does not exist). `extra_findings` on a bar case is therefore not a clean
precision metric - bar-01's "9 extra" is not a precision failure.

## The three failure modes, and which detector catches which

- **Wedge**: `open=0 agents=0` forever, productivity counters flat. Caught - `stalled()`.
- **Lane outage**: every agent log a single `error:` line (an exhausted subscription, a
  gateway that is not listening). Caught - `lane_down()` scores ERROR, never MISSED, and
  cancels the cases that have not started.
- **Retry storm**: counters move, failures compound, only the deadline ends it. NOT caught
  by any detector. Its known cause is addressed in the goal text (see below), not in code.

## The goal-text rule that cost three hours to find

The lead was attaching invented file-existence acceptance checks
(`test -s /tmp/bernstein-review-<id>/lens5.md`) to tasks whose workers had been told to
publish through the KB instead. Three cases, three different invented paths, 72 failed
tasks against 11 done on case-06. The fix is two sentences in the "You are the lead"
paragraph of `review-goal.md`, landed in 929787c. See
`docs/knowledge/findings/manager-invented-acceptance-tests-fail-good-work.md`.

## Next, if you want a number

A four-case comparison, the same cases on both lanes, audited as clean and valid:
**bar/bar-05, floor/case-05, floor/case-02, floor/case-03** - four different finding
shapes and four different scoring paths (authority-file omission, injection plus the
obedience check, PR-body claim via `scope: meta`, in-hunk arithmetic). Roughly 2h per lane
at `--jobs 2`. Do NOT raise `--jobs` past 2: 429s appeared on 36 of 67 sessions at 4 in
flight. It can establish that both lanes are alive and contract-compliant and give honest
wall-clock per lane; with n=4 and one trial each it cannot establish a rate.

agy quota (the subscription lane's workers) was verified clear on 2026-09-12 with a real
model call.

## Engine: 3.19.2, SIX patches

Checkout `~/pj/bernstein-operator-engine` detached at `ebad8f5b3`; patches applied by
`skills/build-run/scripts/prepare-engine.py`. Installed tree is under **python3.14**:
`~/.local/share/uv/tools/bernstein/lib/python3.14/site-packages/bernstein/`. Tests ONLY
via `cd bernstein_operator && uv run python scripts/acceptance.py` (96 passed). Run the
real pre-commit check with `just --justfile bernstein_operator/Justfile check` - a bare
`ruff` from the repo root passes things that check rejects, because the config resolves
relative to bernstein_operator.

## Hard-won facts (all measured on this host)

- A bernstein run does not end when its driver does, nor when the CLI returns. `--wait`
  bounds only the waiter. Only a `/proc` cwd sweep ends a run:
  `harness.sweep(pathlib.Path(dir))` - it takes a Path, not a str.
- bernstein cannot tell "this agent did nothing" from "this CLI reports nothing": pi
  writes a 0-byte log and meters 0 tokens, which is the same shape as a refused lane.
- Until patch six, EVERY run ever measured here - ours and the old driver's - ran with a
  third-party persona replacing the role prompt (`reviewer` = a UI design critic, `qa` = a
  GIS engineer). Invisible in every log; only `/proc/<pid>/cmdline` on a live worker shows
  it. Numbers from before c6b3845 are persona-polluted.
- Do NOT set an aggressive `--timeout`. The detector and the report, not the clock, end a
  run.
- Every seed needs the `tuning:` floors, or workers are SIGTERMed at the 90s liveness
  grace.

## Operator follow-ups (not mine to do)

`just ship` after the commits land (it pushes - ask first); **rotate the glim gateway key**
(it leaked into a subagent transcript on 09-11); cancel the OpenCode Go subscription.
