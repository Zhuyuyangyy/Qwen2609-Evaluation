from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from emotion_agent.adaptive_environment import (  # noqa: E402
    AdaptiveEnvironment, TaskPool, AUTO_EXECUTE, SIMULATE_FIRST,
    HUMAN_REVIEW, BLOCK, C_FAIL,
)
from emotion_agent.adaptive_v15_instrument import (  # noqa: E402
    StepRecorder, decompose_cost, policy_switch_rate,
)

AB300_PATH = os.path.join(PROJECT_ROOT, "data", "rebuild", "synthetic_ab300_seed42.json")
DEFAULT_OUT = os.path.join(PROJECT_ROOT, "results", "v10_diag")

SUBJECT = "affect_memory_v14b"
REFERENCE = "stateless"


def load_pool() -> TaskPool:
    with open(AB300_PATH, encoding="utf-8") as f:
        records = json.load(f)["records"]
    return TaskPool(records)


def run_pair(r_base_mode: str, feedback: str, seed: int, pool: TaskPool) -> Dict:
    """Run both systems on identical environments; record per-step detail.

    The environment is fully determined by (seed, r_base_mode, feedback), so
    replaying the same seed reproduces the same draws. The subject is the system
    whose actions the environment executes (that is the only way to charge its
    costs); the reference's decisions are computed from the *same* observation
    via a second, identically-seeded environment pass — see `run_reference`.
    """
    subj_env = AdaptiveEnvironment(pool, r_base_mode=r_base_mode,
                                  feedback=feedback, seed=seed)
    subj = make_system_holder(SUBJECT)
    rec = StepRecorder()
    recent_classes: List[str] = []
    subj_actions: List[str] = []

    for _ in range(subj_env.T_test):
        obs = subj_env.begin_step()
        d_subj = subj.act(obs)
        res = subj_env.submit(obs, d_subj)
        subj.observe_result(res)
        if res.outcome is not None:
            subj.observe(res.outcome)

        state = subj._agent.state()
        vb = max(0.0, min(1.0, 0.35 * state.get("anxiety", 0.0)
                          + 0.25 * state.get("threat", 0.0)
                          - 0.20 * state.get("confidence", 0.5)))
        rec.record(step=obs.step, seed=seed, r_base_mode=r_base_mode,
                   feedback=feedback, obs=obs, state=state,
                   verification_budget=vb, stateless_action="REPLAY",
                   v14b_action=d_subj, result=res, catches=dict(res.draws),
                   recent_classes=recent_classes[-5:])
        recent_classes.append(obs.task_class)
        subj_actions.append(d_subj)

    ref_actions, ref_costs, ref_failed, ref_comps = run_reference(
        pool, r_base_mode, feedback, seed, rec.records)
    for r, a, c, f, comp in zip(rec.records, ref_actions, ref_costs,
                                ref_failed, ref_comps):
        r.stateless_action = a
        r.step_J_reference = c
        r.unsafe_executed_reference = f
        for key, val in comp.items():
            setattr(r, key + "_ref", val)
        r.delta_J_vs_stateless = round(r.step_J - c, 4)

    return {
        "records": rec.records,
        "switch_rate_subj": policy_switch_rate(subj_actions),
        "switch_rate_ref": policy_switch_rate(ref_actions),
        "env_summary": subj_env.summary(),
    }


def run_reference(pool, r_base_mode, feedback, seed, subject_records):
    """Replay the SAME environment with only `stateless` acting.

    Because the environment draws (task choice, tau, noise, outcome) are all
    seeded per step, a fresh `AdaptiveEnvironment(seed=...)` reproduces the
    same sequence of observations. The `stateless` system's own actions do not
    affect the environment, so this is a faithful paired counterfactual —
    verified step-for-step against an independent replay by
    `test_reference_counterfactual_matches_independent_replay`.
    """
    env = AdaptiveEnvironment(pool, r_base_mode=r_base_mode, feedback=feedback,
                              seed=seed)
    base = make_system_holder(REFERENCE)
    actions, costs, failed_flags, components = [], [], [], []
    for _ in range(env.T_test):
        obs = env.begin_step()
        d = base.act(obs)
        res = env.submit(obs, d)
        actions.append(d)
        costs.append(res.cost)
        failed_flags.append(bool(res.failed and res.executed))
        comps = decompose_cost(d, res.executed, res.failed and res.executed,
                              obs.danger, res.draws)
        components.append(comps)
        base.observe_result(res)
        if res.outcome is not None:
            base.observe(res.outcome)
    return actions, costs, failed_flags, components


