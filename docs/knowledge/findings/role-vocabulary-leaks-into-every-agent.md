---
type: Finding
title: Bernstein validates a role two different ways, and the built-in vocabulary reaches every agent unless the run ships its own templates
description: The HTTP task-create route validates a task's role against the seed's `role_model_policy` keys and never against `KNOWN_ROLES`, so a run may name its own roles - but the built-in vocabulary still arrives in every agent's prompt, because the role resolver hands a skill-backed role an index of all seventeen built-in skills and the bundled manager template names eight roles as the only valid ones; shipping `<workdir>/.bernstein/templates/roles/` with no sibling `skills/` directory is what closes it.
tags: [bernstein, engine, spawn-prompt, roles, review-pr]
status: stable
stale_after: "2027-03-14T00:00:00Z"
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:45:00Z" }
sources:
  - id: engine
    resource: "bernstein 3.19.2 as installed (site-packages): core/routes/task_crud.py:1029-1050, core/planning/plan_schema.py:22 and :153, mcp/input_validation.py:181-189, core/planning/role_resolver.py:90-110 and :155, core/planning/role_resolver.py:211-218, __init__.py:60-75, core/agents/spawn_prompt.py:99-113 and :955-957, core/orchestration/orchestrator.py:6459-6470"
    title: the engine source, read at the pinned version
  - id: templates
    resource: "bernstein 3.19.2 bundled templates: _default_templates/roles/manager/system_prompt.md:17-28, _default_templates/skills/manager/SKILL.md:27-30, _default_templates/skills/manager/references/task-api.md"
    title: the bundled prompts that carry the list
  - id: measured
    resource: "resolve_role_prompt called directly against the installed engine, 2026-09-14: role `analyst` under the bundled templates returns a 1142-byte body naming every built-in role; the same role under a workdir templates dir with no skills/ returns the 34-byte stub. A live case-01 run then created nine tasks under the then-current seed-declared roles and the task server accepted every one; those two shadow roles were later removed from production in c5a0ae1."
    title: measured on the installed engine and on the historical nine-task graph
  - id: upstream
    resource: "upstream bernstein main at e95defe2a (2026-09-14), same version 3.19.2: plan_schema.py, input_validation.py, task_crud.py, role_resolver.py, spawn_prompt.py, teams/manifest.py, seed_parser.py and the whole templates/ tree are byte-identical to the pinned build"
    title: verified against upstream, so this is not a stale-fork artifact
  - id: seed
    resource: /skills/review-pr/templates/review-seed.yaml
    title: where the run declares its own roles
---

# Finding

Routing in bernstein is per role, so a role is the only lever that puts a named
task on a named model. Whether a role name is legal depends entirely on which
door the task comes through, and the two doors disagree.

`KNOWN_ROLES` is a closed list of nineteen names.[^engine] It is bound as a JSON
schema `enum` for a plan step, and re-bound at load time into the
`bernstein_create_subtask` MCP tool so the schema and the constant cannot drift.
A task created through either of those paths must use a built-in name.

The HTTP task-create route does something else entirely: it validates the role
against the keys of the run's own `role_model_policy` and rejects anything else
with a 400 that lists the valid ones.[^engine] `KNOWN_ROLES` is never consulted
there. A manager that creates tasks by curl - which is how a stock `bernstein
run` plans - therefore lives under the seed's vocabulary, not the engine's. A
seed may declare `custom-review-role` and it is as valid as `backend`.

One name is still not ours: the engine tests the literal string `manager` in its
prompt section rules, its specialists block and its consensus relay.[^engine]

## The leak, and why declaring custom roles is not enough

The permission to name roles is worthless while every agent is told a different
list. Three places carry the built-in vocabulary into a prompt:

- The role resolver tries a skill pack first, and a skill-backed role gets a
  compact index of **every** installed skill plus a `load_skill` pointer - the
  skill body itself is deliberately not injected.[^engine] Measured: role
  `analyst` receives 1142 bytes naming all seventeen built-in roles.[^measured]
- The bundled manager prompt states "Use these EXACT role names ... The task
  server validates roles and will reject any name not in this list" and then
  lists eight built-in names[^templates] - all of which the server would reject
  under a seed that declares its own.
- The bundled task-api reference uses `"role": "backend"` and `"role": "qa"` in
  the curl examples a manager copies.[^templates]

## What closes it

`get_templates_dir` prefers `<workdir>/.bernstein/templates` over the bundled
tree and never merges the two,[^engine] and the skills root is derived
structurally as the roles directory's sibling.[^engine] So a run that ships
`roles/` and deliberately ships **no** `skills/` directory leaves
`loader.has(role)` false for every role: the resolver falls through to the run's
own legacy template, or to the bare `"You are a <role> specialist."` stub.
Measured: the same `analyst` drops from 1142 bytes to 34.[^measured]

There is no supported switch for this. `skills:` is not a seed key, and the
`include_plugins` flag gates only third-party skill sources, never the built-ins.
The sibling-directory behaviour is structural rather than declared, which makes
it stable but undocumented - the same shape of problem as
[the persona catalogue](catalog-persona-replaces-the-role-prompt.md), where the
supported-looking `catalogs:` key also could not do the job alone.

## The trap in a partial override

Two consumers read the roles **directory** rather than the seed: the spawn
prompt builds its `AVAILABLE_ROLES` from its subdirectories, and the
orchestrator builds `valid_roles` the same way when applying a manager-review
reassign.[^engine] A reassign to a role with no directory is skipped with a log
warning and never fails the run. So an override that ships only
`roles/manager/` silently makes every other role unreassignable. Ship one
directory per role the seed declares.

## Not fixed upstream

Upstream main is byte-identical here - same closed `KNOWN_ROLES`, same resolver,
same section rules, same bundled prompts carrying the same lists.[^upstream]
Waiting does not close this.

[^engine]: the engine source, read at the pinned version
[^templates]: the bundled prompts that carry the list
[^measured]: measured on the installed engine and on a live run
[^upstream]: verified against upstream, so this is not a stale-fork artifact
