# Handoff 2026-09-11 16:50Z build-workflow@feat/review-pr

Supersedes 2609-11-1455-review-quality-loop.md for position and next steps.

## Position

The /goal loop (report + one-command invocation) was delivered and shipped as
v0.1.26 (fca511c). The operator then answered the open questions Q1-Q5 and this
window executed all of them except Q4, which they deferred.

Answers as given, verbatim in intent:

- Q1: OPENROUTER_API_KEY is in ./.env for now.
- Q2: yes, allowlist it.
- Q3: yes, switch the fast loop to opencode Zen - "i don't have any more limits
  left on my claude max sub", "lets switch to muse spark 1.3 free or something".
  They ran `opencode auth login` (OpenCode Zen) on this box.
- Q4: pi needs real sandboxed isolation later ("only what the pipeline gives
  it, sandboxed way like with codex"), deferred for now.
- Q5: yes, switch production's provider too - "it should be a common very
  simple thing to do for us".

Done, committed as feb4227 on feat/review-pr (NOT yet shipped):

- `stages-fast.yaml` runs every lens and the claims role on
  `opencode/muse-spark-1.3-contributor-free` at `effort: high`, codex
  (gpt-5.6-sol) still verifying, `routing.opposite: {opencode: codex}`.
  `stages-opencode.yaml` was DELETED and folded into it.
- `stages.yaml` keeps a family named `gemini` but reaches it through
  `[npx, --yes, opencode-ai@1.18.30, acp, --pure]` with
  `opencode/gemini-3.8-flash` and `opencode/gemini-3.7-flash`,
  `effort_option: effort`, `env: [XDG_DATA_HOME, XDG_CONFIG_HOME]`,
  `strip_paths: [opencode.json, opencode.jsonc, .opencode]`,
  `pond_adapter: opencode`. Every lens now states `effort: high` (the Claude
  bridge ignores it; opencode would otherwise run at `minimal`).
- `OPENCODE_API_KEY` and `OPENROUTER_API_KEY` added to `proc.ENV_ALLOWLIST`.
- Three brittle spots closed: malformed lens rubric -> `rejected_rubric`,
  never a park; readiness pond-adapter check driven by `pondsync.plan_adapters`;
  the recorded fixture derives adapter argv (regex over `adapter_argv:`) and
  advertises the model the session asks for.

## Next steps

1. Read the second corpus run's result (the first ran pre-rubric-fix). Command,
   from the repo root:
   `OPENCODE_API_KEY="$(jq -r '.opencode.key' ~/.local/share/opencode/auth.json)" python3 fixtures/review-pr-cases/harness.py --jobs 2`
   Numbers land in `docs/review-ledger/evals.jsonl`; workspaces under
   `/tmp/review-eval-<stamp>/`.
2. Report the free-lane corpus number to the operator next to the sonnet
   baseline (14/14 RECOVERED, 0 MISFILED, 0 MISSED, 7 extras).
3. `just ship` (bumps both plugin.json, commits, pushes) - feb4227 is unpushed.
4. Q4 stays open: pi needs per-session HOME isolation before the lane runs a
   real PR.

## Decisions

- A family names the MODEL family, not the transport. That is what lets
  production keep the `gemini` name on a Zen-served lane, and it matters
  because `routing.opposite` keys must be declared families and the same table
  is what reroutes a gemini-AUTHORED pull request to claude.
- Production's third lane is load bearing, not latent: the gating lens forbids
  codex, so with only claude and codex declared it would lose its dual-family
  second opinion entirely (`pipeline.lens_families` picks the alternate by
  sorted family name).
- Free Zen ids stay out of production: they train on prompts and are fenced to
  open-source repositories. The eval corpus qualifies - its README says every
  tier is publishable, and the harness only runs floor and bar, which are
  synthetic.
- A malformed rubric is dropped and recorded, not fatal. The rubric is optional
  by design, its absence already demotes the finding to SUGGESTION, and the
  verifier's `rejected_rubric` was the precedent. The parser stays strict
  because stage 3 executes what it returns.

## Findings

- opencode's Zen provider reads `OPENCODE_API_KEY` (models.dev provider entry
  `env: ["OPENCODE_API_KEY"]`). This matters because every opencode family
  redirects `XDG_DATA_HOME`, which is where `opencode auth login` writes
  `auth.json` - so without the env name a redirected session has no credential.