def make_system_holder(name: str):
    from emotion_agent.adaptive_systems import make_system
    return make_system(name)


def summarize(records, key, where=None) -> Dict:
    total = 0.0
    for r in records:
        if where is not None and not where(r):
            continue
        total += getattr(r, key) if hasattr(r, key) else 0.0
    return round(total, 3)


# ---------------------------------------------------------------------------
# Q1 - Q4 attribution
# ---------------------------------------------------------------------------
def _phase(r, name):
    return r["phase"] == name


def attribution_table(records) -> Dict:
    """ΣΔJ broken down by (phase, cost component); the rows must sum to the gap.

    Each side's cost is decomposed into the SAME named components, so
    ``delta = subject_component − reference_component`` is well defined and the
    accounting is exact (asserted by test_attribution_rows_sum_to_gap).
    """
    keys = ["cost_unsafe", "cost_review", "cost_simulate", "cost_block",
            "cost_opportunity"]
    rows = []
    for phase in ("SAFE", "DANGER", "RECOVERY"):
        for key in keys:
            ref_key = key + "_ref"
            d = sum(r[key] - r.get(ref_key, 0.0)
                    for r in records if _phase(r, phase))
            if abs(d) > 1e-9:
                rows.append({"bucket": f"{phase}/{key[len('cost_'):]}",
                             "delta_J": round(d, 3)})
    total = round(sum(r["delta_J"] for r in rows), 3)
    for row in rows:
        row["share_pct"] = (round(100.0 * row["delta_J"] / total, 1)
                            if abs(total) > 1e-9 else 0.0)
    return {"rows": rows, "total": total}


def transition_matrix(records) -> List[Dict]:
    """Per-transition count / added cost / unsafe prevented / net cost."""
    buckets = defaultdict(lambda: {"count": 0, "added_cost": 0.0,
                                   "unsafe_prevented": 0.0,
                                   "unsafe_added": 0.0})
    for r in records:
        a, b = r["stateless_action"], r["v14b_action"]
        key = (a, b)
        bkt = buckets[key]
        bkt["count"] += 1
        bkt["added_cost"] += r["delta_J_vs_stateless"]
        # unsafe "prevented" = reference did AUTO+failed, subject avoided it
        if r["unsafe_executed_reference"] and not r["unsafe_executed"]:
            bkt["unsafe_prevented"] += C_FAIL
        elif r["unsafe_executed"] and not r["unsafe_executed_reference"]:
            bkt["unsafe_added"] += C_FAIL
    out = []
    for (a, b), v in sorted(buckets.items(), key=lambda kv: -abs(kv[1]["added_cost"])):
        out.append({"from": a, "to": b, "count": v["count"],
                    "added_cost": round(v["added_cost"], 2),
                    "unsafe_prevented": round(v["unsafe_prevented"], 2),
                    "unsafe_added": round(v["unsafe_added"], 2),
                    "net_cost": round(v["added_cost"], 2)})
    return out


def spillover_stats(records) -> Dict:
    """Q3: how often does the subject differ from stateless on a low-risk
    UNRELATED task, and what does that cost?")
    """
    spill = [r for r in records if r["low_risk_unrelated"]]
    n = len(spill)
    if n == 0:
        return {"n_low_risk_unrelated": 0}
    differs = [r for r in spill if r["stateless_action"] != r["v14b_action"]]
    return {
        "n_low_risk_unrelated": n,
        "P_action_differs": round(len(differs) / n, 4),
        "delta_J_spillover_total": round(sum(r["delta_J_vs_stateless"]
                                            for r in differs), 3),
    }


