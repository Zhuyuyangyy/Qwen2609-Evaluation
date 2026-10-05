"""
Generate hidden gold reference for kappa computation.

This file is NOT for distribution to annotators.
It contains the gold labels that will be used as the reference
in Cohen's kappa calculation.

The project maintainer must keep this file separate from the
annotation package distributed to annotators.
"""

import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from emotion_agent.affective_benchmark import AffectiveBenchmark


RISK_TO_DECISION = {
    "CRITICAL": "BLOCK",
    "HIGH": "HUMAN_REVIEW",
    "MEDIUM": "SIMULATE_FIRST",
    "LOW": "AUTO_EXECUTE",
}


def generate_gold_reference(
    csv_output_path: str,
    json_output_path: str,
    sample_size: int = 100,
    seed: int = 42,
):
    benchmark = AffectiveBenchmark(seed=seed)

    if len(benchmark.tasks) < sample_size:
        sample_size = len(benchmark.tasks)

    random.seed(seed)
    sampled = random.sample(benchmark.tasks, sample_size)

    gold_dict = {}

    fieldnames = [
        "sample_id",
        "task_description",
        "category",
        "risk_context",
        "gold_decision",
    ]

    os.makedirs(os.path.dirname(csv_output_path), exist_ok=True)

    with open(csv_output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for task in sampled:
            decision = RISK_TO_DECISION.get(task.expected_risk_level, "HUMAN_REVIEW")
            writer.writerow({
                "sample_id": task.id,
                "task_description": task.description,
                "category": task.category.value,
                "risk_context": task.expected_risk_level,
                "gold_decision": decision,
            })
            gold_dict[task.id] = decision

    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(gold_dict, f, indent=2, ensure_ascii=False)

    print(f"Generated gold reference for {sample_size} samples")
    print(f"CSV: {csv_output_path}")
    print(f"JSON: {json_output_path}")
    print("WARNING: This file contains gold labels. Do NOT distribute to annotators.")


if __name__ == "__main__":
    base_dir = os.path.dirname(__file__)
    generate_gold_reference(
        csv_output_path=os.path.join(
            base_dir, "blind_annotation_sample_100_with_gold_hidden_reference.csv"
        ),
        json_output_path=os.path.join(
            base_dir, "gold_reference_hidden.json"
        ),
    )
