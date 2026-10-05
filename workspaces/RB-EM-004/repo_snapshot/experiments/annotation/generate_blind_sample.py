"""
Generate blind annotation sample from AffectiveBench benchmark tasks.

Creates a 100-sample CSV for independent annotation with:
- sample_id, task_description, category, risk_context
- annotator_label (EMPTY)
- annotator_rationale (EMPTY)

Does NOT include: gold_decision, model prediction, expected_decision
"""

import csv
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from emotion_agent.affective_benchmark import AffectiveBenchmark


RISK_CONTEXT_MAP = {
    "IRREVERSIBLE_FILE_OPS": "The operation is potentially irreversible and may cause permanent data loss.",
    "TRUST_SOURCE_ADVICE": "The advice comes from an external source whose reliability is unverified.",
    "HIGH_UNCERTAINTY": "The outcome of this operation is highly uncertain.",
    "HIGH_REWARD_RISK": "The operation offers high reward but carries significant risk.",
    "RECOVERY_GENERALIZATION": "The operation involves recovery or generalization from a previous state.",
}


def generate_blind_sample(output_path: str, sample_size: int = 100, seed: int = 42):
    benchmark = AffectiveBenchmark(seed=seed)

    if len(benchmark.tasks) < sample_size:
        sample_size = len(benchmark.tasks)

    random.seed(seed)
    sampled = random.sample(benchmark.tasks, sample_size)

    fieldnames = [
        "sample_id",
        "task_description",
        "category",
        "risk_context",
        "annotator_label",
        "annotator_rationale",
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for task in sampled:
            writer.writerow({
                "sample_id": task.id,
                "task_description": task.description,
                "category": task.category.value,
                "risk_context": RISK_CONTEXT_MAP.get(task.category.value, ""),
                "annotator_label": "",
                "annotator_rationale": "",
            })

    print(f"Generated {sample_size} blind samples to: {output_path}")
    print("Fields annotator_label and annotator_rationale are EMPTY (to be filled by annotator).")
    print("No gold_decision, model prediction, or expected_decision is included.")


if __name__ == "__main__":
    output = os.path.join(
        os.path.dirname(__file__),
        "blind_annotation_sample_100.csv",
    )
    generate_blind_sample(output)
