"""Run V3.3 ablation experiments on Semi-Real-150 traces.

V3.3 ablation design: all configurations use only observable features
(no ground-truth labels like attack_stage, chain_id, step_index).
Ablations remove specific capabilities to measure their contribution.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.baselines import (
    evaluate,
    risk_agent_shield,
    risk_agent_shield_graph,
    risk_content_keyword,
    risk_llm_as_judge,
    risk_local_context,
)
from benchmark.nemo_guardrails_baseline import risk_nemo_guardrails
from benchmark.llm_guard_baseline import risk_llm_guard
from benchmark.evaluate_semireal import load_traces, trace_to_case


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "test_cases" / "test_cases_semireal_150.json"
DEFAULT_JSON = ROOT / "results" / "semireal_ablation_report.json"
DEFAULT_MD = ROOT / "results" / "semireal_ablation_table.md"

CasePredictor = Callable[[Dict[str, Any]], float]


ABLATIONS: List[Tuple[str, CasePredictor, str]] = [
    (
        "AgentShield + Graph",
        risk_agent_shield_graph,
        "Full pipeline: label-free chain-aware scoring + graph risk propagation.",
    ),
    (
        "AgentShield (no graph)",
        risk_agent_shield,
        "Label-free chain-aware scoring without graph risk propagation.",
    ),
    (
        "NeMo Guardrails",
        risk_nemo_guardrails,
        "NVIDIA NeMo Guardrails simulation: multi-rail architecture (topic/jailbreak/input/output/execution).",
    ),
    (
        "LLM Guard",
        risk_llm_guard,
        "ProtectAI LLM Guard simulation: scanner pipeline (secrets/injection/code/regex/topics/toxicity).",
    ),
    (
        "LLM-as-Judge",
        risk_llm_as_judge,
        "Simulated LLM risk assessment using observable features.",
    ),
    (
        "w/o chain inference",
        risk_local_context,
        "Removes chain inference: uses only category priors + keyword matching.",
    ),
    (
        "Content keywords only",
        risk_content_keyword,
        "Uses only serialized tool input keywords, no category or chain context.",
    ),
]


def cases_from_traces(traces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [trace_to_case(trace) for trace in traces]


def write_markdown(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Semi-Real Trace Ablation Study",
        "",
        f"Dataset: `{report['dataset']}`",
        f"Traces: {report['total_traces']}",
        f"Steps: {report['total_steps']}",
        "",
        "| Configuration | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["ablations"]:
        lines.append(
            "| {name} | {acc:.2%} | {f1:.2%} | {block:.2%} | {fa:.2%} | {fb:.2%} |".format(
                name=item["name"],
                acc=item["action_accuracy"],
                f1=item["macro_f1"],
                block=item["block_recall"],
                fa=item["false_allow_rate"],
                fb=item["false_block_rate"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `AgentShield + Graph` is the full pipeline: label-free chain-aware scoring + graph risk propagation.",
            "- `AgentShield (no graph)` uses label-free chain-aware scoring without graph risk propagation.",
            "- `NeMo Guardrails` simulates NVIDIA's multi-rail architecture (topic/jailbreak/input/output/execution rails).",
            "- `LLM Guard` simulates ProtectAI's scanner pipeline (secrets/injection/code/regex/topics/toxicity/dataflow/toolsafety).",
            "- `LLM-as-Judge` simulates a strong LLM's risk assessment from observable features.",
            "- `w/o chain inference` removes chain inference entirely, using only category priors + keywords.",
            "- `Content keywords only` uses only serialized tool input keywords.",
            "",
            "## Fairness Note",
            "",
            "All configurations use ONLY observable features (tool name, tool input, category).",
            "No ground-truth labels (attack_stage, chain_id, step_index) are used.",
            "Chain context is inferred from content patterns.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    dataset: Path = DEFAULT_DATASET,
    json_out: Path = DEFAULT_JSON,
    md_out: Path = DEFAULT_MD,
) -> Dict[str, Any]:
    traces = load_traces(dataset)
    cases = cases_from_traces(traces)
    results = []
    for name, predictor, description in ABLATIONS:
        item = evaluate(name, predictor, cases)
        item["description"] = description
        results.append(item)

    report = {
        "dataset": str(dataset),
        "total_traces": len(traces),
        "total_steps": sum(len(trace.get("steps", [])) for trace in traces),
        "note": "V3.3 ablation: all configurations use only observable features (no ground-truth labels).",
        "ablations": results,
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, md_out)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V3.2 semi-real ablation study.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    report = run(dataset=args.dataset, json_out=args.json_out, md_out=args.md_out)
    print(f"Evaluated {report['total_traces']} traces / {report['total_steps']} steps")
    print(f"JSON report: {args.json_out}")
    print(f"Markdown table: {args.md_out}")
    for item in report["ablations"]:
        print(
            f"{item['name']:<28} acc={item['action_accuracy']:.3f} "
            f"macro_f1={item['macro_f1']:.3f} block_recall={item['block_recall']:.3f}"
        )


if __name__ == "__main__":
    main()