- Zen charges TWICE Google list for Gemini flash: $1.50/M in, $7.50/M out
  against Google's $0.75/$3.75 (models.dev cache, read 2026-09-11). The swap
  bought one key and no local wrapper; it did not buy a lower rate.
  glm-5.3-flash is $0.15/$0.50 with 1M context and is the next cost lever.
- `pondcost` prices claude-code, codex-cli and agy sessions only. There is no
  opencode branch, so a Zen lane's cost figure is null rather than a floor.
- acpx refuses a `--model` the ACP agent did not advertise; that is why the
  recorded fixture broke on the swap (`Cannot apply --model
  "opencode/gemini-3.7-flash"`).
- Free-lane smoke: `floor/case-01` RECOVERED in 95.5s, no spend.
- Suite after the swap: 360 passed, 11 failed (the known engine-patch parks,
  same set), 1 skipped. `just check` clean. `review-pr ready` READY, and it now
  prints `pond:claude-code`, `pond:codex-cli`, `pond:opencode`.

## Open questions

Q4 (unchanged, deferred by the operator): pi needs per-session HOME isolation -
a redirected pi session still loads all 22 operator skills and EXECUTES
`~/.pi/agent/extensions/*.ts`, and pi-acp forwards neither `--no-skills` nor
`--no-extensions`. The lane must not run a real PR until that is closed.
Q6 (new): measure glm-5.3-flash on the free loop as the paid third lane, and
decide whether to teach pondcost an opencode branch so the Zen lane reports a
cost floor again.

## Undone instructions

- `just ship` for feb4227.
- The #5791 review payload was never posted to GitHub (never asked for).

## References

Plan: docs/plans/2609-11-review-quality.md (status paragraph rewritten).
Lanes reference: docs/knowledge/references/review-model-lanes-2609-11.md
("Where the lanes stand after 2026-09-11").
Prior handoff: .agents/compact-handoff/2609-11-1455-review-quality-loop.md.
Commit: feb4227.

## AMENDED 17:30Z - routing redesign agreed, nothing built yet

The operator rejected the shape shipped in feb4227 and set a new direction. NOTHING
below is implemented; feb4227 and ad56435 remain the committed state.

### What the operator asked for, in their words

- q1/q2: both keys are in `./.env` now (GEMINI_API_KEY, OPENROUTER_API_KEY). Nothing
  in the pipeline reads `.env`; `just review` and `just eval` read the Zen key out of
  `~/.local/share/opencode/auth.json`. An OpenRouter equivalent is NOT wired yet.
- q3: "lets change codex to must spark too for now pls, can we?" - answered: not as
  stated, muse-spark verifying muse-spark is same-model self-judging, which is the
  measured failure that parked 11 of 14 cases.
- q5: "why? please don't confuse. lets have a clean <provider>/<model_id> convention,
  where each provider has a list of models available for them, structure that
  professionally." and "no gemini pls, instead of it can you do deepseek v4.1 flash
  through openrouter key?"
- Then: "can we do good with just free options?"
- Then: consult Fable 5 (NOT 5.1) with the KB and the free-model catalogue.

### The agreed redesign (approved in principle, NOT yet given a build go)

Replace `families:` with `providers:`. A provider owns transport, adapter_argv,
requires_env, env redirects, strip_paths, effort_option, pond_adapter, and its own
`models:` map. Every lens and role names `<provider>/<model_id>`. Independence keys on
the MODEL family declared per model, not on the provider - that is the change that lets
two models on the same opencode adapter verify each other, and it is why the Zen lane
had to be misleadingly named `gemini` in feb4227.

Root cause of that naming, for the record: `families:` conflates three things - the
transport/credential lane, the independence unit, and the key space for author routing
(`routing.opposite` keys must be declared families, and `checkout.author_family` only
ever emits claude/codex/gemini).

Interim trick that needs NO refactor: declare two families named for their model
families (e.g. `muse` and `minimax`) both using the opencode adapter. The current code
keys independence on family name, so cross-family verification is satisfied today.
That is how the all-free experiment can run before the refactor.

