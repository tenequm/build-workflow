# The catalog persona prefix (2026-09-02)

Every Bernstein spawn prompt opens with a catalog persona ("Catalog agent 'AI Data
Remediation Engineer' ... selected for role 'backend'" in the spawner log). Read from
Bernstein 3.19.0 source in `~/pjv/sipyourdrink-ltd/bernstein/src/bernstein`.

## Where it is built

- `core/agents/spawner_core.py:4162` - `catalog_agent = self._catalog.match(role, task_description)`.
- `core/agents/spawner_core.py:4174-4181` - the matched agent's `system_prompt` (plus a
  "Preferred tools" hint) becomes `catalog_system_prompt`, passed to the renderer at `:4281`.
  The log line is `:4296`.
- `core/agents/spawn_prompt.py:704-705` - `_resolve_role_prompt` returns
  `catalog_system_prompt` first, ahead of the skill pack and the role template, so the
  persona *replaces* the role block; it is placed as the first named section at
  `spawn_prompt.py:1006` (`("role", role_prompt)`), i.e. the prompt's prefix.

## Where the personas come from

`core/orchestration/orchestrator.py:6862-6875` registers every agent found in
`~/.bernstein/catalogs/agency` (`agents/agency_provider.py:458-460`) into the registry,
guarded only by `agency_cache_path.exists()`. Divisions map to Bernstein roles at
`agents/agency_provider.py:45-52` (engineering -> backend, testing -> qa).

## The switch: there is none

`agent_catalog` (the spike's guess) only ADDS a directory catalog: `seed_parser.py:2476`,
`seed_config.py:413`, consumed at `orchestrator.py:6832-6839`, and validated to exist
(`config_path_validation.py:99-116`). The `catalogs:` seed key (`seed_parser.py:1998-2007`)
replaces the registry entries, but the agency-cache load above ignores entries, so
`catalogs: []` does not disable it. No env var and no `run` flag reaches either site.

Prefix size, measured: the backend persona
`~/.bernstein/catalogs/agency/engineering/engineering-ai-data-remediation-engineer.md` is
10,691 bytes / 211 lines.

## Two levers without patching Bernstein

1. Remove or rename `~/.bernstein/catalogs/agency` - the `exists()` gate above is the whole
   condition. Machine-local, not seed-declared, so readiness must check it.
2. Use role names no catalog agent carries and that have no affinity set
   (`agents/catalog.py:790-800`): `match()` returns None when there is no exact-role agent
   and `_ROLE_AFFINITY.get(role)` is empty (`catalog.py:714-730`, `:769-780`). Roles are
   free strings (`core/tasks/models.py:2125`), so `builder`/`grader` dodge the catalog where
   `backend`/`reviewer` do not. Cost: the role becomes the key for `role_model_policy` too,
   and the role prompt falls back to a generic "You are a <role> specialist." stub.

Upstream issue candidate: a seed key gating `orchestrator.py:6862-6875` (and the `match()`
call at `spawner_core.py:4162`), so a plan can opt out of catalog personas.
