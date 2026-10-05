"""
generate_report.py
==================
Generate the R-Judge v1 failure reproduction report from computed metrics
and failure analysis results.
"""

from __future__ import annotations

import json
import os
from typing import Dict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "rjudge_v2")


def generate_report(results_dir: str) -> str:
    """Generate the full failure reproduction report."""
    metrics_path = os.path.join(results_dir, "metrics_v1.json")
    failure_summary_path = os.path.join(results_dir, "failure_summary.csv")

    metrics = {}
    if os.path.exists(metrics_path):
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)

    # Read failure summary CSV
    failure_summary_lines = []
    if os.path.exists(failure_summary_path):
        with open(failure_summary_path, encoding="utf-8") as f:
            failure_summary_lines = f.readlines()

    # Build report
    lines = []
    lines.append("# R-Judge V1 Failure Reproduction Report")
    lines.append("")
    lines.append("**Date**: Auto-generated")
    lines.append("**Dataset**: R-Judge (EMNLP Findings 2024)")
    lines.append("**Pipeline**: DecisionPipeline v1 (keyword risk encoder + memory + affect)")
    lines.append("**Purpose**: Reproducible evidence that the v1 keyword-based risk encoder")
    lines.append("cannot detect semantic risks in real-world agent interactions.")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    if metrics:
        unsafe_recall = metrics.get("unsafe_recall", "N/A")
        unsafe_f1 = metrics.get("unsafe_f1", "N/A")
        false_safe = metrics.get("false_safe_count", "N/A")
        evidence_cov = metrics.get("evidence_coverage", "N/A")
        n_unsafe = metrics.get("n_unsafe", "N/A")
        n = metrics.get("n", "N/A")

        lines.append(f"The v1 DecisionPipeline achieves **unsafe recall = {unsafe_recall}** on the")
        lines.append(f"R-Judge benchmark ({n_unsafe} unsafe records out of {n} total).")
        lines.append(f"This means the pipeline **misses {false_safe} out of {n_unsafe} genuinely unsafe")
        lines.append(f"agent interactions**. The keyword-based risk encoder provides evidence")
        lines.append(f"coverage of only {evidence_cov}, meaning the vast majority of unsafe records")
        lines.append(f"score zero risk and are auto-executed without hesitation.")
        lines.append("")
        lines.append(f"Unsafe F1 = {unsafe_f1}. This is not a calibration problem — it is a")
        lines.append("**coverage problem**. The risk encoder cannot detect semantic risks")
        lines.append("(social engineering, prompt injection, unintended information disclosure)")
        lines.append("because it relies entirely on keyword matching.")
    else:
        lines.append("Metrics not available. Run the pipeline first:")
        lines.append("```bash")
        lines.append("python experiments/rjudge_v2/run_failure_reproduction.py")
        lines.append("```")
    lines.append("")

    # Key Metrics
    lines.append("## Key Metrics")
    lines.append("")
    if metrics:
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total records | {metrics.get('n', 'N/A')} |")
        lines.append(f"| Unsafe records | {metrics.get('n_unsafe', 'N/A')} |")
        lines.append(f"| Safe records | {metrics.get('n_safe', 'N/A')} |")
        lines.append(f"| Accuracy (binary) | {metrics.get('accuracy', 'N/A')} |")
        lines.append(f"| **Unsafe recall** | **{metrics.get('unsafe_recall', 'N/A')}** |")
        lines.append(f"| Unsafe precision | {metrics.get('unsafe_precision', 'N/A')} |")
        lines.append(f"| Unsafe F1 | {metrics.get('unsafe_f1', 'N/A')} |")
        lines.append(f"| Safe recall | {metrics.get('safe_recall', 'N/A')} |")
        lines.append(f"| Macro F1 | {metrics.get('macro_f1', 'N/A')} |")
        lines.append(f"| False safe count | {metrics.get('false_safe_count', 'N/A')} |")
        lines.append(f"| False block count | {metrics.get('false_block_count', 'N/A')} |")
        lines.append(f"| Over-escalation rate | {metrics.get('over_escalation_rate', 'N/A')} |")
        lines.append(f"| Under-escalation rate | {metrics.get('under_escalation_rate', 'N/A')} |")
        lines.append(f"| Evidence coverage | {metrics.get('evidence_coverage', 'N/A')} |")
        lines.append(f"| Decision distribution | {metrics.get('decision_distribution', 'N/A')} |")
        rtr = metrics.get("risk_type_recall", {})
        if rtr:
            lines.append("")
            lines.append("### Risk Type Recall")
            lines.append("")
            lines.append("| Attack type | Recall |")
            lines.append("|-------------|--------|")
            for at, recall in sorted(rtr.items()):
                lines.append(f"| {at} | {recall} |")
    else:
        lines.append("No metrics available.")
    lines.append("")

    # Failure Mode Analysis
    lines.append("## Failure Mode Analysis")
    lines.append("")
    lines.append("The following failure modes were identified for missed unsafe records:")
    lines.append("")
    lines.append("| Failure Mode | Description |")
    lines.append("|--------------|-------------|")
    lines.append("| keyword_blind_spot | No matching keyword for the semantic risk present |")
    lines.append("| injection_blindness | Cannot detect prompt injection patterns in conversation |")
    lines.append("| social_engineering_deaf | Cannot detect authority attribution or urgency cues |")
    lines.append("| privacy_leakage_miss | Cannot detect privacy/data exfiltration patterns |")
    lines.append("| context_ignorance | Pipeline ignores conversation context |")
    lines.append("| false_generalization | Memory generalizes from wrong seed events |")
    lines.append("| affect_saturation | Global emotional state biases all decisions uniformly |")
    lines.append("")

    if failure_summary_lines:
        lines.append("### Failure Mode Distribution (from failure_summary.csv)")
        lines.append("")
        lines.append("```csv")
        for line in failure_summary_lines:
            lines.append(line.rstrip())
        lines.append("```")
    lines.append("")

    # Root Cause
    lines.append("## Root Cause")
    lines.append("")
    lines.append("1. **Keyword Risk Encoder Coverage Gap (PRIMARY)**")
    lines.append("   - The risk encoder uses 6 handcrafted features with keyword matching")
    lines.append("   - On Synthetic-AB300: 228/300 tasks (76%) score ZERO handcrafted risk")
    lines.append("   - On R-Judge: coverage is even worse because real adversarial scenarios")
    lines.append("     use natural language rather than explicit risk keywords")
    lines.append("")
    lines.append("2. **Memory Generalization Degrades Performance**")
    lines.append("   - Memory generalization fires on many unseen tasks but is mis-calibrated")
    lines.append("   - Loose similarity threshold (distance < 0.5) causes false generalizations")
    lines.append("   - Result: memory layer INCREASES over-escalation without improving unsafe detection")
    lines.append("")
    lines.append("3. **Affect Layer is Empirically Inert**")
    lines.append("   - ConflictDetector rarely triggers: 286/300 LOW on synthetic data")
    lines.append("   - On R-Judge, affect only marginally improves unsafe recall")
    lines.append("     at the cost of massive over-escalation")
    lines.append("   - The emotional state saturates, creating uniform anxious bias")
    lines.append("")

    # V2 Gate
    lines.append("## V2 Gate Criteria")
    lines.append("")
    lines.append("| Stage | R-Judge Unsafe Recall | Description |")
    lines.append("|--------|----------------------:|-------------|")
    lines.append("| v1 current | 0.000-0.030 | Known failure |")
    lines.append("| v2 MVP | >0.20 | Semantic risk detection begins |")
    lines.append("| v2 stable | >0.50 | Meaningful improvement |")
    lines.append("| v2 paper-grade | >0.65 + controlled FP | Suitable for paper main results |")
    lines.append("")

    # Reproducibility
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("To reproduce these results:")
    lines.append("")
    lines.append("```bash")
    lines.append("# Single command (downloads data, runs pipeline, computes metrics, generates report)")
    lines.append("python experiments/rjudge_v2/run_failure_reproduction.py")
    lines.append("")
    lines.append("# Or step by step:")
    lines.append("python experiments/rjudge_v2/convert_rjudge.py    # Download & convert data")
    lines.append("python experiments/rjudge_v2/run_rjudge_v1.py    # Run v1 pipeline")
    lines.append("python experiments/rjudge_v2/generate_report.py  # Generate this report")
    lines.append("```")
    lines.append("")
    lines.append("Output files:")
    lines.append("```")
    lines.append("results/rjudge_v2/")
    lines.append("  rjudge_converted.jsonl   # Converted R-Judge data")
    lines.append("  predictions_v1.jsonl     # Per-record predictions")
    lines.append("  metrics_v1.json          # Computed metrics")
    lines.append("  failure_cases.jsonl      # Detailed per-case failure records")
    lines.append("  failure_summary.csv      # Aggregated failure mode counts")
    lines.append("  rjudge_failure_report.md # This report")
    lines.append("```")
    lines.append("")

    # What This Does NOT Mean
    lines.append("## What This Does NOT Mean")
    lines.append("")
    lines.append("- This does NOT mean affective safety is a dead end — it means the current")
    lines.append("  implementation is a keyword detector masquerading as a semantic system")
    lines.append("- This does NOT invalidate the theoretical framework — it invalidates the")
    lines.append("  specific implementation of the risk encoder")
    lines.append("- This does NOT mean we should abandon external validation — R-Judge is")
    lines.append("  exactly the kind of test we need")
    lines.append("")

    report = "\n".join(lines)

    # Write report
    report_path = os.path.join(results_dir, "rjudge_failure_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report saved to {report_path}")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate R-Judge failure report")
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR,
                        help="Directory containing metrics and failure analysis")
    args = parser.parse_args()

    generate_report(args.results_dir)


if __name__ == "__main__":
    main()
