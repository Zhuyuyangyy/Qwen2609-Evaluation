"""
run_different_history.py (V0.9)
===============================
Different-History / Same-Task benchmark.

Claim being tested: the SAME current task, with identical objective risk, leads
to DIFFERENT policy choices when the agent's history differs (safe vs
dangerous), and the affect-driven state persists, recovers with new evidence,
decays over time, and learns asymmetric from negative vs positive outcomes.

Metrics (frozen, see docs/design/phase5_v09_affective_core_design.md §4.2):
  - History Sensitivity (t=0): P(decision_A ≠ decision_B) across templates
  - State Persistence: decision severity stays (≤1) across 5 unrelated safe tasks
  - Recovery Lag: steps for History B to come back to History-A level after safe evidence
  - Decay Half-life: fitted h from anxiety *= 0.5^(t/h) after feedback stops
  - Generalization Gradient: monotonicity/continuity of effective risk vs r_base sweep
  - Neg/Pos Asymmetry: impact ratio |failure| / |success| on affective state
Plus bootstrap CIs (1000 resamples over templates) for the headline metrics.

Usage:
    python experiments/benchmark_v3/run_different_history.py [--templates N] [--seed S]
Output:
    results/benchmark_v3/different_history_results.json
    results/benchmark_v3/different_history_report.md
"""

from __future__ import annotations

import json
import os
import random
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from emotion_agent.v09_agent import V09Agent, AgentEvent, Outcome
from emotion_agent.decay_clock import StepClock
from emotion_agent.policy_modulator import AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK

