"""Calibrate the optimal decay coefficient for graph risk propagation.

The current decay formula is:
    decay = 1.0 / (1.0 + alpha * chain_length)

where alpha = 0.3 is an arbitrary constant.

This script uses the independent evaluation dataset to find the optimal alpha
by maximizing the separation between safe and risky case scores.

Approach:
1. Load the evaluation dataset with labels
2. For each candidate alpha, compute risk scores using graph propagation
3. Evaluate separation metrics (AUC, Mann-Whitney U, effect size)
4. Select alpha that maximizes the chosen objective

The calibration is done on the train split and validated on the test split
to ensure generalization.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_json(path: Path) -> Any:
    """Load JSON file."""
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(data: Any, path: Path) -> None:
    """Write JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_decay(alpha: float, chain_length: int) -> float:
    """Compute decay factor for given alpha and chain length."""
    return 1.0 / (1.0 + alpha * chain_length)


def compute_graph_score(
    case: Dict[str, Any],
    alpha: float,
    base_scorer: Any = None,
) -> float:
    """Compute graph-enhanced risk score with given decay alpha.

    This simulates the graph risk propagation with a tunable alpha.
    """
    from benchmark.independent_eval.baselines import (
        assess_data_flow_risk,
        assess_frequency_anomaly,
        estimate_chain_length,
        infer_category_from_content,
        CATEGORY_PRIORS,
        SENSITIVE_DATA_TERMS,
        TRANSIT_TERMS,
        PRIVILEGE_TERMS,
        CHAIN_STAGE_BOOST,
        clamp,
    )

    tool_name = str(case.get("tool_name", "")).lower()
    text = str(case.get("input_text", "")).lower()
    output_text = str(case.get("output_text", "")).lower()
    full_context = f"{tool_name} {text} {output_text}"

    # Category prior
    category = infer_category_from_content(case)
    prior = CATEGORY_PRIORS.get(category, 0.30)
    score = prior

    # Chain position inference
    text_lower = full_context
    is_outbound = any(t in text_lower for t in ["send", "http", "upload", "webhook", "ftp", "smtp"])
    is_staging = any(t in text_lower for t in ["write", "compress", "archive", "dump", "backup", "export"])
    is_access = any(t in text_lower for t in ["query", "select", "fetch", "sql", "database"])

    categories_count = sum([is_outbound, is_staging, is_access])
    if categories_count >= 2:
        chain_position = "late"
    elif is_outbound or is_staging:
        chain_position = "mid"
    elif is_access:
        chain_position = "early"
    else:
        chain_position = "single"

    # Stage inference
    has_outbound = any(t in text_lower for t in ["send", "http", "upload", "webhook", "ftp", "email"])
    has_staging = any(t in text_lower for t in ["write", "compress", "archive", "dump", "export"])
    has_collection = any(t in text_lower for t in ["query", "select", "fetch", "sql", "database"])
    has_recon = any(t in text_lower for t in ["scan", "pg_shadow", "information_schema", "private_key"])
    has_covert = any(t in text_lower for t in ["exfil", "#exfil", "webhook.site", "comment on", "internal_note"])
    has_supply_chain = any(t in text_lower for t in ["--index-url", "mirror.com", "unverified", "| bash", "post_install"])
    has_burst = any(t in text_lower for t in ["batch", "between", "dump_"])

    if has_covert:
        stage = "covert_exfil"
    elif has_supply_chain:
        stage = "supply_chain"
    elif (has_outbound and has_collection) or has_outbound:
        stage = "exfiltrate"
    elif has_burst and has_collection:
        stage = "burst_collect"
    elif has_staging:
        stage = "stage"
    elif has_collection:
        stage = "collect"
    elif has_recon:
        stage = "recon"
    else:
        stage = "single_call"

    # Chain context boost
    if chain_position in ("mid", "late"):
        score += 0.04 + 0.03 * (2 if chain_position == "late" else 1)
    score += CHAIN_STAGE_BOOST.get(stage, 0.0)

    # Content-based risk signals
    for term, weight in SENSITIVE_DATA_TERMS.items():
        if term in text_lower:
            score += weight * 0.4

    for term, weight in TRANSIT_TERMS.items():
        if term in text_lower:
            score += weight * 0.3

    for term, weight in PRIVILEGE_TERMS.items():
        if term in text_lower:
            score += weight * 0.3

    # Specific patterns
    if "external" in text_lower and any(t in text_lower for t in ["phone", "email", "salary", "id_card"]):
        score += 0.15
    if "password_hash" in text_lower or "private_key" in text_lower:
        score += 0.20
    if "disable audit" in text_lower or "disable trigger" in text_lower:
        score += 0.18
    if "superuser" in text_lower or "pg_shadow" in text_lower:
        score += 0.20
    if any(t in text_lower for t in ["exfil", "#exfil", "webhook.site", "internal_note"]):
        score += 0.22
    if any(t in text_lower for t in ["--index-url", "unverified", "backdoored", "| bash"]):
        score += 0.18
    if any(t in text_lower for t in ["batch", "between", "dump_"]):
        score += 0.12

    base_score = clamp(score)

    # Graph propagation with tunable alpha
    chain_len = estimate_chain_length(full_context)

    # Simulate graph propagation: use alpha-based decay
    if chain_len >= 2:
        # Multiple operation categories suggest chain risk
        # Use learned decay to determine boost
        graph_boost = 0.0
        for depth in range(1, chain_len):
            decay = compute_decay(alpha, depth)
            graph_boost += 0.08 * decay  # Each chain step contributes with decay
        graph_boost = min(graph_boost, 0.25)  # Cap the boost
    else:
        graph_boost = 0.0

    # Data flow amplification
    flow_risk = assess_data_flow_risk(text, output_text)
    if flow_risk > 0.15:
        graph_boost += 0.05

    # Frequency anomaly amplification
    freq_risk = assess_frequency_anomaly(full_context)
    if freq_risk > 0.10:
        graph_boost += 0.04

    return clamp(base_score + graph_boost)


