# Readiness checklist (run by /build-ready before any executor starts)

Mechanical, per step, against the base commit:
- [ ] `bernstein plan validate <plan>` clean (schema, unique titles, deps, cycles)
- [ ] every allowlisted path exists or is declared new
- [ ] sibling steps in a stage own disjoint files
- [ ] every validation command runs on the base and its expected state matches (green, or the named red window)
- [ ] every cited spec section, symbol and path resolves; spec sha256 recorded
- [ ] every item has a done-criterion the scorer can check
- [ ] completion contract and Deviations rule present in the brief
- [ ] parallel seam splits have a driver-written interface contract in contracts/
- [ ] brief under the length cap, headers present

Critic, one fresh Opus subagent per brief, read-only tools:
- underspecified points; contradictions with the spec; items that cannot be validated; anything two briefs both claim
- blocking findings go back as brief edits; rerun until a round warrants no edits
