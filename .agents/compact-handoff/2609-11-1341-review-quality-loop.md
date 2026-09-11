# Handoff 2026-09-11 13:41Z build-workflow@feat/review-pr

## Position

Driving /review-pr to /polish-grade quality per docs/plans/2609-11-review-quality.md,
under an active /goal hook: "proceed until all ready and report at then end with
complete verified numbers and usable one command line simple invocation command that
does the review on any pr github link for me." The one-liner exists: `just review
<github-pr-url>`. The corpus, harness, and lever (a) are landed and measured; we are
mid Wave 3 iteration 2 with three subagents still working in this checkout (their
uncommitted edits are in the working tree - do NOT commit or clean them; they pathspec-
commit their own files).

Eval measurements so far (ledger: docs/review-ledger/evals.jsonl):
- Run 1 (workspaces /tmp/review-eval-20260911T125608Z): 0/14, infrastructure (gemini
  429 burst + verifier-family park), fixed by 97279dc + fb26e9e.
- Run 2 (workspaces /tmp/review-eval-20260911T131457Z) at rev 74b203e:
  RECOVERED 8, MISFILED 1, MISSED 5 of 14. Bar tier 6/6 found (5 RECOVERED +
  bar-03 MISFILED on a scorer alias gap). Floor 3/8: case-04/05 parked (fixes in
  flight), case-02/03/08 missed via lens crowding + unchecked test claims.
- Ground-truth baseline: replay 3 vs bernstein#5737 = 8/14 recall, 2/3 correctness,
  0 hallucinations, $26.74 list-price floor.

## Next steps (in order)

1. Wait for the three in-flight subagents (they notify; do not poll):
   - a2c7cc3afae05e292: opencode lane (c1de77a landed; still owed: case-04 park fix
     = verifier scratch/ allowlist widening at runner.py:236 + command-rubric-names-
     missing-path guard; opencode.json strip in session worktrees; claude adapter
     --setting-sources=project,local vulnerability check REPORT).
   - adbe3078bb6d4d524: iteration-2 fixes (fdc0839, fe673b4, ef990f1 landed; still
     owed: commit 4 = findings.py suggestion fix - drop `or not replacement` at
     findings.py:122, drop-and-record at :192).
   - a9c5f98384e3052f0: pi pond per-run scoping + bernstein pi support dig ->
     scratchpad/pi-pond-bernstein.md.
2. Rule on their reports (accept/reject; diffstat + lean bar).
3. Re-run the corpus: `cd /home/tenequm/pj/build-workflow && just eval` (background,
   ~40-70 min at --jobs 2). Expect floor near 8/8 and bar 6/6 after fixes; ledger row
   appends automatically. Triage any remaining miss via a gemini lane (pattern:
   scratchpad/lane-misstriage/brief.md).
4. Consolidate model research into docs/knowledge as one Reference concept (sources:
   scratchpad/model-options-report.md, opencode-zen-report.md, pi-openrouter-runbook.md,
   pi-pond-bernstein.md when it lands). Load okf-project-knowledge-base skill first;
   regen with `python3 scripts/kb_index.py`.
5. Wave 4 milestone: when bar+floor green, one full-routing run against a fresh unseen
   PR (candidate bernstein#5791 once its 2 inline comments' fates resolve; NOT #5737 -
   bar training data). Paid; production stages.yaml.
6. Final report to the user: verified numbers (floor/bar scoreboards, milestone
   recovered-of-N, zero-hallucination count) + the one-liner
   `just review https://github.com/owner/repo/pull/<n>`.
7. Eventually `just ship` (skill edits require ship, not bare push; docs-only commits
   do not).

## Decisions

- Lever (a) + authority-regex fix applied BEFORE first corpus baseline; replay 3 is
  the baseline; separate commits preserve attribution (recorded in plan Wave 2).
- Free-tier model routes that train on prompts: OPEN-SOURCE REPOS ONLY (operator,
  2026-09-11). KB: docs/knowledge/decisions/free-tier-models-are-open-source-only-lanes.md.
- Shadow model runs will be compared FROM POND later -> capture with model id, family,
  lens, run identity is a hard requirement (plan, forward requirement section).
- Model picks: opencode Zen muse-spark-1.3-contributor-free = ADOPT-TRIAL (AA 48);
  nemotron-3-ultra = SKIP (TB 1%, 6 tok/s, ToS); OpenRouter :free tiers dead (rate
  limits); opencode is the OpenRouter-key vehicle, pi fallback (under re-dig).
- bar-03 stays frozen; the fix was scorer-side (CATEGORY_ALIASES design alias,
  fdc0839). Cases are never edited to make a model pass.
- Lever (b) (normative-source check) stays in the drawer: bar-04/06 recovered without
  it. Draft ready at scratchpad/lane-leverb/{report.md,proposal.diff}.
- Park rulings: case-04 = brief defect (scratch grant + rubric guard), case-05 =
  boundary too strict (empty replacement is deletion). Both being fixed.