### Measured model data gathered this window (Artificial Analysis Intelligence Index v4.3)

| model | Index | in/out per 1M | Terminal-Bench v4 | AA-LCR | AA-Omniscience |
|---|---|---|---|---|---|
| Muse Spark 1.3 (max) | 48 | 1.25/4.25, free on Zen | 33% | 83% | +25 |
| GLM-5.3-Flash | 42 | 0.15/0.50 | 33% | 80% | +7 |
| DeepSeek V4.1 Flash | 40 | 0.30/1.20 (0.15/0.60 on OpenRouter) | 27% | 84% | -5 |
| DeepSeek V4 Flash 0731 (Zen free) | 35 | free | 12% | 80% | -14 |
| MiniMax-M3 (Zen free) | 30 | free | 2% | 83% | +1 |
| MiMo-V2-Pro (Zen free) | 29 est | free | - | 68% | +5 |
| GLM-5 (Zen free) | 28 est | free | - | 76% | 0 |
| Qwen3.6 Plus (Zen free) | 27 est | free | - | 78% | +1 |
| Kimi K2.5 (Zen free) | 23 est | free | - | 78% | -7 |

WARNING: AA publishes Muse Spark 1.3 (max) as 48 on its comparison tables and 62 in its
launch article. Those do not reconcile. Every figure above is from the comparison
tables, one scale, so the ordering holds; never mix them with AA article figures.

`openrouter/deepseek/deepseek-v4.1-flash` was verified addressable from this box
through opencode with OPENROUTER_API_KEY set.

### The recommendation put to the operator (awaiting their call)

| slot | model | provider | rationale |
|---|---|---|---|
| fast-loop lenses + claims | muse-spark-1.3-contributor-free | opencode Zen | best free on TB/LCR/Omniscience; already 13/14 on our corpus |
| fast-loop verifier | glm-5.3-flash (paid, ~$1-2 per 14-case pass) OR minimax-m3-free (free) | opencode Zen | judging wants anti-hallucination + long context, not Terminal-Bench |
| production second opinion (replaces gemini) | deepseek/deepseek-v4.1-flash | openrouter | best AA-LCR of the three, AutomationBench 69%, 1M ctx, $0.15/$0.60 |

Hard constraint restated: every `-free` Zen id trains on prompts, so all-free is
available for the fast loop (synthetic public fixtures) and FORBIDDEN for production,
which reviews other people's private trees. That fence, not quality, is what stops
"all free everywhere".

Proposed experiment, not yet run: Pass A (muse lenses + codex verifier, the run in
flight) against Pass B (muse lenses + minimax-m3-free verifier, fully free). If B holds
14/14 with comparable extras, codex leaves the fast loop.

### In flight at the time of writing

1. Corpus re-run on the CURRENT committed routing, background id bsw2gjd3e, output
   `/tmp/claude-10003/.../tasks/bsw2gjd3e.output`, workspaces
   `/tmp/review-eval-20260911T165025Z/`. At 12 of 14 with zero parks when last checked.
   This is the number that proves the rubric fix.
2. Fable 5 consultation, background id ba0u9hyly, acpx session `fable5` at
   `--model 'claude-fable-5[1m]'`, cwd and bundle at
   `/tmp/claude-10003/.../scratchpad/fable-consult/`. It was given the whole knowledge
   bundle, SKILL.md, all three templates, the corpus README, the quality plan, and
   `free-models.md`. It writes `report.md` in that directory; `run.log` holds the
   transcript. Asked: best free model per slot with evidence, the cross-family pairing,
   where free breaks and what shape the damage takes, the smallest set of corpus runs
   that would settle it, and whether the direction violates anything in the bundle.

### Next steps after compaction

1. Read `/tmp/claude-10003/.../scratchpad/fable-consult/report.md` and relay it
   AGAINST the recommendation above, flagging disagreement rather than merging voices.
2. Read the Pass A corpus number from bsw2gjd3e / the evals ledger.
3. Get the operator's call on the free-verifier experiment and on building the
   providers refactor. Neither has a build go yet.
4. `just ship` is still owed for feb4227 and ad56435.
