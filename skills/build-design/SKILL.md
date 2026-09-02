---
name: build-design
description: "Stage 1 of the build workflow: turn an idea into docs/spec.md. Interviews the user grill-me style, fans out section drafts to Opus subagents, runs one fresh critic over the spec for contradictions, converges when a critic round warrants no edits. Use when starting a big build from an idea, or when the spec must change. Triggers: /build-design, design the spec, start a build from an idea."
---

# build-design

Output: `docs/spec.md` (tracked; section numbers frozen once a plan cites them)
and `.agents/build/runs/<slug>/ledger.md` opened with the spec sha256.

Pick `<slug>` here, one lowercase word or two joined by `-`. It is the run
directory name AND the plan's `name:` in stage 2 AND the plan file name: the
tool derives the run dir from the plan's `name:`, so they cannot differ. Every
later stage is invoked as `/build-<stage> .agents/build/runs/<slug>`.

1. Orient:

       cat CLAUDE.md AGENTS.md 2>/dev/null; cat docs/spec.md 2>/dev/null
       ls .agents/build/runs/*/handoff.md 2>/dev/null

2. Interview: the three to five questions that change the design, grill-me
   style, one message. Record each answer as a decision with the alternative it
   rejected; those lines are what the drafters are given.
3. Draft: one Opus subagent per top-level spec section, at most four in
   parallel, `model: opus`. Give each: the decisions verbatim with "do not
   re-litigate", the one section it owns with its exact heading, the existing
   spec's voice, "ASCII only, no em-dashes", a line cap, and "return ONLY the
   finished markdown section as your final message; write no files". The driver
   pastes the returned sections into `docs/spec.md`. Never let two subagents own
   one section, and never let one write the file.
4. Critic: one fresh Opus subagent, read-only, given the whole spec plus the
   code it describes: "list contradictions, undefined terms, and invariants with
   no check behind them; blocking findings only; write no files". Blocking
   findings become driver edits; rerun until a round warrants no edits. One
   round is normal for a small spec.
5. Close:

       git add docs/spec.md && git commit -m "docs(spec): <what changed>"
       mkdir -p .agents/build/runs/<slug>
       printf -- "- %s design: spec.md sha256=%s sections %s\n" \
         "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(shasum -a 256 docs/spec.md | cut -d' ' -f1)" \
         "<the section numbers this round changed, e.g. 1,3>" \
         >> .agents/build/runs/<slug>/ledger.md

   Then offer `/build-plan .agents/build/runs/<slug>`.

Rules: ASCII only; the spec changes only through this skill; never mid-plan.
Number sections `## <n>. <title>` -- readiness resolves brief citations against
exactly that pattern.