def cost_effectiveness_ratio(records) -> Dict:
    """Q4: CER = additional intervention cost / unsafe executions prevented."""
    added_cost = sum(max(0.0, r["delta_J_vs_stateless"]) for r in records)
    # intervention cost = everything except unsafe: review + sim + block + opp
    intervention = sum(r["cost_review"] + r["cost_simulate"] + r["cost_block"]
                       + r["cost_opportunity"] for r in records)
    intervention_ref = sum(r["step_J_reference"] for r in records
                           if r["stateless_action"] in (SIMULATE_FIRST,
                                                        HUMAN_REVIEW, BLOCK))
    unsafe_subj = sum(1 for r in records if r["unsafe_executed"])
    unsafe_ref = sum(1 for r in records if r["unsafe_executed_reference"])
    prevented = unsafe_ref - unsafe_subj
    return {
        "unsafe_reference": unsafe_ref,
        "unsafe_subject": unsafe_subj,
        "unsafe_prevented": prevented,
        "unsafe_cost_avoided": round(prevented * C_FAIL, 2),
        "intervention_cost_subject": round(intervention, 2),
        "intervention_cost_reference": round(intervention_ref, 2),
        "extra_intervention_cost": round(intervention - intervention_ref, 2),
        "CER": (round((intervention - intervention_ref) / prevented, 2)
                if prevented > 0 else None),
        "net_delta_J": round(sum(r["delta_J_vs_stateless"] for r in records), 3),
        "added_cost_positive_only": round(added_cost, 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--r-base", default="v2")
    parser.add_argument("--feedback", default="full,sparse")
    parser.add_argument("--output", default=DEFAULT_OUT)
    args = parser.parse_args()

    pool = load_pool()
    rb_modes = [m.strip() for m in args.r_base.split(",") if m.strip()]
    fb_modes = [f.strip() for f in args.feedback.split(",") if f.strip()]

    all_records = []
    switch_rates = {"subj": [], "ref": []}
    for rb in rb_modes:
        for fb in fb_modes:
            for i in range(args.seeds):
                seed = args.seed_start + i
                out = run_pair(rb, fb, seed, pool)
                all_records.extend(out["records"])
                switch_rates["subj"].append(out["switch_rate_subj"])
                switch_rates["ref"].append(out["switch_rate_ref"])
            print(f"  done {rb}/{fb} x{args.seeds}")

    os.makedirs(args.output, exist_ok=True)
    by_combo = defaultdict(list)
    for r in all_records:
        by_combo[(r.r_base_mode, r.feedback)].append(r)

    report = {"subject": SUBJECT, "reference": REFERENCE,
              "config": {"seeds": args.seeds, "seed_start": args.seed_start,
                         "r_base_modes": rb_modes, "feedback_modes": fb_modes},
              "per_combo": {}, "overall": {}}
    for (rb, fb), recs_objs in sorted(by_combo.items()):
        recs = [r.to_dict() for r in recs_objs]
        entry = {
            "n_steps": len(recs),
            "net_delta_J": round(sum(r["delta_J_vs_stateless"] for r in recs), 3),
            "subject_J": round(sum(r["step_J"] for r in recs), 3),
            "reference_J": round(sum(r["step_J_reference"] for r in recs), 3),
            "attribution": attribution_table(recs),
            "transitions": transition_matrix(recs),
            "spillover": spillover_stats(recs),
            "effectiveness": cost_effectiveness_ratio(recs),
        }
        report["per_combo"][f"{rb}|{fb}"] = entry

    all_dicts = [r.to_dict() for r in all_records]
    report["overall"] = {
        "switch_rate": {"subject_mean": round(sum(switch_rates["subj"])
                                             / len(switch_rates["subj"]), 4),
                        "reference_mean": round(sum(switch_rates["ref"])
                                                / len(switch_rates["ref"]), 4)},
        "effectiveness": cost_effectiveness_ratio(all_dicts),
        "spillover": spillover_stats(all_dicts),
    }

    payload = {
        "protocol": "docs/design/phase6_v10_adaptive_environment.md §6.10",
        "subject": SUBJECT,
        "reference": REFERENCE,
        "config": {"seeds": args.seeds, "seed_start": args.seed_start,
                   "r_base_modes": rb_modes, "feedback_modes": fb_modes},
        "n_steps": len(all_records),
        "switch_rate": report["overall"]["switch_rate"],
        "per_step": [r.to_dict() for r in all_records],
    }

    path = os.path.join(args.output, "v1.5_per_step.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    report_path = os.path.join(args.output, "v1.5_attribution_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    md = render_markdown(report)
    md_path = os.path.join(args.output, "v1.5_attribution_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\nwrote {path} ({len(all_records)} steps)")
    print(f"wrote {report_path}")
    print(f"wrote {md_path}")
    print("\n--- net ΔJ per combination ---")
    for key, entry in sorted(report["per_combo"].items()):
        print(f"  {key:16s} net={entry['net_delta_J']:+9.3f}  "
              f"J_subj={entry['subject_J']:8.1f}  J_ref={entry['reference_J']:8.1f}")


def render_markdown(report: Dict) -> str:
    L = ["# V1.5 cost attribution — where does the gap come from?", ""]
    L.append("Protocol: `docs/design/phase6_v10_adaptive_environment.md` §6.10 "
             "(diagnosis only — no policy change, no new seeds, no half-life sweep).")
    L.append("")
    L.append("Subject `%s` vs reference `%s`, paired on identical environments."
             % (report["subject"], report["reference"]))
    L.append("")
    L.append("| combo | n steps | J subject | J reference | net ΔJ |")
    L.append("|---|---|---|---|---|")
    for key, e in sorted(report["per_combo"].items()):
        L.append("| %s | %d | %.1f | %.1f | %+.3f |"
                 % (key, e["n_steps"], e["subject_J"], e["reference_J"],
                    e["net_delta_J"]))
    L.append("")
    for key, e in sorted(report["per_combo"].items()):
        att = e["attribution"]
        if att["total"] == 0:
            continue
        L.append("## %s — ΔJ attribution (total %+.3f)" % (key, att["total"]))
        L.append("")
        L.append("| bucket | ΔJ | share |")
        L.append("|---|---:|---:|")
        for row in sorted(att["rows"], key=lambda r: -abs(r["share_pct"])):
            L.append("| %s | %+.3f | %.1f%% |"
                     % (row["bucket"], row["delta_J"], row["share_pct"]))
        L.append("")
    for key, e in sorted(report["per_combo"].items()):
        eff = e["effectiveness"]
        sp = e["spillover"]
        if not eff.get("unsafe_reference"):
            continue
        L.append("## %s — effectiveness & spillover" % key)
        L.append("")
        L.append("- unsafe executions: reference %d → subject %d (**%d prevented**)"
                 % (eff["unsafe_reference"], eff["unsafe_subject"],
                    eff["unsafe_prevented"]))
        L.append("- unsafe cost avoided: **%s**" % eff["unsafe_cost_avoided"])
        L.append("- extra intervention cost: **%s** (subject %s vs reference %s)"
                 % (eff["extra_intervention_cost"],
                    eff["intervention_cost_subject"],
                    eff["intervention_cost_reference"]))
        L.append("- **CER** (extra intervention cost / unsafe prevented): **%s**"
                 % eff["CER"])
        if sp.get("n_low_risk_unrelated"):
            L.append("- low-risk unrelated tasks: %d, action differs on **%.1f%%** "
                     "of them, ΔJ from those = **%+.3f**"
                     % (sp["n_low_risk_unrelated"],
                        100.0 * sp["P_action_differs"],
                        sp["delta_J_spillover_total"]))
        L.append("")
    L.append("## Policy oscillation")
    L.append("")
    L.append("| system | mean switch rate |")
    L.append("|---|---:|")
    L.append("| %s (reference) | %.4f |"
             % (report["reference"], report["overall"]["switch_rate"]["reference_mean"]))
    L.append("| %s (subject) | %.4f |"
             % (report["subject"], report["overall"]["switch_rate"]["subject_mean"]))
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
