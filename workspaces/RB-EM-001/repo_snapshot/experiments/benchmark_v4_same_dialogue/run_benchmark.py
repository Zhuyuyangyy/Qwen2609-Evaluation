"""run_benchmark.py (V1.0)
=======================
Benchmark B — same dialogue, different histories.

The experiment behind the companion layer (P2): hold the *current
message* identical and vary only the *history* (history A = engaged and
welcoming; history B = refuses asks, requests quiet, replies late and
terse until a recovery phase).  Five ablation arms run the same protocol
(``protocol.py``), and ten social metrics decide whether history
conditioning does anything a history-blind agent could not.

The benchmark can lose: ``v09_baseline`` pins the history-blind scale
(every paired and memory metric must sit at its trivial value), and the
ablation arms exist to attribute each behaviour to a channel.

Usage:
    python experiments/benchmark_v4_same_dialogue/run_benchmark.py \
        [--seeds 5] [--systems all] [--output results/v4_same_dialogue] [--tag ""]

Outputs:
    <output>/results.json    machine-readable (incl. per-seed detail)
    <output>/report.md       human-readable summary + divergence table
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from emotion_agent import companion_metrics as cm
from emotion_agent.companion_systems import (
    ARM_ORDER, ARM_ROLES, check_arm_integrity, make_all_arms,
)
from protocol import compute_table, run_arm

DEFAULT_OUT = os.path.join(PROJECT_ROOT, "results", "v4_same_dialogue")

METRICS = [
    "history_sensitivity", "policy_divergence", "state_persistence",
    "recovery_lag", "temporal_consistency",
    "memory_attribution_a", "memory_attribution_b",
    "repeated_question_rate_a", "repeated_question_rate_b",
    "pending_thread_resolution_a", "pending_thread_resolution_b",
    "proactive_appropriateness_a", "proactive_appropriateness_b",
    "intrusiveness_rate_a", "intrusiveness_rate_b",
]

BASELINE_EXPECTED = {
    "history_sensitivity": 0.0,
    "policy_divergence": 0.0,
    "state_persistence": 0.0,
    "recovery_lag": 0.0,
    "temporal_consistency": 1.0,
    "memory_attribution_a": 0.0,
    "memory_attribution_b": 0.0,
    "repeated_question_rate_a": 0.0,
    "repeated_question_rate_b": 0.0,
    "pending_thread_resolution_a": 1.0,
    "pending_thread_resolution_b": 1.0,
    "proactive_appropriateness_a": 1.0,
    "proactive_appropriateness_b": 1.0,
    "intrusiveness_rate_a": 0.0,
    "intrusiveness_rate_b": 0.0,
}


def run_seeds(name: str, seeds) -> list:
    out = []
    for seed in seeds:
        run = run_arm(name, seed)
        out.append(compute_table(run))
    return out


def baseline_self_check(arm: str, agg: dict) -> dict:
    """The history-blind control must pin the scale — verify from data."""
    check = {}
    for metric, expected in BASELINE_EXPECTED.items():
        entry = agg.get(metric) or {}
        observed = entry.get("mean")
        if expected is None:
            ok = observed is None
        elif observed is None:
            ok = False
        else:
            ok = abs(float(observed) - float(expected)) < 1e-9
        check[metric] = {"expected": expected, "observed": observed, "ok": bool(ok)}
    return check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--systems", default="all")
    parser.add_argument("--output", default=DEFAULT_OUT)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    systems = (ARM_ORDER if args.systems == "all"
               else [s.strip() for s in args.systems.split(",") if s.strip()])
    seeds = [args.seed_start + i for i in range(args.seeds)]

    problems = check_arm_integrity(make_all_arms())
    if problems:
        for line in problems:
            print(f"arm integrity: {line}")
        raise SystemExit("arm integrity check failed — aborting benchmark")

    print("plan: %d arms x %d seeds = %d runs (%s)"
          % (len(systems), len(seeds), len(systems) * len(seeds),
             "seeds %d..%d" % (seeds[0], seeds[-1])))

    summary, per_seed, baseline_check = {}, [], {}
    details, cold_proactive, final_slow = {}, {}, {}
    for name in systems:
        runs = run_seeds(name, seeds)
        per_seed.extend(dict(table, arm=name, seed=seed)
                        for seed, table in zip(seeds, runs))
        summary[name] = cm.aggregate(runs)
        seed0 = run_arm(name, seeds[0])
        details[name] = seed0.divergence
        cold_proactive[name] = seed0.cold_proactive
        final_slow[name] = seed0.final_slow
        if name == "v09_baseline":
            baseline_check = baseline_self_check(name, summary[name])

        def cell(metric, _agg=summary[name]):
            v = _agg.get(metric, {}).get("mean")
            return "n/a" if v is None else "%.3f" % v

        print("  %-14s hist_sens=%s policy_div=%s attrib_a=%s repeat_a=%s "
              "intrus_a=%s rec_lag=%s"
              % (name, cell("history_sensitivity"), cell("policy_divergence"),
                 cell("memory_attribution_a"), cell("repeated_question_rate_a"),
                 cell("intrusiveness_rate_a"), cell("recovery_lag")))

    payload = {
        "protocol": "experiments/benchmark_v4_same_dialogue/protocol.py",
        "config": {
            "seeds": args.seeds, "seed_start": args.seed_start,
            "systems": systems, "tag": args.tag,
        },
        "summary": summary,
        "baseline_self_check": baseline_check,
        "cold_proactive": cold_proactive,
        "divergence_seed0": details,
        "final_slow_seed0": final_slow,
        "per_seed": per_seed,
    }

    os.makedirs(args.output, exist_ok=True)
    results_path = os.path.join(args.output, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nresults: {results_path}")

    report_path = os.path.join(args.output, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(render_report(payload))
    print(f"report:  {report_path}")


def _cell(agg: dict, metric: str) -> str:
    entry = agg.get(metric) or {}
    mean = entry.get("mean")
    if mean is None:
        return "never" if entry.get("n", 0) == 0 else "n/a"
    return "%.3f ± %.3f" % (mean, entry.get("std", 0.0))


def render_report(payload: dict) -> str:
    cfg = payload["config"]
    summary = payload["summary"]
    L = ["# Benchmark B — Same Dialogue, Different Histories (P2)", ""]
    L.append("Protocol: `%s` | seeds %d..%d | arms: %s"
             % (payload["protocol"], cfg["seed_start"],
                cfg["seed_start"] + cfg["seeds"] - 1,
                ", ".join(cfg["systems"])))
    L.append("")
    L.append("Identical current probes, two histories: **A** answers the "
             "agent's questions and welcomes check-ins; **B** refuses asks "
             "(`别问`), requests quiet, replies late and terse, then "
             "recovers to the engaged pattern. Arms: "
             + "; ".join("`%s` = %s" % (n, ARM_ROLES.get(n, ""))
                         for n in cfg["systems"]) + ".")
    L.append("")

    L.append("## Verdict")
    L.append("")
    L.append(summarize_verdict(payload))
    L.append("")

    L.append("## All ten metrics by arm")
    L.append("")
    L.append("| metric | direction | " + " | ".join(cfg["systems"]) + " |")
    L.append("|---|---|" + "---|" * len(cfg["systems"]))
    direction = {
        "history_sensitivity": "higher ≠ baseline", "policy_divergence": "higher ≠ baseline",
        "state_persistence": "higher = gap survives quiet", "recovery_lag": "lower = faster recovery",
        "temporal_consistency": "higher = no churn",
        "memory_attribution_a": "higher = memory explains decisions",
        "memory_attribution_b": "higher = memory explains decisions",
        "repeated_question_rate_a": "lower = remembers its asks",
        "repeated_question_rate_b": "lower = remembers its asks",
        "pending_thread_resolution_a": "higher = threads close",
        "pending_thread_resolution_b": "higher = threads close",
        "proactive_appropriateness_a": "higher = outreach welcome",
        "proactive_appropriateness_b": "higher = outreach welcome",
        "intrusiveness_rate_a": "lower = less nagging",
        "intrusiveness_rate_b": "lower = less nagging",
    }
    for metric in METRICS:
        cells = [_cell(summary[name], metric) for name in cfg["systems"]]
        L.append("| %s | %s | %s |" % (metric, direction.get(metric, ""),
                                       " | ".join(cells)))
    L.append("")
    L.append("`mean ± std` over seeds; `recovery_lag` shows `never` when "
             "history B's slow state never rejoined A within the window "
             "(steps until rejoin otherwise).")
    L.append("")

    check = payload.get("baseline_self_check") or {}
    if check:
        L.append("## Baseline self-check (`v09_baseline`)")
        L.append("")
        L.append("| metric | expected (history-blind) | observed | ok |")
        L.append("|---|---|---|---|")
        for metric in METRICS:
            entry = check.get(metric)
            if not entry:
                continue
            L.append("| %s | %s | %s | %s |"
                     % (metric, entry["expected"], entry["observed"],
                        "yes" if entry["ok"] else "NO"))
        L.append("")

    cold = payload.get("cold_proactive") or {}
    if cold:
        L.append("## Proactive phase (cold history, before the probes)")
        L.append("")
        L.append("| arm | A engaged / sent | B engaged / sent |")
        L.append("|---|---|---|")
        for name in cfg["systems"]:
            entry = cold.get(name) or {}
            a, b = entry.get("a", {}), entry.get("b", {})
            L.append("| %s | %d / %d | %d / %d |"
                     % (name, a.get("engaged", 0), a.get("sent", 0),
                        b.get("engaged", 0), b.get("sent", 0)))
        L.append("")
        L.append("Five outreach opportunities per history, spaced outside "
                 "the 40-step ask-recency window. B's fifth is suppressed "
                 "by the gate once learned `proactivity_tolerance` drops "
                 "below the 0.35 floor; recovery-phase check-ins are "
                 "excluded from this table.")
        L.append("")

    divergence = payload.get("divergence_seed0") or {}
    if divergence:
        L.append("## Same-dialogue divergence (seed %d)" % cfg["seed_start"])
        L.append("")
        for name in cfg["systems"]:
            rows = divergence.get(name) or []
            if not rows:
                continue
            L.append("### `%s`" % name)
            L.append("")
            L.append("| t | user | A action (conf) | B action (conf) |")
            L.append("|---|---|---|---|")
            for row in rows:
                marker = " **←**" if row["a_action"] != row["b_action"] else ""
                L.append("| %.0f | %s | %s (%.2f) | %s (%.2f)%s |"
                         % (row["at"], row["user_text"],
                            row["a_action"], row["a_confidence"],
                            row["b_action"], row["b_confidence"], marker))
            L.append("")

    slow = payload.get("final_slow_seed0") or {}
    if slow:
        L.append("## Final slow state (seed %d, after recovery)" % cfg["seed_start"])
        L.append("")
        dims = ["interaction_trust", "uncertainty_baseline",
                "proactivity_tolerance", "control_preference"]
        L.append("| arm | " + " | ".join("%s A / B" % d.replace("_", " ")
                                        for d in dims) + " |")
        L.append("|" + "---|" * (len(dims) + 1))
        for name in cfg["systems"]:
            entry = slow.get(name) or {}
            a, b = entry.get("a", {}), entry.get("b", {})
            cells = ["%.3f / %.3f" % (a.get(d, 0.0), b.get(d, 0.0))
                     for d in dims]
            L.append("| %s | %s |" % (name, " | ".join(cells)))
        L.append("")

    L.append("## How to read this")
    L.append("")
    L.append("Paired metrics (history sensitivity, policy divergence, "
             "state persistence, recovery lag) compare the two histories "
             "inside one arm — a history-blind agent must score its "
             "trivial value on all of them, which the baseline "
             "self-check verifies. Single-arm metrics use each history's "
             "own trajectory and ask ledger: repeated-question rate and "
             "intrusiveness are lower-is-better, memory attribution and "
             "thread resolution are higher-is-better, and proactive "
             "appropriateness measures how often check-ins landed on a "
             "human who actually engaged. Nothing here claims subjective "
             "emotion: the core outputs decisions, the outer layer owns "
             "scheduling and delivery.")
    L.append("")
    return "\n".join(L)


def summarize_verdict(payload: dict) -> str:
    """Verdict derived from the data, so it cannot drift from it."""
    cfg = payload["config"]
    summary = payload["summary"]
    lines = []

    check = payload.get("baseline_self_check") or {}
    if check:
        bad = [m for m, e in check.items() if not e["ok"]]
        if bad:
            lines.append("**Baseline pinning FAILED** for: %s — the "
                         "history-blind control is not trivial, so paired "
                         "numbers cannot be trusted this run."
                         % ", ".join(sorted(bad)))
        else:
            lines.append("**Baseline pinning holds:** `v09_baseline` sits "
                         "at its history-blind value on all fifteen "
                         "control points (0.0 divergence / memory / "
                         "intrusiveness, 1.0 consistency / resolution / "
                         "appropriateness, no recovery lag), so any "
                         "non-trivial number below is history doing work.")

    def mean(arm, metric):
        entry = (summary.get(arm) or {}).get(metric) or {}
        return entry.get("mean")

    subject = "full" if "full" in summary else (
        cfg["systems"][-1] if cfg["systems"] else None)
    if subject:
        hs = mean(subject, "history_sensitivity")
        pd = mean(subject, "policy_divergence")
        rep_a = mean(subject, "repeated_question_rate_a")
        rep_b = mean(subject, "repeated_question_rate_b")
        app_b = mean(subject, "proactive_appropriateness_b")
        lag = mean(subject, "recovery_lag")
        lines.append("")
        lines.append("**`%s`:** history sensitivity %.3f, mean confidence "
                     "gap %.3f across the identical probe dialogue; "
                     "repeated-question rate %.3f (A) / %.3f (B); "
                     "cold-history proactive appropriateness %.3f on B; "
                     "recovery lag %s."
                     % (subject, hs or 0.0, pd or 0.0, rep_a or 0.0,
                        rep_b or 0.0, app_b if app_b is not None else 0.0,
                        "never rejoined A" if lag is None
                        else "%.1f steps" % lag))

    arms_with_attribution = [a for a in cfg["systems"]
                             if (mean(a, "memory_attribution_a") or 0.0) > 0.0
                             or (mean(a, "memory_attribution_b") or 0.0) > 0.0]
    if arms_with_attribution:
        lines.append("")
        lines.append("Memory-attributed decisions appear in: %s — the "
                     "channels where the ask ledger / gate actually "
                     "explains the decision." % ", ".join(arms_with_attribution))

    if not lines:
        return "No arms ran; nothing to summarise."
    lines.append("")
    lines.append("Ablation reading: `memory_only` carries the ask-ledger "
                 "behaviour without persistent affect; `affect_only` "
                 "carries the state without recall; `memory_affect` and "
                 "`full` need both channels to diverge on high-risk "
                 "confirmations and to time the recovery. An arm that "
                 "shows nothing above the baseline has earned nothing.")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
