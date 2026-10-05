"""V1.6 judgement: run the SAME V1.5 attribution pipeline on the V1.6 subject
and answer H1-H6 against the pre-registered criteria (design doc §6.13.2).

Nothing here changes a policy; it only re-points the diagnosis at v16.
"""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from emotion_agent.adaptive_environment import (  # noqa: E402
    AdaptiveEnvironment, TaskPool, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK,
    C_FAIL,
)
import experiments.adaptive_v10.run_v15_attribution as R  # noqa: E402

OUTPUT_DEFAULT = os.path.join(PROJECT_ROOT, "results", "v10_diag")


def run_v16_pair(pool, rb, fb, seed):
    """Same pairing, but with `affect_memory_v16` as the subject."""
    subj_env = AdaptiveEnvironment(pool, r_base_mode=rb, feedback=fb, seed=seed)
    subj = R.make_system_holder("affect_memory_v16")
    rec = R.StepRecorder()
    recent, subj_actions = [], []
    for _ in range(subj_env.T_test):
        obs = subj_env.begin_step()
        d = subj.act(obs)
        res = subj_env.submit(obs, d)
        subj.observe_result(res)
        if res.outcome is not None:
            subj.observe(res.outcome)
        state = subj._agent.state()
        vb = max(0.0, min(1.0, 0.35 * state.get("anxiety", 0.0)
                          + 0.25 * state.get("threat", 0.0)
                          - 0.20 * state.get("confidence", 0.5)))
        rec.record(step=obs.step, seed=seed, r_base_mode=rb, feedback=fb,
                   obs=obs, state=state, verification_budget=vb,
                   stateless_action="REPLAY", v14b_action=d, result=res,
                   catches=dict(res.draws), recent_classes=recent[-5:])
        recent.append(obs.task_class)
        subj_actions.append(d)

    ref_actions, ref_costs, ref_failed, ref_comps = R.run_reference(
        pool, rb, fb, seed, rec.records)
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
        "switch_rate_subj": R.policy_switch_rate(subj_actions),
        "switch_rate_ref": R.policy_switch_rate(ref_actions),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--r-base", default="v2")
    ap.add_argument("--feedback", default="sparse")
    ap.add_argument("--output", default=OUTPUT_DEFAULT)
    args = ap.parse_args()

    pool = R.load_pool()
    recs = []
    switches = {"subj": [], "ref": []}
    for i in range(args.seeds):
        seed = i
        out = run_v16_pair(pool, args.r_base, args.feedback, seed)
        recs.extend(out["records"])
        switches["subj"].append(out["switch_rate_subj"])
        switches["ref"].append(out["switch_rate_ref"])
    dicts = [r.to_dict() for r in recs]
    report = {
        "subject": "affect_memory_v16",
        "reference": "stateless",
        "config": {"seeds": args.seeds, "r_base_mode": args.r_base,
                   "feedback": args.feedback},
        "n_steps": len(dicts),
        "net_delta_J": round(sum(r["delta_J_vs_stateless"] for r in dicts), 3),
        "attribution": R.attribution_table(dicts),
        "transitions": R.transition_matrix(dicts),
        "spillover": R.spillover_stats(dicts),
        "effectiveness": R.cost_effectiveness_ratio(dicts),
        "switch_rate": {
            "subject_mean": round(sum(switches["subj"]) / len(switches["subj"]), 4),
            "reference_mean": round(sum(switches["ref"]) / len(switches["ref"]), 4),
        },
    }
    os.makedirs(args.output, exist_ok=True)
    p = os.path.join(args.output, "v1.6_attribution_report.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in
                      ("subject", "n_steps", "net_delta_J", "attribution",
                       "effectiveness", "spillover", "switch_rate")},
                     indent=2, ensure_ascii=False))
    print("\nwrote", p)


if __name__ == "__main__":
    main()
