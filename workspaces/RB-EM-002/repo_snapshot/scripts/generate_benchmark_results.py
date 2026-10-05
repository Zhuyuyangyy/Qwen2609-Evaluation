"""
V0.6 Benchmark Audit - Generate results files
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from emotion_agent import AffectiveBenchmark


def generate_benchmark_results():
    """Generate benchmark results for all baselines."""
    benchmark = AffectiveBenchmark(seed=42)
    
    class DummyAgent:
        pass
    
    baselines = ["plain", "memory", "risk", "full"]
    all_results = {}
    
    for baseline in baselines:
        results = benchmark.run_benchmark(DummyAgent(), baseline)
        metrics = benchmark.calculate_metrics(results)
        
        all_results[baseline] = {
            "risky_auto_execution_rate": metrics.risky_auto_execution_rate,
            "verification_appropriateness": metrics.verification_appropriateness,
            "trust_calibration_error": metrics.trust_calibration_error,
            "recovery_quality": metrics.recovery_quality,
            "generalization_precision": metrics.generalization_precision,
            "false_over_caution_rate": metrics.false_over_caution_rate,
            "task_success_rate": metrics.task_success_rate
        }
    
    # Save JSON
    with open("docs/demo_evidence_v0.8/benchmark_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    
    # Generate markdown table
    table_lines = [
        "| Method | Risky Auto-Exec ↓ | Verification ↑ | Trust Error ↓ | Recovery ↑ | Gen Precision ↑ | False Caution ↓ | Success ↑ |",
        "|--------|-------------------|-----------------|---------------|------------|-----------------|----------------|----------|"
    ]
    
    for baseline, metrics in all_results.items():
        table_lines.append(
            f"| {baseline} | {metrics['risky_auto_execution_rate']:.3f} | "
            f"{metrics['verification_appropriateness']:.3f} | {metrics['trust_calibration_error']:.3f} | "
            f"{metrics['recovery_quality']:.3f} | {metrics['generalization_precision']:.3f} | "
            f"{metrics['false_over_caution_rate']:.3f} | {metrics['task_success_rate']:.3f} |"
        )
    
    with open("docs/demo_evidence_v0.8/benchmark_table.md", "w") as f:
        f.write("\n".join(table_lines))
    
    print("Benchmark results generated successfully!")


if __name__ == "__main__":
    generate_benchmark_results()
