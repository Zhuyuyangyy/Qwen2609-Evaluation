"""Generate controlled semi-real AgentShield trace benchmarks."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.semireal_trace_scenarios import SCENARIO_PLAN, make_trace
from benchmark.trace_schema import validate_trace


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "test_cases" / "test_cases_semireal_150.json"


def generate_traces(output: Path = DEFAULT_OUTPUT, size: int = 150, seed: int = 20260526) -> List[Dict[str, Any]]:
    if size % 15 != 0:
        raise ValueError("size must be divisible by 15 to preserve label balance")

    size // 150
    if size != 150:
        max(1, size // 150)

    rng = random.Random(seed)
    traces: List[Dict[str, Any]] = []
    index = 1
    for spec in SCENARIO_PLAN:
        count = spec.count if size == 150 else max(1, round(spec.count * size / 150))
        for _ in range(count):
            trace = make_trace(index, spec.scenario_type, spec.chain_label, rng)
            validate_trace(trace)
            traces.append(trace)
            index += 1

    traces = traces[:size]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
    return traces


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate controlled semi-real traces.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--size", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20260526)
    args = parser.parse_args()

    traces = generate_traces(output=args.output, size=args.size, seed=args.seed)
    print(f"Generated {len(traces)} traces: {args.output}")


if __name__ == "__main__":
    main()
