# Methodology

Facts only, reconstructed from the frozen benchmark's own artifacts
(`README.md`, `benchmark_manifest.json`, `harness/*`) after an earlier bundle
rebuild replaced the copy that had lived outside the frozen tree. Nothing here
is a new claim.

## What it measures

Repository-level software-engineering tasks built from real local Python
repositories, not synthetic algorithm problems. Each task ships a private
snapshot of a real codebase with one defect present, and is graded on whether an
agent can find and repair it without breaking the repository or gaming the
checks.

## Composition (frozen set: 8)

| repository | tasks |
|---|---|
| AgentShield_V3 | 5 |
| emotion-like-functional-modulation-main | 3 |
| DRX SPARK | 0 (deferred) |

Task types (see `BENCHMARK_FACT_SHEET.md` for the per-task table):
`hidden_only_bug` ×4, `public_visible_bug` ×1, `docs_consistency` ×1,
`behavior_preserving_refactor` ×1, plus `UNSPECIFIED` ×1 for RB-AS-001, which
predates the `task_type` field.

Four types are deliberate: a benchmark that repeats one trick measures one
ability, and an agent that only solves one kind of problem should not score well
on the other four.

## Construction chain

```
real repository
  -> current code
  -> re-inject an equivalent defect
  -> private snapshot, .git stripped
  -> own public + hidden checks
  -> SHA-256 freeze
```

Recorded properties of that chain:

- **private reconstructed defect** — the shipped defect is re-injected into a
  private snapshot, not taken from a live public repository.
- **defective/reference dual-state verification** — every task was verified in
  both states before freezing: the defect must be *detectable* (at least one
  target check fails) and the reference repair must clear it.
- **public/hidden isolation** — hidden checks and the grader are never present
  in the agent's workspace; grading runs on an isolated staging copy outside it.
- **protected files** — the tests, the frozen artifacts and the task's own test
  command are checksummed; modifying them is a constraint violation.
- **checksum freeze** — the frozen set is recorded in `checksums.sha256`, and
  ``git remote`` is empty in every exported workspace.
- **reference repair validation** — each task's reference change was applied and
  the resulting state verified green.
- **baseline-relative regression** — see `GRADING.md`.

No snapshot contains git history. AgentShield_V3 is a public repository and the
fixes to the real historical bugs live in its commits, so a snapshot that carried
`.git` would let an agent look the answer up.

## Why 12 candidates became 8 frozen tasks

- `RB-EM-003` — **rejected at construction.** `pytest --collect-only -q` returns
  413 collected, so the README's "412 passed" is correct for passed-count
  semantics; the only stale figure is a single location. No frozen artifact
  backs the README's regime-means table, so a richer docs-consistency instance
  could not be built without inventing data.
- `RB-PS-001/002/003` — **deferred.** The DRX SPARK environment and harness
  were not baselined. Padding the set was judged worse than a smaller honest
  one.

The frozen set is declared explicitly in the benchmark's
`harness/manifest.py::FROZEN_SET` and mirrored by
`benchmark_manifest.json::frozen_task_ids`; `aggregate.py` refuses to run unless
that set is exactly these 8 tasks.

## Two tasks required a real correction during construction, both recorded

- The export initially pruned the AgentDojo `.arrow` dataset as "cache", which
  turned a working task into 19 environment errors. Data files are now kept;
  only build residue is pruned.
- The export initially flattened the snapshot, breaking the public checks that
  locate the code under test. The snapshot is now kept under `repo_snapshot/`.

Both are recorded because they affect how the workspace audit should be read.
