# Deferred code work (2026-09-03)

The doc/template half of the validated retro review landed as 12 commits ending
`a931162`; this file is the CODE half, deferred until after the first real
build so untested behavior changes never precede first use. Source evidence:
the retro validation of 2026-09-03 (scratchpad `workflow-retro-validation.md`,
session 35c0a261).

## Deferred code half

| File | Function / site | What the code must do |
|---|---|---|
| `bernstein_herdr/src/bernstein_herdr/judge.py` | `parse_verdict` (:61-88), `DECLARED`, `VERDICTS` | Anchor the parse to the LAST three lines instead of `text.split("Verdict", 1)` and a whole-file `re.M` count search; reject malformed, duplicate or undeclared blocks by blocking the judge gate rather than merging as `unclear` with word-count fallbacks. Items 1 and 8; until this lands, the prompt rules and fix-brief's refusal path are the only guards. |
| `bernstein_herdr/src/bernstein_herdr/ready.py` | ownership loop (:227-256) | Hoist `owned` above the stage loop, keep EVERY glob per step (currently `owned[step.title] = g` overwrites each iteration), compare only concurrently-open step pairs via the `ancestors()` reachability the role-batching check already builds, and use a real glob-intersection predicate (`fnmatch(a, b)` misses `src/*/x` vs `src/a/*`). Item 3 / S2. Docs now promise only what the current code does, so this is an upgrade, not a repair of a lie. |
| `ready.py` | :130-132 | The no-roles error recommends `backend` / `backend2` / `reviewer` -- the persona-dragging names every skill forbids. Should name `resolver` / `ci-fixer` / `analyst` / `adversary`. Item 11. |
| `ready.py` | :272-289 | Suppress the `gate_cmd` NOTE for steps with `judges:` -- it prints "judge step, gate is the verdict parser, no gate command" and then recommends a gate command. Item 11 (the build-ready doc half is done: the skill now tells the driver to ignore that NOTE). |
| `ready.py` | :337-339 | Remove the NOTE recommending `completion_signals`; the plan template forbids them because Bernstein drops them. Missed item 6. |
| `bernstein_herdr/src/bernstein_herdr/plan.py` | module docstring :17-18 | Says the sidecar `cli` is "the authoritative executor choice ... the adapter reads it from here". There is no adapter of ours and `cli` is not the dispatch key; role + `role_model_policy` is. Item 11. |
| `plan.py` | :118 (`[:48]`), :128 (`just check`) | Optional: have readiness PRINT each judge step's resolved `<run>/judge/<slug>/` path so planners never reproduce the slugging by hand (validation's preferred fix for item 9), and consider making the missing-`gate_cmd` fallback an error instead of `just check`. |
| `bernstein_herdr/src/bernstein_herdr/gates/scorer.py` | `TEST_FILE`, `NOLINT`, `lint_expected` (:30-33, :97) | Either tested language adapters (Python/Rust test filenames and suppression forms with scope+reason rules) or leave as is -- the coverage gap is now documented in the sidecar template and README rather than papered over. Item 12. |
| `scorer.py` | :88-114 | A fix-N REFUSAL currently passes: it commits a report, changed files are empty, `commits > 0`. Validation item 8 asks for a defined way for a refusal to become a failed/parked task (a gate-recognized refusal receipt). Documented meanwhile in build-run step 8 ("read fix-N's report on every run"). |

## Not applied cleanly

- **Item 1's real fix is code.** The validation's preferred remedy is an anchored parser,
  not prompt rules. What landed prompt-side is the honest subset: the requirement stated
  plainly, plus a self-check that is correct (unlike the gopost one, which expected three
  lines from a pattern that prints one).
- **Item 2's engine gating is advisory only.** The workflow now REQUIRES the patched clone
  in prose and gives the runtime verification command, but nothing checks the installed
  engine's commit. A readiness pin on the engine build would be the enforcing fix and is
  code. Note the currently installed 3.19.0 build does carry the module-lookup patch
  (`core/agents/heartbeat.py` imports `defaults as _defaults`, `_batch_timeout_seconds`
  reads `_defaults.TASK`), so the tuning keys do reach the kill paths on this machine
  today -- the doc is written for the general case.
- **Item 12's `spec N.M` half is doc-only.** `ready.py`'s `SECTION_CITE` still accepts only
  `DESIGN N` / `spec N.M`; the brief template and build-plan now teach that grammar rather
  than widening the regex.
