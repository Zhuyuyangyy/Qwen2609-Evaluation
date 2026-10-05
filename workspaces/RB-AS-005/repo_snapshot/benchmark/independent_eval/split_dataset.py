"""Create train/test split for independent evaluation dataset.

The split ensures zero-shot generalization testing by holding out
specific attack pattern variants from the training set.

Split Strategy:
- 70% train, 30% test
- Test set contains attack patterns NOT seen in training
- Pattern variants are split by tool_name combinations:
  - Pattern A (Data Chain): Train uses send_email/webhook variants,
    test uses http_request/upload_to_s3 variants
  - Pattern B (Privilege Escalation): Train uses GRANT/CREATE,
    test uses ALTER/ASSUME variants
  - Pattern C (Info Recon): Train uses SQL-based recon,
    test uses scan_network/read_file variants
  - Pattern D (Audit Bypass): Train uses DELETE/UPDATE,
    test uses DISABLE TRIGGER/forge variants
  - Pattern E (Bulk Export): Train uses export_csv,
    test uses COPY/bulk_export variants
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent


# Define which tool_name variants go to test (not seen in training)
# These are the "zero-shot" variants that test generalization
ZERO_SHOT_TEST_TOOLS: Dict[str, Set[str]] = {
    # Pattern A: Data Chain - test uses different transmission tools
    "pattern_a_transmission": {"http_request", "upload_to_s3", "webhook_post"},
    # Pattern B: Privilege Escalation - test uses different escalation tools
    "pattern_b_escalation": {"assume_iam_role"},
    # Pattern C: Info Recon - test uses different recon tools
    "pattern_c_recon": {"scan_network", "read_file"},
    # Pattern D: Audit Bypass - test uses different bypass tools
    "pattern_d_bypass": {"forge_audit_log", "execute_admin_command"},
    # Pattern E: Bulk Export - test uses different export tools
    "pattern_e_export": {"bulk_export"},
    # Pattern F: Covert Channel - test uses different exfil vectors
    "pattern_f_covert": {"send_notification", "http_request", "call_api"},
    # Pattern G: Supply Chain - test uses different package managers
    "pattern_g_supply": {"execute_admin_command", "write_file"},
    # Pattern H: Time Series Anomaly - test uses different burst patterns
    "pattern_h_burst": {"compress_file", "list_files"},
}


def classify_case_for_split(
    case: Dict[str, Any],
    label: Dict[str, Any],
    risky_tool_groups: Dict[str, List[Dict[str, Any]]],
) -> str:
    """Determine if a case should go to train or test.

    Strategy:
    - Safe cases: 70% train, 30% test (random split)
    - Risky cases: Split by tool_name variant to ensure zero-shot testing
    """
    if not label["is_risky"]:
        # Safe cases: hash-based deterministic split
        case_id = case["id"]
        hash_val = sum(ord(c) for c in case_id)
        return "train" if hash_val % 10 < 7 else "test"

    # Risky cases: check if tool_name matches zero-shot test tools
    tool_name = case["tool_name"]

    # Check each pattern's zero-shot tools
    for pattern_name, test_tools in ZERO_SHOT_TEST_TOOLS.items():
        if tool_name in test_tools:
            return "test"

    # Default: train
    return "train"


def split_dataset(
    cases: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    seed: int = 42,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Split dataset into train and test sets.

    Returns:
        train_data: {"cases": [...], "metadata": {...}}
        test_data: {"cases": [...], "metadata": {...}}
    """
    labels = metadata["labels"]
    label_map = {l["case_id"]: l for l in labels}

    train_cases = []
    train_labels = []
    test_cases = []
    test_labels = []

    for case in cases:
        case_id = case["id"]
        label = label_map[case_id]
        split = classify_case_for_split(case, label, {})

        if split == "train":
            train_cases.append(case)
            train_labels.append(label)
        else:
            test_cases.append(case)
            test_labels.append(label)

    # Build metadata for each split
    train_metadata = {
        "split": "train",
        "total_cases": len(train_cases),
        "safe_cases": sum(1 for l in train_labels if not l["is_risky"]),
        "risky_cases": sum(1 for l in train_labels if l["is_risky"]),
        "labels": train_labels,
    }

    test_metadata = {
        "split": "test",
        "total_cases": len(test_cases),
        "safe_cases": sum(1 for l in test_labels if not l["is_risky"]),
        "risky_cases": sum(1 for l in test_labels if l["is_risky"]),
        "zero_shot_patterns": list(ZERO_SHOT_TEST_TOOLS.keys()),
        "labels": test_labels,
    }

    return (
        {"cases": train_cases, "metadata": train_metadata},
        {"cases": test_cases, "metadata": test_metadata},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Split dataset into train/test.")
    parser.add_argument("--input-dir", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load cases and metadata
    cases_path = input_dir / "eval_cases.json"
    labels_path = input_dir / "labels.json"

    if not cases_path.exists() or not labels_path.exists():
        print("Error: eval_cases.json or labels.json not found. Run generate_dataset.py first.")
        return

    with cases_path.open(encoding="utf-8") as f:
        cases = json.load(f)
    with labels_path.open(encoding="utf-8") as f:
        metadata = json.load(f)

    # Split
    train_data, test_data = split_dataset(cases, metadata, seed=args.seed)

    # Write train set
    train_cases_path = output_dir / "train_cases.json"
    train_labels_path = output_dir / "train_labels.json"
    with train_cases_path.open("w", encoding="utf-8") as f:
        json.dump(train_data["cases"], f, ensure_ascii=False, indent=2)
    with train_labels_path.open("w", encoding="utf-8") as f:
        json.dump(train_data["metadata"], f, ensure_ascii=False, indent=2)

    # Write test set
    test_cases_path = output_dir / "test_cases.json"
    test_labels_path = output_dir / "test_labels.json"
    with test_cases_path.open("w", encoding="utf-8") as f:
        json.dump(test_data["cases"], f, ensure_ascii=False, indent=2)
    with test_labels_path.open("w", encoding="utf-8") as f:
        json.dump(test_data["metadata"], f, ensure_ascii=False, indent=2)

    print(f"Train set: {train_data['metadata']['total_cases']} cases")
    print(f"  Safe: {train_data['metadata']['safe_cases']}")
    print(f"  Risky: {train_data['metadata']['risky_cases']}")
    print(f"Test set: {test_data['metadata']['total_cases']} cases")
    print(f"  Safe: {test_data['metadata']['safe_cases']}")
    print(f"  Risky: {test_data['metadata']['risky_cases']}")
    print("\nZero-shot patterns in test set:")
    for pattern in test_data["metadata"]["zero_shot_patterns"]:
        print(f"  - {pattern}")


if __name__ == "__main__":
    main()