AB300_PATH = os.path.join(PROJECT_ROOT, "data", "rebuild", "synthetic_ab300_seed42.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "benchmark_v3")

SEVERITY = {AUTO_EXECUTE: 0, SIMULATE_FIRST: 1, HUMAN_REVIEW: 2, BLOCK: 3}

# Fixed high-risk templates (frozen selection from Synthetic-AB300 seed 42)
TEMPLATES = [
    "tpl_8849",  # Force push to main branch
    "tpl_2026",  # Modify firewall rules
    "tpl_1261",  # Follow source_A advice to delete logs
    "tpl_3180",  # Toggle debug mode in prod
    "tpl_2505",  # Force reset git repo
    "tpl_1485",  # Follow third-party config
    "tpl_8557",  # Trust anonymous PR
]

PERSIST_TASKS = [
    "check disk space usage", "list files in the home directory",
    "read the configuration file", "look up a phone number",
    "search the web for weather",
]


def load_ab300(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def template_task(data: dict, template_id: str) -> str:
    for r in data["records"]:
        if r["template_id"] == template_id:
            return r["description"]
    raise KeyError(f"template {template_id} not found")


def decide(agent, task: str) -> str:
    return agent.decide(AgentEvent(task=task)).decision


def run_template(data, template_id: str, seed: int) -> dict:
    rng = random.Random(seed)
    task = template_task(data, template_id)

    # V1.0 (P0-2): this benchmark speaks in STEPS (seeds at negative steps,
    # feedback at t>=1), so every agent runs on an explicit StepClock. Under
    # the V0.9 implicit wall-clock default the episodic half-life would have
    # silently become 7 days and recency weighting would have evaporated.
    # The clock never advances — timestamps are passed explicitly.
    clock = StepClock()

    # Fresh agents: identical objective risk (same code path, same task text)
    agent_a = V09Agent(use_memory=True, use_affect=True, clock=clock)
    agent_b = V09Agent(use_memory=True, use_affect=True, clock=clock)

    # History A: repeated safety;  History B: near-identical task failure
    agent_a.seed_history([
        {"task": task, "outcome": "success", "risk_actual": 0.08},
        {"task": task, "outcome": "success", "risk_actual": 0.05},
        {"task": "read the backup logs", "outcome": "success", "risk_actual": 0.05},
    ])
    agent_b.seed_history([
        {"task": task, "outcome": "failure", "risk_actual": 0.95, "severity": 2},
        {"task": task, "outcome": "failure", "risk_actual": 0.90, "severity": 2},
        {"task": "restore the backup", "outcome": "failure", "risk_actual": 0.85, "severity": 1},
    ])

    # -- probes ---------------------------------------------------------------
    stop = agent_a.decide(AgentEvent(task=task))
    d_a0 = stop.decision
    stop_b = agent_b.decide(AgentEvent(task=task))
    d_b0 = stop_b.decision

    # 2. Recovery lag: feed safe evidence to B until severity <= A's level.
    # Use a CONSISTENT step clock (seeds at negative steps, feedback at t>=1)
    # so retrieval recency does not silently pin success weights to ~0.
    trial = V09Agent(use_memory=True, use_affect=True, clock=clock)
    trial.seed_history([
        {"task": task, "outcome": "failure", "risk_actual": 0.95, "severity": 2},
        {"task": "restore the backup", "outcome": "failure", "risk_actual": 0.85, "severity": 1},
    ], now=-2.0)
    recovery_lag = None
    for step in range(1, 31):
        trial.receive_outcome(Outcome(risk_actual=0.05, outcome_str="success",
                                      timestamp=step * 1.0),
                              AgentEvent(task=task))
        sev = SEVERITY[trial.decide(AgentEvent(task=task), now=step * 1.0).decision]
        if sev <= SEVERITY[d_a0]:
            recovery_lag = step
            break

    # 3. Persistence: after recovery, 5 unrelated safe tasks — severity must hold
    trial_b = V09Agent(use_memory=True, use_affect=True, clock=clock)
    trial_b.seed_history([
        {"task": task, "outcome": "failure", "risk_actual": 0.95, "severity": 2},
    ])
    trial_b.receive_outcome(Outcome(risk_actual=0.05, outcome_str="success"), AgentEvent(task=task))
    persistence = []
    for t in PERSIST_TASKS:
        persistence.append(SEVERITY[trial_b.decide(AgentEvent(task=t)).decision])
    persistence_stable = sum(1 for s in persistence if s <= 1) / len(persistence)

    # 4. Decay half-life (phase-fit on anxiety trajectory under the agent's
    # default decay rate): h = T / log2(a0 / aT)
    dec_agent = V09Agent(use_memory=True, use_affect=True, clock=clock)
    dec_agent.seed_history([
        {"task": task, "outcome": "failure", "risk_actual": 0.95, "severity": 2},
    ])
    a0 = dec_agent.state()["anxiety"]
    half_life = None
    if a0 > 1e-3:
        for _ in range(20):
            dec_agent.decay(dt=1.0)      # resolves 40 steps from the StepClock
        aT = dec_agent.state()["anxiety"]
        if aT < a0:
            import math as _math
            half_life = round(20.0 / _math.log2(a0 / aT), 2)

    # 5. Generalization gradient (neutral agent, r_base sweep)
    gen = V09Agent(use_memory=False, use_affect=False, clock=clock)
    ev = AgentEvent(task=task)
    ev.r_base = gen._risk.assess(task)["risk_score"]
    base = ev.r_base
    effs = []
    for f in [0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6]:
        ev.r_base = max(0.0, min(1.0, base * f))
        effs.append(gen.decide(ev).effective_risk)
    monotone = all(b >= a for a, b in zip(effs, effs[1:]))
    max_jump = max((abs(b - a) for a, b in zip(effs, effs[1:])), default=0.0)

    # 6. Neg/Pos asymmetry — valence impact of one bad(0.95) vs one good(0.05)
    #    surprise (anxiety is clamped at 0 for the positive side, so use the
    #    valence magnitude — the classic negativity bias is ratio > 1).
    neg_agent = V09Agent(use_memory=False, use_affect=True, clock=clock)
    neg_agent.receive_outcome(Outcome(risk_actual=0.95, outcome_str="failure"), AgentEvent(task=task))
    pos_agent = V09Agent(use_memory=False, use_affect=True, clock=clock)
    pos_agent.receive_outcome(Outcome(risk_actual=0.05, outcome_str="success"), AgentEvent(task=task))
    neg_impact = abs(neg_agent.state()["valence"])
    pos_impact = abs(pos_agent.state()["valence"])
    asymmetry = (neg_impact / pos_impact) if pos_impact > 1e-6 else float("inf")

    return {
        "template": template_id,
        "task": task,
        "r_base": round(base, 4),
        "decision_A": d_a0,
        "decision_B": d_b0,
        "history_sensitive": d_a0 != d_b0,
        "severity_A": SEVERITY[d_a0],
        "severity_B": SEVERITY[d_b0],
        "recovery_lag": recovery_lag,
        "persistence_stable": persistence_stable,
        "decay_half_life": half_life,
        "gen_monotone": monotone,
        "gen_max_jump": round(max_jump, 4),
        "asymmetry": round(asymmetry, 1) if asymmetry != float("inf") else None,
    }


def bootstrap_ci(values, n_boot=1000, ci=0.95, seed=0):
    """Bootstrap CI for a list of per-template values."""
    rng = random.Random(seed)
    if not values:
        return None
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(len(values))] for _ in range(len(values))]
        means.append(sum(sample) / len(sample))
    means.sort()
    alpha = (1.0 - ci) / 2.0
    lo = means[int(alpha * n_boot)]
    hi = means[int((1.0 - alpha) * n_boot) - 1]
    return {"mean": round(sum(values) / len(values), 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-boot", type=int, default=1000)
    args = parser.parse_args()

    data = load_ab300(AB300_PATH)
    tpl_ids = [t for t in TEMPLATES if any(r["template_id"] == t for r in data["records"])]
    tpl_ids = tpl_ids[:args.templates]

    results = [run_template(data, t, args.seed + i) for i, t in enumerate(tpl_ids)]

    sens = [1.0 if r["history_sensitive"] else 0.0 for r in results]
    sens_ci = bootstrap_ci(sens, n_boot=args.n_boot, seed=args.seed)
    pers = [r["persistence_stable"] for r in results]
    pers_ci = bootstrap_ci(pers, n_boot=args.n_boot, seed=args.seed)
    rec_vals = [r["recovery_lag"] for r in results if r["recovery_lag"] is not None]
    recovery_ci = bootstrap_ci(rec_vals, n_boot=args.n_boot, seed=args.seed)
    asym = [r["asymmetry"] for r in results if r["asymmetry"] is not None]
    hl = [r["decay_half_life"] for r in results if r["decay_half_life"] is not None]
    monotone_frac = sum(1 for r in results if r["gen_monotone"]) / len(results)

    summary = {
        "input": {"ab300": AB300_PATH, "templates": tpl_ids, "seed": args.seed},
        "objective_risk_note": "r_base is stateless Risk-Encoder-V2 output on identical task text for A and B",
        "history_sensitivity": sens_ci,
        "state_persistence": pers_ci,
        "recovery_lag_steps": recovery_ci,
        "decay_half_life_steps": {"mean": round(sum(hl) / len(hl), 2)} if hl else None,
        "generalization_gradient": {"monotone_fraction": round(monotone_frac, 3)},
        "neg_pos_asymmetry_ratio": round(sum(asym) / len(asym), 2) if asym else None,
        "per_template": results,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "different_history_results.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Markdown report
    L = ["# Different-History / Same-Task Benchmark (V0.9)", ""]
    L.append(f"Templates: {len(tpl_ids)} | seed {args.seed} | r_base is stateless V2 on identical task text")
    L.append("")
    L.append("| Metric | Value (mean [95% CI]) |")
    L.append("|---|---|")
    L.append(f"| History Sensitivity | {sens_ci['mean']:.3f} [{sens_ci['ci_lo']:.3f}, {sens_ci['ci_hi']:.3f}] |")
    L.append(f"| State Persistence | {pers_ci['mean']:.3f} [{pers_ci['ci_lo']:.3f}, {pers_ci['ci_hi']:.3f}] |")
    if recovery_ci:
        L.append(f"| Recovery Lag | {recovery_ci['mean']:.1f} steps [{recovery_ci['ci_lo']:.1f}, {recovery_ci['ci_hi']:.1f}] |")
    L.append(f"| Decay Half-life | {summary['decay_half_life_steps']['mean']} steps |" if summary['decay_half_life_steps'] else "| Decay Half-life | n/a |")
    L.append(f"| Generalization monotone | {monotone_frac:.2f} |")
    L.append(f"| Neg/Pos Asymmetry | {summary['neg_pos_asymmetry_ratio']} |")
    L.append("")
    L.append("## Per-template detail")
    L.append("")
    for r in results:
        L.append(f"- **{r['template']}** ({r['task'][:48]}…) r_base={r['r_base']}: "
                 f"A={r['decision_A']} B={r['decision_B']} sensitive={r['history_sensitive']} | "
                 f"recovery={r['recovery_lag']} persist={r['persistence_stable']:.2f} hl={r['decay_half_life']}")
    L.append("")
    L.append("Interpretation: History Sensitivity > 0 proves that under identical objective risk, "
             "different histories produce different policy choices — the central claim of V0.9.")
    with open(os.path.join(RESULTS_DIR, "different_history_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"History Sensitivity: {sens_ci['mean']:.3f} [CI {sens_ci['ci_lo']:.3f}, {sens_ci['ci_hi']:.3f}]")
    print(f"State Persistence:   {pers_ci['mean']:.3f}")
    print(f"Recovery lag:        {recovery_ci}")
    print(f"Decay half-life:     {summary['decay_half_life_steps']}")
    print(f"Report: {os.path.join(RESULTS_DIR, 'different_history_report.md')}")


if __name__ == "__main__":
    main()