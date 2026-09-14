---
name: review-pr
description: "Review a GitHub pull request by handing one free-text review goal to the stock bernstein orchestrator in the target repo's checkout. Use /review-pr <number|url> on public repositories only. Bernstein owns spawning, models, budgets; the goal text carries the five-lens review doctrine and the report lands as review-report.md."
---

# review-pr

Hand the pull request to stock bernstein with this skill's goal text and seed.
Bernstein spawns the agents, routes the models, holds the budget, and writes
its receipts under `.sdd/`; the review doctrine lives entirely in
`templates/review-goal.md`, the model routing in `templates/review-seed.yaml`.

## Fence

Review PUBLIC repositories and the eval corpus only. The lanes run on a
local gateway or on personal subscription accounts whose data-use terms
are settled at the account, not per run, and a reviewed tree would
otherwise reconfigure its own reviewer. The PATH shims below suppress the
measured Pi and Claude project surfaces. For Codex they suppress operator config,
rules, apps, plugins and hooks, plus AGENTS files and rollout persistence. Codex
0.154 still has no proven switch for a reviewed tree's `.codex/` directory, and
still injects its product baseline and host skill catalogue; `agy` project config
is also unclosed. Never point this at a private repo, and never hand a model session
a credential or a GitHub token - the two fetch commands below are the only place
`gh` runs.

## Invocation

In a THROWAWAY checkout of the target repository with the BASE commit of the
pull request checked out, and with no remote on it. Put the checkout AND
`TMPDIR` on a filesystem with tens of gigabytes free - `df -h` first, and do
not assume the default `/tmp` qualifies:

    work=<big-filesystem>/review-<repo>-<N>
    mkdir -p "$work/tmp" && export TMPDIR="$work/tmp"
    for fs in "$work" /tmp; do   # the export above moves worker scratch; /tmp is granted anyway
      free=$(df -BG --output=avail "$fs" | tail -1 | tr -dc '0-9')
      [ "${free:-0}" -ge 10 ] || { echo "refusing: $fs has ${free}G free, need 10G"; exit 1; }
    done
    git clone <url> "$work/src" && cd "$work/src" && git checkout <base-sha>
    printf '/.bernstein-pr.diff\n/.bernstein-pr.md\n/.bernstein/\n/.sdd/\n/review-report.md\n' >> .git/info/exclude
    gh pr diff <N> > .bernstein-pr.diff
    gh pr view <N> --json title,body --template '# {{.title}}

    {{.body}}' > .bernstein-pr.md
    git remote remove origin          # after the two gh reads, before the engine
    mkdir -p .bernstein
    [ ! -e .bernstein/templates ] && [ ! -L .bernstein/templates ] || {
      echo "refusing: reviewed tree already owns .bernstein/templates"; exit 1;
    }
    [ ! -e "$work/review-templates" ] || {
      echo "refusing: $work/review-templates already exists"; exit 1;
    }
    cp -R <skill>/templates/bernstein-templates "$work/review-templates"
    ln -s "$work/review-templates" .bernstein/templates
    shims=$(mktemp -d)
    command -v pi >/dev/null && printf '#!/usr/bin/env bash\nexec %s -ne -ns -np --no-themes -nc -na --no-session "$@"\n' "$(command -v pi)" > "$shims/pi" && chmod +x "$shims/pi"
    command -v claude >/dev/null && printf '#!/usr/bin/env bash\nexec %s --safe-mode --strict-mcp-config --no-session-persistence "$@"\n' "$(command -v claude)" > "$shims/claude" && chmod +x "$shims/claude"
    if command -v codex >/dev/null; then cat > "$shims/codex" <<EOF && chmod +x "$shims/codex"
#!/usr/bin/env bash
if [ "\${1:-}" = exec ]; then
  shift
  exec $(command -v codex) exec --ignore-user-config --ignore-rules --ephemeral \\
    --disable hooks --disable apps --disable plugins --disable plugin_sharing \\
    --disable remote_plugin -c project_doc_max_bytes=0 \\
    -c model_reasoning_effort=high \\
    -c sandbox_workspace_write.network_access=true \\
    -c 'sandbox_workspace_write.writable_roots=["$work/src"]' "\$@"
fi
exec $(command -v codex) "\$@"
EOF
    fi
    mkdir -p "$work/src/.sdd/sandbox-probe"   # probe from a SUBDIR: the root grants itself
    (cd "$work/src/.sdd/sandbox-probe" && codex sandbox -c sandbox_mode='"workspace-write"' \
       -c "sandbox_workspace_write.writable_roots=[\"$work/src\"]" -- \
       sh -c 'touch ../../.sandbox-probe') ; rmdir "$work/src/.sdd/sandbox-probe"
    [ -f "$work/src/.sandbox-probe" ] || { echo "refusing: codex cannot write to $work/src"; exit 1; }
    rm -f "$work/src/.sandbox-probe"
    BERNSTEIN_SEED_PATH=<skill>/templates/review-seed.yaml \
      PATH="$shims:$PATH" bernstein run --seed <skill>/templates/review-seed.yaml \
      --goal "$(cat <skill>/templates/review-goal.md)" \
      --budget '$3.00' --auto-approve --quiet --wait 3000

