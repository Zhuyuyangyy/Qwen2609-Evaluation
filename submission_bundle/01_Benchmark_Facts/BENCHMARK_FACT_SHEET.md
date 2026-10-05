# Benchmark fact sheet

All figures below were verified against the frozen artifacts
(`benchmark_manifest.json`, `harness/manifest.py::FROZEN_SET`, `tasks.jsonl`),
not copied from any earlier statement.

| field | value |
|---|---|
| Benchmark | RealRepoBench-Q2609 |
| Version | 0.1 |
| Frozen state | `frozen: true` |
| **Frozen sample size** | **8** |
| Repository sources | 2 (AgentShield_V3, emotion-like-functional-modulation-main) |
| Original candidate count | 12 (12 rows in `tasks.jsonl`) |
| Rejected / deferred | 4 (RB-EM-003 rejected; RB-PS-001/002/003 deferred) |

**"最初候选数" 与 "最终 frozen task 数" 是两件事。** `tasks.jsonl` has 12 rows
because it also records the candidates that were not delivered. The formal
benchmark sample size is **8**, the `FROZEN_SET` declared by the benchmark and
mirrored by `benchmark_manifest.json::frozen_task_ids`. Rejected and deferred
tasks never enter any denominator in this submission.

## Frozen task set

| task_id | repository | task_type | category | difficulty |
|---|---|---|---|---|
| RB-AS-001 | AgentShield_V3 | UNSPECIFIED | bug_fix | medium |
| RB-AS-002 | AgentShield_V3 | hidden_only_bug | bug_fix | medium |
| RB-AS-003 | AgentShield_V3 | hidden_only_bug | bug_fix | hard |
| RB-AS-004 | AgentShield_V3 | docs_consistency | docs_sync | easy |
| RB-AS-005 | AgentShield_V3 | behavior_preserving_refactor | refactor | hard |
| RB-EM-001 | emotion-like-functional-modulation-main | hidden_only_bug | bug_fix | medium |
| RB-EM-002 | emotion-like-functional-modulation-main | hidden_only_bug | bug_fix | hard |
| RB-EM-004 | emotion-like-functional-modulation-main | public_visible_bug | instrumentation | medium |

## Distribution

| dimension | distribution |
|---|---|
| repository | AgentShield_V3 × 5; emotion × 3 |
| task_type | 4 declared types across 7 tasks: hidden_only_bug × 4; public_visible_bug × 1; docs_consistency × 1; behavior_preserving_refactor × 1 — plus 1 UNSPECIFIED task (RB-AS-001) |
| category | bug_fix × 5; docs_sync × 1; refactor × 1; instrumentation × 1 |
| difficulty | medium × 4; hard × 3; easy × 1 |
| capabilities | 4 declared each on 7 tasks; **UNSPECIFIED on RB-AS-001** |

`UNSPECIFIED` is retained rather than filled in. RB-AS-001 was built before the
`task_type` and `capabilities` fields existed; assigning one now would be
fabrication, and the benchmark is frozen so it cannot be amended.

## Construction method

Recorded facts, from `METHODOLOGY.md` and the benchmark's own tooling:

- **private reconstructed defect** — the shipped defect is re-injected into a
  private snapshot, not taken from a live public repository;
- **defective/reference dual-state verification** — every task was verified in
  both states before freezing: the defect must be *detectable* (at least one
  target check fails) and the reference repair must clear it;
- **public/hidden isolation** — hidden checks and the grader are never present
  in the agent's workspace; grading runs on an isolated staging copy;
- **protected files** — tests, frozen artifacts and the task's own test command
  are checksummed; modifying them is a constraint violation;
- **checksum freeze** — the frozen set is recorded in `checksums.sha256`;
- **reference repair validation** — each task's reference change was applied and
  the resulting state verified green;
- **baseline-relative regression** — see `GRADING.md`.

## Why the frozen set is smaller than the candidate set

`RB-EM-003` was rejected at construction. `pytest --collect-only -q` returns 413
collected, so the README's "412 passed" is correct for passed-count semantics;
the only stale figure is a single location, and no frozen artifact backs the
README's regime-means table, so a richer instance could not be built without
inventing data.

`RB-PS-001/002/003` were deferred: the DRX SPARK environment and harness were
not baselined. Padding the set was judged worse than a smaller honest one.
