"""
run_synthetic_v2.py
===================
Run Risk Encoder V2 on the Synthetic-AB300 dataset for comparison with v1.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from risk_encoder_v2.pipeline import RiskEncoderV2Pipeline

SYNTHETIC_PATH = os.path.join(PROJECT_ROOT, "data", "rebuild", "synthetic_ab300_seed42.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "rebuild")

DECISIONS = ["AUTO_EXECUTE", "SIMULATE_FIRST", "HUMAN_REVIEW", "BLOCK"]
SEVERITY = {d: i for i, d in enumerate(DECISIONS)}


def load_synthetic(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gold_label(task: Dict) -> str:
    risk = task.get("base_risk", 0)
    if risk >= 0.75:
        return "BLOCK"
    elif risk >= 0.50:
        return "HUMAN_REVIEW"
    elif risk >= 0.25:
        return "SIMULATE_FIRST"
    return "AUTO_EXECUTE"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=SYNTHETIC_PATH)
    parser.add_argument("--output-dir", default=RESULTS_DIR)
    args = parser.parse_args()

    tasks = load_synthetic(args.input)
    print(f"Loaded {len(tasks)} synthetic tasks")

    pipeline = RiskEncoderV2Pipeline(use_tfidf=True)

    results = []
    correct = 0
    for task in tasks:
        desc = task.get("description", "")
        gold = gold_label(task)

        result = pipeline.assess(desc)
        pred = result["decision"]

        results.append({
            "id": task.get("id", ""),
            "template_id": task.get("template_id", ""),
            "gold": gold,
            "pred": pred,
            "risk_score": result["risk_score"],
            "calibrated_score": result["calibrated_score"],
            "risk_types": result["risk_types"],
        })

        if gold == pred:
            correct += 1

    acc = correct / len(tasks) if tasks else 0.0
    print(f"\nV2 on Synthetic-AB300: accuracy={acc:.4f} ({correct}/{len(tasks)})")

    # Decision distribution
    from collections import Counter
    pred_dist = Counter(r["pred"] for r in results)
    gold_dist = Counter(r["gold"] for r in results)
    print(f"  Pred distribution: {dict(pred_dist)}")
    print(f"  Gold distribution: {dict(gold_dist)}")

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, "synthetic_v2_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "accuracy": round(acc, 4),
            "n": len(tasks),
            "correct": correct,
            "pred_distribution": dict(pred_dist),
            "gold_distribution": dict(gold_dist),
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {output_path}")

    # Compare with v1 ablation results
    print(f"\n  v1 baseline comparison:")
    print(f"    plain=0.060  risk=0.293  memory=0.127  full=0.130")
    print(f"    v2={acc:.3f}")


if __name__ == "__main__":
    main()
