# Harness reliability

Reported separately from model quality, because the two measure different
things. A task whose session never produced a stable submission tells us
nothing about the model: there was no model output to judge.

All figures come from `EVALUATION_STATUS.json`.

## A. Benchmark execution (denominator: 8 frozen tasks)

| outcome | count | tasks |
|---|---:|---|
| valid model runs | 7 | RB-AS-001, RB-AS-002, RB-AS-003, RB-AS-005, RB-EM-001, RB-EM-002, RB-EM-004 |
| infrastructure failures | 1 | RB-AS-004 |
| not run | 0 | — |
| invalid runs | 0 | — |

## B. Model performance (denominator: valid runs only)

`valid_run_task_success_rate = 7 / 7 = 1.0`

This is **not** the 8-task Task Success Rate. RB-AS-004 contributes no model
output, so it is outside the denominator rather than a zero. No 8-task TSR is
reported for this run.

## C. Harness reliability (denominator: 8)

| metric | value |
|---|---|
| harness valid submission rate | 7 / 8 = 0.875 |
| zero-resume autonomous completion rate | 7 / 8 = 0.875 |
| tasks with a manual resume | 0 |
| tasks with a recorded runtime error | 0 |
| infrastructure failure tasks | 1 (RB-AS-004) |

## What "resume" means here

`manual_resume_count` and `semantic_human_intervention_count` are separate
fields. Clicking "continue" or "retry" without any解题 information is a resume,
not an intervention, and is counted only in `manual_resume_count`. No task in
this run recorded either, so both are zero for all 8 tasks.

## RB-AS-004

Recorded as `INFRASTRUCTURE_FAILURE` with evidence in
`evaluation_runs/RB-AS-004/`. Facts recorded there: 0 tracked `.py` files
modified, no untracked non-cache files, and the only tracked delta is a SQLite
file the repository's own test suite writes at runtime. No `grade.json` was
produced for it and none may be invented, which is why `aggregate.py` reports
`evaluation_complete: false` and a null formal `task_success_rate`. That null is
the intended output, not a defect in the tooling.
