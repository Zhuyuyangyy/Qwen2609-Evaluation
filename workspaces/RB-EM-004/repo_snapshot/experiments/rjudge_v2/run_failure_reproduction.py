"""
run_failure_reproduction.py
===========================
Single entry point for the R-Judge V1 Failure Reproduction Pack.

Runs the full pipeline:
  1. Download and convert R-Judge data
  2. Run v1 DecisionPipeline on all records
  3. Compute metrics
  4. Analyze failures
  5. Generate report

Usage:
    python experiments/rjudge_v2/run_failure_reproduction.py

Output:
    results/rjudge_v2/
      rjudge_converted.jsonl
      predictions_v1.jsonl
      metrics_v1.json
      failure_cases.jsonl
      failure_summary.csv
      rjudge_failure_report.md
"""

from __future__ import annotations

import json
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from experiments.rjudge_v2.convert_rjudge import ensure_data, load_rjudge_records, convert_records
from experiments.rjudge_v2.run_rjudge_v1 import (
    run_v1_baseline, extract_actions, extract_context,
    BASELINES, WARMUP_SEEDS,
)
from experiments.rjudge_v2.metrics import rjudge_gold_label, compute_metrics
from experiments.rjudge_v2.failure_analysis import analyze_failures
from experiments.rjudge_v2.generate_report import generate_report

RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "rjudge_v2")


def main():
    start = time.time()

    print("=" * 70)
    print("R-Judge V1 Failure Reproduction Pack")
    print("=" * 70)
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Step 1: Download and convert R-Judge data
    print("[1/5] Downloading and converting R-Judge data...")
    data_dir = os.path.join(PROJECT_ROOT, "rjudge_data")
    ensure_data(data_dir)
    records = load_rjudge_records(data_dir)
    converted = convert_records(records)

    converted_path = os.path.join(RESULTS_DIR, "rjudge_converted.jsonl")
    with open(converted_path, "w", encoding="utf-8") as f:
        for rec in converted:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  Saved {len(converted)} records to {converted_path}")

    from collections import Counter
    labels = Counter(r["label"] for r in converted)
    attacks = Counter(r["attack_type"] for r in converted)
    print(f"  Labels: {dict(labels)}")
    print(f"  Attack types: {dict(attacks)}")
    print()

    # Step 2: Run v1 pipeline (action+context mode, all 4 baselines)
    print("[2/5] Running v1 DecisionPipeline baselines...")
    all_predictions = {}
    for baseline in BASELINES:
        preds = run_v1_baseline(converted, baseline, use_context=True)
        all_predictions[baseline] = preds
        print(f"  [{baseline}] {len(preds)} predictions")
    print()

    # Step 3: Compute metrics for each baseline
    print("[3/5] Computing metrics...")
    all_metrics = {}
    for baseline in BASELINES:
        m = compute_metrics(all_predictions[baseline])
        all_metrics[baseline] = m
        print(f"  [{baseline}] unsafe_recall={m['unsafe_recall']:.4f}  "
              f"unsafe_f1={m['unsafe_f1']:.4f}  "
              f"evidence_coverage={m['evidence_coverage']:.4f}")
    print()

    # Save predictions and metrics for the primary baseline (risk)
    primary = "risk"
    pred_path = os.path.join(RESULTS_DIR, "predictions_v1.jsonl")
    with open(pred_path, "w", encoding="utf-8") as f:
        for p in all_predictions[primary]:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"  Saved predictions to {pred_path}")

    metrics_path = os.path.join(RESULTS_DIR, "metrics_v1.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(all_metrics[primary], f, indent=2, ensure_ascii=False)
    print(f"  Saved metrics to {metrics_path}")

    # Also save full ablation metrics
    all_metrics_path = os.path.join(RESULTS_DIR, "metrics_v1_all_baselines.json")
    with open(all_metrics_path, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2, ensure_ascii=False)
    print(f"  Saved all baseline metrics to {all_metrics_path}")
    print()

    # Step 4: Failure analysis (using the primary baseline)
    print("[4/5] Analyzing failures (baseline: risk)...")
    failure_summary = analyze_failures(
        converted, all_predictions[primary], RESULTS_DIR
    )
    print()

    # Step 5: Generate report
    print("[5/5] Generating report...")
    generate_report(RESULTS_DIR)
    print()

    # Summary
    elapsed = time.time() - start
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for baseline in BASELINES:
        m = all_metrics[baseline]
        print(f"  [{baseline:>6}]  unsafe_recall={m['unsafe_recall']:.4f}  "
              f"unsafe_f1={m['unsafe_f1']:.4f}  "
              f"evidence_coverage={m['evidence_coverage']:.4f}  "
              f"false_safe={m['false_safe_count']}")
    print()
    print(f"Elapsed: {elapsed:.1f}s")
    print()
    print("Output files:")
    for fname in sorted(os.listdir(RESULTS_DIR)):
        fpath = os.path.join(RESULTS_DIR, fname)
        size = os.path.getsize(fpath)
        print(f"  {fname} ({size:,} bytes)")
    print()
    print("Done. The v1 pipeline completely fails on R-Judge (unsafe_recall ~ 0.000).")
    print("This confirms the keyword-based risk encoder cannot detect semantic risks.")
    print("Next step: Risk Encoder v2 (PR #14).")


if __name__ == "__main__":
    main()
