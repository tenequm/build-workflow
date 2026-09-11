# Handoff 2026-09-11 14:30Z build-workflow@feat/review-pr

Supersedes 2609-11-1341-review-quality-loop.md for position and next steps; that
file's Decisions and Findings still hold except where amended here.

## Position

Same goal loop (plan docs/plans/2609-11-review-quality.md; /goal hook: proceed until
all ready, report verified numbers + `just review <github-pr-url>`). All three
subagents landed and were ruled on; every iteration-2 fix is committed. The
iteration-2 corpus measurement (run 6) is RUNNING at --jobs 3 on the metered
API-key lane: background task b0ml2pty8, workspace /tmp/review-eval-20260911T141028Z,
8/14 cases had summary.json at 14:26Z. Its scoreboard is the next decision input.

Eval run history today (ledger docs/review-ledger/evals.jsonl):
- run 1 0/14 (infra), run 2 RECOVERED 8/MISFILED 1/MISSED 5 at rev 74b203e.
- run 3: INVALID - subscription 5h window exhausted mid-run ("Usage Limit Reached"
  notice as clean end_turn); the 4 cases that ran before exhaustion (01,02,03,05)
  all RECOVERED, incl. three iteration-2 targets. Ledger row committed 9da663d.
- run 4: INVALID - API-key lane at --jobs 7, all 14 parked on per-minute 429s.
- run 5: floor/case-01 alone at --jobs 1 on API lane: RECOVERED. Tier confirmed fine.
- run 6: full corpus --jobs 3, in flight.

## The metered API-key lane (new since last handoff)

- Key: GEMINI_API_KEY in ./.env (gitignored; TEMPORARY - user will revoke; never
  print it). Launch pattern: `set -a && . ./.env && set +a && export
  GEMINI_HOME=$HOME/.gemini-api-lane && just eval --jobs 3`.
- ~/.gemini-api-lane/antigravity-acp/settings.json = {"auth":{"type":"gemini-api-key"}};
  subscription lane untouched; dropping the two env vars restores it.
- GEMINI_API_KEY + GEMINI_HOME added to ENV_ALLOWLIST (proc.py) with exposure-parity
  comment. Commit: 'feat(review-pr): a metered gemini API-key lane via GEMINI_HOME
  isolation'.
- Concurrency: 7 dead, 1 proven, 3 in flight. TPM-bound with ~120k briefs.
- CAVEAT for Wave 4: pondsync stage_agy_root() reads ~/.gemini; with GEMINI_HOME
  relocated, agy conversations land under ~/.gemini-api-lane - a pond-captured
  (milestone) run on the API lane needs a pondsync source adjustment OR the
  subscription lane back. Eval runs are --no-pond so unaffected.
- Subscription reset timer: Monitor task b04kxma2y fires ~17:23Z. Stop it (TaskStop)
  if the API lane carries the day, or use the reset to return to the subscription.

## New commits since 13:41 handoff

0cd583f docs (handoff+plan+ledger), 230bc72 + follow-ups docs(knowledge) model-lane
reference, afd2a9c quota-notice provider signature + test, 9da663d ledger row,
chore gitignore .env, feat proc.py allowlist, docs(knowledge) batch (reviewer-
reconfiguration finding, quota false-approve amendment, metered-lane section,
measured-claim fix). Agent commits c1de77a/eca0010/3a06f01 (opencode lane, rubric
guard, config strip) and fdc0839/fe673b4/ef990f1/0a82117 (floor fixes) all in.
Nothing pushed; `just ship` owed at the end for skill-code commits.

## Rulings made on agent reports

- a2c7cc report-only items: houserules "PR carries agent config" finding DEFERRED
  (receipt/ledger record suffices, lean bar); --no-pond-fold knob DEFERRED until
  shadow comparisons actually run; claude CLAUDE.md-via-settingSources probe LOW.
- pi dig: pond CAN scope pi per-run (three redirect routes, verified twice); my
  earlier claim refuted; captured in KB reference. bernstein pi adapter shallow/dated.
- muse-spark smoke (bar/bar-01, stages-opencode.yaml): lenses found the planted
  defect dead-on (+5 plausible extras); run parked honestly on dead gemini verifier.
  Free-lane recall present at bar tier; verification-side precision still unmeasured.

## Next steps

1. Read run 6 scoreboard (task b0ml2pty8 notifies; output file under scratchpad
   tasks/). Commit the new ledger rows. If floor ~8/8 and bar 6/6: proceed. Else
   triage misses via a gemini lane (pattern scratchpad/lane-misstriage/brief.md).
2. Wave 4 milestone: full-routing paid run on fresh unseen PR (candidate
   bernstein#5791 if its 2 inline comment fates resolved; NOT #5737). Uses
   production stages.yaml WITH pond - mind the GEMINI_HOME/pondsync caveat above.
3. Final goal report: verified numbers + `just review https://github.com/owner/repo/pull/<n>`.
4. `just ship` for skill-code commits. 5. Remind user to revoke the temp key
   (.env) and decide open questions Q1-Q3 of the 1341 handoff (OpenRouter channel,
   Zen lane switch, milestone PR).

## References

Prior handoff: .agents/compact-handoff/2609-11-1341-review-quality-loop.md (decisions,
findings, open questions). KB: docs/knowledge/ (model lanes reference + today's
findings). Scratchpad: /tmp/claude-10003/-home-tenequm-pj-build-workflow/a0422db5-3d18-438b-ab30-86ef23ec10be/scratchpad/.
