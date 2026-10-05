"""
plot_adaptive_curves.py (V1.0)
===============================
Figure for the Adaptive Environment Benchmark: per-10-step escalation rate
(and, when the trace carries it, unsafe-execution rate) across the three
non-stationary phases.

Frozen protocol: docs/design/phase6_v10_adaptive_environment.md §5.

Window-level curves — not phase averages — because "adapts in DANGER, then
hands control back in RECOVERY" is only visible per window.

Usage:
    python experiments/adaptive_v10/plot_adaptive_curves.py \
        [--input results/v10_adaptive/results.json] [--output results/v10_adaptive]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_INPUT = os.path.join(PROJECT_ROOT, "results", "v10_adaptive", "results.json")
DEFAULT_OUTPUT = DEFAULT_INPUT[:-len("results.json")] if False else PROJECT_ROOT

SYSTEM_ORDER = ["stateless", "memory_only", "affect_only", "affect_memory",
                "ewma", "bayes_hazard"]
SYSTEM_STYLE = {
    "stateless":     {"color": "#7f7f7f", "ls": "--", "label": "stateless"},
    "memory_only":   {"color": "#1f77b4", "ls": "-",  "label": "memory-only"},
    "affect_only":   {"color": "#2ca02c", "ls": "-",  "label": "affect-only"},
    "affect_memory": {"color": "#d62728", "ls": "-",  "label": "affect+memory"},
    "ewma":          {"color": "#ff7f0e", "ls": "-.", "label": "EWMA"},
    "bayes_hazard":  {"color": "#9467bd", "ls": ":",  "label": "Bayes hazard"},
}


def load_trace(path: str):
    """Return ({(system, rb, fb): {step: decision}}, {(sys, rb, fb, step): failed})."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("per_step_decisions")
    if not raw:
        raise SystemExit(
            f"{path} has no `per_step_decisions`; regenerate it with "
            "run_adaptive_benchmark.py (it always writes the trace).")
    grouped = defaultdict(dict)
    for key_step, decision in raw.items():
        sysname, rb, fb, step = key_step.split("##")
        grouped[(sysname, rb, fb)][int(step)] = decision
    failed = {}
    for key_step, flag in (data.get("per_step_failures") or {}).items():
        sysname, rb, fb, step = key_step.split("##")
        failed[(sysname, rb, fb, int(step))] = bool(flag)
    return grouped, failed


def rolling(flags, window):
    if len(flags) < window:
        return list(range(1, len(flags) + 1)), [], []
    xs = list(range(window, len(flags) + 1))
    ys = [sum(flags[k - window:k]) / window for k in range(window, len(flags) + 1)]
    cum = []
    running = 0.0
    for i, f in enumerate(flags, start=1):
        running += f
        if i >= window:
            cum.append(running / i)
    return xs, ys, cum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default="")
    parser.add_argument("--window", type=int, default=10)
    args = parser.parse_args()

    out = args.output or os.path.join(
        os.path.dirname(os.path.abspath(args.input)), "adaptive_benchmark_curves.png")
    if os.path.isdir(out) or not out.endswith(".png"):
        out = os.path.join(out, "adaptive_benchmark_curves.png")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    grouped, failed = load_trace(args.input)
    rb_modes = sorted({rb for (_s, rb, _f) in grouped})
    fb_modes = sorted({fb for (_s, _r, fb) in grouped})
    have_failures = bool(failed)

    kinds = ["unsafe", "escalation"] if have_failures else ["escalation"]
    fig, axes = plt.subplots(len(rb_modes) * len(kinds), len(fb_modes),
                             figsize=(7.0 * len(fb_modes),
                                      3.0 * len(rb_modes) * len(kinds)),
                             squeeze=False)
    for i, rb in enumerate(rb_modes):
        for j, fb in enumerate(fb_modes):
            for k, kind in enumerate(kinds):
                ax = axes[i * len(kinds) + k][j]
                for sysname in SYSTEM_ORDER:
                    key = (sysname, rb, fb)
                    if key not in grouped:
                        continue
                    decisions = grouped[key]
                    steps = sorted(decisions)
                    if kind == "escalation":
                        flags = [1.0 if decisions[s] in ("HUMAN_REVIEW", "BLOCK")
                                 else 0.0 for s in steps]
                    else:
                        flags = [1.0 if (decisions[s] == "AUTO_EXECUTE"
                                         and failed.get((sysname, rb, fb, s), False))
                                 else 0.0 for s in steps]
                    xs, ys, _cum = rolling(flags, args.window)
                    style = SYSTEM_STYLE[sysname]
                    ax.plot(xs, ys, color=style["color"], ls=style["ls"],
                            lw=1.8, label=style["label"])
                for boundary in (40, 80):
                    ax.axvline(boundary + 0.5, color="k", lw=0.6, ls=":")
                ylabel = ("unsafe execution rate" if kind == "unsafe"
                          else "escalation rate")
                ax.set_title(f"r_base={rb}, feedback={fb} — {ylabel} "
                             f"({args.window}-step)", fontsize=9)
                ax.set_xlabel("step (SAFE 1-40 · DANGER 41-80 · RECOVERY 81-120)")
                ax.set_ylabel(ylabel)
                ax.set_ylim(-0.02, 1.02)
                ax.grid(alpha=0.25)
                if i == 0 and j == 0 and k == 0:
                    ax.legend(fontsize=7, loc="upper left", framealpha=0.85)

    fig.suptitle("V1.0 Adaptive Environment Benchmark — window-level behaviour "
                 "across a non-stationary risk stream", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out, dpi=150)
    print(f"figure: {out}")


if __name__ == "__main__":
    main()
