---
type: Finding
title: A third-party persona catalogue replaces every role prompt, and only an engine patch switches it off
description: Bernstein enables the Agency persona marketplace by default and a matched persona REPLACES the built-in role prompt, so on this host /review-pr's `reviewer` ran as a UI design critic and `qa` as a GIS data engineer; the `catalogs:` seed key cannot stop it because the orchestrator loads the host-local cache without consulting the registry, so the operator engine carries a patch that makes that load honour the configured entries.
tags: [bernstein, engine, spawn-prompt, catalog, review-pr]
status: stable
stale_after: "2027-03-12T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-12T00:55:00Z" }
sources:
  - id: engine
    resource: "bernstein 3.19.2 as installed (site-packages): core/agents/spawner_core.py:4510 and :1262, core/agents/spawn_prompt.py:704, core/orchestration/orchestrator.py:7008-7020, agents/catalog.py:315-328, agents/agency_provider.py:458-460"
    title: the engine source, read at the pinned version
  - id: observed
    resource: "/review-pr eval gate of 2026-09-12 00:14 UTC: the live pi command line for the gate's reviewer worker began `# UI Finish-Gate Reviewer Agent Personality`, and the qa worker `# GISQAEngineer`, read from /proc/<pid>/cmdline while the run was in flight"
    title: measured on a live run, not inferred
  - id: patch
    resource: /skills/build-run/scripts/prepare-engine.py
    title: the sixth operator patch, which supplies the missing gate
  - id: seed
    resource: /skills/review-pr/templates/review-seed.yaml
    title: the seed that opts out
---

# What replaces the role prompt

A matched catalogue persona does not decorate the role prompt, it *replaces* it:
`spawner_core.py:1262` assigns `role_prompt = catalog_system_prompt` for every
non-manager role, and `spawn_prompt.py:704` returns that prompt ahead of the skill
pack and the role template. The persona is then the prompt's first section, so the
review doctrine rides underneath somebody else's job description.[^engine]

The catalogue is on by default. `CatalogRegistry.default()` (`catalog.py:315-328`)
enables one entry sourced from `https://github.com/msitarzewski/agency-agents`,
cloned to `~/.bernstein/catalogs/agency` - 324 persona files across divisions like
design, gis, finance and healthcare. Matching is by role name, and the roles
/review-pr uses collide badly: on this host `reviewer` drew
`design/design-ui-finish-gate-reviewer.md` (8,988 bytes of UI-shipping criteria) and
`qa` drew `gis/gis-qa-engineer.md` (5,400 bytes about CRS mismatches and polygon
topology).[^observed]

This was invisible in every log the harness reads. It surfaced only by reading a live
worker's `/proc/<pid>/cmdline` during a gate run.[^observed]

# Why the seed key alone does not close it

`catalogs: []` parses correctly and yields an empty registry, and the orchestrator does
prefer a seed-supplied registry over the default. It makes no difference, because the
next block loads the host-local cache without ever consulting the registry's
entries - `agency_cache_path.exists()` is the entire condition, and every persona found
there is registered into the match path.[^engine] Config says which catalogues are
enabled; this path does not ask.

That is a portability defect, not a preference: the same seed produces different system
prompts on two machines depending on whether a directory happens to exist under `$HOME`.

# The switch, as an operator patch

The sixth patch in `prepare-engine.py` gates that load on the configured registry:

    if any(e.type == "agency" for e in catalog_registry.entries) and agency_cache_path.exists():

Stock behaviour is unchanged for anyone who does not configure `catalogs:`, since the
default registry carries an enabled agency entry. A seed that sets `catalogs: []` now
actually opts out.[^patch][^seed] Verified on a live worker after the rebuild: the
reviewer's prompt begins `# You are a Code Reviewer`, the engine's own role template.

The two unpatched levers remain available and remain bad: deleting
`~/.bernstein/catalogs/agency` is machine-local and silently undone by a resync, and
choosing role names no persona matches costs the role prompt entirely and changes the
key that `role_model_policy` routes on.
