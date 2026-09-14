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
otherwise reconfigure its own reviewer: stock bernstein strips no
project-local CLI config from the tree it checks out, so a committed
`.pi/mcp.json`, `.pi/extensions/`, `.mcp.json`, `.claude/settings*.json`,
AGENTS.md or CLAUDE.md would all reach the session. The PATH shims below
close every one of those by measurement, for `pi` and `claude` only. The
`codex` shim below pins reasoning effort and adds no isolation, so `codex`
and its `.codex/`, and `agy` and its `.agy/`, still read the reviewed tree. Never point this at a private repo, and never hand a
model session a credential or a GitHub token - the two fetch commands below
are the only place `gh` runs.

## Invocation

In a THROWAWAY checkout of the target repository with the BASE commit of the
pull request checked out, and with no remote on it:

    cd <checkout>
    printf '.bernstein-pr.diff\n.bernstein-pr.md\n' >> .git/info/exclude
    gh pr diff <N> > .bernstein-pr.diff
    gh pr view <N> --json title,body --template '# {{.title}}

    {{.body}}' > .bernstein-pr.md
    git remote remove origin          # after the two gh reads, before the engine
    mkdir -p .bernstein/templates
    cp -r <skill>/templates/bernstein-templates/roles .bernstein/templates/
    shims=$(mktemp -d)
    command -v pi >/dev/null && printf '#!/usr/bin/env bash\nexec %s -ne -nc -na "$@"\n' "$(command -v pi)" > "$shims/pi" && chmod +x "$shims/pi"
    command -v claude >/dev/null && printf '#!/usr/bin/env bash\nexec %s --strict-mcp-config --setting-sources user "$@"\n' "$(command -v claude)" > "$shims/claude" && chmod +x "$shims/claude"
    command -v codex >/dev/null && printf '#!/usr/bin/env bash\nexec %s -c model_reasoning_effort=high "$@"\n' "$(command -v codex)" > "$shims/codex" && chmod +x "$shims/codex"
    PATH="$shims:$PATH" bernstein run --seed <skill>/templates/review-seed.yaml \
      --goal "$(cat <skill>/templates/review-goal.md)" \
      --budget '$3.00' --auto-approve --quiet --wait 3000

The report is `review-report.md` at the checkout root; it ends with a fenced
json block of the findings. Read it, relay it. Nothing is ever posted to
GitHub by this skill.

Notes that cost time to learn:

- **The `codex` shim pins reasoning effort to the run, not to the host.** It is
  the one shim that is not about isolation. `codex exec` reads
  `model_reasoning_effort` from `~/.codex/config.toml` and takes no dedicated
  effort flag, but it does take `-c key=value` (verified codex-cli 0.154.0), and
  bernstein's codex adapter builds its argv with no hook - it reads neither that
  file nor `role_model_policy.<role>.effort`, which the seed parser accepts and
  then drops. PATH is the only way in. Keep the value a literal: codex accepts a
  misspelled effort and reports it back as the effort, even under
  `--strict-config`, so an interpolated typo would downgrade the lane silently.
- **The templates copy is what keeps the built-in role vocabulary out of every
  agent's context, and it is not optional.** `get_templates_dir` prefers
  `<workdir>/.bernstein/templates` over the engine's bundled defaults, and
  `role_resolver.resolve_role_prompt` tries a skill pack, then a legacy role
  template, then the bare `"You are a <role> specialist."` stub. Copying
  `roles/` and deliberately NOT copying a `skills/` directory puts the manager
  on our own template - which names only this seed's roles - and every lens on
  the stub. Left out, the manager is handed the engine's list of built-in roles
  and assigns names the task server answers with a 400.
- `bernstein run` blocks only with `--quiet` and `--wait`; `--headless` on the
  root group is a parsed no-op.
- The seed file must carry a `goal:` string even though `--goal` supplies the
  real one - the detached orchestrator re-parses the seed and refuses one
  without it.
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
  session start, no trust gate) and the user's own servers; `pi -nc` stops
  `<cwd>/AGENTS.md` and `<cwd>/CLAUDE.md`, which load before pi's trust decision
  so nothing else suppresses them; `pi -na` stops `<cwd>/.pi/SYSTEM.md` replacing
  the system prompt and `<cwd>/.pi/extensions/*.js` executing on a trusted host.
  `claude --strict-mcp-config` keeps only what bernstein injects via
  `--mcp-config`; `claude --setting-sources user` drops the tree's CLAUDE.md
  (defeating the adapter's own `--add-dir <workdir>`), its settings hooks, and
  its `.claude/skills` and `.claude/agents`, while `--mcp-config` and `--agents`
  survive because they are command line, not a setting source.
