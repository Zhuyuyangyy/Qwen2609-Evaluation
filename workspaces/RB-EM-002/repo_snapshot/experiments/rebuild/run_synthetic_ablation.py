"""
run_synthetic_ablation
======================

Run the four ablations of DecisionPipeline over the frozen Synthetic-AB300
dataset and produce structured results with full provenance.

This replaces the old benchmark_v2 approach by:
1. Reading from a frozen JSON dataset instead of dynamically generating tasks
2. Explicitly marking all gold labels as heuristic (not human-validated)
3. Writing results with clear provenance and limitations

Usage
-----
    python experiments/rebuild/run_synthetic_ablation.py \\
        --input data/rebuild/synthetic_ab300_seed42.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from experiments.benchmark_v2.real_pipeline import (
    DecisionPipeline, assert_is_real_agent,
    AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK, DECISIONS, SEVERITY,
)

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


def macro_f1(y_true: List[str], y_pred: List[str]) -> float:
    f1s = []
    for c in DECISIONS:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    return sum(f1s) / len(f1s)


def per_class_metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, Dict[str, float]]:
    metrics = {}
    for c in DECISIONS:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        metrics[c] = {
            "precision": round(prec, 3),
            "recall": round(rec, 3),
            "f1": round(f1, 3),
            "support": sum(1 for t in y_true if t == c),
        }
    return metrics


def confusion_matrix(y_true: List[str], y_pred: List[str]) -> List[List[int]]:
    idx = {d: i for i, d in enumerate(DECISIONS)}
    mat = [[0] * len(DECISIONS) for _ in range(len(DECISIONS))]
    for t, p in zip(y_true, y_pred):
        mat[idx[t]][idx[p]] += 1
    return mat


def evaluate(records: List[dict], baseline: str) -> Dict:
    """Evaluate a single baseline on the frozen dataset."""
    pipe = DecisionPipeline(baseline=baseline)
    assert_is_real_agent(pipe)
    pipe.warm_up(WARMUP_SEEDS)

    golds = [r["heuristic_gold_decision"] for r in records]
    preds = []
    traces = []
    for r in records:
        tr = pipe.decide(r["description"])
        preds.append(tr.decision)
        traces.append(tr)

    n = len(records)
    accuracy = sum(1 for p, g in zip(preds, golds) if p == g) / n
    sev_mae = sum(abs(SEVERITY[p] - SEVERITY[g]) for p, g in zip(preds, golds)) / n

    high_idx = [i for i, r in enumerate(records) if r["expected_risk_level"] in ("HIGH", "CRITICAL")]
    low_idx = [i for i, g in enumerate(golds) if g == AUTO_EXECUTE]

    risky_auto = (sum(1 for i in high_idx if preds[i] == AUTO_EXECUTE) / len(high_idx)) if high_idx else 0.0
    over_caution = (sum(1 for i in low_idx if SEVERITY[preds[i]] >= SEVERITY[HUMAN_REVIEW]) / len(low_idx)) if low_idx else 0.0

    n_escalated = sum(1 for tr in traces if tr.escalated)
    n_deescalated = sum(1 for tr in traces if tr.de_escalated)
    seed_events = {s["event"] for s in WARMUP_SEEDS}
    n_generalized = sum(1 for r, tr in zip(records, traces) if r["description"] not in seed_events and tr.similar_seen)

    conf_mat = confusion_matrix(golds, preds)
    class_metrics = per_class_metrics(golds, preds)

    return {
        "baseline": baseline,
        "n": n,
        "accuracy": round(accuracy, 3),
        "macro_f1": round(macro_f1(golds, preds), 3),
        "severity_mae": round(sev_mae, 3),
        "risky_auto_exec_rate": round(risky_auto, 3),
        "over_caution_rate": round(over_caution, 3),
        "per_class": class_metrics,
        "confusion_matrix": conf_mat,
        "decision_distribution": dict(Counter(preds)),
        "n_escalated_by_affect": n_escalated,
        "n_de_escalated_by_affect": n_deescalated,
        "n_generalized_from_memory": n_generalized,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run synthetic ablation on frozen Synthetic-AB300 dataset"
    )
    parser.add_argument(
        "--input", type=str,
        default="data/rebuild/synthetic_ab300_seed42.json",
        help="Path to frozen dataset JSON (default: data/rebuild/synthetic_ab300_seed42.json)",
    )
    args = parser.parse_args()

    # Load frozen dataset
    input_path = args.input
    if not os.path.isabs(input_path):
        input_path = os.path.join(os.path.dirname(__file__), "..", "..", input_path)
    input_path = os.path.normpath(input_path)

    with open(input_path, encoding="utf-8") as f:
        dataset = json.load(f)

    records = dataset["records"]
    print(f"Dataset: {dataset['dataset_name']}")
    print(f"Records: {len(records)} ({dataset['n_unique_templates']} unique templates)")
    print(f"Gold labels: heuristic (NOT human-validated)")
    print()

    results = {}
    for b in BASELINES:
        r = evaluate(records, b)
        results[b] = r
        print(f"[{b:>6}] acc={r['accuracy']:.3f}  macro_f1={r['macro_f1']:.3f}  "
              f"sev_mae={r['severity_mae']:.3f}  "
              f"risky_auto={r['risky_auto_exec_rate']:.3f}  "
              f"over_caution={r['over_caution_rate']:.3f}")
        for cls in DECISIONS:
            cm = r["per_class"][cls]
            print(f"  {cls:>15}: P={cm['precision']:.3f}  R={cm['recall']:.3f}  "
                  f"F1={cm['f1']:.3f}  support={cm['support']}")

    # Ablation deltas
    print("\nAblation deltas:")
    for a, b in [("plain", "risk"), ("risk", "memory"), ("memory", "full")]:
        d_acc = results[b]["accuracy"] - results[a]["accuracy"]
        d_f1 = results[b]["macro_f1"] - results[a]["macro_f1"]
        d_risky = results[a]["risky_auto_exec_rate"] - results[b]["risky_auto_exec_rate"]
        print(f"  {a:6} -> {b:6}: Δacc={d_acc:+.3f}  Δf1={d_f1:+.3f}  Δrisky-auto={d_risky:+.3f}")

    # Guard test
    guard_ok = False
    try:
        class DummyAgent:
            pass
        assert_is_real_agent(DummyAgent())
    except TypeError:
        guard_ok = True
    print(f"\nDummyAgent rejected by guard: {guard_ok}")

    # Write results
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "results", "rebuild")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "synthetic_ablation_results.json")

    output = {
        "dataset_name": dataset["dataset_name"],
        "dataset_source": os.path.basename(input_path),
        "gold_label_type": "heuristic (NOT human-validated)",
        "baselines": BASELINES,
        "results": results,
        "guard_rejects_dummy": guard_ok,
        "caveats": [
            "Gold labels are heuristic, derived from hand-authored task metadata.",
            "This is a mechanism sanity check on synthetic/template-generated data.",
            "These results do NOT validate real-world safety effectiveness.",
            "The original main-table results (DummyAgent) are NOT reproducible and should not be compared.",
        ],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
