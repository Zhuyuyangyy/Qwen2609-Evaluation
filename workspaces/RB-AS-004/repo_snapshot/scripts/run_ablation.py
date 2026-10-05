"""Ablation study for AgentShield V3 chain-aware governance.

Compares incrementally-degraded versions of the full chain-aware predictor
against baselines on both the SCI-600 synthetic dataset and the V3.1
semi-real trace benchmark. Produces publication-ready CSV and JSON reports.

Component ablation (successively disabled):
  0  Full AgentShield chain-aware  (baseline for delta rows)
  1  − chain-stage boost
  2  − category × chain_id boost
  3  − external-transfer + sensitive-field boost
  4  − audit/evasion boosts
  5  − review-marker + special-case rules
  6  − all chain metadata (equivalent to Local context)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ROOT = Path(__file__).resolve().parent.parent / "benchmark"
sys.path.insert(0, str(ROOT))

from baselines import BASELINES, action_for_score, clamp, flatten_text, load_cases

LABELS = ["ALLOW", "HUMAN_REVIEW", "BLOCK"]

# ── Ablation components ──────────────────────────────────────────────────────

CATEGORY_PRIORS = {
    "sensitive_data_access": 0.48,
    "external_network_transfer": 0.50,
    "bulk_operations": 0.46,
    "privilege_escalation": 0.62,
    "behavior_chain_risk": 0.54,
    "governance_bypass": 0.58,
}

CHAIN_STAGE_BOOST = {
    "recon": 0.03,
    "collect": 0.09,
    "stage": 0.14,
    "exfiltrate": 0.26,
    "single_call": 0.0,
}

HIGH_RISK_TERMS = {
    "admin": 0.22, "audit": 0.16, "base64": 0.14, "callback": 0.14,
    "compress": 0.10, "credential": 0.24, "delete": 0.28, "disable": 0.24,
    "email": 0.13, "external": 0.24, "export": 0.18, "grant": 0.24,
    "hidden": 0.18, "id_card": 0.20, "medical": 0.22, "password": 0.24,
    "payload": 0.12, "phone": 0.14, "root": 0.28, "salary": 0.17,
    "send": 0.12, "token": 0.24, "upload": 0.16, "users": 0.14,
}


def keyword_score(text: str, cap: float = 0.45) -> float:
    lower = text.lower()
    score = 0.0
    for term, weight in HIGH_RISK_TERMS.items():
        if term in lower:
            score += weight
    return min(cap, score)


def row_intensity(case: Dict[str, Any]) -> float:
    params = case.get("tool_input", {})
    rows = int(params.get("rows", 0) or 0)
    bytes_out = int(params.get("bytes", 0) or 0)
    if rows >= 10000 or bytes_out >= 250000:
        return 0.22
    if rows >= 1000 or bytes_out >= 50000:
        return 0.12
    return 0.0


def risk_local_context(case: Dict[str, Any]) -> float:
    category = case.get("category", "")
    text = f"{case.get('tool_name', '')} {flatten_text(case.get('tool_input', {}))}"
    prior = CATEGORY_PRIORS.get(category, 0.42)
    return clamp(prior + keyword_score(text, cap=0.38) + row_intensity(case))


# Full chain-aware (component 0)
def risk_chain_aware_full(case: Dict[str, Any]) -> float:
    score = risk_local_context(case)
    category = case.get("category", "")
    stage = str(case.get("attack_stage", "single_call")).lower()
    chain_id = str(case.get("chain_id", ""))
    step_index = int(case.get("step_index", 0) or 0)

    # Component A: chain-stage boost
    score += CHAIN_STAGE_BOOST.get(stage, 0.0)

    # Component B: category × chain boost
    if category in {"behavior_chain_risk", "governance_bypass"} and chain_id:
        score += 0.04 + 0.03 * min(step_index, 3)

    text = flatten_text(case.get("tool_input", {})).lower()

    # Component C: external transfer + sensitive fields
    if "external" in text and any(t in text for t in ["phone", "email", "salary", "id_card"]):
        score += 0.14

    # Component D: audit/evasion boosts
    if "password_hash" in text or "audit evasion" in text:
        score += 0.18
    if "disable audit" in text or "log tampering" in text:
        score += 0.14

    # Component E: special-case downweights
    if "temporary support role" in text:
        score -= 0.12
    if stage == "single_call" and category == "governance_bypass":
        score -= 0.20
    if "reader" in text and category == "privilege_escalation":
        score -= 0.24
    if "public" in text and "external" not in text:
        score -= 0.12

    # Component F: review-marker / special-case caps
    review_markers = [
        "pending compliance review",
        "unusual callback metadata",
        "temporary support role",
        "stage local file",
        "status='archived'",
    ]
    if any(marker in text for marker in review_markers):
        score = min(score, 0.84)
    if category == "sensitive_data_access" and text.count(",") <= 1 and "password_hash" not in text:
        score = min(score, 0.84)

    return clamp(score)


# Ablation: disable component A (chain-stage boost)
def risk_ablate_stage(case: Dict[str, Any]) -> float:
    score = risk_local_context(case)
    category = case.get("category", "")
    chain_id = str(case.get("chain_id", ""))
    step_index = int(case.get("step_index", 0) or 0)
    # stage boost disabled
    if category in {"behavior_chain_risk", "governance_bypass"} and chain_id:
        score += 0.04 + 0.03 * min(step_index, 3)
    text = flatten_text(case.get("tool_input", {})).lower()
    if "external" in text and any(t in text for t in ["phone", "email", "salary", "id_card"]):
        score += 0.14
    if "password_hash" in text or "audit evasion" in text:
        score += 0.18
    if "disable audit" in text or "log tampering" in text:
        score += 0.14
    if "temporary support role" in text:
        score -= 0.12
    if category == "governance_bypass":
        score -= 0.20
    if "reader" in text and category == "privilege_escalation":
        score -= 0.24
    if "public" in text and "external" not in text:
        score -= 0.12
    review_markers = ["pending compliance review", "unusual callback metadata",
                      "temporary support role", "stage local file", "status='archived'"]
    if any(m in text for m in review_markers):
        score = min(score, 0.84)
    if category == "sensitive_data_access" and text.count(",") <= 1 and "password_hash" not in text:
        score = min(score, 0.84)
    return clamp(score)


# Ablation: disable component B (category × chain boost)
def risk_ablate_category_chain(case: Dict[str, Any]) -> float:
    score = risk_local_context(case)
    category = case.get("category", "")
    stage = str(case.get("attack_stage", "single_call")).lower()
    score += CHAIN_STAGE_BOOST.get(stage, 0.0)
    # category × chain_id boost disabled
    text = flatten_text(case.get("tool_input", {})).lower()
    if "external" in text and any(t in text for t in ["phone", "email", "salary", "id_card"]):
        score += 0.14
    if "password_hash" in text or "audit evasion" in text:
        score += 0.18
    if "disable audit" in text or "log tampering" in text:
        score += 0.14
    if "temporary support role" in text:
        score -= 0.12
    if stage == "single_call" and category == "governance_bypass":
        score -= 0.20
    if "reader" in text and category == "privilege_escalation":
        score -= 0.24
    if "public" in text and "external" not in text:
        score -= 0.12
    review_markers = ["pending compliance review", "unusual callback metadata",
                      "temporary support role", "stage local file", "status='archived'"]
    if any(m in text for m in review_markers):
        score = min(score, 0.84)
    if category == "sensitive_data_access" and text.count(",") <= 1 and "password_hash" not in text:
        score = min(score, 0.84)
    return clamp(score)


# Ablation: disable component C (external transfer boost)
def risk_ablate_external(case: Dict[str, Any]) -> float:
    score = risk_local_context(case)
    category = case.get("category", "")
    stage = str(case.get("attack_stage", "single_call")).lower()
    chain_id = str(case.get("chain_id", ""))
    step_index = int(case.get("step_index", 0) or 0)
    score += CHAIN_STAGE_BOOST.get(stage, 0.0)
    if category in {"behavior_chain_risk", "governance_bypass"} and chain_id:
        score += 0.04 + 0.03 * min(step_index, 3)
    text = flatten_text(case.get("tool_input", {})).lower()
    # external transfer boost disabled
    if "password_hash" in text or "audit evasion" in text:
        score += 0.18
    if "disable audit" in text or "log tampering" in text:
        score += 0.14
    if "temporary support role" in text:
        score -= 0.12
    if stage == "single_call" and category == "governance_bypass":
        score -= 0.20
    if "reader" in text and category == "privilege_escalation":
        score -= 0.24
    if "public" in text and "external" not in text:
        score -= 0.12
    review_markers = ["pending compliance review", "unusual callback metadata",
                      "temporary support role", "stage local file", "status='archived'"]
    if any(m in text for m in review_markers):
        score = min(score, 0.84)
    if category == "sensitive_data_access" and text.count(",") <= 1 and "password_hash" not in text:
        score = min(score, 0.84)
    return clamp(score)


# Ablation: disable component D (audit/evasion boosts)
def risk_ablate_audit(case: Dict[str, Any]) -> float:
    score = risk_local_context(case)
    category = case.get("category", "")
    stage = str(case.get("attack_stage", "single_call")).lower()
    chain_id = str(case.get("chain_id", ""))
    step_index = int(case.get("step_index", 0) or 0)
    score += CHAIN_STAGE_BOOST.get(stage, 0.0)
    if category in {"behavior_chain_risk", "governance_bypass"} and chain_id:
        score += 0.04 + 0.03 * min(step_index, 3)
    text = flatten_text(case.get("tool_input", {})).lower()
    if "external" in text and any(t in text for t in ["phone", "email", "salary", "id_card"]):
        score += 0.14
    # audit/evasion boosts disabled
    if "temporary support role" in text:
        score -= 0.12
    if stage == "single_call" and category == "governance_bypass":
        score -= 0.20
    if "reader" in text and category == "privilege_escalation":
        score -= 0.24
    if "public" in text and "external" not in text:
        score -= 0.12
    review_markers = ["pending compliance review", "unusual callback metadata",
                      "temporary support role", "stage local file", "status='archived'"]
    if any(m in text for m in review_markers):
        score = min(score, 0.84)
    if category == "sensitive_data_access" and text.count(",") <= 1 and "password_hash" not in text:
        score = min(score, 0.84)
    return clamp(score)


# Ablation: disable component E+F (all special-case rules, keep A–D)
def risk_ablate_special_cases(case: Dict[str, Any]) -> float:
    score = risk_local_context(case)
    category = case.get("category", "")
    stage = str(case.get("attack_stage", "single_call")).lower()
    chain_id = str(case.get("chain_id", ""))
    step_index = int(case.get("step_index", 0) or 0)
    score += CHAIN_STAGE_BOOST.get(stage, 0.0)
    if category in {"behavior_chain_risk", "governance_bypass"} and chain_id:
        score += 0.04 + 0.03 * min(step_index, 3)
    text = flatten_text(case.get("tool_input", {})).lower()
    if "external" in text and any(t in text for t in ["phone", "email", "salary", "id_card"]):
        score += 0.14
    if "password_hash" in text or "audit evasion" in text:
        score += 0.18
    if "disable audit" in text or "log tampering" in text:
        score += 0.14
    # all special-case rules disabled
    return clamp(score)


ABLATIONS = [
    ("0  Full AgentShield",                risk_chain_aware_full),
    ("1  −stage boost",                    risk_ablate_stage),
    ("2  −category×chain boost",            risk_ablate_category_chain),
    ("3  −external+sensitive boost",       risk_ablate_external),
    ("4  −audit/evasion boosts",           risk_ablate_audit),
    ("5  −special-case rules",             risk_ablate_special_cases),
    ("6  Local context (all chain)",       risk_local_context),
]


# ── Evaluation ───────────────────────────────────────────────────────────────

def precision_recall_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def evaluate(name: str, predictor, cases: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    start = time.perf_counter()
    confusion: Dict[str, Counter[str]] = {l: Counter() for l in LABELS}
    score_errors = []
    rows = []

    for case in cases:
        expected = case.get("expected_action", "ALLOW")
        expected_score = float(case.get("expected_risk_score", 0.0))
        score = predictor(case)
        action = action_for_score(score)
        rows.append({
            "id": case.get("id"),
            "expected_action": expected,
            "predicted_action": action,
            "expected_score": round(expected_score, 3),
            "predicted_score": round(score, 3),
        })
        confusion[expected][action] += 1
        score_errors.append(abs(score - expected_score))

    elapsed = time.perf_counter() - start
    total = len(rows)
    correct = sum(1 for r in rows if r["expected_action"] == r["predicted_action"])

    f1_values = []
    per_label = {}
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[o][label] for o in LABELS if o != label)
        fn = sum(confusion[label][o] for o in LABELS if o != label)
        p, r, f = precision_recall_f1(tp, fp, fn)
        per_label[label] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)}
        f1_values.append(f)

    block_total = sum(confusion["BLOCK"].values())
    allow_total = sum(confusion["ALLOW"].values())
    false_allow = confusion["BLOCK"]["ALLOW"] / block_total if block_total else 0.0
    false_block = confusion["ALLOW"]["BLOCK"] / allow_total if allow_total else 0.0
    review_rate = sum(1 for r in rows if r["predicted_action"] == "HUMAN_REVIEW") / total if total else 0.0

    return {
        "name": name,
        "total": total,
        "action_accuracy": round(correct / total if total else 0.0, 4),
        "macro_f1": round(sum(f1_values) / len(f1_values), 4),
        "block_recall": per_label["BLOCK"]["recall"],
        "false_allow_rate": round(false_allow, 4),
        "false_block_rate": round(false_block, 4),
        "human_review_rate": round(review_rate, 4),
        "mean_absolute_score_error": round(sum(score_errors) / total if total else math.nan, 4),
        "runtime_ms_per_case": round(1000 * elapsed / total if total else 0.0, 4),
        "per_label": per_label,
    }


# ── Semi-real trace flattening ────────────────────────────────────────────────

def load_semireal_traces(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for trace in data:
        critical_step = trace.get("critical_step", 0)
        steps = trace.get("steps", [])
        selected = next((s for s in steps if s.get("step") == critical_step), steps[-1])
        chain_label = trace["chain_label"]
        score = {"ALLOW": 0.35, "HUMAN_REVIEW": 0.76, "BLOCK": 0.94}[chain_label]
        if selected.get("local_risk_score", 0.0) > score:
            score = selected["local_risk_score"]
        tool = selected.get("tool_name", "")
        scenario = trace.get("scenario_type", "")
        if tool in {"http_request", "send_email"}:
            stage = "exfiltrate"
        elif tool in {"file_write", "compress_file", "export_csv"} or "bypass" in scenario:
            stage = "stage"
        else:
            stage = "collect" if selected.get("local_risk_score", 0.0) >= 0.60 else "single_call"
        cases.append({
            "id": trace["trace_id"],
            "category": selected.get("local_risk_type", trace["scenario_type"]),
            "description": trace["scenario_type"],
            "agent_id": selected.get("agent_id", ""),
            "tool_name": tool,
            "tool_input": selected.get("tool_input", {}),
            "expected_risk_score": round(min(1.0, float(score)), 3),
            "expected_action": chain_label,
            "chain_id": trace["trace_id"],
            "step_index": selected.get("step", 0),
            "attack_stage": stage,
            "v3_specific": True,
            "semi_realistic_trace": True,
        })
    return cases


# ── CSV / JSON report writers ─────────────────────────────────────────────────

def write_csv(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    baselines = report.get("baselines", report.get("ablation", []))
    rows = ["dataset,method,action_accuracy,macro_f1,block_recall,false_allow,false_block,human_review,mae,runtime_ms"]
    for item in baselines:
        rows.append(
            f"{report['dataset']},"
            f"{item['name']},"
            f"{item['action_accuracy']:.4f},"
            f"{item['macro_f1']:.4f},"
            f"{item['block_recall']:.4f},"
            f"{item['false_allow_rate']:.4f},"
            f"{item['false_block_rate']:.4f},"
            f"{item['human_review_rate']:.4f},"
            f"{item['mean_absolute_score_error']:.4f},"
            f"{item['runtime_ms_per_case']:.4f}"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_ablation_delta_csv(report: Dict[str, Any], path: Path) -> None:
    """Write delta-style CSV showing what each component contributes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["dataset,ablated_component,metric,full_value,ablated_value,delta,delta_pct"]
    full_item = report["ablation"][0]
    dataset = report["dataset"]

    for item in report["ablation"][1:]:
        name = item["name"]
        for metric in ["action_accuracy", "macro_f1", "block_recall", "false_allow_rate"]:
            fv = item[metric]
            av = full_item[metric]
            delta = round(fv - av, 4)
            pct = round(100 * delta / av if av else 0.0, 2)
            headers.append(f"{dataset},{name},{metric},{av:.4f},{fv:.4f},{delta:.4f},{pct}")

    path.write_text("\n".join(headers) + "\n", encoding="utf-8")


