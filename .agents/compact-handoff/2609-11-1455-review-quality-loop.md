# Handoff 2026-09-11 14:55Z build-workflow@feat/review-pr

Supersedes 2609-11-1430-review-quality-loop.md for position and next steps; the
1341 file's Decisions and Findings still hold except where amended here.

## Position

Goal loop (plan docs/plans/2609-11-review-quality.md; /goal hook: proceed until all
ready, report verified numbers + one-command `just review <github-pr-url>`).

- Corpus gate GREEN: run 6 rescored 14/14 RECOVERED, 0 MISFILED, 0 MISSED, 7 extras
  (floor 8/8, bar 6/6). Ledger rows committed (46a10cf and earlier).
- Wave 4 milestone DONE: bernstein#5791, full stages.yaml, API lane, pond-captured.
  Score vs hand review at head 1713ccc1: 3 of 4 recovered; the miss is the
  trivy.py:324 `c:data` colon-anchoring nit whose own author said "I would not
  change the behaviour". 18 tool findings total (15 CONFIRMED, 2 PLAUSIBLE),
  14 not in the hand review, recommendation comment-only, 11 payload comments.
  Workspace ~/pj/reviews/sipyourdrink-ltd-bernstein-pr5791 (report.md,
  summary.json, pr-review.json). NOT posted to GitHub (the run asked; nobody
  answered y).
- Hallucination check: the one bad CONFIRMED was CHECK:gate "validation fails on
  head" whose evidence was "Network is unreachable" building the venv (sandbox
  blocks egress). Fixed: gate + claims share sandbox.could_not_run(); environment
  refusal is inconclusive, never a finding (c3f6e53, with tests). First resume
  also parked on claims `"expect": null` - fixed 560e824 (null takes the default;
  invalid strings still park). Verdict for #5791 unchanged by the gate fix
  (13 other CONFIRMED findings keep it comment-only); only the stated reason
  was wrong.
- Operator directive (this window, verbatim intent): "stop test our runs on
  gemini models... switch those to sonnet 5... we'll swap it to free/cheap
  alternatives later anyways." DONE for test lanes: stages-fast.yaml all lenses +
  claims on claude/claude-sonnet-5, verifier codex/gpt-5.6-sol (same-family
  verification is measured-forbidden; codex content filter risk on gating
  vocabulary documented in the template, parks loudly); gating keeps
  forbid_families: [codex]. stages-opencode.yaml verifier gemini -> claude sonnet.
  Commits 213b24f, a810de5; template tests re-pinned. Production stages.yaml
  still has gemini (one lens slot + verifier entries) - the ONLY remaining gemini
  spend; swap not yet authorized.
- python-dev skill was updated (lefthook, ruff 0.16 default-rules warning, pytest
  strict ini key). Measured repo gaps: select list makes ruff weaker than default
  (100 findings under default rules), dead pre-commit dev dep, minor pytest/asyncio
  ini items. Operator: "have subagents to deal with all the mess" - conformance
  agent launched (see agents below).

## In flight (background)

1. Opus worktree agent chore/pythondev-conformance (ruff 0.16 default rule set +
   ~100 findings, remove pre-commit dep, pytest strict=true +
   asyncio_default_fixture_loop_scope, sync-skill-code, full bar). Notifies on
   completion; task output under scratchpad tasks/a5e65c1b8758b2841.output.
2. DONE, ruled ACCEPT, NOT yet merged: feat/family-swap at 6deca84 (worktree
   ~/pj/worktrees/.treehouse/build-workflow-4d7558/2/build-workflow). One-flag
   `--family` whole-run swap + 4 real hazard fixes (model fallback, routing-value
   validation at load, readiness.routed(), pond_adapter registry field,
   Task.family default removed). 283 review tests pass there.
