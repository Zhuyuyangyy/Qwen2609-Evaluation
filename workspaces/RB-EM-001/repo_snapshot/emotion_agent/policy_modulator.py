"""
policy_modulator.py (V0.9)
==========================
Policy Modulator: turn (objective risk + appraisal + affective state + episodic
memory evidence) into a decision, WITHOUT the affect layer acting as a second
"risk detector".

Design separation (docs/design/phase5_v09_affective_core_design.md):
  Risk Encoder  : how dangerous is this action, objectively (stateless).
  Affective Core: how cautious / anxious is the agent right now (history-shaped).
  PolicyModulator: under the SAME objective risk, how to shift the verification
                   budget, execution threshold and exploration tendency.

Each signal is applied exactly once (no double counting — same principle as the
Phase 4.1 threshold fix):
  * memory evidence      → moves the *effective risk* (decide)
  * affect + appraisal   → moves the *policy budget* (threshold / verification)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

AUTO_EXECUTE = "AUTO_EXECUTE"
SIMULATE_FIRST = "SIMULATE_FIRST"
HUMAN_REVIEW = "HUMAN_REVIEW"
BLOCK = "BLOCK"


@dataclass
class PolicyBudget:
    verification_budget: float = 0.0   # 0..1 — extra caution applied to effective risk
    execution_threshold: float = 0.0   # shift of the decision thresholds (signed)
    exploration_gain: float = 0.0      # -0.2..0.2 — nudge toward AUTO for low-risk novel tasks


class PolicyModulator:
    """Deterministic policy modulation (frozen constants for V0.9)."""

    BASE_THRESHOLDS = {
        "BLOCK": 0.80,
        "HUMAN_REVIEW": 0.58,
        "SIMULATE_FIRST": 0.35,
    }
    # memory -> effective-risk weights (apply once, in decide)
    NEG_MEMORY_WEIGHT = 0.60
    VERIFICATION_WEIGHT = 0.15   # affect-driven verification -> effective risk

    def modulate(
        self,
        appraisal: Dict[str, float],
        state: Dict[str, float],
        memory_hits: Optional[List[Tuple]] = None,
    ) -> PolicyBudget:
        """
        Compute the policy budget from appraisal + affective state.
        (Memory evidence is deliberately NOT included here — it is consumed
        once, in ``decide``, to keep the evidence accounting single-shot.)
        """
        budget = PolicyBudget()

        # -- affect ------------------------------------------------------------
        anxiety = state.get("anxiety", 0.0)
        control_need = state.get("control_need", 0.0)
        confidence = state.get("confidence", 0.5)
        budget.verification_budget += 0.35 * anxiety + 0.25 * control_need
        budget.execution_threshold += 0.30 * anxiety + 0.15 * control_need
        budget.verification_budget -= 0.20 * confidence
        budget.execution_threshold -= 0.15 * confidence   # confidence de-escalates caution

        # -- appraisal ----------------------------------------------------------
        uncertainty = appraisal.get("uncertainty", 0.0)
        if uncertainty > 0.4:
            budget.verification_budget += 0.20 * uncertainty
        novelty = appraisal.get("novelty", 0.0)
        agency = appraisal.get("agency", 0.5)
        if novelty > 0.6 and agency > 0.6:
            budget.exploration_gain = min(0.2, 0.2 * novelty)

        # -- appraisal: reversibility / controllability --------------------------
        # V1.0 fix (P0-4): these two dimensions were computed by the appraisal
        # layer but never consumed — a dead branch. They now modulate the
        # budget exactly once each, on top of the uncertainty term:
        # an irreversible or uncontrollable action earns extra verification
        # and a higher execution threshold regardless of its objective risk.
        irreversibility = 1.0 - max(0.0, min(1.0, appraisal.get("reversibility", 1.0)))
        uncontrollability = 1.0 - max(0.0, min(1.0, appraisal.get("controllability", 0.5)))
        budget.verification_budget += 0.25 * irreversibility + 0.15 * uncontrollability
        budget.execution_threshold += 0.20 * irreversibility + 0.15 * uncontrollability

        # -- clamp ---------------------------------------------------------------
        budget.verification_budget = max(0.0, min(1.0, budget.verification_budget))
        budget.execution_threshold = max(-0.4, min(0.5, budget.execution_threshold))
        budget.exploration_gain = max(-0.2, min(0.2, budget.exploration_gain))
        return budget

    @staticmethod
    def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, v))

    def effective_risk(
        self,
        r_base: float,
        budget: PolicyBudget,
        memory_hits: Optional[List[Tuple]] = None,
    ) -> float:
        """
        Single source of truth for the risk a decision is actually made on.

        Memory evidence is aggregated as a **score-weighted mean** over all
        retrieved memories (not the single strongest hit):

            net = (Σ s·risk_actual over failures − Σ s·1.0 over successes) / Σ s

        so repeated success on a task progressively suppresses the residual
        fear of an old failure (extinction / recovery). Then:

            effective_risk = r_base
                            + NEG_MEMORY_WEIGHT · net               (memory, once)
                            + VERIFICATION_WEIGHT · verification_budget  (affect, once)

        exploration_gain nudges low-risk risks toward AUTO_EXECUTE. The
        decision path (``decide``) and the trace path (``V09Agent.decide``)
        MUST both call this — never re-derive it — so an audit trace always
        matches the decision that was actually taken.
        """
        memory_hits = memory_hits or []
        effective = float(r_base)

        if memory_hits:
            scores_sum = sum(s for _m, s in memory_hits)
            neg_total = sum(s * m.risk_actual for m, s in memory_hits
                            if m.outcome == "failure")
            pos_total = sum(s * 1.0 for m, s in memory_hits
                            if m.outcome in ("success", "partial"))
            if scores_sum > 1e-9:
                net = (neg_total - pos_total) / scores_sum   # in [-1, 1]
                effective += self.NEG_MEMORY_WEIGHT * net
            else:
                effective += self.NEG_MEMORY_WEIGHT * (
                    max((m.risk_actual for m, _s in memory_hits if m.outcome == "failure"),
                        default=0.0))

        effective += self.VERIFICATION_WEIGHT * budget.verification_budget
        effective = self._clamp(effective)

        # exploration: novel + low-risk tasks lean toward AUTO_EXECUTE
        if budget.exploration_gain > 0 and effective < 0.30:
            effective = max(0.0, effective - budget.exploration_gain)
        return effective

    def decide(
        self,
        r_base: float,
        budget: PolicyBudget,
        memory_hits: Optional[List[Tuple]] = None,
    ) -> str:
        """
        Final 4-level decision.

        The risk the decision is taken on is ``effective_risk`` (see there);
        the base thresholds are shifted by ``budget.execution_threshold``
        (affect + appraisal, once).
        """
        effective = self.effective_risk(r_base, budget, memory_hits)

        shifted = {k: v + budget.execution_threshold for k, v in self.BASE_THRESHOLDS.items()}
        if effective >= shifted["BLOCK"]:
            return BLOCK
        if effective >= shifted["HUMAN_REVIEW"]:
            return HUMAN_REVIEW
        if effective >= shifted["SIMULATE_FIRST"]:
            return SIMULATE_FIRST
        return AUTO_EXECUTE