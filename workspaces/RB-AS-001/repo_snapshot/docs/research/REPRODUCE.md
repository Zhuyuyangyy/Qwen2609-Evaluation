# REPRODUCE.md - AgentShield V3

## Prerequisites

- **Python**: 3.10+
- **OS**: Linux / macOS / Windows
- **GPU**: Not required

## Install

```bash
cd AgentShield_V3
pip install -r requirements.txt
```

Dependencies: fastapi, uvicorn, pydantic, loguru, httpx, pytest, slowapi

## Smoke Test

```bash
cd backend
python -m pytest tests/ -v
```

## Run Benchmark

```bash
python benchmark/evaluate.py
```

Pre-computed benchmark results available:
- `benchmark/benchmark_report.json`
- `benchmark/benchmark_expanded_report.json`
- `benchmark/benchmark_v3_standard.json`
- `benchmark/confusion_matrix_v3.json`

## Expected Outputs

- Behavior-chain risk governance for multi-agent tool-use
- Risk propagation through behavior graphs
- Three-level governance: ALLOW / HUMAN_REVIEW / BLOCK
- Audit evidence and counterfactual analysis

## Known Issues

- **Hardcoded paths**: Multiple files reference `D:\ZYY Project\ASF-BGT-Framework` and `D:\ZYY Project\AgentShield_V3`
  - `benchmark/analyze_action_failures.py`
  - `benchmark/analyze_failures.py`
  - `benchmark/check_cases.py`
  - `backend/app/shield/__init__.py`
- `benchmark_expand.py` and `dashboard.py` contain `/mnt/d/` paths
- Requires ASF-BGT-Framework as dependency (referenced via hardcoded path)
