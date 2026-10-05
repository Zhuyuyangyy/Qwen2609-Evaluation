"""
plot_affect_trajectory.py (V0.9)
================================
Produce the acceptance figures for V0.9:

  1. affect_state_trajectory.png — valence / arousal / anxiety / decision
     severity across an online episode for History B (dangerous) with a
     recovery block (safe evidence) appended.
  2. affect_decay_recovery.png     — anxiety decay under the agent's default
     half-life, plus the recovered trajectory after new safe evidence.

Usage:
    python experiments/benchmark_v3/plot_affect_trajectory.py
Output:
    results/benchmark_v3/affect_state_trajectory.png
    results/benchmark_v3/affect_decay_recovery.png
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emotion_agent.v09_agent import V09Agent, AgentEvent, Outcome
from emotion_agent.decay_clock import StepClock
from emotion_agent.policy_modulator import (AUTO_EXECUTE, SIMULATE_FIRST,
                                            HUMAN_REVIEW, BLOCK)

RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "benchmark_v3")
SEVERITY = {AUTO_EXECUTE: 0, SIMULATE_FIRST: 1, HUMAN_REVIEW: 2, BLOCK: 3}

TASK = "deploy the production patch"

# V1.0 (P0-2): the figures are drawn in step time (seeds at negative steps,
# feedback at integer steps), so the agents run on an explicit StepClock —
# the episodic half-life is 40 steps, and decay(dt=1.0) halves the state
# every 40 steps, exactly as the axes are labelled.
CLOCK = StepClock()


def run_online_episode() -> tuple:
    """History B: failure shock at t0, then safe successes from t=1."""
    agent = V09Agent(use_memory=True, use_affect=True, clock=CLOCK)
    agent.seed_history([
        {"task": TASK, "outcome": "failure", "risk_actual": 0.95, "severity": 2},
    ], now=-1.0)

    valence, arousal, anxiety, sev, steps = [], [], [], [], []
    # t=0: decide under shock history
    for i in range(1, 13):
        if i >= 1:  # every step after the shock, a safe success lands
            agent.receive_outcome(Outcome(risk_actual=0.05, outcome_str="success",
                                          timestamp=i * 1.0),
                                  AgentEvent(task=TASK))
        st = agent.state()
        dec = agent.decide(AgentEvent(task=TASK), now=i * 1.0).decision
        valence.append(st["valence"]); arousal.append(st["arousal"])
        anxiety.append(st["anxiety"]); sev.append(SEVERITY[dec])
        steps.append(i)
    return agent, steps, valence, arousal, anxiety, sev


def plot_trajectory():
    _agent, steps, valence, arousal, anxiety, sev = run_online_episode()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax1.plot(steps, valence, label="valence", marker="o", ms=3)
    ax1.plot(steps, arousal, label="arousal", marker="s", ms=3)
    ax1.plot(steps, anxiety, label="anxiety", marker="^", ms=3)
    ax1.axhline(0, color="grey", lw=0.6)
    ax1.set_ylabel("affective dimensions")
    ax1.legend(); ax1.set_title("Affective state during recovery (History B, safe evidence per step)")
    ax2.plot(steps, sev, marker="D", ms=4, color="crimson")
    ax2.set_yticks(list(SEVERITY.values()))
    ax2.set_yticklabels(list(SEVERITY.keys()), fontsize=8)
    ax2.set_ylabel("decision severity")
    ax2.set_xlabel("online step")
    fig.tight_layout()
    path = os.path.join(RESULTS_DIR, "affect_state_trajectory.png")
    fig.savefig(path, dpi=150)
    print(f"saved {path}")


def plot_decay_recovery():
    # decay: anxiety halves with the fitted half-life (~40 steps)
    dec = V09Agent(use_memory=True, use_affect=True, clock=CLOCK)
    dec.seed_history([{"task": TASK, "outcome": "failure", "risk_actual": 0.95, "severity": 2}])
    a0 = dec.state()["anxiety"]
    y = []
    for t in range(41):
        y.append(dec.state()["anxiety"])
        dec.decay(dt=1.0)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(range(41), y, marker="o", ms=3, label="anxiety (no feedback)")
    ax.axhline(a0 / 2, color="grey", ls="--", lw=0.8, label="half of start")
    ax.set_xlabel("decay steps"); ax.set_ylabel("anxiety")
    ax.set_title("Affective decay toward neutral (default half-life)")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(RESULTS_DIR, "affect_decay_recovery.png")
    fig.savefig(path, dpi=150)
    print(f"saved {path}")


if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)
    plot_trajectory()
    plot_decay_recovery()