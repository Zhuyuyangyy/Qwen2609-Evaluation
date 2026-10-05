"""
Run LLM Safety Judge Baseline on Affective-Agent-Safety-300 dataset.

Usage:
    python run_llm_safety_judge_baseline.py [--provider PROVIDER] [--model MODEL]

Environment variables:
    OPENAI_API_KEY, DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, QWEN_API_KEY
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from experiments.llm_baseline.llm_safety_judge_baseline import LLMSafetyJudgeBaseline


def load_dataset(path: str) -> list:
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append(row)
    return samples


def check_api_available(provider: str) -> bool:
    key_map = {
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
        "qwen": "QWEN_API_KEY",
    }
    env_var = key_map.get(provider, f"{provider.upper()}_API_KEY")
    return bool(os.environ.get(env_var))


def find_dataset() -> str:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "affective_agent_safety_300.csv"),
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "affective_agent_safety_100.csv"),
        os.path.join(os.path.dirname(__file__), "..", "..", "benchmark", "affective_benchmark_tasks.csv"),
    ]
    for path in candidates:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            return abs_path
    return ""


def main():
    parser = argparse.ArgumentParser(description="Run LLM Safety Judge Baseline")
    parser.add_argument("--provider", default="openai", help="LLM provider")
    parser.add_argument("--model", default="gpt-4", help="Model name")
    parser.add_argument("--dataset", default="", help="Path to dataset CSV")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        os.path.dirname(__file__), "..", "results", "llm_baseline"
    )
    os.makedirs(output_dir, exist_ok=True)

    if not check_api_available(args.provider):
        print(f"[BLOCKED] No API key found for provider: {args.provider}")
        print("Cannot run real LLM baseline. Outputting protocol-only status.")
        protocol = {
            "status": "protocol_only",
            "reason": f"No API key available for {args.provider}",
            "provider": args.provider,
            "model": args.model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        protocol_path = os.path.join(output_dir, "llm_safety_judge_protocol_status.json")
        with open(protocol_path, "w") as f:
            json.dump(protocol, f, indent=2)
        print(f"Protocol status saved to: {protocol_path}")
        return

    dataset_path = args.dataset or find_dataset()
    if not dataset_path:
        print("[BLOCKED] No dataset found. Specify --dataset path.")
        return

    print(f"Loading dataset from: {dataset_path}")
    samples = load_dataset(dataset_path)
    print(f"Loaded {len(samples)} samples")

    judge = LLMSafetyJudgeBaseline(
        model=args.model,
        provider=args.provider,
        temperature=args.temperature,
        max_retries=args.max_retries,
    )

    print(f"Running LLM Safety Judge baseline with {args.provider}/{args.model}...")
    results = judge.judge_dataset(samples)

    raw_outputs_path = os.path.join(output_dir, "llm_safety_judge_raw_outputs.jsonl")
    with open(raw_outputs_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "sample_id": r.sample_id,
                "decision": r.decision,
                "rationale": r.rationale,
                "raw_output": r.raw_output,
                "parse_success": r.parse_success,
                "retry_count": r.retry_count,
                "error": r.error,
            }, ensure_ascii=False) + "\n")
    print(f"Raw outputs saved to: {raw_outputs_path}")

    predictions = {
        r.sample_id: r.decision for r in results if r.parse_success
    }
    predictions_path = os.path.join(output_dir, "llm_safety_judge_predictions.json")
    with open(predictions_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)
    print(f"Predictions saved to: {predictions_path}")

    summary = judge.get_summary()
    summary["model"] = args.model
    summary["provider"] = args.provider
    summary["temperature"] = args.temperature
    summary["prompt_version"] = judge.prompt_version
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
    summary["dataset"] = dataset_path
    summary["total_samples"] = len(samples)

    metrics_path = os.path.join(output_dir, "llm_safety_judge_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Metrics saved to: {metrics_path}")
    print(f"\nSummary: {json.dumps(summary, indent=2)}")


if __name__ == "__main__":
    main()