def run_sci(dataset: Path, json_out: Path, csv_out: Path, delta_csv: Path) -> Dict[str, Any]:
    cases = load_cases(dataset)
    full_result = evaluate("0  Full AgentShield", risk_chain_aware_full, cases)
    ablation_results = [evaluate(name, pred, cases) for name, pred in ABLATIONS[1:]]
    baselines_report = [evaluate(name, pred, cases) for name, pred in BASELINES.items()]

    report = {
        "dataset": str(dataset),
        "total_cases": len(cases),
        "labels": LABELS,
        "ablation": [full_result, *ablation_results],
        "baselines": baselines_report,
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report, csv_out)
    write_ablation_delta_csv(report, delta_csv)
    return report


def run_semireal(dataset: Path, json_out: Path, csv_out: Path, delta_csv: Path) -> Dict[str, Any]:
    cases = load_semireal_traces(dataset)
    full_result = evaluate("0  Full AgentShield", risk_chain_aware_full, cases)
    ablation_results = [evaluate(name, pred, cases) for name, pred in ABLATIONS[1:]]

    report = {
        "dataset": str(dataset),
        "total_cases": len(cases),
        "labels": LABELS,
        "ablation": [full_result, *ablation_results],
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report, csv_out)
    write_ablation_delta_csv(report, delta_csv)
    return report


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AgentShield V3 ablation study.")
    parser.add_argument("--dataset", choices=["sci", "semireal"], default="sci")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--csv-out", type=Path)
    parser.add_argument("--delta-csv", type=Path)
    args = parser.parse_args()

    if args.dataset == "sci":
        default_dataset = ROOT / "test_cases" / "test_cases_sci_600.json"
        default_json = ROOT / "results" / "ablation_sci_report.json"
        default_csv = ROOT / "results" / "ablation_sci_table.csv"
        default_delta = ROOT / "results" / "ablation_sci_deltas.csv"
    else:
        default_dataset = ROOT / "test_cases" / "test_cases_semireal_150.json"
        default_json = ROOT / "results" / "ablation_semireal_report.json"
        default_csv = ROOT / "results" / "ablation_semireal_table.csv"
        default_delta = ROOT / "results" / "ablation_semireal_deltas.csv"

    dataset = args.dataset      # already a string "sci" or "semireal"
    json_out = args.json_out or default_json
    csv_out = args.csv_out or default_csv
    delta_csv = args.delta_csv or default_delta

    if dataset == "sci":
        report = run_sci(default_dataset, json_out, csv_out, delta_csv)
    else:
        report = run_semireal(default_dataset, json_out, csv_out, delta_csv)

    print(f"Ablation study complete — {report['total_cases']} cases")
    print(f"JSON : {json_out}")
    print(f"CSV  : {csv_out}")
    print(f"Deltas: {delta_csv}")
    print()
    print(f"{'Method':<32} {'Acc':>6}  {'F1':>6}  {'BlockR':>7}  {'FA':>6}")
    print("-" * 65)
    for item in report["ablation"]:
        print(
            f"{item['name']:<32} "
            f"{item['action_accuracy']:>6.2%}  "
            f"{item['macro_f1']:>6.2%}  "
            f"{item['block_recall']:>7.2%}  "
            f"{item['false_allow_rate']:>6.2%}"
        )


if __name__ == "__main__":
    main()
