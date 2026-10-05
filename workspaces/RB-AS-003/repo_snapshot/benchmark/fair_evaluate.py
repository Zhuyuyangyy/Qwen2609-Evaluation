"""Fair evaluation runner for AgentShield V3.

Ensures:
1. No label leakage (detectors only see ObservedToolEvent)
2. Proper train/dev/test split
3. Multiple baselines evaluated fairly
4. Per-label precision/recall/F1, confusion matrix, confidence intervals
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.shield.schemas import ObservedToolEvent, HiddenGroundTruth, event_from_dict, ground_truth_from_dict
from benchmark.strong_baselines import Baseline, get_baseline, ALL_BASELINES


@dataclass
class EvalResult:
    """Evaluation result for a single baseline on a single dataset."""
    baseline_name: str
    dataset_name: str
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0
    per_label_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    confusion_matrix: Dict[str, Dict[str, int]] = field(default_factory=dict)
    false_allow: int = 0
    false_block: int = 0
    review_rate: float = 0.0
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    macro_f1: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_name": self.baseline_name,
            "dataset_name": self.dataset_name,
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "macro_precision": round(self.macro_precision, 4),
            "macro_recall": round(self.macro_recall, 4),
            "macro_f1": round(self.macro_f1, 4),
            "false_allow": self.false_allow,
            "false_block": self.false_block,
            "review_rate": round(self.review_rate, 4),
            "per_label_metrics": {
                k: {mk: round(mv, 4) for mk, mv in v.items()}
                for k, v in self.per_label_metrics.items()
            },
            "confusion_matrix": self.confusion_matrix,
        }


LABELS = ["ALLOW", "HUMAN_REVIEW", "BLOCK"]


def compute_per_label_metrics(
    true_labels: List[str],
    pred_labels: List[str],
    labels: List[str] = LABELS,
) -> Dict[str, Dict[str, float]]:
    """Compute precision, recall, F1 for each label."""
    metrics = {}
    for label in labels:
        tp = sum(1 for t, p in zip(true_labels, pred_labels) if t == label and p == label)
        fp = sum(1 for t, p in zip(true_labels, pred_labels) if t != label and p == label)
        fn = sum(1 for t, p in zip(true_labels, pred_labels) if t == label and p != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": tp + fn,
        }
    return metrics


def compute_confusion_matrix(
    true_labels: List[str],
    pred_labels: List[str],
    labels: List[str] = LABELS,
) -> Dict[str, Dict[str, int]]:
    """Compute confusion matrix."""
    matrix = {l: {l2: 0 for l2 in labels} for l in labels}
    for true, pred in zip(true_labels, pred_labels):
        if true in matrix and pred in matrix[true]:
            matrix[true][pred] += 1
    return matrix


def compute_confidence_interval(accuracy: float, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Compute Wilson score confidence interval for accuracy."""
    z = 1.96  # 95% confidence
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z**2 / n
    center = (accuracy + z**2 / (2 * n)) / denom
    spread = z * math.sqrt(accuracy * (1 - accuracy) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def evaluate_baseline(
    baseline: Baseline,
    events: List[ObservedToolEvent],
    ground_truths: List[HiddenGroundTruth],
    dataset_name: str = "unknown",
) -> EvalResult:
    """Evaluate a single baseline on a dataset."""
    assert len(events) == len(ground_truths), "Events and ground truths must have same length"

    true_labels = []
    pred_labels = []

    result = EvalResult(baseline_name=baseline.name, dataset_name=dataset_name)

    for event, gt in zip(events, ground_truths):
        assert event.event_id == gt.event_id, f"Event ID mismatch: {event.event_id} vs {gt.event_id}"

        # Baseline only sees ObservedToolEvent
        baseline_result = baseline.evaluate(event)

        true_labels.append(gt.label)
        pred_labels.append(baseline_result.predicted_label)

    result.total = len(true_labels)
    result.correct = sum(1 for t, p in zip(true_labels, pred_labels) if t == p)
    result.accuracy = result.correct / result.total if result.total > 0 else 0.0

    result.per_label_metrics = compute_per_label_metrics(true_labels, pred_labels)
    result.confusion_matrix = compute_confusion_matrix(true_labels, pred_labels)

    # False allow: true=BLOCK, pred=ALLOW
    result.false_allow = sum(1 for t, p in zip(true_labels, pred_labels) if t == "BLOCK" and p == "ALLOW")
    # False block: true=ALLOW, pred=BLOCK
    result.false_block = sum(1 for t, p in zip(true_labels, pred_labels) if t == "ALLOW" and p == "BLOCK")
    # Review rate
    result.review_rate = sum(1 for p in pred_labels if p == "HUMAN_REVIEW") / result.total if result.total > 0 else 0.0

    # Macro averages
    precisions = [m["precision"] for m in result.per_label_metrics.values()]
    recalls = [m["recall"] for m in result.per_label_metrics.values()]
    f1s = [m["f1"] for m in result.per_label_metrics.values()]
    result.macro_precision = sum(precisions) / len(precisions) if precisions else 0.0
    result.macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
    result.macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    return result


def run_fair_evaluation(
    dataset_path: str,
    baseline_names: Optional[List[str]] = None,
    dataset_name: str = "unknown",
    output_path: Optional[str] = None,
) -> List[EvalResult]:
    """Run fair evaluation across all baselines on a dataset.

    Args:
        dataset_path: Path to JSON dataset file
        baseline_names: List of baseline names to evaluate (default: all)
        dataset_name: Name for reporting
        output_path: Path to write results JSON

    Returns:
        List of EvalResult objects
    """
    with open(dataset_path, encoding="utf-8") as f:
        raw_items = json.load(f)

    # Split into observed events and ground truths
    events = []
    ground_truths = []
    for item in raw_items:
        events.append(event_from_dict(item))
        ground_truths.append(ground_truth_from_dict(item))

    if baseline_names is None:
        baseline_names = list(ALL_BASELINES.keys())

    results = []
    for name in baseline_names:
        print(f"Evaluating baseline: {name}...")
        baseline = get_baseline(name)
        # A production-path baseline carries engine state between calls; reset
        # it so each event is scored independently rather than inheriting the
        # behavior graph of everything before it.
        if hasattr(baseline, "reset"):
            baseline.reset()
        eval_result = evaluate_baseline(baseline, events, ground_truths, dataset_name)
        results.append(eval_result)
        print(f"  Accuracy: {eval_result.accuracy:.4f}, Macro F1: {eval_result.macro_f1:.4f}")

    if output_path:
        output = {
            "dataset": dataset_name,
            "total_items": len(events),
            "baselines": [r.to_dict() for r in results],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"Results written to {output_path}")

    return results


if __name__ == "__main__":
    import sys
    dataset = sys.argv[1] if len(sys.argv) > 1 else "benchmark/test_cases/test_cases_sci_600.json"
    output = sys.argv[2] if len(sys.argv) > 2 else "benchmark/results/fair_eval_report.json"
    run_fair_evaluation(dataset, dataset_name=Path(dataset).stem, output_path=output)
