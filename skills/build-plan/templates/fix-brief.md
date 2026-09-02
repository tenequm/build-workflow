# Brief: fix-N - judge findings on <phase>

Read `<run dir>/judge/<phase>/blind-review.md`. If its Verdict is "merge as-is",
write `.agents/fix-N.md` saying "no fix needed" with the verdict line quoted and
complete the task. Otherwise fix every defect labelled certain, in the listed
order, each with a test that fails before and passes after; treat plausible
defects as items only when the ledger gives a reproduction. Same allowlist as
<phase>. Validation as in <phase>'s brief. Report per item with file:line.