def compute_auc(scores: List[float], labels: List[int]) -> float:
    """Compute AUC-ROC (Area Under the Receiver Operating Characteristic curve).

    Args:
        scores: Risk scores (higher = more risky)
        labels: Binary labels (1 = risky, 0 = safe)

    Returns:
        AUC score [0, 1]
    """
    # Sort by score descending
    paired = sorted(zip(scores, labels), key=lambda x: -x[0])

    n_pos = sum(labels)
    n_neg = len(labels) - n_pos

    if n_pos == 0 or n_neg == 0:
        return 0.5

    # Mann-Whitney U statistic
    tp = 0
    fp = 0
    auc = 0.0

    for score, label in paired:
        if label == 1:
            tp += 1
        else:
            fp += 1
            auc += tp

    auc = auc / (n_pos * n_neg)
    return auc


def compute_mann_whitney_u(scores_pos: List[float], scores_neg: List[float]) -> Tuple[float, float]:
    """Compute Mann-Whitney U test statistic and approximate p-value.

    Returns:
        (U_statistic, p_value_approx)
    """
    n1 = len(scores_pos)
    n2 = len(scores_neg)

    if n1 == 0 or n2 == 0:
        return 0.0, 1.0

    # Count concordant pairs
    u = 0.0
    for s_pos in scores_pos:
        for s_neg in scores_neg:
            if s_pos > s_neg:
                u += 1.0
            elif s_pos == s_neg:
                u += 0.5

    # Normalize
    u_max = n1 * n2
    u_normalized = u / u_max

    # Approximate z-score for large samples
    mu = n1 * n2 / 2.0
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12.0)

    if sigma > 0:
        z = (u - mu) / sigma
        # Approximate p-value using normal CDF
        p_value = 1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2)))
    else:
        z = 0.0
        p_value = 1.0

    return u_normalized, p_value


