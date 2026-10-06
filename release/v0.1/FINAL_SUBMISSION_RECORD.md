# FINAL SUBMISSION RECORD

**Release:** RealRepoBench-Q2609 v0.1 submission
**Status:** FROZEN — do not repackage without a blocking error

## Archive

```text
Archive   : submission_bundle.zip
SHA256    : 14b2eac3196a12edc54b246c2bab022c0d0ebf2cfbd94a3520d3083136f29b77
Bytes     : 92297
Entries   : 81
testzip() : OK
```

## Benchmark

```text
Frozen tasks : 8
pytest       : 112 passed
Frozen set   : RB-AS-001, RB-AS-002, RB-AS-003, RB-AS-004, RB-AS-005,
               RB-EM-001, RB-EM-002, RB-EM-004
Excluded     : RB-EM-003 (rejected at construction)
               RB-PS-001, RB-PS-002, RB-PS-003 (deferred)
```

## Grade

```text
Reported grades : 7
All total       : 100
All task_success: true
```

RB-AS-004 produced no grade and no model submission. It is recorded as
`INFRASTRUCTURE_FAILURE` with a `task_success` of `null` — not `false`, not a
model failure, and not a fabricated grade.

## Rates — with their denominators stated

```text
Valid-run Task Success Rate       = 7 / 7 = 100%   (denominator: valid model runs)
Harness Valid Submission Rate     = 7 / 8 = 87.5%  (denominator: frozen tasks)
8-task Task Success Rate          = DOES NOT EXIST
```

The two published rates have different denominators and must never be merged
into a single figure.

## Coverage semantics

These fields carry a coverage qualifier because a zero is only meaningful when
the underlying quantity was actually observed.

```text
confirmed_manual_resume_task_count = 0
manual_resume_count_coverage      = 1/8
manual_resume_count_status        = PARTIAL_COVERAGE

confirmed_runtime_error_task_count = 0
runtime_error_count_coverage      = 1/8
runtime_error_count_status        = PARTIAL_COVERAGE

recorded_semantic_human_interventions = 0
semantic_intervention_coverage        = 7/8
```

## Deprecated interpretations

Do **not** restate any of the following:

- "zero-resume 7/8" — the zero-resume rate is `null` / `NOT_AVAILABLE`; a
  denominator of 8 would score tasks that were never measured.
- "all 8 tasks completed without manual resume" — only 1 of 8 tasks has a
  recovered count; the confirmed zero applies to that 1 task alone.
- "no runtime errors across the benchmark" — coverage is 1/8.
- "no semantic human intervention in any task" — coverage is 7/8; the 8th task's
  count was not recovered and the claim is not extended to it.
- "Qwen scored 87.5%" — that is the harness valid-submission rate, not a model
  quality figure.

## Reproducing this hash

```bash
python -c "import hashlib,pathlib; \
print(hashlib.sha256(pathlib.Path('submission_bundle.zip').read_bytes()).hexdigest())"
```

Expected output: `14b2eac3196a12edc54b246c2bab022c0d0ebf2cfbd94a3520d3083136f29b77`

## What was NOT changed to reach this release

- `frozen benchmark` — untouched; `pytest -q` 112 passed at freeze time.
- `grade.json` — 7 records, all produced by the frozen grader.
- `TaskSuccess` — taken verbatim from the grader, never re-derived here.
- `patch.diff` — model output, recorded as produced.
- `tests` — no test was added, removed, or edited for this release.

All post-freeze edits were confined to metadata and to how partial coverage is
worded. The measurement semantics fix (unknown is not zero) is a reporting
correction, not a change to any measured result.