- Fast loop verifier = claude-sonnet-5 (cross-family law; small real-money cost).
  agy ACP server serves ONLY gemini models (probed; claude ids refused).
- Eval default --jobs 2 (429 burst: 36/67 sessions hit at 4x concurrency).

## Findings (verbatim where it matters)

- Gemini 429s end turns with `[done] end_turn` exit 0; runner.provider_failure()
  (97279dc) now fails sessions whose stream ENDS on: model unreachable |
  RESOURCE_EXHAUSTED | RATE_LIMIT_EXCEEDED | Agent execution terminated due to error |
  request failed \(code [45]\d\d\). Mid-turn recovered errors are NOT failures.
- Lens crowding: run-2 implementation lens identified the case-03 off-by-one in
  reasoning and dropped it as "logic bug, rather than a claim vs. implementation
  conflict". KB: findings/a-mandatory-brief-checklist-crowds-out-coequal-duties.md.
- False-CONFIRM latent bug: command rubric `sh <missing file>` exits non-zero ->
  expect exit_nonzero scored PASSED. KB: third instance appended to
  findings/a-check-that-cannot-run-refutes-nothing.md.
- A PR tree can reconfigure the reviewer: opencode.json in session cwd outranks
  global config (verified keylessly; could repoint provider baseURL to harvest a
  key). Fix in flight; claude adapter project,local settings = same class, report owed.
- pond: opencode adapter works and scopes via per-run XDG_DATA_HOME (verified, exactly
  1 probe session). pi-coding-agent adapter ingests (~/.pi/agent/sessions, 8 sessions
  measured) but per-run scoping unproven - re-dig in flight.
- XDG_CONFIG_HOME redirect does NOT clean opencode context: --pure + both XDG
  redirects still loaded all ~/.claude/skills as commands.
- opencode effort option id is `effort` (NOT reasoning_effort, -32602), default
  minimal. Adapter: [npx, --yes, opencode-ai@1.18.30, acp, --pure].
- Gemini 3.7 flash list price: $0.75/M in, $3.75/M out; a lens session ~123k in/6.3k
  out = ~$0.12; full 14-case fast-loop corpus ~$5-8 at list (subscription pays it).
- Antigravity 5h window smooths burst; quota was NOT exhausted (86% weekly, 46% 5h at
  the time of the 429 storm).

## Open questions

1. OpenRouter key channel: gopass store NOT initialized on this box (`gopass ls`
   fails). Recommended: operator initializes gopass, entry llm/openrouter/api-key,
   injected as OPENROUTER_API_KEY at launch. Runbook Q1-Q4 at
   scratchpad/pi-openrouter-runbook.md.
2. ENV_ALLOWLIST exception for OPENROUTER_API_KEY vs key-on-disk vs Zen-only?
   Recommended: keep Zen keyless lane for open-source; defer the exception until a
   paid OpenRouter model is actually wanted.
3. Switch fast loop to free Zen lanes (muse-spark) to stop spending gemini quota?
   Recommended: not yet - keep the yardstick fixed until floor is green; then trial
   via stages-opencode.yaml (already landed, c1de77a) with `just eval bar/bar-01
   --jobs 1 --stages skills/review-pr/templates/stages-opencode.yaml`.
4. Wave 4 milestone PR: #5791 fates unresolved (PR open). Recommended: wait for its
   fates; do not spend on a milestone until floor+bar green anyway.

## Undone instructions

- Final report with complete verified numbers + one-liner (goal hook) - blocked on
  iteration-2 landing + re-run + milestone.
- KB consolidation of model research (user: "lets gather all that data into kb") -
  step 4 above; deliberately waiting for the last report.
- Shadow-run readiness verification (capture with model id preserved) - a2c7cc report
  owed.
- `just ship` for all the skill-code commits of this session.

## References

- Plan: docs/plans/2609-11-review-quality.md (kept current through a578289).
- Ledger: docs/review-ledger/evals.jsonl (eval rows), runs.jsonl (review runs).
- Corpus: fixtures/review-pr-cases/ (README carries freeze rule + publicity fence).
- Harness: fixtures/review-pr-cases/harness.py; recipes `just eval`, `just review`.
- Scratchpad (session): /tmp/claude-10003/-home-tenequm-pj-build-workflow/a0422db5-3d18-438b-ab30-86ef23ec10be/scratchpad/
  - model-options-report.md, opencode-zen-report.md, pi-openrouter-runbook.md,
    stages-openrouter.yaml, park-triage.md, lane-misstriage/report.md,
    lane-levera/, lane-leverb/ (drawer), pi-pond-bernstein.md (pending).
- Eval workspaces: /tmp/review-eval-20260911T125608Z (run 1), /tmp/review-eval-20260911T131457Z (run 2).
- KB commit: 55cfa94. Memory dir has delegate-mechanical-work, review-pr-quality-bar,
  act-on-discretion, lean-codebase.
- Subagent model rule: gemini acpx lanes (gemini-3.7-flash-medium) for mechanical work,
  Agent tool with explicit model opus otherwise, NEVER Fable.