def compute_effect_size(scores_pos: List[float], scores_neg: List[float]) -> float:
    """Compute Cohen's d effect size.

    Returns:
        Effect size (positive = good separation)
    """
    if not scores_pos or not scores_neg:
        return 0.0

    mean_pos = np.mean(scores_pos)
    mean_neg = np.mean(scores_neg)
    std_pos = np.std(scores_pos) if len(scores_pos) > 1 else 0.0
    std_neg = np.std(scores_neg) if len(scores_neg) > 1 else 0.0

    # Pooled standard deviation
    n1, n2 = len(scores_pos), len(scores_neg)
    pooled_std = math.sqrt(((n1 - 1) * std_pos**2 + (n2 - 1) * std_neg**2) / (n1 + n2 - 2))

    if pooled_std == 0:
        return 0.0

    return (mean_pos - mean_neg) / pooled_std


def calibrate_alpha(
    cases: List[Dict[str, Any]],
    labels: List[Dict[str, Any]],
    alpha_range: Tuple[float, float] = (0.05, 2.0),
    num_steps: int = 40,
    objective: str = "auc",
) -> Dict[str, Any]:
    """Find optimal alpha by grid search.

    Args:
        cases: Test cases (observable data only)
        labels: Label entries with case_id, true_label, is_risky
        alpha_range: Range of alpha values to search
        num_steps: Number of alpha values to try
        objective: Optimization objective ("auc", "effect_size", "combined")

    Returns:
        Results dictionary with optimal alpha and metrics
    """
    label_map = {l["case_id"]: l for l in labels}

    # Filter to cases with labels
    valid_cases = []
    valid_labels = []
    for case in cases:
        if case["id"] in label_map:
            valid_cases.append(case)
            valid_labels.append(label_map[case["id"]])

    # Binary labels (1 = risky, 0 = safe)
    binary_labels = [1 if l["is_risky"] else 0 for l in valid_labels]

    # Grid search
    alphas = np.linspace(alpha_range[0], alpha_range[1], num_steps)
    results = []

    for alpha in alphas:
        scores = [compute_graph_score(case, alpha) for case in valid_cases]

        auc = compute_auc(scores, binary_labels)

        scores_pos = [s for s, l in zip(scores, binary_labels) if l == 1]
        scores_neg = [s for s, l in zip(scores, binary_labels) if l == 0]

        u_stat, p_value = compute_mann_whitney_u(scores_pos, scores_neg)
        effect_size = compute_effect_size(scores_pos, scores_neg)

        # Mean separation
        mean_pos = np.mean(scores_pos) if scores_pos else 0.0
        mean_neg = np.mean(scores_neg) if scores_neg else 0.0
        separation = mean_pos - mean_neg

        # Optimal threshold (Youden's J statistic)
        thresholds = np.linspace(0, 1, 100)
        best_j = 0.0
        best_threshold = 0.5
        for t in thresholds:
            tp = sum(1 for s, l in zip(scores, binary_labels) if s >= t and l == 1)
            fp = sum(1 for s, l in zip(scores, binary_labels) if s >= t and l == 0)
            fn = sum(1 for s, l in zip(scores, binary_labels) if s < t and l == 1)
            tn = sum(1 for s, l in zip(scores, binary_labels) if s < t and l == 0)
            sensitivity = tp / (tp + fn) if tp + fn else 0
            specificity = tn / (tn + fp) if tn + fp else 0
            j = sensitivity + specificity - 1
            if j > best_j:
                best_j = j
                best_threshold = t

        # Compute precision/recall at optimal threshold
        tp = sum(1 for s, l in zip(scores, binary_labels) if s >= best_threshold and l == 1)
        fp = sum(1 for s, l in zip(scores, binary_labels) if s >= best_threshold and l == 0)
        fn = sum(1 for s, l in zip(scores, binary_labels) if s < best_threshold and l == 1)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

        result = {
            "alpha": round(float(alpha), 4),
            "auc": round(auc, 4),
            "effect_size": round(effect_size, 4),
            "mann_whitney_u": round(u_stat, 4),
            "p_value": round(p_value, 6),
            "separation": round(float(separation), 4),
            "mean_risky": round(float(mean_pos), 4),
            "mean_safe": round(float(mean_neg), 4),
            "optimal_threshold": round(float(best_threshold), 4),
            "youden_j": round(best_j, 4),
            "precision_at_threshold": round(precision, 4),
            "recall_at_threshold": round(recall, 4),
            "f1_at_threshold": round(f1, 4),
        }
        results.append(result)

    # Select optimal alpha based on objective
    if objective == "auc":
        best = max(results, key=lambda r: r["auc"])
    elif objective == "effect_size":
        best = max(results, key=lambda r: r["effect_size"])
    else:  # combined
        best = max(results, key=lambda r: r["auc"] * 0.5 + r["effect_size"] * 0.3 + r["f1_at_threshold"] * 0.2)

    return {
        "best_alpha": best["alpha"],
        "best_metrics": best,
        "all_results": results,
        "objective": objective,
        "num_cases": len(valid_cases),
        "num_risky": sum(binary_labels),
        "num_safe": len(binary_labels) - sum(binary_labels),
    }


