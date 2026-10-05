"""
run_adaptive_benchmark.py (V1.0)
================================
Adaptive Environment Benchmark — the experiment that decides whether a
history-conditioned persistent state is worth anything at *task level*.

It compares six systems (design doc §3) on a non-stationary task stream
(safe → danger → recovery) under 3 objective-risk regimes × 2 feedback regimes,
over multiple seeds, and reports **paired** bootstrap CIs.

The point of the benchmark is that it can lose: ``ewma`` and ``bayes_hazard``
are ~15-line conventional controllers. If they tie the affective system, the
report says so.

Usage:
    python experiments/adaptive_v10/run_adaptive_benchmark.py \
        [--seeds 30] [--systems all] [--r-base oracle,noisy,v2] \
        [--feedback full,sparse] [--n-boot 1000] [--output results/v10_adaptive]

Outputs:
    <output>/results.json    machine-readable (incl. per-seed detail)
    <output>/report.md       human-readable summary + significance table
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from emotion_agent.adaptive_environment import AdaptiveEnvironment, TaskPool  # noqa: E402
from emotion_agent.adaptive_metrics import compute_metrics, paired_bootstrap_ci  # noqa: E402
from emotion_agent.adaptive_systems import SYSTEM_BUILDERS, SYSTEM_ORDER  # noqa: E402

AB300_PATH = os.path.join(PROJECT_ROOT, "data", "rebuild", "synthetic_ab300_seed42.json")
DEFAULT_OUT = os.path.join(PROJECT_ROOT, "results", "v10_adaptive")

BASELINES = ["stateless", "memory_only", "affect_only", "ewma", "bayes_hazard"]
HEADLINE = ["unsafe_execution", "false_escalation", "cumulative_cost",
            "adaptation_delay", "recovery_delay"]


def load_pool() -> TaskPool:
    with open(AB300_PATH, encoding="utf-8") as f:
        records = json.load(f)["records"]
    return TaskPool(records)


def run_one(system_name: str, r_base_mode: str, feedback: str, seed: int,
            pool: TaskPool) -> dict:
    env = AdaptiveEnvironment(pool, r_base_mode=r_base_mode, feedback=feedback, seed=seed)
    system = SYSTEM_BUILDERS[system_name]()
    step_decisions, step_failures = {}, {}
    for _ in range(env.T_test):
        obs = env.begin_step()
        obs.meta_system = system_name
        obs.meta_r_base_mode = r_base_mode
        obs.meta_feedback = feedback
        decision = system.act(obs)
        result = env.submit(obs, decision)
        system.observe_result(result)
        if result.outcome is not None:
            system.observe(result.outcome)
        step_decisions[obs.meta_key] = decision
        step_failures[obs.meta_key] = int(result.failed and result.executed)
    metrics = compute_metrics(env.history)
    metrics["seed"] = seed
    metrics["system"] = system_name
    metrics["r_base_mode"] = r_base_mode
    metrics["feedback"] = feedback
    metrics["env_summary"] = env.summary()
    metrics["step_decisions"] = step_decisions
    metrics["step_failures"] = step_failures
    return metrics


def _pair_all(treatment: list, baseline: list, n_boot: int) -> dict:
    """Paired bootstrap CI of ``treatment − baseline`` for every headline metric.

    Returns {metric: {mean, ci_lo, ci_hi, significant, n_seeds}}; metrics with
    missing values are dropped so the report can show "n/a".
    """
    out = {}
    for metric in HEADLINE:
        a = [r[metric] for r in treatment if r.get(metric) is not None]
        b = [r[metric] for r in baseline if r.get(metric) is not None]
        if len(a) != len(b) or not a:
            continue
        out[metric] = paired_bootstrap_ci(b, a, n_boot=n_boot, seed=n_boot)
    return out


def aggregate(runs: list) -> dict:
    """Per-metric mean + spread over seeds (unpaired, for readability)."""
    out = {}
    for key in HEADLINE:
        vals = [r[key] for r in runs if r.get(key) is not None]
        if not vals:
            out[key] = {"mean": None, "n": 0}
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1) if len(vals) > 1 else 0.0
        out[key] = {
            "mean": round(mean, 4),
            "std": round(var ** 0.5, 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "n": len(vals),
        }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--systems", default="all")
    parser.add_argument("--r-base", default="oracle,noisy,v2")
    parser.add_argument("--feedback", default="full,sparse")
    parser.add_argument("--n-boot", type=int, default=1000)
    parser.add_argument("--output", default=DEFAULT_OUT)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()

    systems = SYSTEM_ORDER if args.systems == "all" else \
        [s.strip() for s in args.systems.split(",") if s.strip()]
    rb_modes = [m.strip() for m in args.r_base.split(",") if m.strip()]
    fb_modes = [f.strip() for f in args.feedback.split(",") if f.strip()]

    pool = load_pool()
    print(f"task pool: {len(pool)} tasks across {len(pool.classes())} classes "
          f"({', '.join(pool.classes())})")
    total = len(systems) * len(rb_modes) * len(fb_modes) * args.seeds
    print(f"plan: {len(systems)} systems x {len(rb_modes)} r_base x "
          f"{len(fb_modes)} feedback x {args.seeds} seeds = {total} episodes")

    all_runs = []
    for rb in rb_modes:
        for fb in fb_modes:
            for sysname in systems:
                runs = []
                for i in range(args.seeds):
                    seed = args.seed_start + i
                    r = run_one(sysname, rb, fb, seed, pool)
                    runs.append(r)
                    all_runs.append(r)
                agg = aggregate(runs)
                key = f"{sysname}|{rb}|{fb}"
                print(f"  {key:42s} "
                      f"unsafe={agg['unsafe_execution']['mean']} "
                      f"esc={agg['false_escalation']['mean']} "
                      f"J={agg['cumulative_cost']['mean']}")
                _LATEST[key] = runs

    # --- paired significance tests ------------------------------------------
    # (a) THE generational A/B: V0.9 -> V1.1 (coupling repair) -> V1.2
    #     (task-level uncertainty separated from persistent affect), each on
    #     identical environments and seeds.
    # (b) the full baseline picture for whichever system is the subject.
    comparisons = {}
    version_ab = {"v11_vs_v09": {}, "v12_vs_v11": {},
                  "v13_vs_v12": {}, "v13b_vs_v12": {},
                  "v14_vs_v13": {}, "v14b_vs_v13": {},
                  "v16_vs_v14b": {}}
    for rb in rb_modes:
        for fb in fb_modes:
            group = f"{rb}|{fb}"
            runs = {name: _LATEST.get(f"{name}|{group}")
                    for name in ("affect_memory", "affect_memory_v11",
                                 "affect_memory_v12", "affect_memory_v13",
                                 "affect_memory_v13b", "affect_memory_v14",
                                 "affect_memory_v14b", "affect_memory_v16")}
            if runs["affect_memory"] and runs["affect_memory_v11"]:
                version_ab["v11_vs_v09"][group] = _pair_all(
                    runs["affect_memory_v11"], runs["affect_memory"], args.n_boot)
            if runs["affect_memory_v11"] and runs["affect_memory_v12"]:
                version_ab["v12_vs_v11"][group] = _pair_all(
                    runs["affect_memory_v12"], runs["affect_memory_v11"],
                    args.n_boot)
            if runs["affect_memory_v12"] and runs["affect_memory_v13"]:
                version_ab["v13_vs_v12"][group] = _pair_all(
                    runs["affect_memory_v13"], runs["affect_memory_v12"],
                    args.n_boot)
            if runs["affect_memory_v12"] and runs["affect_memory_v13b"]:
                version_ab["v13b_vs_v12"][group] = _pair_all(
                    runs["affect_memory_v13b"], runs["affect_memory_v12"],
                    args.n_boot)
            if runs["affect_memory_v13"] and runs["affect_memory_v14"]:
                version_ab["v14_vs_v13"][group] = _pair_all(
                    runs["affect_memory_v14"], runs["affect_memory_v13"],
                    args.n_boot)
            if runs["affect_memory_v13"] and runs["affect_memory_v14b"]:
                version_ab["v14b_vs_v13"][group] = _pair_all(
                    runs["affect_memory_v14b"], runs["affect_memory_v13"],
                    args.n_boot)
            if runs["affect_memory_v14b"] and runs["affect_memory_v16"]:
                version_ab["v16_vs_v14b"][group] = _pair_all(
                    runs["affect_memory_v16"], runs["affect_memory_v14b"],
                    args.n_boot)
            # subject = the newest generation that ran
            subject_name, subject = None, None
            for name in ("affect_memory_v16", "affect_memory_v14",
                         "affect_memory_v14b",
                         "affect_memory_v13", "affect_memory_v13b",
                         "affect_memory_v12", "affect_memory_v11",
                         "affect_memory"):
                if runs.get(name):
                    subject_name, subject = name, runs[name]
                    break
            per_baseline = {}
            if subject:
                for base in BASELINES:
                    theirs = _LATEST.get(f"{base}|{group}")
                    if theirs:
                        per_baseline[base] = _pair_all(subject, theirs,
                                                       args.n_boot)
            comparisons[group] = {"subject": subject_name,
                                  "baselines": per_baseline}

    os.makedirs(args.output, exist_ok=True)
    # per-step traces: merged over seeds (last write wins) for the figure
    trace_decisions, trace_failures = {}, {}
    for r in all_runs:
        trace_decisions.update(r["step_decisions"])
        trace_failures.update(r["step_failures"])
    payload = {
        "protocol": "docs/design/phase6_v10_adaptive_environment.md",
        "config": {
            "seeds": args.seeds, "seed_start": args.seed_start,
            "systems": systems, "r_base_modes": rb_modes, "feedback_modes": fb_modes,
            "n_boot": args.n_boot,
        },
        "pool": {"size": len(pool), "classes": pool.classes()},
        "summary": {k: aggregate(v) for k, v in _LATEST.items()},
        "paired_vs_affect_memory": comparisons,
        "generational_ab": version_ab,
        "per_step_decisions": trace_decisions,
        "per_step_failures": trace_failures,
        "per_seed": all_runs,
    }
    results_path = os.path.join(args.output, "results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nresults: {results_path}")

    report_path = os.path.join(args.output, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(render_report(payload))
    print(f"report:  {report_path}")


_LATEST: dict = {}


def render_report(payload: dict) -> str:
    cfg = payload["config"]
    gen = payload.get("generational_ab") or {}
    title = "# V1.0 Adaptive Environment Benchmark"
    if gen:
        title += " (+ V1.1 coupling repair, + V1.2 channel separation)"
    L = [title, ""]
    L.append("Protocol: `docs/design/phase6_v10_adaptive_environment.md` | "
             "seeds %d..%d | bootstrap n=%d (paired over seeds)"
             % (cfg["seed_start"], cfg["seed_start"] + cfg["seeds"] - 1,
                cfg["n_boot"]))
    L.append("")
    L.append("Task pool: %d tasks, %d classes. Non-stationary phases: "
             "SAFE x40 -> DANGER x40 (abrupt) -> RECOVERY x40. "
             "All metrics: **lower is better**."
             % (payload["pool"]["size"], len(payload["pool"]["classes"])))
    L.append("")

    L.append("## Verdict")
    L.append("")
    L.append(summarize_verdict(payload))
    L.append("")

    # ---- generational A/B chain ------------------------------------------
    AB_LABELS = {
        "v11_vs_v09": ("V1.1 vs V0.9",
                       "`affect_memory_v11 - affect_memory`: W_AFFECT 0.15 -> "
                       "0.50 and the threshold shift reversed. "
                       "Diagnosed in design doc 6.2b."),
        "v12_vs_v11": ("V1.2 vs V1.1",
                       "`affect_memory_v12 - affect_memory_v11`: task-level "
                       "`uncertainty` moved out of `verification_budget` into "
                       "its own W_UNC = 0.05 channel. Diagnosed in 6.2d."),
        "v13_vs_v12": ("V1.3 vs V1.2 (aggressive decay)",
                       "`affect_memory_v13 - affect_memory_v12`: decay() is "
                       "finally called in the closed loop, half_life = 10 so "
                       "the state can unwind inside one 40-step phase. "
                       "Pre-registered in 6.6."),
        "v13b_vs_v12": ("V1.3b vs V1.2 (V0.9's half_life = 40)",
                        "`affect_memory_v13b - affect_memory_v12`: same wiring "
                        "but the faithful V0.9 constant, which the measurement "
                        "in 6.6.2 shows cannot unwind in 40 steps."),
        "v14_vs_v13": ("V1.4 vs V1.3 (decay trigger: steps, not feedback)",
                       "`affect_memory_v14 - affect_memory_v13`: the decay call "
                       "moves from `observe()` (once per received feedback) to "
                       "`act()` (once per environment step). Pre-registered in "
                       "6.8."),
        "v14b_vs_v13": ("V1.4b vs V1.3 (same trigger, half_life=40)",
                        "`affect_memory_v14b - affect_memory_v13`: per-step "
                        "trigger with V0.9's own 40 constant."),
        "v16_vs_v14b": ("V1.6 vs V1.4b (bounded affect authority)",
                        "`affect_memory_v16 - affect_memory_v14b`: the ONE "
                        "structural constraint `s_final = min(s_affect, "
                        "s_objective + 1)` — affect may escalate at most one "
                        "level and may never de-escalate. Pre-registered "
                        "in design doc 6.13."),
    }
    for key, (label, blurb) in AB_LABELS.items():
        blocks = gen.get(key) or {}
        if not blocks:
            continue
        L.append("## %s" % label)
        L.append("")
        L.append(blurb)
        L.append("")
        L.append("| metric | " + " | ".join(sorted(blocks)) + " |")
        L.append("|" + "---|" * (len(blocks) + 1))
        for metric in HEADLINE:
            cells = []
            for group in sorted(blocks):
                ci = blocks[group].get(metric)
                if not ci:
                    cells.append("n/a")
                    continue
                mark = "**" if ci.get("significant") else ""
                cells.append("%s%+.3f [%+.3f, %+.3f]%s"
                             % (mark, ci["mean"], ci["ci_lo"],
                                ci["ci_hi"], mark))
            L.append("| %s | %s |" % (metric, " | ".join(cells)))
        L.append("")
        L.append("Negative = newer version better (lower is better). `**` "
                 "marks CIs excluding 0.")
        L.append("")

    # ---- subject vs every baseline ----------------------------------------
    for group, block in payload["paired_vs_affect_memory"].items():
        rb, fb = group.split("|")
        subject = block.get("subject", "affect_memory")
        per_base = block.get("baselines", {})
        if not per_base:
            continue
        L.append("## %s vs baselines - r_base = `%s`, feedback = `%s`"
                 % (subject, rb, fb))
        L.append("")
        L.append("| metric | " + " | ".join(sorted(per_base)) + " |")
        L.append("|" + "---|" * (len(per_base) + 1))
        by_metric = {m: {} for m in HEADLINE}
        for base, entry in per_base.items():
            for metric, ci in entry.items():
                by_metric.setdefault(metric, {})[base] = ci
        for metric in HEADLINE:
            cells = []
            for base in sorted(per_base):
                ci = by_metric.get(metric, {}).get(base)
                if not ci:
                    cells.append("n/a")
                    continue
                mark = "**" if ci.get("significant") else ""
                cells.append("%s%+.3f [%+.3f, %+.3f]%s"
                             % (mark, ci["mean"], ci["ci_lo"],
                                ci["ci_hi"], mark))
            L.append("| %s | %s |" % (metric, " | ".join(cells)))
        L.append("")
        L.append("Each cell is the **paired** difference `%s - baseline` "
                 "(mean [95%% CI]); negative = %s better (lower is better). "
                 "`**` marks CIs that exclude 0." % (subject, subject))
        L.append("")

    L.append("## Per-regime system means")
    L.append("")
    L.append("| system | regime | unsafe | false-esc | cost J | adapt delay | "
             "recover delay |")
    L.append("|---|---|---|---|---|---|---|")
    for key, agg in sorted(payload["summary"].items()):
        sysname, rb, fb = key.split("|")

        def cell(metric, _agg=agg):
            v = _agg[metric]["mean"]
            return "n/a" if v is None else "%.3f" % v

        L.append("| %s | %s/%s | %s | %s | %s | %s | %s |"
                 % (sysname, rb, fb, cell("unsafe_execution"),
                    cell("false_escalation"), cell("cumulative_cost"),
                    cell("adaptation_delay"), cell("recovery_delay")))
    L.append("")
    L.append("## How to read this")
    L.append("")
    L.append("The generational A/B tables isolate ONE mechanism change each, "
             "on identical environments and seeds; the baseline tables pit the "
             "newest generation against the five baselines. Negative paired "
             "differences are better (all metrics are lower-is-better). CIs "
             "excluding 0 are the only cells the protocol treats as evidence; "
             "everything else is noise and is reported as noise.")
    L.append("")
    return "\n".join(L)


def _tally(blocks) -> dict:
    """Count significant wins / losses / ties over nested paired-CI blocks."""
    wins = losses = ties = 0
    for entry in blocks:
        for metric, ci in entry.items():
            if not ci or ci.get("mean") is None:
                continue
            if not ci.get("significant"):
                ties += 1
            elif ci["mean"] < 0:
                wins += 1
            else:
                losses += 1
    return {"wins": wins, "losses": losses, "ties": ties}


def summarize_verdict(payload: dict) -> str:
    """Report the verdict from the paired CIs, so it cannot drift from them."""
    gen = payload.get("generational_ab") or {}
    lines = []

    for key, label in (("v11_vs_v09", "V1.1 vs V0.9"),
                       ("v12_vs_v11", "V1.2 vs V1.1"),
                       ("v13_vs_v12", "V1.3 vs V1.2 (aggressive decay)"),
                       ("v13b_vs_v12", "V1.3b vs V1.2 (half_life=40)"),
                       ("v14_vs_v13", "V1.4 vs V1.3 (trigger=steps)"),
                       ("v14b_vs_v13", "V1.4b vs V1.3 (trigger=steps, hl=40)"),
                       ("v16_vs_v14b", "V1.6 vs V1.4b (bounded authority)")):
        blocks = gen.get(key) or {}
        if not blocks:
            continue
        t = _tally(list(blocks.values()))
        n = t["wins"] + t["losses"] + t["ties"]
        lines.append("**%s:** across %d paired (regime x metric) cells, "
                     "**%d significant improvements, %d significant "
                     "regressions, %d ties**."
                     % (label, n, t["wins"], t["losses"], t["ties"]))

    subject = None
    baseline_blocks = []
    for _group, block in payload["paired_vs_affect_memory"].items():
        subject = block.get("subject", subject)
        for _base, entry in block.get("baselines", {}).items():
            baseline_blocks.append(entry)
    if baseline_blocks:
        t = _tally(baseline_blocks)
        n = t["wins"] + t["losses"] + t["ties"]
        lines.append("**`%s` vs the five baselines:** across %d paired "
                     "(regime x metric x baseline) cells, **%d significant "
                     "wins, %d significant losses, %d ties**."
                     % (subject, n, t["wins"], t["losses"], t["ties"]))

    if not lines:
        return "No paired comparisons were produced (missing systems)."

    lines.append("")
    lines.append("A generation that wins on one regime but regresses on "
                 "another has produced a trade-off, not a Pareto "
                 "improvement; where that happened the report keeps it. "
                 "Diagnostics: "
                 "`docs/design/phase6_v10_adaptive_environment.md` 6.2.")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
