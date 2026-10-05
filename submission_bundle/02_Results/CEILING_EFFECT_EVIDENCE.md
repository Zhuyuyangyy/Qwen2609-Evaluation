# Ceiling-effect evidence

Facts only. This document establishes what the numbers *are*; it does not
establish the model's capability ceiling.

## Observed facts

| item | value |
|---|---|
| valid model runs | 7 |
| successes among valid runs | 7 |
| perfect scores (100/100) among valid runs | 7 |
| correctness failures among valid runs | 0 |
| valid-run Task Success Rate | 7/7 = 100% |

## Score distribution among valid runs

| total_score | count |
|---:|---:|
| 100 | 7 |
| 90–99 | 0 |
| <90 | 0 |

Every valid run earned the full 60 functional + 20 hidden + 10 constraint +
10 regression allocation.

## Failure distribution

`failure_cases.jsonl` is empty. Among the 7 valid model runs there is no
recorded correctness failure, no constraint violation, no regression, and no
incomplete fix.

## Patch size (files modified per run)

| task_id | files modified |
|---|---:|
| RB-AS-001 | 1 |
| RB-AS-002 | 1 |
| RB-AS-003 | 1 |
| RB-AS-005 | 2 |
| RB-EM-001 | 1 |
| RB-EM-002 | 1 |
| RB-EM-004 | 1 |

Six of seven runs changed a single file; one changed two.

## Consistency statement

> Results are consistent with a ceiling effect on the valid runs.

That is the full extent of the claim supported by these data. It is **not** a
claim that the model's capability ceiling has been located, and it cannot be:
one of eight tasks produced no model output at all, so the benchmark never
exercised the model on its full frozen set.

## What these data cannot support

- No 8-task Task Success Rate exists. See `TASK_RESULT_TABLE.md` and
  `HARNESS_RELIABILITY_FACTS.md`.
- No difficulty gradient can be read from n=7 with 7 successes; "easy" and
  "hard" labels are construction-time labels, not measured discrimination.
- No comparison against another model is possible from this run alone.
