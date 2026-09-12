---
type: Finding
title: Concurrent bernstein runs collide on the task server port
description: Every bernstein run binds --port 8052 by default; a second concurrent run crash-loops its server, mints a fresh auth token per restart, and locks its own waiter out - the signature is an endless 401 flood against /status. Allocating a port per run is the only fix, and it costs something - parts of the spawn prompt still hardcode 8052, so a manager on a non-default port can burn its whole first turn hunting for the real one.
tags: [bernstein, review-pr, eval]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T22:35:00Z" }
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
  - id: onecall
    resource: bernstein 3.19.1 as installed - _resolve_task_server_url is referenced at spawner_core.py:655 and :707 only; spawn_prompt.py names no resolver
    title: the resolver governs the auth section and nothing else
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

# What a per-run port costs

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

There is no config lever that closes this. `_resolve_task_server_url` has
exactly one call site, the prompt's auth section; the curl examples in
`spawn_prompt.py` are literal f-strings no env var or seed key
reaches.[^onecall] A harness allocating a port can only reduce the odds - by
exporting `BERNSTEIN_SERVER_URL` so the auth section is unambiguous, and by
stating the real port in the goal text - and must expect a manager to lose a
turn to it anyway.

[^help]: --port INTEGER, default 8052
[^runs]: crash forensics
[^fix]: free_port() per case
[^resolver]: the resolver prefers the env var, then server.port, then 8052
[^hardcoded]: the prompt's curl examples are literal 8052
[^hunt]: a manager lost its first turn to the placeholder
[^onecall]: the resolver has one call site; the curl examples are literals
