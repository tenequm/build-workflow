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
