"""
Parse LLM Safety Judge raw outputs and extract structured predictions.

Usage:
    python parse_llm_judge_output.py --input raw_outputs.jsonl --output predictions.json
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from experiments.llm_baseline.llm_safety_judge_baseline import LLMSafetyJudgeBaseline


def main():
    parser = argparse.ArgumentParser(description="Parse LLM Judge raw outputs")
    parser.add_argument("--input", required=True, help="Path to raw_outputs.jsonl")
    parser.add_argument("--output", required=True, help="Path to output predictions.json")
    parser.add_argument("--failures", default="", help="Path to parse failures JSONL")
    args = parser.parse_args()

    judge = LLMSafetyJudgeBaseline()
    predictions = {}
    failures = []

    with open(args.input, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            sample_id = record.get("sample_id", "")
            raw_output = record.get("raw_output", "")

            decision, rationale = judge.parse_output(raw_output)

            if decision is not None:
                predictions[sample_id] = {
                    "decision": decision,
                    "rationale": rationale or record.get("rationale", ""),
                }
            else:
                failures.append({
                    "sample_id": sample_id,
                    "raw_output": raw_output,
                    "original_decision": record.get("decision", ""),
                    "error": "Parse failure",
                })

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)

    print(f"Parsed {len(predictions)} predictions, {len(failures)} failures")

    if args.failures and failures:
        with open(args.failures, "w", encoding="utf-8") as f:
            for fail in failures:
                f.write(json.dumps(fail, ensure_ascii=False) + "\n")
        print(f"Failures saved to: {args.failures}")


if __name__ == "__main__":
    main()
