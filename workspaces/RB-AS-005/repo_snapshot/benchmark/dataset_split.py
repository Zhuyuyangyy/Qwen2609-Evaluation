"""Dataset splitting utility for fair evaluation.

Splits benchmark datasets into train/dev/test with proper isolation:
- Dev-Synthetic: for development and debugging
- Heldout-Adversarial: for paper evaluation (generation rules isolated from detection rules)
- Real/Anonymized: for enterprise credibility (future)
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List


def deterministic_split(
    items: List[Dict[str, Any]],
    train_ratio: float = 0.6,
    dev_ratio: float = 0.2,
    test_ratio: float = 0.2,
    seed: int = 42,
) -> tuple[List[Dict], List[Dict], List[Dict]]:
    """Split items deterministically based on content hash.

    Uses content hashing to ensure the same item always ends up in
    the same split, regardless of ordering.
    """
    assert abs(train_ratio + dev_ratio + test_ratio - 1.0) < 0.001

    train, dev, test = [], [], []

    for item in items:
        # Hash the item content for deterministic assignment
        content = json.dumps(item, sort_keys=True, ensure_ascii=False)
        h = int(hashlib.md5(content.encode()).hexdigest(), 16)
        roll = (h % 10000) / 10000.0

        if roll < train_ratio:
            train.append(item)
        elif roll < train_ratio + dev_ratio:
            dev.append(item)
        else:
            test.append(item)

    return train, dev, test


def split_dataset_file(
    input_path: str,
    output_dir: str,
    label_key: str = "label",
    train_ratio: float = 0.6,
    dev_ratio: float = 0.2,
    test_ratio: float = 0.2,
    seed: int = 42,
) -> Dict[str, int]:
    """Split a dataset JSON file into train/dev/test files.

    Ensures label distribution is roughly preserved across splits.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(input_path, encoding="utf-8") as f:
        items = json.load(f)

    # Group by label for stratified split
    by_label: Dict[str, List[Dict]] = {}
    for item in items:
        label = item.get(label_key, "UNKNOWN")
        by_label.setdefault(label, []).append(item)

    train_all, dev_all, test_all = [], [], []
    for label, group in by_label.items():
        t, d, te = deterministic_split(group, train_ratio, dev_ratio, test_ratio, seed)
        train_all.extend(t)
        dev_all.extend(d)
        test_all.extend(te)

    # Write splits
    splits = {"train": train_all, "dev": dev_all, "test": test_all}
    counts = {}
    for split_name, split_items in splits.items():
        out_path = output_dir / f"{input_path.stem}_{split_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(split_items, f, indent=2, ensure_ascii=False)
        counts[split_name] = len(split_items)
        print(f"  {split_name}: {len(split_items)} items -> {out_path}")

    return counts


if __name__ == "__main__":

    datasets = [
        ("benchmark/test_cases/test_cases_sci_600.json", "benchmark/test_cases/split"),
        ("benchmark/test_cases/test_cases_semireal_150.json", "benchmark/test_cases/split"),
    ]

    for input_path, output_dir in datasets:
        p = Path(input_path)
        if not p.exists():
            print(f"Skipping {input_path} (not found)")
            continue
        print(f"Splitting {input_path}...")
        counts = split_dataset_file(input_path, output_dir)
        print(f"  Result: {counts}")
