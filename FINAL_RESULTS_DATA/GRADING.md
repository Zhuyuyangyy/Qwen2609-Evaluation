# Grading facts

Extracted from `RealRepoBench-Q2609/grader/score.py`. The definitions below are
the implemented ones; they are not restated from memory.

## Score allocation: 60 / 20 / 10 / 10

Verified in `grader/score.py`:

```python
W_FUNCTIONAL  = 60
W_HIDDEN      = 20
W_CONSTRAINTS = 10
W_REGRESSION  = 10
```

| component | max | implemented rule |
|---|---:|---|
| Functional Correctness | 60 | awarded **only when** `public_tests.ok AND hidden_tests.ok` |
| Hidden Tests | 20 | full marks when `hidden_tests.ok`; otherwise `round(20 × passed/hidden_case_count)`, and **0 when the run exited non-zero** |
| Constraint Compliance | 10 | full marks when there are **no** frozen-file violations |
| Regression Safety | 10 | full marks when there is **no failure outside the baseline** |

## `TestRun.ok`

```python
if self.exit_code != 0:
    return False
return self.failed == 0 and self.errors == 0
```

A run that prints "N passed" but exits non-zero is not green.

## TaskSuccess

Binary, all legs required:

```python
task_success = bool(
    public_tests.ok
    and hidden_tests.ok
    and not violations
    and no_new_regression
    and target_fix_pass
)
```

## Baseline-relative regression — the actual formulas

```python
known  = set(baseline_failures or [])
target = set(target_failures or [])
allowed = known | target

if regression_tests.failed_test_ids:
    candidate = set(regression_tests.failed_test_ids)
else:
    candidate = {"<unreported>"} if not regression_tests.ok else set()

new_failures      = sorted(candidate - allowed)
surviving_target  = sorted(target & candidate)

target_fix_pass = bool(not surviving_target)
regression      = W_REGRESSION if not new_failures else 0
```

So, as implemented:

- **RegressionPass** ⇔ `candidate_failures − (known ∪ target) = ∅`
- **TargetFixPass** ⇔ `target_failures ∩ candidate_failures = ∅`

### Why `allowed` includes the target failures

A target failure that is still present is charged to the **target** leg only.
Counting it as a new failure as well would charge the same fact twice and make
the two legs impossible to read apart in the report.

### Why this is not "the suite must be green"

Several upstream repositories ship broken tests. `emotion-like-functional-
modulation` has a pre-existing failure
(`tests/test_adaptive_v10.py::TestSystemComparability::test_all_systems_run_an_episode`,
`AttributeError: 'EwmaAppraisalSystem' object has no attribute 'hazard_hat'`,
`emotion_agent/adaptive_systems.py:634`), and RB-EM-004's defect is itself
caught by an upstream test (`test_buckets_sum_to_net_gap`, the frozen
protocol's own acceptance criterion §6.10.6.4).

Scoring "must be green" would therefore fail a correct submission for a defect
it did not cause. The rule is: **pre-existing failures may remain, nothing new
may break, and the failure this task's defect causes must be gone.**

Each task ships `baseline_failures.json` recording
`known_preexisting_failures` and `target_failures`.

## Evidence per task

`03_Execution_Evidence/evaluation_runs/<TASK_ID>/grade.json` holds the grader's
own output. `06_Environment/REVERIFICATION.json`
records an independent recomputation of the same grades on isolated staging
copies, so a recorded grade can be checked rather than taken on trust. records an independent recomputation
of the same grades on isolated staging copies.

## One recorded grade was corrected, and how

`RB-EM-004`'s regression suite was originally invoked from the workspace root, so
pytest reported its one failure with a `repo_snapshot/` prefix that the baseline
does not use. Set arithmetic then counted an already-known failure as new,
scoring 90 instead of 100.

The correction re-ran the **frozen grader** on an isolated copy with the suite
invoked from the root the baseline was recorded from. Scoring semantics were
untouched; every number still comes from the benchmark's grader. The change is
recorded in that task's `grade.json` under `grade_correction` with before/after
values.
