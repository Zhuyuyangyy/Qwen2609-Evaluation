# QA summary — machine facts only

Release: RealRepoBench-Q2609 v0.1 submission
Archive: `submission_bundle.zip`, SHA-256
`14b2eac3196a12edc54b246c2bab022c0d0ebf2cfbd94a3520d3083136f29b77`

## Integrity

```text
zip entries        : 81
zip testzip()      : OK
bundle QA failures : 0
consistency QA     : OK
absolute-path leaks: 0
embargoed material : 0 files published
```

## Benchmark

```text
frozen tasks       : 8
pytest             : 112 passed
freeze verify      : 8/8 OK
```

## Grades

```text
reported grades    : 7
total_score        : 100 (all 7)
task_success       : true (all 7)
ungraded           : 1 (RB-AS-004, INFRASTRUCTURE_FAILURE)
```

## Measurement coverage

```text
manual_resume:
  confirmed zero on 1/8 covered task
  7/8 unavailable

runtime_error:
  confirmed zero on 1/8 covered task
  7/8 unavailable

semantic intervention:
  0 recorded over 7/8 covered tasks
  1/8 unavailable

duration:
  2/8 tasks carry a value
  no representative median reported
```

## Checks that ran

```text
pytest -q                                   -> 112 passed
build_submission_bundle.py                  -> QA failures: 0
consistency_qa.py                           -> CONSISTENCY OK
zipfile.testzip()                           -> OK
zip SHA-256 recomputed from disk             -> matches FINAL_SUBMISSION_RECORD.md
negative control on the coverage guard       -> QA correctly refused a
                                                full-coverage claim
```

## Deprecated wordings

```text
DO NOT say "zero-resume 7/8"
DO NOT extrapolate a 1/8 confirmed zero to all tasks
DO NOT extrapolate the semantic-intervention zero to the uncovered 8th task
DO NOT merge the 7/7 model rate with the 7/8 harness rate
```
