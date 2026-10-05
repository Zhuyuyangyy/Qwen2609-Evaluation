"""
Compute Cohen's Kappa and other inter-annotator agreement metrics.

Usage:
    python compute_kappa.py \
        --gold <gold_reference.csv or .json> \
        --annotator <annotator_2_completed.csv> \
        --output <output.json>

The gold reference CSV must have columns: sample_id, gold_decision
The annotator CSV must have columns: sample_id, annotator_label

Both files must share the same sample_id values for comparison.
"""

import argparse
import csv
import json
import os
import sys


LABELS = ["AUTO_EXECUTE", "SIMULATE_FIRST", "HUMAN_REVIEW", "BLOCK"]


def load_gold_csv(path: str) -> dict:
    gold = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gold[row["sample_id"]] = row["gold_decision"]
    return gold


def load_gold_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_annotator_csv(path: str) -> dict:
    annotations = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = row.get("annotator_label", "").strip()
            if label:
                annotations[row["sample_id"]] = label
    return annotations


def compute_confusion_matrix(gold: dict, annotator: dict) -> list:
    n = len(LABELS)
    label_to_idx = {l: i for i, l in enumerate(LABELS)}
    matrix = [[0] * n for _ in range(n)]

    for sid in gold:
        if sid not in annotator:
            continue
        g = gold[sid]
        a = annotator[sid]
        if g in label_to_idx and a in label_to_idx:
            matrix[label_to_idx[g]][label_to_idx[a]] += 1

    return matrix


def compute_cohens_kappa(matrix: list) -> float:
    n = len(matrix)
    total = sum(sum(row) for row in matrix)
    if total == 0:
        return 0.0

    po = sum(matrix[i][i] for i in range(n)) / total

    pe = 0.0
    for i in range(n):
        row_sum = sum(matrix[i])
        col_sum = sum(matrix[j][i] for j in range(n))
        pe += (row_sum * col_sum) / (total * total)

    if pe == 1.0:
        return 1.0

    return (po - pe) / (1.0 - pe)


def compute_percentage_agreement(gold: dict, annotator: dict) -> float:
    agreed = 0
    total = 0
    for sid in gold:
        if sid not in annotator:
            continue
        total += 1
        if gold[sid] == annotator[sid]:
            agreed += 1
    return agreed / total if total > 0 else 0.0


def compute_per_class_metrics(matrix: list) -> dict:
    n = len(matrix)
    metrics = {}
    for i, label in enumerate(LABELS):
        tp = matrix[i][i]
        fp = sum(matrix[j][i] for j in range(n)) - tp
        fn = sum(matrix[i][j] for j in range(n)) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        metrics[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support_gold": sum(matrix[i]),
            "support_annotator": sum(matrix[j][i] for j in range(n)),
        }
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Compute Cohen's Kappa")
    parser.add_argument("--gold", required=True, help="Gold reference CSV or JSON")
    parser.add_argument("--annotator", required=True, help="Annotator completed CSV")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    if not os.path.exists(args.gold):
        print(f"ERROR: Gold reference file not found: {args.gold}")
        print("The project maintainer must provide the hidden gold reference.")
        print("Run: python experiments/annotation/generate_gold_reference.py")
        sys.exit(1)

    if not os.path.exists(args.annotator):
        print(f"ERROR: Annotator file not found: {args.annotator}")
        print("The second annotator must complete annotation first.")
        print("Expected file: annotation_reliability/for_annotator_2/annotator_2_completed.csv")
        sys.exit(1)

    if args.gold.endswith(".json"):
        gold = load_gold_json(args.gold)
    else:
        gold = load_gold_csv(args.gold)

    annotator = load_annotator_csv(args.annotator)

    common_ids = set(gold.keys()) & set(annotator.keys())
    if not common_ids:
        print("ERROR: No common sample IDs between gold and annotator files.")
        sys.exit(1)

    print(f"Found {len(common_ids)} common samples for comparison")

    matrix = compute_confusion_matrix(gold, annotator)
    kappa = compute_cohens_kappa(matrix)
    agreement = compute_percentage_agreement(gold, annotator)
    per_class = compute_per_class_metrics(matrix)

    result = {
        "cohen_kappa": round(kappa, 4),
        "percentage_agreement": round(agreement, 4),
        "total_compared": len(common_ids),
        "gold_total": len(gold),
        "annotator_total": len(annotator),
        "confusion_matrix": {
            "labels": LABELS,
            "matrix": matrix,
        },
        "per_class_metrics": per_class,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n=== Inter-Annotator Agreement ===")
    print(f"Cohen's Kappa: {kappa:.4f}")
    print(f"Percentage Agreement: {agreement:.4f}")
    print(f"Samples compared: {len(common_ids)}")
    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
