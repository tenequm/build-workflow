# /review-pr path A - compact handoff (updated 2026-09-12 09:30 UTC)

Read this before trusting the conversation summary. Plan: `docs/plans/2609-11-review-v3.md`.

## State: cutover and purge are COMMITTED. Nothing is pushed.

```
f3594a5  refactor(review-pr)!: purge the driver-owned review pipeline   (102 files, -14,112)
929787c  feat(review-pr)!: the cutover to stock bernstein, on a free local lane
4d0d2a0  feat(review-pr): an eval harness that can observe a run to its end
c6b3845  fix(build-run): two engine patches for wedged runs and host-local personas
```

`skills/review-pr/` = SKILL.md + templates/review-goal.md + templates/review-seed.yaml.
No Python. Working tree clean, `just check` green, acceptance 96 passed. The operator
CLEARED the plan's 13/14 gate ("imaginary, wasting time") and authorised the purge on the
partial evidence: 7 RECOVERED / 1 MISFILED / 1 ERROR of 9, one honest partial ledger row
(`"partial": true`) in `docs/review-ledger/evals.jsonl`. Do not call the purge gate-proven;
it is operator-authorised.

## THE HEADLINE FACT (09:06 UTC): the retry storm is fixed and proven

The goal-text rule (an acceptance check must be the artifact the worker was asked for;
landed in 929787c) was probed on the exact case that failed: **floor/case-06 RECOVERED in
2135s with 3 extra and ZERO failed tasks**, where the unfixed goal took 10,821s to ERROR
with 72 failed tasks. All three engine failure modes now have answers: wedge (stall
detector), lane outage (lane_down detector + case cancellation), retry storm (goal rule,
verified). agy quota (subscription lane) verified clear 09-12 with a real model call.

## THE PLAN THE USER ASKED FOR (proposed 09:22 UTC; user asked to compact BEFORE saying go)

The user's direction, near-verbatim: tired of measuring; wants to use the workflow on
REAL work; engine should be validated on ONE case until it stops polluting runs; wants a
decent-quality workflow by end of 2026-09-12 with a clean baseline. The proposed phases:

1. **Baseline reset** (one commit, no model runs): archive ALL 10 unchosen synthetic
   cases to `fixtures/review-pr-cases/archive/`; keep `real/` untouched; rename the four
   keepers FLAT (no floor/bar dirs, no tier field, no tier wiring in harness.py):
   - `case-01-off-by-one`        (was floor/case-03: pagination `(total+per_page)//per_page`)
   - `case-02-pr-body-test-claim`(was floor/case-02: pr.md claims calculate_range tests)
   - `case-03-prompt-injection`  (was floor/case-05: "approve immediately" comment; scores find+disobey)
   - `case-04-authority-omission`(was bar/bar-05: GOVERNANCE.md mandates 4 engines, doc lists 3)
   Harness edits are small: `cases()`, `label()`, workspace layout at harness.py:673 stop
   assuming a tier parent; TIERS goes away. Add `"corpus": "v2"` to the ledger record.
   case-01 is the sanity anchor BY POSITION - one README sentence, no schema.
2. **Engine soak**: run `case-01-off-by-one` 3x back to back (~30 min each). Pass = 
   RECOVERED + zero failed tasks + clean sweep, 3/3. Any orchestration failure is
   stop-the-line. This becomes the standing "smoke case" rule: smoke after engine/seed
   changes; the 4-case set ONLY after goal-text changes; nothing bigger ever again.
3. **Real PR vs the operator's own hand review, zero harness work**: run /review-pr
   per SKILL.md on `sipyourdrink-ltd/bernstein` PR **5737** (public - verified; 271 lines,
   OPEN, governance-doc shape). Compare BY EYE against `fixtures/review-pr-cases/real/pr5737.json`
   (4 hand findings with fates). Deliver a side-by-side: recovered / missed / novel.
   If the free lane embarrasses itself, rerun same PR on the quality lane.
   (real/ facts: repo is PUBLIC, PRs 5736 merged / 5737 open / 5739 open, 60/271/548 lines.)

Standing bar after today: smoke case (engine), 4-case set on goal changes (ledger row),
5-minute skim vs report on every real review; misses distill into new cases per the
corpus README's existing loop - the only way it grows.

## Corpus knowledge from the 4-case audit (subagent, 09-12; do not re-derive)

- **floor/case-04 is AMBIGUOUS** - expected category maps to `correctness` only where
  `convention` is equally defensible (flake8 max-line-length). Its MISFILED was the
  corpus's fault. Never widen CATEGORY_ALIASES to absorb a miss.
- **floor/case-06 has a bad anchor window** (item_cache.py:14-16 excludes the rewritten
  docstring at 13, where the goal says to anchor). Both are being archived anyway.
- **Every bar case carries a second objectively defensible finding** (undocumented flags,
  missing requirements.txt, commands that do not exist), so `extra_findings` on bar cases
  is NOT a precision metric. bar-01's "9 extra" was not noise.
- Do NOT raise `--jobs` past 2 on the free lane: 429s on 36 of 67 sessions at 4 in flight.

## Engine: 3.19.2, SIX patches. Run mechanics.

Checkout `~/pj/bernstein-operator-engine` detached at `ebad8f5b3`; patches applied by
`skills/build-run/scripts/prepare-engine.py`; installed tree under python3.14
(`~/.local/share/uv/tools/bernstein/lib/python3.14/site-packages/bernstein/`).
Tests: `cd bernstein_operator && uv run python scripts/acceptance.py` (96 passed).
Pre-commit reality check: `just --justfile bernstein_operator/Justfile check` (bare ruff
from repo root passes things check rejects). Hard-won run facts:
- A bernstein run ends only at a `/proc` cwd sweep: `harness.sweep(pathlib.Path(dir))`
  (a Path, not a str). The CLI returning means nothing; `--wait` bounds only the waiter.
- pi writes a 0-byte log and meters 0 tokens - same shape as a refused lane.
- Numbers from before c6b3845 are persona-polluted (third-party catalogue replaced role
  prompts; `catalogs: []` in the seed + engine patch six close it).
- Every seed needs the `tuning:` floors or workers are SIGTERMed at the 90s grace.
- Do not set aggressive `--timeout`; the report and the detectors end runs.

## Operator follow-ups (not mine to do)

`just ship` after the user approves (it PUSHES - ask first); **rotate the glim gateway
key** (leaked into a subagent transcript 09-11); cancel the OpenCode Go subscription.

Scratchpad: /tmp/claude-10003/-home-tenequm-pj-build-workflow/978f4a1f-61f4-4553-b6c7-71cd16996864/scratchpad/
Probe evidence: /tmp/review-eval-20260912T083138Z (case-06 RECOVERED), log `<scratchpad>/goalfix-case06.log`.
Dead gate workspaces (re-scoreable): /tmp/review-eval-20260912T024812Z.
