"""
run_rjudge_v1.py
================
Run the v1 DecisionPipeline on the R-Judge dataset and produce:
  - predictions_v1.jsonl: per-record predictions with full traces
  - metrics_v1.json: computed metrics

This is the v1 baseline reproduction — the keyword-based risk encoder.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from experiments.benchmark_v2.real_pipeline import (
    DecisionPipeline, assert_is_real_agent,
    AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK, DECISIONS, SEVERITY,
)
from experiments.rjudge_v2.metrics import rjudge_gold_label, compute_metrics

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_INPUT = os.path.join(PROJECT_ROOT, "results", "rjudge_v2", "rjudge_converted.jsonl")
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "results", "rjudge_v2")

BASELINES = ["plain", "risk", "memory", "full"]

WARMUP_SEEDS = [
    {"event": "Delete production database", "outcome": "failure", "risk_actual": 0.95},
    {"event": "Drop table users", "outcome": "failure", "risk_actual": 0.95},
    {"event": "Force push to main branch", "outcome": "failure", "risk_actual": 0.85},
    {"event": "Install unvetted package", "outcome": "failure", "risk_actual": 0.80},
    {"event": "Run unknown binary", "outcome": "failure", "risk_actual": 0.90},
    {"event": "Check disk space", "outcome": "success", "risk_actual": 0.05},
    {"event": "Verify user access", "outcome": "success", "risk_actual": 0.05},
    {"event": "Deploy to staging", "outcome": "success", "risk_actual": 0.10},
]


def load_records(path: str) -> List[Dict]:
    """Load converted R-Judge records from JSONL."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_actions(record: Dict) -> List[str]:
    """Extract agent action texts from a R-Judge record."""
    actions = []
    for turn in record.get("contents", []):
        if isinstance(turn, list):
            for msg in turn:
                if isinstance(msg, dict) and msg.get("role") == "agent":
                    action = msg.get("action") or msg.get("content") or ""
                    if action and action.strip():
                        actions.append(action.strip())
    return actions


def extract_context(record: Dict) -> str:
    """Build a context string from user messages + environment feedback."""
    parts = []
    for turn in record.get("contents", []):
        if isinstance(turn, list):
            for msg in turn:
                if isinstance(msg, dict):
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        if content:
                            parts.append(f"User: {content[:200]}")
                    elif msg.get("role") == "environment":
                        content = msg.get("content", "")
                        if content:
                            parts.append(f"Env: {content[:200]}")
    return " | ".join(parts)


def run_v1_baseline(
    records: List[Dict],
    baseline: str,
    use_context: bool = True,
) -> List[Dict]:
    """Run a single baseline and return per-record predictions."""
    pipe = DecisionPipeline(baseline=baseline)
    assert_is_real_agent(pipe)
    pipe.warm_up(WARMUP_SEEDS)

    predictions = []
    for rec in records:
        actions = extract_actions(rec)
        if not actions:
            predictions.append({
                "id": rec.get("id", ""),
                "gold_label": rjudge_gold_label(rec.get("label", 0)),
                "pred_label": AUTO_EXECUTE,
                "attack_type": rec.get("attack_type", ""),
                "base_risk": 0.0,
                "adjusted_risk": 0.0,
                "escalated": False,
                "de_escalated": False,
                "similar_seen": [],
                "n_actions": 0,
            })
            continue

        gold = rjudge_gold_label(rec.get("label", 0))
        context = extract_context(rec) if use_context else ""

        worst_decision = AUTO_EXECUTE
        worst_trace = None
        for action in actions:
            input_text = f"{context} | Action: {action}" if use_context else action
            tr = pipe.decide(input_text)
            if SEVERITY[tr.decision] > SEVERITY[worst_decision]:
                worst_decision = tr.decision
                worst_trace = tr

        predictions.append({
            "id": rec.get("id", ""),
            "gold_label": gold,
            "pred_label": worst_decision,
            "attack_type": rec.get("attack_type", ""),
            "base_risk": round(worst_trace.base_risk, 4) if worst_trace else 0.0,
            "adjusted_risk": round(worst_trace.adjusted_risk, 4) if worst_trace else 0.0,
            "escalated": worst_trace.escalated if worst_trace else False,
            "de_escalated": worst_trace.de_escalated if worst_trace else False,
            "similar_seen": worst_trace.similar_seen if worst_trace else [],
            "n_actions": len(actions),
        })

    return predictions


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run R-Judge v1 baseline")
    parser.add_argument("--input", default=DEFAULT_INPUT,
                        help="Path to converted R-Judge JSONL")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help="Output directory for results")
    parser.add_argument("--baseline", default="risk",
                        choices=BASELINES,
                        help="Which baseline to run (default: risk — the main v1)")
    parser.add_argument("--use-context", action="store_true", default=True,
                        help="Include conversation context")
    args = parser.parse_args()

    records = load_records(args.input)
    print(f"Loaded {len(records)} records from {args.input}")

    print(f"\nRunning v1 baseline: {args.baseline} (use_context={args.use_context})")
    predictions = run_v1_baseline(records, args.baseline, args.use_context)
    print(f"Produced {len(predictions)} predictions")

    os.makedirs(args.output_dir, exist_ok=True)

    # Save predictions
    pred_path = os.path.join(args.output_dir, "predictions_v1.jsonl")
    with open(pred_path, "w", encoding="utf-8") as f:
        for p in predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"Predictions saved to {pred_path}")

    # Compute metrics
    metrics = compute_metrics(predictions)
    metrics_path = os.path.join(args.output_dir, "metrics_v1.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to {metrics_path}")

    # Print key results
    print(f"\n{'='*60}")
    print(f"V1 Baseline: {args.baseline}")
    print(f"{'='*60}")
    print(f"  n={metrics['n']}  unsafe={metrics['n_unsafe']}  safe={metrics['n_safe']}")
    print(f"  Unsafe recall:    {metrics['unsafe_recall']:.4f}")
    print(f"  Unsafe precision: {metrics['unsafe_precision']:.4f}")
    print(f"  Unsafe F1:        {metrics['unsafe_f1']:.4f}")
    print(f"  Macro F1:         {metrics['macro_f1']:.4f}")
    print(f"  False safe count: {metrics['false_safe_count']}")
    print(f"  False block count:{metrics['false_block_count']}")
    print(f"  Over-escalation:  {metrics['over_escalation_rate']:.4f}")
    print(f"  Under-escalation: {metrics['under_escalation_rate']:.4f}")
    print(f"  Evidence coverage:{metrics['evidence_coverage']:.4f}")
    print(f"  Decision dist:    {metrics['decision_distribution']}")
    print(f"  Risk type recall: {metrics['risk_type_recall']}")

    return metrics


if __name__ == "__main__":
    main()
