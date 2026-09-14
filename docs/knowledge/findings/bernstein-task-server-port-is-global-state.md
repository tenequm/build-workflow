---
type: Finding
title: Concurrent bernstein runs collide on the task server port
description: Every Bernstein run binds port 8052 by default, so concurrent runs require a port each. The operator engine now propagates that run-specific URL and the four-case harness has proved jobs=4; /review-pr also removed its historical literal-8052 examples, leaving the engine-appended authentication section as the sole authority for dynamic connection data.
tags: [bernstein, review-pr, eval]
status: stable
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:45:00Z" }
sources:
  - id: help
    resource: bernstein run --help (3.19.1)
    title: --port INTEGER, default 8052
  - id: runs
    resource: two crashed runs on this host, 2026-09-11 19:25 and 19:33 UTC - server.log showed six server pids dying on "[Errno 98] address already in use", prove-run.log carried 272 paired 401 lines
    title: crash forensics
  - id: fix
    resource: /fixtures/review-pr-cases/harness.py
    title: free_port() per case
  - id: resolver
    resource: bernstein 3.19.1 as installed, core/agents/spawner_core.py:655-685
    title: _resolve_task_server_url reads BERNSTEIN_SERVER_URL, then .sdd/runtime/server.port, then falls back to 8052
  - id: hardcoded
    resource: bernstein 3.19.1 as installed, core/agents/spawn_prompt.py:780, 1102, 1114, 1123, 1127 and _default_templates/prompts/{progress-report,team-awareness}.md
    title: completion, bulletin and channel curl examples are literal http://127.0.0.1:8052
  - id: operator
    resource: bernstein 3.19.2 as installed on 2026-09-14 - core/orchestration/orchestrator.py exports args.port through BERNSTEIN_SERVER_URL, and core/agents/spawner_core.py resolves that URL for the authentication section
    title: The operator propagates one run-specific task-server URL
  - id: reviewhistorical
    resource: "Git tree at 711f340: /skills/review-pr/templates/bernstein-templates/roles/manager/system_prompt.md repeated task-server auth and transport instructions with literal port 8052"
    title: The historical review-manager duplication
  - id: manager
    resource: /skills/review-pr/templates/bernstein-templates/roles/manager/system_prompt.md
    title: The current review manager prompt, which delegates dynamic connection data to the engine-appended authentication section
  - id: proof
    resource: "The four-case corpus row committed in 52e5589: jobs=4 with one free port per case, all cases completed and no result was ERROR or MALFORMED"
    title: The current per-run-port concurrency proof
  - id: hunt
    resource: "preserved run at /tmp/review-eval-20260911T210735Z/floor/case-05/repo/.sdd/runtime/agent_logs/manager-9ae48550/manager-9ae48550.log, 2026-09-11 21:20-21:24Z"
    title: "the manager's own words - \"the actual server port is 50699 (from .sdd/runtime/server.port), not the 8052 placeholder in the instructions\""
---

# Finding

The orchestrator's task server binds a fixed default port (8052), and nothing
namespaces it per run.[^help] When two runs share a box, the second run's
server dies on bind, its watchdog restarts it up to five times, and each
restart mints a fresh auth token - so the foreground waiter polls its own
run's /status with a stale token and drowns the log in 401s while the real
error (the bind failure) sits in `.sdd/runtime/server.log`.[^runs]

The misdirection is the expensive part: the visible symptom (auth failure)
points away from the cause (port collision). Any harness or script that can
ever run two bernsteins concurrently must allocate a port per run.[^fix]

# What a per-run port exposed

The engine resolves the server URL it hands an agent from
`BERNSTEIN_SERVER_URL`, then the run's own `.sdd/runtime/server.port`, and only
then falls back to 8052 - and the docstring there records a past incident where
the fallback sent an agent to another run's server.[^resolver] But the resolver
governs only the auth section. The completion, bulletin and channel curl
examples in the same spawn prompt, and two of the shipped prompt templates,
carry the literal `http://127.0.0.1:8052`.[^hardcoded]

On the default port the contradiction is invisible. On an allocated port it is
a trap for the manager, which is the one role told to drive the task server by
curl. One manager of four spent its entire first turn on it - probing 8052 with
`ss`, `curl /health`, `/proc/<pid>/net/tcp`, even `python3 -c "print(hex(8052))"`
- before finding `server.port` and reporting, in its own log, that 8052 was "the
placeholder in the instructions".[^hunt] By then the stalled-manager detector
and the heartbeat escalation had both fired on it.

The operator engine now publishes each run's URL to the spawned environment, and
its appended authentication section renders that URL dynamically.[^operator]
Together with a free port per case, that has completed the four-case corpus at
`jobs=4`.[^proof]
The upstream literals recorded above remain an engine concern. `/review-pr` once
added a smaller copy of the same contradiction: its static manager role prompt
repeated the auth and transport instructions and hardcoded 8052 in both
review-specific task-create examples.[^reviewhistorical]

That duplication is now removed. The manager prompt owns the review task graph,
roles, dependencies and completion signals; the engine-appended authentication
section is the sole authority for the run-specific server URL, token path, command
form and completion command.[^manager]

[^help]: --port INTEGER, default 8052
[^runs]: crash forensics
[^fix]: free_port() per case
[^resolver]: the resolver prefers the env var, then server.port, then 8052
[^hardcoded]: the prompt's curl examples are literal 8052
[^hunt]: a manager lost its first turn to the placeholder
[^operator]: the current engine propagates the run URL to its authentication section
[^reviewhistorical]: the review manager's former literal task-server examples
[^manager]: the current review manager delegates dynamic connection data to the engine
[^proof]: the jobs=4 per-run-port proof