3. DONE, ruled ACCEPT with the lane FENCED (not production-ready): feat/pi-family
   at 9292c5e (worktree .../build-workflow-4d7558/1/build-workflow). pi wired
   (stages-pi.yaml, pondsync, proc allowlist, strip_paths [.pi, .agents/skills]).
   CRITICAL FINDING: pi redirects do NOT close HOME-rooted discovery - a
   redirected pi session loaded all 22 operator skills and EXECUTED
   ~/.pi/agent/extensions/*.ts; pi-acp forwards no --no-skills/--no-extensions,
   so only a per-session HOME or different adapter closes it. Documented in the
   template + lanes reference. Lane must not run real PRs until HOME isolation.

## AMENDED 15:10Z - merges DONE

All three branches are MERGED into feat/review-pr (4b8d88a family-swap, 91a7b84
pi-family, 3811fd5 conformance). Conflicts resolved: template tests repinned to
the new opposite() tuple API and claude/codex routing; both capture-test additions
kept; claims.py took HEAD then `just fix` reapplied the mechanical rules. Bar
after final merge: just check ALL PASSED, suite 359 passed / 11 failed (the known
engine-patch parks, same set) / 1 skipped. Worktree slots not yet returned
(treehouse return, 3 slots under ~/pj/worktrees/.treehouse/build-workflow-4d7558/).
Steps 1-2 below are done; remaining work = steps 3-5 (final report, just ship,
key reminder + open questions).

## Next steps

1. When the conformance agent notifies: read report, rule on it.
2. Merge queue into feat/review-pr (milestone is finished, tree is free):
   feat/family-swap first, then feat/pi-family (expect a pondsync.py conflict -
   both touched it; family-swap added pond_adapter preference, pi added the
   pi source), then chore/pythondev-conformance (mechanical conflicts likely;
   resolve then re-run `just --justfile bernstein_operator/Justfile fix` + check).
   Full bar after each merge: stage3/sessions/capture/execution tests + just check.
   Then `treehouse return` the worktree slots.
3. Final goal report: baseline run-2 8/14 -> run-6 14/14 rescored (0 misfiled,
   0 missed); milestone 3/4 hand-recovered + 14 extras, 0 hallucinated CONFIRMED
   after the gate fix (state the gate artifact honestly); one-liner
   `just review https://github.com/owner/repo/pull/<n>` (needs local clone at
   ~/pjv/<owner>/<repo>, lowercased).
4. `just ship` (bumps both plugin.json, commits, pushes) - nothing pushed yet.
5. Remind operator: revoke temp GEMINI_API_KEY in ./.env (only production
   stages.yaml still routes gemini; fast loop no longer needs the key).
   Open questions Q1-Q3 from the 1341 handoff still open, plus new Q4/Q5 below.

## Decisions (this window)

- Null claim expect = unspecified -> default exit_zero; invalid string still parks
  (expect is a deciding field). 560e824.
- Environment refusal (127 / not found / Network is unreachable / Failed to
  download / name resolution) is could-not-run, shared detector in sandbox.py;
  gate emits no finding, claims mark unchecked. c3f6e53.
- Test lanes off gemini per operator; verifier must stay cross-family, so codex
  in stages-fast, claude in stages-opencode. 213b24f, a810de5.
- family-swap branch accepted as-is; pi branch accepted but lane fenced pending
  HOME isolation decision.
- Merges deferred until milestone finished (done) - now unblocked.

## Findings

- Claude adapter accepts passthrough model ids at session creation
  (claude-sonnet-5 fine via --model); fast loop now draws on the operator's
  Claude subscription - a 14-case corpus run competes with the driver's own
  usage window.
- The milestone run resumes from session receipts: run --dest on an existing
  workspace reuses receipts (verified - resume redid only claims onward).
- pi HOME leak (see above) - worse class than opencode's (~/.claude text): code
  execution in the reviewer process.
- Ruff 0.16.6 + select=[E,F,I,UP] is weaker than no config (413 default rules);
  measured 100 findings on this repo under defaults.

## Open questions

Q1-Q3: unchanged from 2609-11-1341 handoff (OpenRouter key channel, ENV_ALLOWLIST
exception, Zen-lane switch for the fast loop - Q3 now PARTLY mooted: fast loop is
on sonnet; recommend closing Q3 as done-differently).
Q4: pi lane - invest in per-session HOME isolation (runner change), or park the
lane until an adapter forwards --no-skills/--no-extensions? Recommend: park;
revisit if pi becomes a wanted shadow lane.
Q5: swap production stages.yaml off gemini too? Recommend: yes at next milestone,
same pattern (sonnet lenses stay, gemini slots -> cheap alternative when chosen);
until then the temp key is only needed for production milestone runs.

## Undone instructions

- Final goal report + `just ship` (blocked on merges).
- GEMINI_API_KEY revocation reminder to operator (queued for final report).
- #5791 review payload not posted (operator never asked to post).

## References

Plan: docs/plans/2609-11-review-quality.md (updated this window).
Prior handoffs: .agents/compact-handoff/2609-11-1430-*.md, 2609-11-1341-*.md.
Milestone artifacts: ~/pj/reviews/sipyourdrink-ltd-bernstein-pr5791/.
Eval ledger: docs/review-ledger/evals.jsonl. Bernstein run ledger:
~/pjv/sipyourdrink-ltd/bernstein/docs/review-ledger/runs.jsonl.
Commits this window: 560e824, c3f6e53, 213b24f, a810de5 (+ plan edit uncommitted).
Scratchpad: /tmp/claude-10003/-home-tenequm-pj-build-workflow/a0422db5-3d18-438b-ab30-86ef23ec10be/scratchpad/.
