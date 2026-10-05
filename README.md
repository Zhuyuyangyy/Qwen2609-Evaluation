# Qwen2609-Evaluation

Aggregation tooling for the RealRepoBench-Q2609 v0.1 formal evaluation.

This tree is deliberately OUTSIDE the frozen benchmark. Nothing here is
checksummed by the benchmark, and nothing here writes into it: the 8125 frozen
files are the artifacts the evaluation measures, so the aggregation tooling
must not be able to touch them.

## Layout

```
aggregate.py           read-only result aggregation
make_smoke_runs.py     build a small smoke run from the real grader's output
evaluation_runs/       one directory per task (created by the runner)
results/               results.csv, summary.json, failure_cases.jsonl,
                       AGGREGATION_REPORT.md
tests/                 synthetic fixtures for the aggregation rules
```

## Run convention

Each task's run directory holds:

```
evaluation_runs/<TASK_ID>/
    grade.json          produced by the benchmark's grader; the only source of Task Success
    metadata.json       duration, interventions, completion flags
    patch.diff          the agent's change
    terminal.log        the agent's session
    public_test.log     public check output
    interventions.log   manual edits, if any
```

`grade.json` is the grader's `Score.to_dict()` output. `aggregate.py` reads it
and never re-derives the verdict.

## Aggregate

```
python aggregate.py                     # reads evaluation_runs/, writes results/
```

Hard rules it enforces:

* the denominator comes from the benchmark's frozen manifest and the harness's
  `FROZEN_SET`, and both must agree on exactly 8;
* only frozen task ids are accepted -- a rejected or deferred task entering the
  set aborts the run;
* duplicate task ids abort the run;
* `task_success` must agree with the grader's own components, or the run aborts;
* a partial run never publishes a formal rate: `task_success_rate` stays null
  and a `provisional_task_success_rate` is given instead;
* baseline-relative `regression_pass` is passed through, never re-judged.

## Failure taxonomy

Controlled, so categories are comparable across tasks:
`LOCALIZATION_FAILURE`, `IMPLEMENTATION_FAILURE`, `INCOMPLETE_FIX`,
`REGRESSION`, `CONSTRAINT_VIOLATION`, `TEST_GAMING`, `TOOL_FAILURE`,
`ENVIRONMENT_FAILURE`, `TIMEOUT`, `UNKNOWN`. Anything unmapped becomes
`UNKNOWN` rather than free text. A task with no grade at all is `MISSING` --
a state, not a failure category.

## Tests

```
python -m pytest tests/ -q
```

24 tests covering the six cases that must not silently pass:
A (8/8 complete), B (5/8 never published as final), C (a non-frozen task
enters), D (duplicate task id), E (verdict disagrees with components),
F (a pre-existing baseline failure is not re-judged).
