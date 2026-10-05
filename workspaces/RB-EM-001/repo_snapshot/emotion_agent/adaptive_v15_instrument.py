"""
adaptive_v15_instrument.py (V1.5)
================================
Read-only instrumentation for the V1.5 cost-attribution diagnosis.

Frozen protocol: docs/design/phase6_v10_adaptive_environment.md §6.10.

HARD RULES this module obeys:
  1. It never changes a decision. `StepRecorder` only reads what the systems
     already produced (see `test_instrumentation_does_not_change_decisions`).
  2. It costs nothing the environment did not already charge — every cost
     component is *replayed* from the environment's own model
     (`adaptive_environment`'s constants), and the sum of components must equal
     the environment's charged cost (asserted by
     `test_cost_components_sum_to_step_cost`).
  3. No new policy, no new constants, no new seeds.

What it adds on top of the V0.9 runner:
  * per-step records of BOTH systems' decisions (`stateless_action`,
    `v14b_action`), so transitions can be counted;
  * decomposed cost (unsafe / review / simulate / block / opportunity);
  * the affective trajectory (threat / anxiety / confidence /
    verification_budget);
  * a spillover flag: a *low-risk unrelated* task, i.e. `r_base < 0.15` and a
    class never seen (and not present) among the last `SPILLOVER_WINDOW`
    steps — the "should this experience have touched me at all?" probe;
  * policy switch rate and threshold crossing counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from emotion_agent.adaptive_environment import (
    AdaptiveEnvironment, TaskPool, Observation, StepResult,
    AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK,
    C_FAIL, C_SIM, C_REVIEW, C_BLOCK, C_OPPORTUNITY,
    SIM_CATCH, HUMAN_CATCH, PFAIL_CAP,
)

LOW_RISK_R_BASE = 0.15          # spillover's "this task is not risky"
SPILLOVER_WINDOW = 5            # steps of history to look back over
ESCALATION_ACTIONS = (HUMAN_REVIEW, BLOCK)


def decompose_cost(decision: str, executed: bool, failed: bool,
                   danger: float, catches: Dict[str, float]) -> Dict[str, float]:
    """Replay the environment's cost model into named components.

    ``catches`` supplies the two uniform draws the environment would have made
    (``sim`` for "simulation reveals the danger", ``human`` for "reviewer
    refuses"), so this function computes exactly what the environment charged
    without re-drawing randomness.

    Returns {"unsafe", "review", "simulate", "block", "opportunity"} whose sum
    equals the step's charged cost.
    """
    out = {"cost_unsafe": 0.0, "cost_review": 0.0, "cost_simulate": 0.0,
           "cost_block": 0.0, "cost_opportunity": 0.0}

    if decision == SIMULATE_FIRST:
        out["cost_simulate"] += C_SIM
    elif decision == HUMAN_REVIEW:
        out["cost_review"] += C_REVIEW
    elif decision == BLOCK:
        out["cost_block"] += C_BLOCK

    if decision != BLOCK:
        # the gate draws decide whether the action still fires
        if decision == SIMULATE_FIRST and catches.get("sim", 1.0) < SIM_CATCH:
            return out                      # caught: no execution consequence
        if decision == HUMAN_REVIEW and catches.get("human", 1.0) < HUMAN_CATCH:
            return out                      # correctly refused: no consequence
        if failed:
            out["cost_unsafe"] += C_FAIL
    else:
        # BLOCK on an action that would have succeeded is opportunity cost
        out["cost_opportunity"] += C_OPPORTUNITY * (1.0 - danger)
    return out


@dataclass
class StepRecord:
    """Everything the diagnosis needs for one environment step."""

    step: int
    seed: int
    r_base_mode: str
    feedback: str
    phase: str
    task_class: str
    description: str
    r_base: float
    danger: float
    threat: float
    anxiety: float
    confidence: float
    verification_budget: float
    stateless_action: str
    v14b_action: str
    cost_unsafe: float
    cost_review: float
    cost_simulate: float
    cost_block: float
    cost_opportunity: float
    step_J: float
    unsafe_executed: bool
    low_risk_unrelated: bool
    delta_J_vs_stateless: float = 0.0
    step_J_reference: float = 0.0
    unsafe_executed_reference: bool = False

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


class StepRecorder:
    """Collects StepRecords for one (seed, r_base_mode, feedback) episode.

    Nothing here mutates the systems or the environment; the caller feeds it
    the two decisions and the StepResult it already got.
    """

    def __init__(self):
        self.records: List[StepRecord] = []

    def record(self, *, step, seed, r_base_mode, feedback, obs,
               state, verification_budget, stateless_action, v14b_action,
               result: StepResult, catches: Dict[str, float],
               recent_classes: List[str]) -> StepRecord:
        failed = result.failed and result.executed
        comps = decompose_cost(result.decision, result.executed, failed,
                              obs.danger, catches)
        low_risk_unrelated = (obs.r_base < LOW_RISK_R_BASE
                              and obs.task_class not in recent_classes)
        rec = StepRecord(
            step=obs.step, seed=seed, r_base_mode=r_base_mode, feedback=feedback,
            phase=obs.phase, task_class=obs.task_class,
            description=obs.description, r_base=obs.r_base, danger=obs.danger,
            threat=state.get("threat", 0.0), anxiety=state.get("anxiety", 0.0),
            confidence=state.get("confidence", 0.5),
            verification_budget=verification_budget,
            stateless_action=stateless_action, v14b_action=v14b_action,
            cost_unsafe=comps["cost_unsafe"], cost_review=comps["cost_review"],
            cost_simulate=comps["cost_simulate"], cost_block=comps["cost_block"],
            cost_opportunity=comps["cost_opportunity"],
            step_J=result.cost,
            unsafe_executed=(result.decision == AUTO_EXECUTE and failed),
            low_risk_unrelated=low_risk_unrelated,
        )
        self.records.append(rec)
        return rec


def policy_switch_rate(actions: List[str]) -> float:
    """`#(pi_t != pi_{t-1}) / (T-1)` — decision oscillation."""
    if len(actions) < 2:
        return 0.0
    switches = sum(1 for a, b in zip(actions, actions[1:]) if a != b)
    return switches / (len(actions) - 1)


def threshold_crossings(effective_risks: List[float],
                        levels=(0.35, 0.58, 0.80)) -> int:
    """How many times effective risk crosses one of the decision thresholds."""
    if len(effective_risks) < 2:
        return 0
    count = 0
    for a, b in zip(effective_risks, effective_risks[1:]):
        for lvl in levels:
            if (a < lvl <= b) or (b < lvl <= a):
                count += 1
    return count
