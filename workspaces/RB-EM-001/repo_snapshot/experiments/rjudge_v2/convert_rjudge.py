"""
convert_rjudge.py
=================
Download and convert the R-Judge dataset (EMNLP Findings 2024) into a
standardized JSONL format that the rest of the rjudge_v2 pipeline can consume.

R-Judge source: https://github.com/Lordog/R-Judge

Each converted record contains:
  - id: original record id
  - scenario: application scenario
  - profile: user profile
  - goal: user goal
  - contents: list of turns (each turn = list of messages)
  - label: 0 (safe) or 1 (unsafe)
  - risk_description: human-written risk explanation
  - attack_type: "injection" or "unintended"

Usage:
    python experiments/rjudge_v2/convert_rjudge.py [--data-dir DIR] [--output PATH]

If --data-dir is not specified, this script will attempt to clone the
R-Judge repository into <project_root>/rjudge_data/ automatically.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Dict, List

RJUDGE_REPO = "https://github.com/Lordog/R-Judge.git"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "rjudge_data")
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "results", "rjudge_v2", "rjudge_converted.jsonl")

# Official benchmark files live under data/ in the R-Judge repo.
# Audit (2026-09): the repository contains 571 records in data/ (all ids unique).
#   - ACL EMNLP-Findings 2024 paper reports 569 records (paper-time snapshot,
#     before the repo's 2024-10-05 "update data" commit added 2 injection
#     records and reorganized directories).
#   - NEXUS (arXiv 2607.19356) treats the current repo release as 571 records
#     and reports 564 usable after excluding 7 "leaked" records.
# We load the current official data/ release (571) and keep the loader
# strictly scoped to data/ — the old `**/*.json` glob inflated the set to
# 1243 records by also ingesting eval/results/*.json and results/**/*.json.
DATA_SUBDIR = "data"


def ensure_data(data_dir: str) -> str:
    """Clone R-Judge repo if data directory does not exist."""
    if os.path.isdir(data_dir):
        return data_dir
    print(f"R-Judge data not found at {data_dir}. Cloning from GitHub...")
    subprocess.check_call(["git", "clone", "--depth", "1", RJUDGE_REPO, data_dir])
    print(f"Cloned to {data_dir}")
    return data_dir


def load_rjudge_records(data_dir: str) -> List[Dict]:
    """
    Load the official R-Judge benchmark records.

    Scoped to ``<data_dir>/data/**/*.json`` (the official data files only),
    deduplicated by record ``id``, with per-record provenance tracked in
    ``_source``. Any other JSON files in the repo (eval results, model
    inference outputs, config schemas) are intentionally ignored so that the
    converted set matches the official benchmark release, not the repo tree.
    """
    import glob

    data_root = os.path.join(data_dir, DATA_SUBDIR)
    if not os.path.isdir(data_root):
        raise FileNotFoundError(
            f"R-Judge data directory not found at {data_root} — "
            f"clone the repository first (see ensure_data)."
        )

    seen_ids = set()
    records = []
    dup_ids = []
    search_pattern = os.path.join(data_root, "**", "*.json")
    for f in sorted(glob.glob(search_pattern, recursive=True)):
        # posix-style relative path so `_source` is stable across platforms
        # (Windows relpath uses backslashes, which broke the data/-prefix check)
        rel = os.path.relpath(f, data_dir).replace(os.sep, "/")
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            print(f"  [skip] non-list JSON (not a record file): {rel}")
            continue
        for r in data:
            if not isinstance(r, dict):
                continue
            rid = r.get("id", "")
            if rid in seen_ids:
                dup_ids.append((rid, rel))
                continue
            seen_ids.add(rid)
            record = dict(r)
            record["_source"] = rel
            records.append(record)

    if dup_ids:
        print(f"  [dedup] dropped {len(dup_ids)} duplicate-id records: {dup_ids[:10]}{'…' if len(dup_ids) > 10 else ''}")
    return records


def convert_records(records: List[Dict]) -> List[Dict]:
    """Normalize records to a consistent format."""
    converted = []
    for r in records:
        rec = {
            "id": r.get("id", ""),
            "scenario": r.get("scenario", ""),
            "profile": r.get("profile", ""),
            "goal": r.get("goal", ""),
            "contents": r.get("contents", []),
            "label": r.get("label", -1),
            "risk_description": r.get("risk_description", ""),
            "attack_type": r.get("attack_type", ""),
        }
        if r.get("_source"):
            rec["_source"] = r["_source"]
        converted.append(rec)
    return converted


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convert R-Judge dataset")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                        help="Directory containing R-Judge data")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="Output JSONL path")
    args = parser.parse_args()

    data_dir = ensure_data(args.data_dir)
    records = load_rjudge_records(data_dir)
    converted = convert_records(records)

    # R-Judge record-count audit (569 vs 571) — see module docstring.
    # The official ACL paper reports 569; the current repo data/ release has
    # 571 records. We pin the loader to the official data/ release (571) and
    # surface the discrepancy here so downstream numbers are auditable.
    if len(converted) == 569:
        note = "matches ACL paper count (569)"
    elif len(converted) == 571:
        note = "current official repo data/ release; +2 vs ACL paper (569) due to 2024-10-05 data update"
    else:
        note = ""
    print(f"Loaded {len(converted)} official records from {data_dir}/data  [{note}]")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for rec in converted:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Print label distribution
    from collections import Counter
    labels = Counter(r["label"] for r in converted)
    attacks = Counter(r["attack_type"] for r in converted)
    sources = Counter(r.get("_source", "") for r in converted)
    print(f"Label distribution: {dict(labels)}")
    print(f"Attack type distribution: {dict(attacks)}")
    print("Source file distribution:")
    for src, n in sorted(sources.items()):
        print(f"  {n:4d}  {src}")
    print(f"Saved {len(converted)} records to {args.output}")


if __name__ == "__main__":
    main()