The report is `review-report.md` at the checkout root; it ends with a fenced
json block of the findings. Read it, relay it. Nothing is ever posted to
GitHub by this skill.

Notes that cost time to learn:

- **A review needs tens of gigabytes of disk, and running out of it kills the run
  permanently rather than slowly.** The goal text lets a lens run the repository's
  own validation command from the base branch; on a compiled-language repository
  that command is a full build. Measured 2026-09-14 on pond#237 (Rust): one lens
  put 6.3 GB into its `mktemp -d` scratch, on a 32 GB rootfs that `/tmp` shares
  with the system and that already held 12 GB of `target/` from an earlier run.
  At 0.3 GB free the spawner refuses to start agents - `Disk space critical: 0.3
  GB free (need >= 1.0 GB)` - and a task that cannot spawn burns its respawn
  budget, then its retry budget, then lands in quarantine at `fail_count=3,
  action=skip`. Quarantine is terminal: freeing the disk afterwards recovers
  nothing, and any task depending on a quarantined one is stuck at
  `blocked_by_failed_dep` forever. **`TMPDIR` does reach the workers**, which is
  why the export above is the fix and not a comfort: `TMPDIR` is on bernstein's
  env passthrough allowlist (`adapters/env_isolation.py`), and codex-cli 0.154.0
  grants `$TMPDIR` as a writable root under `workspace-write` even when it points
  entirely outside the workspace - both measured 2026-09-14, and confirmed in a
  four-case corpus run where `/tmp` free never moved while worker scratch
  accumulated under the exported path
  ([the finding](../../docs/knowledge/findings/worker-scratch-follows-tmpdir.md)).
  `/tmp` keeps its own floor regardless, because the sandbox grants it
  unconditionally and run 2 put the manager's shared findings directory there
  under an export that was in force - unexplained, and not worth removing a free
  check to find out. Both limits appear only in
  `.sdd/runtime/orchestrator-debug.log`, never in the run log.
- **A codex worker cannot write the report to the checkout root unless the root is
  granted, and `/tmp` hides this.** `--sandbox workspace-write` grants the worker's
  own cwd - its worktree, nested under the checkout - plus a fixed list of system
  roots that includes `/tmp`. The checkout root is not on that list, and the goal
  text requires `review-report.md` to be written exactly there. So a checkout under
  `/tmp` succeeds by accident and a checkout anywhere else is refused: measured
  2026-09-14 on pond#237, where moving to `/home` to escape a full `/tmp` left every
  lens finished and the report undeliverable. The worker reported the checkout
  "mounted read-only", correctly refused to fake success, and died - and bernstein
  retried it three more times, at up to 1.95M input tokens an attempt. The two
  requirements pull against each other: the disk guard above pushes the checkout off
  `/tmp`, and doing that is what removes the default grant. Hence the
  `writable_roots` entry in the shim, which unlike the effort value IS interpolated
  because the path is per-run, and hence the probe beside it - a mistyped key fails
  closed with a denied write, which without the probe surfaces only after a full lane
  has run. The probe must run from a SUBDIRECTORY of the checkout: from the root
  itself `workspace-write` grants the cwd and the check passes vacuously. Note the
  probe puts its `-c` flags AFTER the subcommand - `codex sandbox` honours them only
  there, while `codex exec` honours them in the shim's position ahead of it (both
  verified, codex-cli 0.154.0).
- **Without `-c sandbox_workspace_write.network_access=true` a codex lane cannot
  run at all.** The adapter spawns codex with `--sandbox workspace-write`, whose
  default denies network, and every bernstein worker reaches the task server over
  127.0.0.1 - the manager to create tasks, everyone to report completion.
  Measured 2026-09-14: a codex manager saw `CODEX_SANDBOX_NETWORK_DISABLED`, got
  `curl: (7) Failed to connect to 127.0.0.1` on both the documented port and the
  real one, correctly refused to fake success, and failed the run after 530k
  input tokens spent diagnosing it. The override grants loopback and the open
  internet alike, which is inside this skill's fence (public repositories) and no
  wider than the public-repository fence permits; the shim isolates configuration,
  not network destinations.
