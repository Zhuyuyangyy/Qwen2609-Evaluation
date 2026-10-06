# Evaluation metadata availability matrix — RealRepoBench-Q2609 v0.1

Derived from `evaluation_runs/<TASK_ID>/metadata.json` and the archived
`grade.json`. `unknown` means the field was absent from the archive; it does
**not** mean the event did not occur.

| Task | manual_resume | runtime_error | duration | semantic_intervention | grade | patch lines |
|---|---|---|---|---|---|---:|
| RB-AS-001 | unknown | unknown | 0.943 | 0 | yes | 13 |
| RB-AS-002 | unknown | unknown | unknown | 0 | yes | 13 |
| RB-AS-003 | unknown | unknown | 147.2 | 0 | yes | 13 |
| RB-AS-004 | unknown | unknown | unknown | unknown | **none** | 3 |
| RB-AS-005 | unknown | unknown | unknown | 0 | yes | 59 |
| RB-EM-001 | **0** | **0** | unknown | 0 | yes | 14 |
| RB-EM-002 | unknown | unknown | unknown | 0 | yes | 37 |
| RB-EM-004 | unknown | unknown | unknown | 0 | yes | 16 |

## Coverage by field

| field | covered | uncovered | covered tasks |
|---|---:|---:|---|
| manual_resume_count | 1/8 | 7/8 | RB-EM-001 |
| runtime_error_count | 1/8 | 7/8 | RB-EM-001 |
| semantic_intervention_count | 7/8 | 1/8 | all but RB-AS-004 |
| duration_seconds | 2/8 | 6/8 | RB-AS-001, RB-AS-003 |
| grade | 7/8 | 1/8 | all but RB-AS-004 |

## Aggregates that this matrix licenses

```text
confirmed_manual_resume_task_count = 0     coverage 1/8  PARTIAL_COVERAGE
confirmed_runtime_error_task_count  = 0    coverage 1/8  PARTIAL_COVERAGE
recorded_semantic_human_interventions = 0  coverage 7/8
zero-resume autonomous completion rate = null  (no defensible denominator)
median duration = null  (2/8 coverage)
```

## Aggregates it does NOT license

- "all 8 tasks needed no manual resume"
- "no runtime errors across the benchmark"
- "no task had a semantic human intervention"
- any single run-wide duration figure
- any 8-task Task Success Rate

## Measurement-validity statement

> Evaluation metadata availability is heterogeneous across tasks; therefore
> aggregate zero-valued claims are reported only over fields with confirmed
> coverage, and each such claim carries its coverage ratio and a
> `PARTIAL_COVERAGE` status.

A zero is a claim about an observation, not about the world. Where the
observation is missing, the honest value is `null` with a stated denominator —
never `0`.

## Note on RB-AS-004

Its row is `unknown` across every telemetry field because no stable model
submission existed; the task is an `INFRASTRUCTURE_FAILURE`, not a graded
failure. Its `patch.diff` records 3 lines because the only tracked delta was a
SQLite runtime-state file written by the repository's own test suite — not a
source change.
