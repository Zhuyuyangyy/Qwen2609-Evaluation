# AgentShield V3.1 Evidence Summary

AgentShield V3.1 extends V3 from a synthetic-only benchmark setting to a mixed evaluation setting with SCI-600 synthetic cases and Semi-Real-150 controlled traces.

The Semi-Real-150 dataset contains 150 traces and 405 tool-call steps across nine controlled semi-real scenario types:

- normal business query
- normal report generation
- sensitive query only
- sensitive query then export
- sensitive query then compress and send
- privilege escalation
- audit log bypass
- bulk delete
- multi-agent delegation risk

## Key Result

Compared with the local-context baseline, AgentShield chain-aware governance improves BLOCK recall from 16.67% to 75.00% on Semi-Real-150.

This supports the core V3.1 claim: single-step local context can identify some local risk, but behavior-chain modeling is substantially better at detecting delayed, delegated, and chain-amplified risks.

## Semi-Real-150 Results

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| Tool-name rules | 33.33% | 17.09% | 0.00% | 91.67% | 0.00% |
| Content keywords | 33.33% | 19.61% | 0.00% | 50.00% | 0.00% |
| Local context | 66.67% | 63.37% | 16.67% | 0.00% | 0.00% |
| AgentShield chain-aware | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |

## Reproduction Commands

```bash
python -m pytest -q
python benchmark\generate_semireal_traces.py
python benchmark\evaluate_semireal.py
```

Expected verification snapshot:

- tests: 14 passed
- generated traces: 150
- generated steps: 405
- output table: `benchmark/results/semireal_baseline_table.md`
- output report: `benchmark/results/semireal_baseline_report.json`

## Scope

This tag is intended as the V3.1 reproducibility anchor for the controlled semi-real benchmark. It does not include private logs, patent materials, backups, or production data.

The next planned research increment should be AgentShield V3.2 Ablation Evidence Pack.
