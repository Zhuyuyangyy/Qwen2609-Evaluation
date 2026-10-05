"""Run independent evaluation of AgentShield baselines.

This evaluation uses the independent dataset that contains ONLY
observable information. Labels are loaded separately and never
read by scoring functions.

Evaluation modes:
1. Full evaluation: All 100 cases
2. Train evaluation: 70% train cases
3. Test evaluation: 30% test cases (zero-shot generalization)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.independent_eval.baselines import BASELINES, evaluate


def load_json(path: Path) -> Any:
    """Load JSON file."""
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(data: Any, path: Path) -> None:
    """Write JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_markdown(report: Dict[str, Any], path: Path) -> None:
    """Write markdown report."""
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Independent Evaluation Report",
        "",
        f"Dataset: `{report['dataset']}`",
        f"Split: `{report['split']}`",
        f"Cases: {report['total_cases']}",
        "",
        "## Design Principles",
        "",
        "- Cases contain ONLY observable information (tool_name, input_text, output_text)",
        "- No ground-truth metadata (attack_stage, chain_id, step_index) in case data",
        "- Labels stored separately and never read by scoring functions",
        "- Risky cases: each step looks safe alone, chains form attack patterns",
        "",
        "## Baseline Comparison",
        "",
        "| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block | Review Rate | MAE | ms/case |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for item in report["baselines"]:
        lines.append(
            "| {name} | {acc:.2%} | {f1:.2%} | {block:.2%} | {fa:.2%} | {fb:.2%} | {review:.2%} | {mae:.4f} | {runtime:.4f} |".format(
                name=item["name"],
                acc=item["action_accuracy"],
                f1=item["macro_f1"],
                block=item["block_recall"],
                fa=item["false_allow_rate"],
                fb=item["false_block_rate"],
                review=item["human_review_rate"],
                mae=item["mean_absolute_score_error"],
                runtime=item["runtime_ms_per_case"],
            )
        )

    lines.extend([
        "",
        "## Per-Label Metrics",
        "",
    ])

    for item in report["baselines"]:
        lines.append(f"### {item['name']}")
        lines.append("")
        lines.append("| Label | Precision | Recall | F1 |")
        lines.append("|---|---:|---:|---:|")
        for label in ["ALLOW", "HUMAN_REVIEW", "BLOCK"]:
            metrics = item["per_label"].get(label, {})
            lines.append(
                f"| {label} | {metrics.get('precision', 0):.2%} | {metrics.get('recall', 0):.2%} | {metrics.get('f1', 0):.2%} |"
            )
        lines.append("")

    lines.extend([
        "## Notes",
        "",
        "- Tool-name rules: Risk based solely on tool name",
        "- Content keywords: Risk from keyword matching in input text",
        "- Local context: Category-aware priors with keyword boost",
        "- NeMo Guardrails: Multi-rail architecture (topic/jailbreak/input/output/execution rails)",
        "- LLM Guard: Scanner pipeline (secrets/injection/code/regex/topics/toxicity/dataflow/toolsafety)",
        "- LLM-as-Judge: Content sensitivity + transfer risk + chain length + privilege risk",
        "- AgentShield chain-aware: Chain position inference + stage inference + content signals",
        "- AgentShield + Graph: Chain-aware + graph risk propagation boost",
        "",
        "## Fairness Guarantee",
        "",
        "All baselines use ONLY observable features:",
        "- tool_name: The name of the tool being called",
        "- input_text: The input parameters to the tool",
        "- output_text: The output/result of the tool call",
        "",
        "NO ground-truth metadata is read by any baseline:",
        "- attack_stage: NOT used",
        "- chain_id: NOT used",
        "- step_index: NOT used",
    ])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_evaluation(
    cases_path: Path,
    labels_path: Path,
    output_dir: Path,
    split_name: str = "full",
) -> Dict[str, Any]:
    """Run evaluation on a dataset split.

    Args:
        cases_path: Path to cases JSON file
        labels_path: Path to labels/metadata JSON file
        output_dir: Directory for output files
        split_name: Name of the split (full, train, test)

    Returns:
        Report dictionary
    """
    cases = load_json(cases_path)
    metadata = load_json(labels_path)
    labels = metadata["labels"]

    print(f"\n{'='*60}")
    print(f"Evaluating: {split_name}")
    print(f"  Cases: {len(cases)}")
    print(f"  Labels: {len(labels)}")
    print(f"{'='*60}")

    # Run all baselines
    baseline_reports = []
    for name, predictor in BASELINES.items():
        print(f"  Running {name}...", end=" ", flush=True)
        report = evaluate(name, predictor, cases, labels)
        baseline_reports.append(report)
        print(f"acc={report['action_accuracy']:.3f} f1={report['macro_f1']:.3f} block_recall={report['block_recall']:.3f}")

    # Build full report
    report = {
        "dataset": str(cases_path),
        "split": split_name,
        "total_cases": len(cases),
        "labels": ["ALLOW", "HUMAN_REVIEW", "BLOCK"],
        "baselines": baseline_reports,
    }

    # Write outputs
    json_path = output_dir / f"report_{split_name}.json"
    md_path = output_dir / f"report_{split_name}.md"

    write_json(report, json_path)
    write_markdown(report, md_path)

    print(f"\n  JSON report: {json_path}")
    print(f"  Markdown report: {md_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent evaluation.")
    parser.add_argument("--data-dir", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--split", choices=["full", "train", "test", "all"], default="all")
    args = parser.parse_args()

    data_dir = args.data_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check if dataset exists
    if not (data_dir / "eval_cases.json").exists():
        print("Error: Dataset not found. Run generate_dataset.py first.")
        sys.exit(1)

    # Check if splits exist
    has_splits = (data_dir / "train_cases.json").exists() and (data_dir / "test_cases.json").exists()
    if not has_splits and args.split in ("train", "test", "all"):
        print("Warning: Train/test splits not found. Run split_dataset.py first.")
        print("Running full evaluation only.")
        args.split = "full"

    reports = {}

    if args.split in ("full", "all"):
        reports["full"] = run_evaluation(
            data_dir / "eval_cases.json",
            data_dir / "labels.json",
            output_dir,
            "full",
        )

    if args.split in ("train", "all") and has_splits:
        reports["train"] = run_evaluation(
            data_dir / "train_cases.json",
            data_dir / "train_labels.json",
            output_dir,
            "train",
        )

    if args.split in ("test", "all") and has_splits:
        reports["test"] = run_evaluation(
            data_dir / "test_cases.json",
            data_dir / "test_labels.json",
            output_dir,
            "test",
        )

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    for split_name, report in reports.items():
        print(f"\n{split_name.upper()} ({report['total_cases']} cases):")
        print(f"  {'Method':<28} {'Acc':>8} {'F1':>8} {'BLOCK Rec':>10}")
        print(f"  {'-'*28} {'-'*8} {'-'*8} {'-'*10}")
        for item in report["baselines"]:
            print(
                f"  {item['name']:<28} {item['action_accuracy']:>8.3f} "
                f"{item['macro_f1']:>8.3f} {item['block_recall']:>10.3f}"
            )

    # Write combined report
    combined_path = output_dir / "combined_report.json"
    write_json(reports, combined_path)
    print(f"\nCombined report: {combined_path}")


if __name__ == "__main__":
    main()