- **The `codex` shim isolates the worker from measured operator surfaces and pins
  reasoning effort to the run.** `--ignore-user-config`, `--ignore-rules`, the
  feature switches and `project_doc_max_bytes=0` prevent operator MCP servers,
  plugins, apps, hooks and AGENTS files from entering a worker;
  `--ephemeral` prevents the review from becoming operator session history.
  Authentication still comes from `CODEX_HOME`. `codex exec` reads
  `model_reasoning_effort` from `~/.codex/config.toml` and takes no dedicated
  effort flag, but it does take `-c key=value` (verified codex-cli 0.154.0), and
  bernstein's codex adapter builds its argv with no hook - it reads neither that
  file nor `role_model_policy.<role>.effort`, which the seed parser accepts and
  then drops. PATH is the only way to supply these flags. Keep the effort a literal:
  codex accepts a
  misspelled effort and reports it back as the effort, even under
  `--strict-config`, so an interpolated typo would downgrade the lane silently.
  Codex 0.154 still injects its product baseline and host skill catalogue; its
  advertised discovery switch does not suppress them. No shipped template carries
  that material, and this CLI version exposes no effective switch for it.
- **The templates link is what keeps the built-in role vocabulary out of every
  agent's context, and it is not optional.** `get_templates_dir` prefers
  `<workdir>/.bernstein/templates` over the engine's bundled defaults. The link points
  to a per-run snapshot outside the reviewed checkout: Bernstein's code index cannot
  feed the templates back to workers as RAG, and edits to the installed skill cannot
  change prompts halfway through a run. This template tree has no `skills/` directory,
  so the engine's built-in role catalogue is not appended to the coordinator prompt.
  Left out, the coordinator is handed roles the task server rejects.
- `bernstein run` blocks only with `--quiet` and `--wait`; `--headless` on the
  root group is a parsed no-op.
- **`BERNSTEIN_SEED_PATH` is not optional, and leaving it out fails in six
  seconds with a message that names the wrong problem.** `--seed` reaches the
  CLI, but the CLI hands off to a detached orchestrator that re-resolves the seed
  by itself, and its only other source is `<workdir>/bernstein.yaml`. With the
  seed living in the skill directory that file does not exist, so the orchestrator
  starts with no `role_model_policy` at all and dies on `FATAL: no adapter
  configured` - which reads like a missing CLI and is actually a seed that never
  arrived. It retries about six times, roughly five seconds apart, then the run
  ends with one declared task and no agents. Measured 2026-09-14 on pond#237;
  `.sdd/runtime/orchestrator-debug.log` is where the real cause appears, never the
  run log.
- The seed file must carry a `goal:` string even though `--goal` supplies the
  real one - the detached orchestrator re-parses the seed and refuses one
  without it. That re-parse is the same hop `BERNSTEIN_SEED_PATH` exists to
  survive.
- The two `.bernstein-pr.*` files are untracked, and agents work in worktrees
  cut from the base commit where untracked files are invisible; the seed's
  `worktree_setup.copy_files` is what carries them in.
- The remote is removed because the engine pushes on its own: on every agent
  merge it runs `git push origin`, and on salvage it pushes the
  `salvage/<session>` branch. That is the engine's build workflow leaking into
  a review, and against a reviewed repository it is a write attempt at someone
  else's project. A checkout with no remote has nowhere to push; the absence of
  a credential is not a substitute, because it fails by luck rather than by
  design. Use a throwaway checkout so a long-lived clone under `~/pjv/` keeps
  its remote.
- An aborted `bernstein run` is not dead: the orchestrator double-forks away
  from the CLI and keeps spawning workers after it exits. To stop a run early,
  scan `/proc/*/cwd` for processes inside the checkout, TERM them, then KILL
  the stragglers - killing only the CLI leaks the run.
- The PATH shims exist because bernstein's adapters pass no isolation switches,
  so a spawned agent otherwise boots the user's global MCP servers AND reads the
  reviewed tree's own agent config. Every flag closes a vector measured on this
  host: `pi -ne` stops `<cwd>/.pi/mcp.json` (an eager server there executes at
  session start, no trust gate) and the user's own servers; `-ns`, `-np` and
  `--no-themes` stop the remaining user and project prompt surfaces; `pi -nc` stops
  `<cwd>/AGENTS.md` and `<cwd>/CLAUDE.md`, which load before pi's trust decision
  so nothing else suppresses them; `pi -na` stops `<cwd>/.pi/SYSTEM.md` replacing
  the system prompt and `<cwd>/.pi/extensions/*.js` executing on a trusted host;
  `--no-session` prevents global history writes.
  `claude --safe-mode` disables CLAUDE.md, skills, plugins, hooks, settings, MCP
  servers and custom agents from both the operator and reviewed tree;
  `--strict-mcp-config` makes that boundary explicit, and
  `--no-session-persistence` keeps the review out of operator history.
