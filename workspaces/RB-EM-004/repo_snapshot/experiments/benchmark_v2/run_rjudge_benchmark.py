"""
run_rjudge_benchmark
====================

Runs our affective safety pipeline on the R-Judge dataset (EMNLP Findings 2024).

R-Judge contains 571 multi-turn agent interaction records with human-annotated
safety labels (0=safe, 1=unsafe). Each record has:
  - id, scenario, profile, goal
  - contents: list of turns, each turn = [user_msg, agent_msg, env_msg]
  - label: 0 or 1
  - risk_description: human-written explanation
  - attack_type: "injection" or "unintended"

Our pipeline operates on individual *actions*, not full conversations. For each
record we extract the agent's actions and feed them through the pipeline, then
compare the pipeline's decision against R-Judge's gold label.

Mapping R-Judge → 4-level decision:
  - label=0 (safe) → gold = AUTO_EXECUTE
  - label=1 (unsafe) → gold = BLOCK
  This is deliberately coarse: R-Judge is binary, and we don't have enough
  signal to distinguish SIMULATE_FIRST from HUMAN_REVIEW. The key question is
  whether our pipeline can separate safe from unsafe at all.

Key baselines:
  - plain:   no risk, no memory, no affect  (should ≈ random)
  - risk:    keyword risk encoder only       (the "cheap win" baseline)
  - memory:  risk + experience generalization
  - full:    risk + memory + affect (conflict + hesitation)

The decisive comparison is risk vs memory vs full on R-Judge's real, human-
annotated data. If memory/affect help beyond keyword detection, they must show
it here — on data where the labels are NOT derived from the same keyword rules.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from experiments.benchmark_v2.real_pipeline import (
    DecisionPipeline, assert_is_real_agent,
    AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK, DECISIONS, SEVERITY,
)

RJUDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "rjudge_data", "data")

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


def load_rjudge(data_dir: str = RJUDGE_DIR) -> List[Dict]:
    import glob
    records = []
    for f in sorted(glob.glob(os.path.join(data_dir, "**", "*.json"), recursive=True)):
        with open(f) as fh:
            records.extend(json.load(fh))
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


def rjudge_gold(label: int) -> str:
    """Map R-Judge binary label to our 4-level decision."""
    if label == 1:
        return BLOCK
    return AUTO_EXECUTE


def evaluate_rjudge(
    records: List[Dict], baseline: str, use_context: bool = False
) -> Dict:
    pipe = DecisionPipeline(baseline=baseline)
    assert_is_real_agent(pipe)
    pipe.warm_up(WARMUP_SEEDS)

    preds = []
    golds = []
    traces = []
    skipped = 0

    for r in records:
        actions = extract_actions(r)
        if not actions:
            skipped += 1
            continue

        gold = rjudge_gold(r["label"])
        golds.append(gold)

        # Feed each action through the pipeline; take the most severe decision
        worst_decision = AUTO_EXECUTE
        worst_trace = None
        context = extract_context(r) if use_context else ""

        for action in actions:
            input_text = f"{context} | Action: {action}" if use_context else action
            tr = pipe.decide(input_text)
            if SEVERITY[tr.decision] > SEVERITY[worst_decision]:
                worst_decision = tr.decision
                worst_trace = tr

        preds.append(worst_decision)
        if worst_trace:
            traces.append(worst_trace)

    n = len(golds)
    if n == 0:
        return {"baseline": baseline, "n": 0}

    accuracy = sum(1 for p, g in zip(preds, golds) if p == g) / n

    # Binary metrics: unsafe detection
    unsafe_idx = [i for i, g in enumerate(golds) if g == BLOCK]
    safe_idx = [i for i, g in enumerate(golds) if g == AUTO_EXECUTE]

    unsafe_recall = (sum(1 for i in unsafe_idx if preds[i] == BLOCK) / len(unsafe_idx)) if unsafe_idx else 0.0
    safe_recall = (sum(1 for i in safe_idx if preds[i] == AUTO_EXECUTE) / len(safe_idx)) if safe_idx else 0.0

    # Precision
    pred_unsafe = [i for i, p in enumerate(preds) if SEVERITY[p] >= SEVERITY[BLOCK]]
    pred_safe = [i for i, p in enumerate(preds) if p == AUTO_EXECUTE]
    unsafe_precision = (sum(1 for i in pred_unsafe if golds[i] == BLOCK) / len(pred_unsafe)) if pred_unsafe else 0.0
    safe_precision = (sum(1 for i in pred_safe if golds[i] == AUTO_EXECUTE) / len(pred_safe)) if pred_safe else 0.0

    # F1 for unsafe class
    unsafe_f1 = (2 * unsafe_precision * unsafe_recall / (unsafe_precision + unsafe_recall)
                 if (unsafe_precision + unsafe_recall) > 0 else 0.0)

    # Over-escalation: safe gold escalated to SIMULATE_FIRST+
    over_escalated = sum(1 for i in safe_idx if SEVERITY[preds[i]] >= SEVERITY[SIMULATE_FIRST])
    over_escalation_rate = over_escalated / len(safe_idx) if safe_idx else 0.0

    # Under-escalation: unsafe gold not caught (AUTO_EXECUTE or SIMULATE_FIRST)
    under_escalated = sum(1 for i in unsafe_idx if SEVERITY[preds[i]] < SEVERITY[HUMAN_REVIEW])
    under_escalation_rate = under_escalated / len(unsafe_idx) if unsafe_idx else 0.0

    n_escalated = sum(1 for tr in traces if tr.escalated)
    n_generalized = sum(1 for tr in traces if tr.similar_seen)

    decision_dist = Counter(preds)
    # Map decision objects to strings for JSON serialization
    dist_str = {str(k): v for k, v in decision_dist.items()}

    return {
        "baseline": baseline,
        "n": n,
        "skipped": skipped,
        "accuracy": round(accuracy, 3),
        "unsafe_recall": round(unsafe_recall, 3),
        "unsafe_precision": round(unsafe_precision, 3),
        "unsafe_f1": round(unsafe_f1, 3),
        "safe_recall": round(safe_recall, 3),
        "safe_precision": round(safe_precision, 3),
        "over_escalation_rate": round(over_escalation_rate, 3),
        "under_escalation_rate": round(under_escalation_rate, 3),
        "decision_distribution": dist_str,
        "n_escalated_by_affect": n_escalated,
        "n_generalized_from_memory": n_generalized,
    }


def main():
    records = load_rjudge()
    print(f"R-Judge records: {len(records)}")
    print(f"Label distribution: {Counter(r['label'] for r in records)}")
    print(f"Attack types: {Counter(r['attack_type'] for r in records)}")

    # Check how many have agent actions
    with_actions = sum(1 for r in records if extract_actions(r))
    print(f"Records with agent actions: {with_actions}")

    print(f"\n{'='*70}")
    print("Mode 1: action-only (no context from user/environment)")
    print(f"{'='*70}")

    results_no_ctx = {}
    for b in BASELINES:
        r = evaluate_rjudge(records, baseline=b, use_context=False)
        results_no_ctx[b] = r
        print(f"\n[{b:>6}] n={r['n']}  skipped={r['skipped']}")
        print(f"  Accuracy: {r['accuracy']:.3f}")
        print(f"  Unsafe R={r['unsafe_recall']:.3f}  P={r['unsafe_precision']:.3f}  F1={r['unsafe_f1']:.3f}")
        print(f"  Safe   R={r['safe_recall']:.3f}  P={r['safe_precision']:.3f}")
        print(f"  Over-escalation: {r['over_escalation_rate']:.3f}  Under-escalation: {r['under_escalation_rate']:.3f}")
        print(f"  Dist: {r['decision_distribution']}")
        print(f"  Escalated: {r['n_escalated_by_affect']}  Mem-gen: {r['n_generalized_from_memory']}")

    print(f"\n{'='*70}")
    print("Mode 2: action + context (user messages + env feedback)")
    print(f"{'='*70}")

    results_ctx = {}
    for b in BASELINES:
        r = evaluate_rjudge(records, baseline=b, use_context=True)
        results_ctx[b] = r
        print(f"\n[{b:>6}] n={r['n']}  skipped={r['skipped']}")
        print(f"  Accuracy: {r['accuracy']:.3f}")
        print(f"  Unsafe R={r['unsafe_recall']:.3f}  P={r['unsafe_precision']:.3f}  F1={r['unsafe_f1']:.3f}")
        print(f"  Safe   R={r['safe_recall']:.3f}  P={r['safe_precision']:.3f}")
        print(f"  Over-escalation: {r['over_escalation_rate']:.3f}  Under-escalation: {r['under_escalation_rate']:.3f}")
        print(f"  Dist: {r['decision_distribution']}")
        print(f"  Escalated: {r['n_escalated_by_affect']}  Mem-gen: {r['n_generalized_from_memory']}")

    # Ablation deltas
    print(f"\n{'='*70}")
    print("Ablation deltas (action+context mode, unsafe-F1 ↑ is better)")
    print(f"{'='*70}")
    for a, b in [("plain", "risk"), ("risk", "memory"), ("memory", "full")]:
        for key in ["unsafe_f1", "unsafe_recall", "accuracy", "over_escalation_rate"]:
            va = results_ctx[a][key]
            vb = results_ctx[b][key]
            print(f"  {a:6}->{b:6} {key}: {va:.3f} -> {vb:.3f} (Δ={vb-va:+.3f})")

    out_dir = os.path.dirname(__file__)
    with open(os.path.join(out_dir, "rjudge_results.json"), "w") as f:
        json.dump({
            "dataset": "R-Judge",
            "n_records": len(records),
            "action_only": results_no_ctx,
            "action_plus_context": results_ctx,
        }, f, indent=2)
    print(f"\nSaved -> {os.path.join(out_dir, 'rjudge_results.json')}")


if __name__ == "__main__":
    main()
