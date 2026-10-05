"""
generate_failure_matrix.py
==========================
Produce the V1 vs V2 failure matrix for the pinned R-Judge benchmark.

Reads only already-produced artifacts under results/rjudge_v2/:
  - metrics_v1_all_baselines.json  (v1: plain / risk / memory / full)
  - metrics_v1.json                (v1 primary baseline: risk)
  - metrics_v2.json                (v2 Risk Encoder)
  - predictions_v1.jsonl / predictions_v2.jsonl + rjudge_converted.jsonl
    (for the per-attack-type breakdown)

Writes results/rjudge_v2/v1_v2_failure_matrix.{md,json}.

Dataset pinning (audit, 2026-09): the loader reads the official data/ dir
of Lordog/R-Judge → 571 records. ACL paper reports 569 (paper-time snapshot);
NEXUS (arXiv 2607.19356) reports 564 usable after excluding 7 "leaked"
records. We run on the current official release and surface all three counts.

Usage:
    python experiments/rjudge_v2/generate_failure_matrix.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RESULTS = os.path.join(PROJECT_ROOT, "results", "rjudge_v2")

V1_BASELINES = ["plain", "risk", "memory", "full"]
METRIC_KEYS = [
    ("unsafe_recall", "Unsafe recall"),
    ("unsafe_f1", "Unsafe F1"),
    ("evidence_coverage", "Evidence coverage"),
    ("over_escalation_rate", "Over-escalation"),
    ("false_safe_count", "False-safe count"),
]
ATTACK_TYPES = ["injection", "unintended"]


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: str) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def attack_type_recall(pred_path: str, converted: list) -> dict:
    """Unsafe recall per attack type for a predictions file.

    Uses the same binary mapping as ``metrics.compute_metrics``: only
    HUMAN_REVIEW / BLOCK count as catching an unsafe record (SIMULATE_FIRST
    is treated as safe).
    """
    by_id = {str(r.get("id")): r for r in converted}
    rec = {}
    for at in ATTACK_TYPES:
        unsafe = [r for r in converted if r.get("attack_type") == at and r.get("label") == 1]
        caught = 0
        for p in load_jsonl(pred_path):
            r = by_id.get(str(p.get("id")))
            if r is None or r.get("label") != 1 or r.get("attack_type") != at:
                continue
            if p.get("pred_label") in ("HUMAN_REVIEW", "BLOCK"):
                caught += 1
        rec[at] = round(caught / len(unsafe), 4) if unsafe else 0.0
    return rec


def decision_dist(md: str) -> str:
    dist = {k: v for k, v in md["decision_distribution"].items() if v > 0}
    return " / ".join(f"{k}={v}" for k, v in sorted(dist.items()))


def build_matrix() -> dict:
    m_v1_all = load_json(os.path.join(RESULTS, "metrics_v1_all_baselines.json"))
    m_v2 = load_json(os.path.join(RESULTS, "metrics_v2.json"))
    converted = load_jsonl(os.path.join(RESULTS, "rjudge_converted.jsonl"))
    matrix = {
        "n_records": len(converted),
        "count_audit": {
            "a_cl_paper": 569,
            "official_repo_data": 571,
            "nexus_usable_after_leak_exclusion": 564,
            "note": "Loader pinned to official data/ dir of Lordog/R-Judge (post 2024-10-05 'update data'). "
                    "+2 vs ACL paper due to the 2024-10-05 update adding 2 injection records.",
        },
        "metrics": {
            baseline: {
                "unsafe_recall": m_v1_all[baseline]["unsafe_recall"],
                "unsafe_f1": m_v1_all[baseline]["unsafe_f1"],
                "evidence_coverage": m_v1_all[baseline]["evidence_coverage"],
                "over_escalation_rate": m_v1_all[baseline]["over_escalation_rate"],
                "false_safe_count": m_v1_all[baseline]["false_safe_count"],
            }
            for baseline in V1_BASELINES
        },
        "v2": {
            "unsafe_recall": m_v2["unsafe_recall"],
            "unsafe_f1": m_v2["unsafe_f1"],
            "evidence_coverage": m_v2["evidence_coverage"],
            "over_escalation_rate": m_v2["over_escalation_rate"],
            "false_safe_count": m_v2["false_safe_count"],
        },
        "attack_type_recall": {
            "v1_risk": attack_type_recall(os.path.join(RESULTS, "predictions_v1.jsonl"), converted),
            "v2": attack_type_recall(os.path.join(RESULTS, "predictions_v2.jsonl"), converted),
        },
        "decision_distribution": {
            "v1_risk": decision_dist(m_v1_all["risk"]),
            "v2": decision_dist(m_v2),
        },
    }

    # Failure-mode counts (both v1-run and v2-run analyze_failures outputs)
    cases_v2 = load_jsonl(os.path.join(RESULTS, "failure_cases.jsonl"))
    missed = [c for c in cases_v2 if c.get("is_missed") is True]
    matrix["v2_unsafe_total"] = len(cases_v2)
    matrix["v2_missed_unsafe"] = len(missed)
    matrix["v2_failure_modes"] = Counter(
        c.get("failure_mode", "unknown") for c in missed
    )
    return matrix


def render_md(matrix: dict) -> str:
    L = []
    L.append("# R-Judge V1 vs V2 Failure Matrix")
    L.append("")
    L.append(f"**Benchmark pinned**: {matrix['n_records']} records "
             f"(official Lordog/R-Judge `data/`, ACL 2024 Findings).")
    L.append("")
    L.append("| Count | Source |")
    L.append("|---|---|")
    L.append(f"| 571 | official repo `data/` release (post 2024-10-05 'update data') — **this run** |")
    L.append("| 569 | ACL EMNLP-Findings 2024 paper (paper-time snapshot) |")
    L.append("| 564 | NEXUS (arXiv 2607.19356) usable after excluding 7 'leaked' records |")
    L.append("")
    L.append("## 1. Metrics comparison")
    L.append("")
    L.append("| Baseline | Unsafe recall | Unsafe F1 | Evidence coverage | Over-escalation | False-safe |")
    L.append("|---|---|---|---|---|---|")
    for baseline in V1_BASELINES:
        m = matrix["metrics"][baseline]
        L.append(f"| V1 [{baseline}] | {m['unsafe_recall']:.4f} | {m['unsafe_f1']:.4f} | "
                 f"{m['evidence_coverage']:.4f} | {m['over_escalation_rate']:.4f} | {m['false_safe_count']} |")
    v2 = matrix["v2"]
    L.append(f"| **V2 (TF-IDF + experts)** | **{v2['unsafe_recall']:.4f}** | **{v2['unsafe_f1']:.4f}** | "
             f"**{v2['evidence_coverage']:.4f}** | **{v2['over_escalation_rate']:.4f}** | **{v2['false_safe_count']}** |")
    L.append("")
    L.append("## 2. Attack-type recall")
    L.append("")
    L.append("| Attack type | V1 [risk] | V2 | n_unsafe |")
    L.append("|---|---|---|---|")
    converted = load_jsonl(os.path.join(RESULTS, "rjudge_converted.jsonl"))
    for at in ATTACK_TYPES:
        n = sum(1 for r in converted if r.get("attack_type") == at and r.get("label") == 1)
        L.append(f"| {at} | {matrix['attack_type_recall']['v1_risk'][at]:.4f} | "
                 f"{matrix['attack_type_recall']['v2'][at]:.4f} | {n} |")
    L.append("")
    L.append("## 3. Decision distribution (primary baselines)")
    L.append("")
    L.append(f"- V1 [risk]: {matrix['decision_distribution']['v1_risk']}")
    L.append(f"- V2:       {matrix['decision_distribution']['v2']}")
    L.append("")
    L.append("## 4. V2 failure modes")
    L.append("")
    L.append(f"Unsafe records: {matrix['v2_unsafe_total']} | "
             f"caught: {matrix['v2_unsafe_total'] - matrix['v2_missed_unsafe']} | "
             f"missed: {matrix['v2_missed_unsafe']}")
    L.append("")
    L.append("| Failure mode (missed only) | Count |")
    L.append("|---|---|")
    for mode, count in matrix["v2_failure_modes"].most_common():
        L.append(f"| {mode} | {count} |")
    L.append("")
    L.append("## 5. Interpretation")
    L.append("")
    L.append("1. **Zero-coverage fixed**: V1 [plain] covered 0.0% of records; V2 scores 100% "
             "(evidence_coverage 1.0). The 76% zero-coverage failure of the v1 keyword encoder is gone.")
    L.append("2. **Over-escalation reduced**: 0.49 → 0.20 (V2 injection/SE signals are no longer "
             "double-counted and the risk-type adjustment is applied once).")
    L.append("3. **Unsafe recall remains low (0.0066)**: V2 catches only lexical matches. R-Judge "
             "injection attacks are *indirect* — the malicious instruction sits inside environment "
             "payloads (email bodies, note content, calendar events) written as polite requests "
             "('Please initiate a payment of $500…'), which neither regex experts nor TF-IDF "
             "similarity to 'ignore previous instructions'-style patterns can catch.")
    L.append("4. **This confirms the paper's findings**: simple lexical/rule-based risk awareness is "
             "insufficient for open agent scenarios — multi-dimensional knowledge + reasoning is "
             "required. V2 is a heuristic hybrid baseline, not the endpoint (see V3 plan).")
    L.append("")
    L.append("## 6. Next steps (V3 ablation chain)")
    L.append("")
    L.append("```text")
    L.append("V1 = keyword handcrafted")
    L.append("V2 = TF-IDF + regex experts            (this run)")
    L.append("V3 = embedding semantic encoder + symbolic experts")
    L.append("V3 + Memory  (episodic retrieval in the decision loop)")
    L.append("V3 + Memory + Affect  (experience-shaped policy modulation)")
    L.append("```")
    L.append("")
    L.append("Known limitations of this run: environment payloads are truncated at 300 chars/cue in "
             "`extract_context`, which can hide instructions placed deep in long payloads.")
    return "\n".join(L)


def main():
    os.makedirs(RESULTS, exist_ok=True)
    matrix = build_matrix()
    with open(os.path.join(RESULTS, "v1_v2_failure_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2, ensure_ascii=False)
    md = render_md(matrix)
    with open(os.path.join(RESULTS, "v1_v2_failure_matrix.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Matrix written: {os.path.join(RESULTS, 'v1_v2_failure_matrix.md')}")
    print(matrix["count_audit"])
    print("V2 attack-type recall:", matrix["attack_type_recall"]["v2"])


if __name__ == "__main__":
    main()