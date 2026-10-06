# Harness metadata schema v0.2 — coverage-aware

Design rule: **a value is only interpretable next to its observation flag.**

v0.1 stored `null` for a field that was never recorded, and every downstream
consumer had to guess whether `null` meant "the event did not happen" or "nobody
looked". Both readings were used, and each produced a wrong aggregate once:

- `null` read as zero → "7/8 tasks completed with no manual resume";
- `null` read as missing → a "zero-resume rate of 12.5%" that looked like a
  measurement while scoring tasks nobody measured.

v0.2 therefore never emits a bare value.

## Required record shape

```json
{
  "task_id": "RB-AS-001",
  "model": "<model id>",
  "harness": "Qoder",
  "schema": "coverage-aware-1",
  "observations": {
    "manual_resume": {
      "value": 0,
      "observed": true,
      "unit": "count"
    },
    "runtime_error": {
      "value": 0,
      "observed": true,
      "unit": "count"
    },
    "semantic_human_intervention": {
      "value": 0,
      "observed": true,
      "unit": "count"
    },
    "duration": {
      "value": 12345,
      "observed": true,
      "unit": "ms"
    }
  }
}
```

## Field conventions

| field | unit | missing representation |
|---|---|---|
| `manual_resume` | count | `{"value": null, "observed": false}` |
| `runtime_error` | count | `{"value": null, "observed": false}` |
| `semantic_human_intervention` | count | `{"value": null, "observed": false}` |
| `duration` | ms (integer) | `{"value": null, "observed": false}` |

`duration` is milliseconds in v0.2; v0.1 archives stored seconds and are
converted by `coverage_schema.py normalise`.

## Aggregation rule

An aggregate over a field with partial observation coverage is **withheld**, not
emitted as zero. `coverage_schema.py summarise` refuses the value and records
the coverage and the reason:

```json
"manual_resume": {
  "coverage": "1/8",
  "coverage_status": "PARTIAL_COVERAGE",
  "value": null,
  "refusal": "aggregate withheld: only 1/8 of tasks have an observed manual_resume; a value over 8 would score unmeasured tasks"
}
```

Only `coverage_status: COMPLETE` fields carry an aggregate.

## Tooling

```bash
python coverage_schema.py selftest     # 8 behavioural checks
python coverage_schema.py normalise <v0.1 metadata.json> ...
python coverage_schema.py report <run root>
```

`selftest` covers the two behaviours that make the schema worth having: a
recorded zero and an unrecorded field are structurally distinguishable, and a
partial-coverage field yields `value: null` rather than `0`.

## Observed on the v0.1 archive

Running `report` over the v0.1 `evaluation_runs/` gives:

| field | coverage | aggregate |
|---|---|---|
| manual_resume | 1/8 | withheld |
| runtime_error | 1/8 | withheld |
| semantic_human_intervention | 7/8 | withheld |
| duration | 2/8 | withheld |

All four match `release/v0.1/AVAILABILITY_MATRIX.md`. The tool refusing every
aggregate is the correct output for that data, not a defect.

## Migration note for v0.1 results

The v0.1 submission bundle is frozen and must not be rewritten. The corrected
interpretation lives in `release/v0.1/FINAL_SUBMISSION_RECORD.md` and
`FINAL_METRICS.json` (`confirmed_*` fields with explicit coverage). This schema
is the forward fix, applied to v0.2 runs, not a retrospective edit of v0.1.
