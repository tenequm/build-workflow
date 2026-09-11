# Fixtures

A fixture is a complete, ready build that a workflow change can be verified
against end to end, with real executors and a real judge. The acceptance suite
proves the driver's contracts against recorded agents; a fixture proves the
parts no recording reaches - dispatch, merges, quiescence timing, judge
transports, and the shape of a brief a model can actually follow.

Read [the acceptance map](../docs/operator-acceptance.md) for what each layer
covers, and run a fixture whenever a change touches the phase boundary, the
scorer, the judge ceremony, or a template a plan author copies.

## slugify

A stdlib-only Python package that starts with `word_count` and gains
`slugify` in one phase. The build is deliberately small - one executor step,
its pinned fix, one judge - so a full run is minutes and a failure has few
possible causes.

```sh
python3 fixtures/slugify/setup.py /tmp/fx
```

That materializes what `/build-plan` would have produced by hand: a primary
checkout, a linked workspace on `feat/slugify`, a committed seed, a sign-off
commit pinned into the sidecar, disabled Git hooks and a `workspace.json`. It
prints the readiness and run commands, which need the interpreter from the
installed Bernstein uv tool (`uv tool dir`, then `bernstein/bin/python`) - see
the repository [install guide](../README.md#install).

Options:

| flag | default | why |
|---|---|---|
| `--role` | `analyst` | `resolver` runs the step on Codex instead of Claude |
| `--analyst-model` | `claude-sonnet-5` | the Claude role's model |
| `--resolver-model` | `gpt-5.6-terra` | the Codex role's model |
| `--judge claude\|agy` | `claude` | `agy` needs `--judge-adapter '<path to the Antigravity ACP server>'` |

An executor model below the brief's complexity fails as a clean exit with
nothing committed, which reads like a sandbox fault - see
[the capability floor](../docs/knowledge/findings/executor-model-capability-floor.md)
before blaming the harness.

A run ends at `build_completed` with the step merged, its report committed and
a judge verdict of `merge as-is`. Anything else parks with its evidence under
`<workspace>/.agents/build/runs/slugify/`; `workflow.jsonl` is the authority
and the park reason names the contract that refused.

Each run costs real provider tokens. The workspace is disposable: delete the
target directory when you are done.

## review-pr

A storefront package whose pull request carries one planted defect per review lens,
an instruction-shaped comment aimed at an automated reviewer, a body that over-claims
its own test count, a suggestion that survives the gate and one that does not.

```sh
python3 fixtures/review-pr/setup.py /tmp/fx --recorded
```

That prints the two commands that review it. `--recorded` points the stage template at
`recording_agent.py`, which answers over the real ACP protocol from `policy.json`
instead of calling a provider: acpx, the session bridge, the launch receipts, the
worktree allowlist check, the report-witness law, the retry and the cost evidence are
all exercised, and only the model's judgment is canned. Drop `--recorded` to run the
same pull request against real models, which costs real tokens.

`test_review_fixture.py` is this fixture asserted - each plant found, the injection
reported and not obeyed, the claim mismatch flagged, the two families' agreement
counted, the unprovable suggestion downgraded, and a ledger row per finding. It is the
cheapest way to tell whether a change to `/review-pr` broke a mechanism.

Unlike the slugify fixture this one needs no engine, no scorer and no network: the
reviewed project is stdlib-only Python and its whole-tree check is
`python3 -m unittest discover -s tests -t .`.
