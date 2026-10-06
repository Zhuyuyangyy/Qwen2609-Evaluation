# Paired-model evaluation protocol — RealRepoBench-Q2609 v0.1

How to run a second (and third) model against the **same frozen benchmark**, so
the comparison is paired rather than a reading of two unrelated report sections.

Nothing in this protocol changes v0.1. The frozen set, workspaces, hidden checks
and grader are inputs, not variables.

## What is held constant

| held fixed | where |
|---|---|
| 8 task statements | `workspaces/<TASK_ID>/prompt.md` |
| defective snapshots | `workspaces/<TASK_ID>/repo_snapshot/` |
| public checks | `workspaces/<TASK_ID>/public_tests/` |
| hidden checks | `RealRepoBench-Q2609/tasks/<TASK_ID>/hidden_tests/` |
| grader | `RealRepoBench-Q2609/grader/score.py` |
| baselines | `RealRepoBench-Q2609/tasks/<TASK_ID>/baseline_failures.json` |
| scoring weights | 60 / 20 / 10 / 10 |

## What is the variable

Only the model, and only the harness that drives it. Each model gets a fresh
session per task, with no git remote and no upstream history in its workspace.

## Run directory convention

```text
runs/<model_id>/<TASK_ID>/
    metadata.json      required
    grade.json         required  (produced by the frozen grader, externally)
    patch.diff         required  (git diff against the frozen baseline)
    terminal.log       optional
    public_test.log    optional
    interventions.log  optional
```

`metadata.json` must use the coverage-aware schema from
`release/v0.2/HARNESS_METADATA_SCHEMA.md`: every telemetry field carries both a
value and an `observed` flag. A runner that cannot observe a field records
`{"value": null, "observed": false}` rather than omitting it, so a later reader
can tell "did not happen" from "not recorded".

## Grading stays external

Grading runs outside the model's workspace, on an isolated copy. Hidden checks
and the grader are never copied into a workspace, and their output is never
surfaced to the running session.

## Commands

```bash
# what will be run
python paired_eval.py plan

# one model's coverage-aware summary
python paired_eval.py collect --model <id> --runs runs/<id>

# two models side by side
python paired_eval.py compare --model a --runs runs/a \
                              --against b --against-runs runs/b
```

## Comparability rule

`compare` marks a telemetry field comparable only when **both** models observed
it on the same set of tasks. A measured field against an unmeasured one is not a
model difference; it is a record-keeping difference, and publishing it as the
former would be fabrication.

## Reporting rule

Each model reports:

```text
valid_run_task_success_rate   = successes / graded tasks (that model)
harness_valid_submission_rate = graded tasks / 8
```

An infrastructure failure is **not** a valid model submission, so it lowers the
submission rate and never enters the model denominator. A task with metadata but
no grade is an infrastructure failure, not a success and not a model failure.

## Known hazard this protocol guards against

The v0.1 run of this benchmark had heterogeneous telemetry coverage across tasks
(manual-resume recorded on 1 of 8, duration on 2 of 8). Comparing two models on
those fields without a coverage check would have produced differences that were
artifacts of the recording, not of the models. The coverage-aware schema exists
to make that mistake detectable rather than invisible.