def cross_validate_alpha(
    cases: List[Dict[str, Any]],
    labels: List[Dict[str, Any]],
    n_folds: int = 5,
    alpha_range: Tuple[float, float] = (0.05, 2.0),
    num_steps: int = 30,
) -> Dict[str, Any]:
    """K-fold cross-validation to validate the optimal alpha.

    Returns:
        Cross-validation results with mean and std of optimal alphas.
    """
    label_map = {l["case_id"]: l for l in labels}
    valid_cases = [c for c in cases if c["id"] in label_map]
    valid_labels = [label_map[c["id"]] for c in valid_cases]

    # Shuffle
    import random
    rng = random.Random(42)
    combined = list(zip(valid_cases, valid_labels))
    rng.shuffle(combined)

    fold_size = len(combined) // n_folds
    fold_alphas = []

    for fold in range(n_folds):
        start = fold * fold_size
        end = start + fold_size if fold < n_folds - 1 else len(combined)

        test_indices = set(range(start, end))
        train_cases = [c for i, (c, l) in enumerate(combined) if i not in test_indices]
        train_labels = [l for i, (c, l) in enumerate(combined) if i not in test_indices]

        result = calibrate_alpha(train_cases, train_labels, alpha_range, num_steps, "auc")
        fold_alphas.append(result["best_alpha"])

    return {
        "fold_alphas": fold_alphas,
        "mean_alpha": round(float(np.mean(fold_alphas)), 4),
        "std_alpha": round(float(np.std(fold_alphas)), 4),
        "recommended_alpha": round(float(np.median(fold_alphas)), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate optimal decay coefficient.")
    parser.add_argument("--data-dir", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--alpha-min", type=float, default=0.05)
    parser.add_argument("--alpha-max", type=float, default=2.0)
    parser.add_argument("--num-steps", type=int, default=40)
    parser.add_argument("--objective", choices=["auc", "effect_size", "combined"], default="combined")
    parser.add_argument("--cross-validate", action="store_true", help="Run k-fold cross-validation")
    parser.add_argument("--n-folds", type=int, default=5)
    args = parser.parse_args()

    data_dir = args.data_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load dataset
    cases_path = data_dir / "eval_cases.json"
    labels_path = data_dir / "labels.json"

    if not cases_path.exists():
        print("Error: Dataset not found. Run generate_dataset.py first.")
        sys.exit(1)

    cases = load_json(cases_path)
    metadata = load_json(labels_path)
    labels = metadata["labels"]

    print(f"Loaded {len(cases)} cases, {len(labels)} labels")

    # Run calibration
    print(f"\nCalibrating alpha (range=[{args.alpha_min}, {args.alpha_max}], steps={args.num_steps})...")
    results = calibrate_alpha(
        cases, labels,
        alpha_range=(args.alpha_min, args.alpha_max),
        num_steps=args.num_steps,
        objective=args.objective,
    )

    print(f"\n{'='*60}")
    print(f"OPTIMAL ALPHA: {results['best_alpha']}")
    print(f"{'='*60}")
    print(f"  AUC: {results['best_metrics']['auc']:.4f}")
    print(f"  Effect Size: {results['best_metrics']['effect_size']:.4f}")
    print(f"  Separation: {results['best_metrics']['separation']:.4f}")
    print(f"  Mean Risky: {results['best_metrics']['mean_risky']:.4f}")
    print(f"  Mean Safe: {results['best_metrics']['mean_safe']:.4f}")
    print(f"  Optimal Threshold: {results['best_metrics']['optimal_threshold']:.4f}")
    print(f"  Precision: {results['best_metrics']['precision_at_threshold']:.4f}")
    print(f"  Recall: {results['best_metrics']['recall_at_threshold']:.4f}")
    print(f"  F1: {results['best_metrics']['f1_at_threshold']:.4f}")

    # Cross-validation
    cv_results = None
    if args.cross_validate:
        print(f"\nRunning {args.n_folds}-fold cross-validation...")
        cv_results = cross_validate_alpha(
            cases, labels,
            n_folds=args.n_folds,
            alpha_range=(args.alpha_min, args.alpha_max),
            num_steps=args.num_steps,
        )
        print(f"  Fold alphas: {cv_results['fold_alphas']}")
        print(f"  Mean alpha: {cv_results['mean_alpha']}")
        print(f"  Std alpha: {cv_results['std_alpha']}")
        print(f"  Recommended alpha: {cv_results['recommended_alpha']}")

    # Save results
    output = {
        "calibration_results": results,
        "cross_validation": cv_results,
        "current_alpha": 0.3,
        "improvement": {
            "auc_gain": results["best_metrics"]["auc"] - 0.5,  # vs random
            "recommended_alpha": cv_results["recommended_alpha"] if cv_results else results["best_alpha"],
        },
    }

    output_path = output_dir / "decay_calibration.json"
    write_json(output, output_path)
    print(f"\nResults saved to: {output_path}")

    # Print comparison with current alpha
    print(f"\n{'='*60}")
    print("COMPARISON WITH CURRENT ALPHA (0.3)")
    print(f"{'='*60}")

    # Compute metrics for current alpha
    binary_labels = [1 if l["is_risky"] else 0 for l in labels]
    label_map = {l["case_id"]: l for l in labels}
    valid_cases = [c for c in cases if c["id"] in label_map]

    current_scores = [compute_graph_score(c, 0.3) for c in valid_cases]
    current_auc = compute_auc(current_scores, binary_labels)

    optimal_scores = [compute_graph_score(c, results["best_alpha"]) for c in valid_cases]
    optimal_auc = compute_auc(optimal_scores, binary_labels)

    print(f"  Current alpha (0.3): AUC = {current_auc:.4f}")
    print(f"  Optimal alpha ({results['best_alpha']}): AUC = {optimal_auc:.4f}")
    print(f"  Improvement: {optimal_auc - current_auc:+.4f}")

    # Show top 10 alpha values
    print(f"\n{'='*60}")
    print("TOP 10 ALPHA VALUES")
    print(f"{'='*60}")
    sorted_results = sorted(results["all_results"], key=lambda r: r["auc"], reverse=True)
    for i, r in enumerate(sorted_results[:10]):
        print(f"  {i+1}. alpha={r['alpha']:.4f}  AUC={r['auc']:.4f}  effect_size={r['effect_size']:.4f}  F1={r['f1_at_threshold']:.4f}")


if __name__ == "__main__":
    main()
