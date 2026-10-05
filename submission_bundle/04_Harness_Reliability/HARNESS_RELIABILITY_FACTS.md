# Harness reliability facts

Objective observations only. No internal Qoder root cause is asserted.

All figures are recomputed from the archived `metadata.json` /
`grade.json` / workspace evidence by `final_results.py`.

## Summary

| metric | value | denominator |
|---|---:|---|
| tasks in benchmark | 8 | — |
| valid model submissions | 7 | 8 |
| infrastructure failures | 1 | 8 |
| not run | 0 | 8 |
| invalid runs | 0 | 8 |
| harness valid submission rate | 87.5% (7/8) | 8 |
| confirmed tasks needing a manual resume | 0 | 1 (of 1 recovered) |
| total manual resumes recorded | 0 | 1 (of 1 recovered) |
| tasks with a recorded runtime error | 0 | 1 (of 1 recovered) |
| resume-count known tasks | 1 | 8 |
| resume-count unknown tasks | 7 | 8 |
| tasks whose resume/error count is unrecoverable | 7 | 8 |
| zero-resume autonomous completions (recovered) | 1 | 8 |
| **zero-resume autonomous completion rate** | **NOT_AVAILABLE** | — |

> `NOT_AVAILABLE` in the resume / runtime-error columns means the count could
> not be recovered from the archived metadata. It does **not** mean zero. Only
> RB-EM-001 recorded a recovered count of 0, so only that task is known to have
> needed no manual resume. Counting the unrecoverable tasks as zero would have
> produced a run-wide zero-resume figure that the evidence does not support.


> The zero-resume **rate** is deliberately `null` / NOT_AVAILABLE. A denominator
> of 8 would score the 7 tasks whose resume count could not be recovered as if
> they had been measured, so only the raw counts are published:
> `confirmed_zero_resume_tasks = 1`, `resume_count_known_tasks = 1`,
> `resume_count_unknown_tasks = 7`.


## Per-task

| task_id | run_status | valid submission | manual resume | runtime errors | completed without resume |
|---|---|---|---:|---:|---|
| RB-AS-001 | VALID_SUBMISSION | yes | NOT_AVAILABLE | NOT_AVAILABLE | unknown |
| RB-AS-002 | VALID_SUBMISSION | yes | NOT_AVAILABLE | NOT_AVAILABLE | unknown |
| RB-AS-003 | VALID_SUBMISSION | yes | NOT_AVAILABLE | NOT_AVAILABLE | unknown |
| RB-AS-004 | INFRASTRUCTURE_FAILURE | no | NOT_AVAILABLE | NOT_AVAILABLE | no |
| RB-AS-005 | VALID_SUBMISSION | yes | NOT_AVAILABLE | NOT_AVAILABLE | unknown |
| RB-EM-001 | VALID_SUBMISSION | yes | 0 | 0 | yes |
| RB-EM-002 | VALID_SUBMISSION | yes | NOT_AVAILABLE | NOT_AVAILABLE | unknown |
| RB-EM-004 | VALID_SUBMISSION | yes | NOT_AVAILABLE | NOT_AVAILABLE | unknown |

`NOT_AVAILABLE` for RB-AS-004 means the surviving session evidence did not
establish the counts. They were not estimated.

## Term definitions (kept distinct)

- **manual resume** — a human had to click "continue"/"retry" to make the
  session proceed, without supplying any解题 information.
- **semantic human intervention** — a human supplied solution information. **No
  task in this run recorded one.** Both fields are recorded separately so a
  resume is never miscounted as a hint.

## RB-AS-004

Recorded as `INFRASTRUCTURE_FAILURE`. Evidence in
`03_Execution_Evidence/evaluation_runs/RB-AS-004/`:

- `git status --porcelain`: no tracked `.py` modified; no untracked non-cache
  files.
- `git diff --stat HEAD`: the only tracked delta is
  `repo_snapshot/backend/shield_sessions.db`, a SQLite file the repository's own
  governance service writes while its test suite exercises it. It is runtime
  state, not source.
- No evidence of a terminal command that produced a final patch.
- Baseline commit unchanged; no git remote.

Consequences, recorded deliberately:

- no `grade.json` was produced for this task and none may be invented;
- it is **not** counted as a model failure — there was no model output to judge;
- `aggregate.py` therefore reports `evaluation_complete: false` and a null
  formal `task_success_rate`, which is the intended behaviour.

Not established, and not asserted here: whether the session exited during
reasoning or during tool execution, and the exact retry count.
