"""
interaction_policy.py (V1.0 - P1-c)
===================================
Interaction policy: RESPOND / ASK / WAIT / CLARIFY / PROACTIVE.

Why a policy at all: the P0 core answers "how cautious should the agent
be?", not "what should it *do*".  The roadmap requires an explicit,
auditable decision layer that consumes

  * the fast affective state (P0 core — threat / anxiety right now),
  * the slow stable traits (P1-a — control_preference, proactivity …),
  * the ask ledger / pending threads (P1-b — the Askability Gate),

and emits exactly one interaction action per turn.  The presentation
layer (bubble planner, emoji, timing) stays *downstream* of this module.

Action semantics:

  RESPOND   answer / act now
  ASK       goal understood, a required fact is missing → info-gathering
  CLARIFY   the request is ambiguous (or high-risk & oversight-hungry)
            → restate understanding / ask for confirmation
  WAIT      do nothing now — no question is worth asking and answering
            would be irresponsible
  PROACTIVE unsolicited outreach, only when the gate tolerates it
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from emotion_agent.working_memory import (
    AskLedger,
    AskProposal,
    AskabilityGate,
    ProactiveDecision,
    ThreadRegister,
)

# Action vocabulary (stable strings — the benchmark logs them verbatim).
RESPOND = "RESPOND"
ASK = "ASK"
WAIT = "WAIT"
CLARIFY = "CLARIFY"
PROACTIVE = "PROACTIVE"
ACTIONS = (RESPOND, ASK, WAIT, CLARIFY, PROACTIVE)


@dataclass(frozen=True)
class PolicyInputs:
    """Everything the policy needs to judge one turn."""

    #: the human's message ("" for a pure proactive evaluation)
    user_message: str = ""
    #: required fields the agent still lacks (e.g. ["target_env"])
    missing_fields: List[str] = field(default_factory=list)
    #: how well the agent believes it understood the request [0, 1]
    task_confidence: float = 0.8
    #: risk level of the action under consideration [0, 1]
    risk_level: float = 0.0
    #: how time-critical acting is [0, 1]
    urgency: float = 0.5
    #: expected value of asking (information gain) [0, 1]
    information_gain: float = 0.5
    #: unsolicited outreach evaluation (no user message)
    proactive_requested: bool = False


@dataclass(frozen=True)
class InteractionDecision:
    """One auditable interaction decision."""

    action: str
    confidence: float
    reasons: List[str] = field(default_factory=list)
    #: True when RESPOND fires under uncertainty — the presentation/runtime
    #: layer should slow down and raise its verification budget.
    cautious: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {"action": self.action,
                "confidence": round(self.confidence, 4),
                "reasons": list(self.reasons),
                "cautious": self.cautious}


class InteractionPolicy:
    """History-conditioned interaction policy (fast + slow + gate)."""

    #: below this task confidence the request itself is ambiguous → CLARIFY
    CLARIFY_CONFIDENCE = 0.55
    #: risk at/above this demands confirmation when the human wants it
    CONFIRM_RISK = 0.60
    #: fast-state threat at/above this adds caution even for "safe" asks
    THREAT_CAUTION = 0.70
    #: slow-state control preference at/above this → confirm before acting
    CONTROL_CONFIRM = 0.60

    def __init__(self, gate: AskabilityGate,
                 ledger: Optional[AskLedger] = None,
                 threads: Optional[ThreadRegister] = None):
        self.gate = gate
        # explicit None checks: AskLedger/ThreadRegister are truthy containers,
        # so ``ledger or AskLedger()`` would silently swap an *empty* shared
        # ledger for a private one (found by the P2 companion adapter).
        self.ledger = ledger if ledger is not None else AskLedger()
        self.threads = threads if threads is not None else ThreadRegister()

    # -- helpers -------------------------------------------------------------------
    def _ask_proposal(self, inputs: PolicyInputs) -> AskProposal:
        """Synthesize the question the policy *would* ask, so the gate can
        judge the real thing instead of a hypothetical.  The original
        request travels as ``context`` so a re-ask of the same topic is
        caught even when the wording differs."""
        if inputs.missing_fields:
            question = "please provide " + ", ".join(inputs.missing_fields)
        else:
            question = ("confirm before acting: "
                        + (inputs.user_message or "planned action")[:48])
        return AskProposal(question=question,
                           information_gain=inputs.information_gain,
                           urgency=inputs.urgency,
                           proactive=False,
                           context=inputs.user_message)

    def _confirm_proposal(self, inputs: PolicyInputs) -> AskProposal:
        return AskProposal(
            question="confirm before acting: "
                     + (inputs.user_message or "planned action")[:48],
            information_gain=max(inputs.information_gain, inputs.risk_level),
            urgency=inputs.urgency,
            proactive=False,
            context=inputs.user_message)

    def propose_question(self, inputs: PolicyInputs,
                         fast_state: Optional[Dict[str, float]] = None,
                         slow=None) -> AskProposal:
        """The question :meth:`decide` would put to the gate for ``inputs``.

        Public so the outer layer (e.g. the companion adapter) can record
        *exactly* the text the gate judged — the ask ledger must contain
        the judged proposal, not a rephrased one, or duplicate detection
        drifts.  :meth:`decide` delegates here so the two cannot diverge.
        """
        fast_state = fast_state or {}
        threat = float(fast_state.get("threat", 0.0))
        control_pref = (float(getattr(slow, "control_preference", 0.5))
                        if slow is not None else 0.5)
        ambiguous = inputs.task_confidence < self.CLARIFY_CONFIDENCE
        needs_fact = bool(inputs.missing_fields)
        needs_confirm = (inputs.risk_level >= self.CONFIRM_RISK
                         and (control_pref >= self.CONTROL_CONFIRM
                              or threat >= self.THREAT_CAUTION))
        if needs_confirm and not (needs_fact or ambiguous):
            return self._confirm_proposal(inputs)
        return self._ask_proposal(inputs)

    # -- decision ---------------------------------------------------------------------
    def decide(self,
               inputs: PolicyInputs,
               fast_state: Optional[Dict[str, float]] = None,
               slow=None,
               now: Optional[float] = None) -> InteractionDecision:
        fast_state = fast_state or {}
        threat = float(fast_state.get("threat", 0.0))
        anxiety = float(fast_state.get("anxiety", 0.0))
        control_pref = (float(getattr(slow, "control_preference", 0.5))
                        if slow is not None else 0.5)

        # -- proactive branch: no user message, pure gate decision ---------------
        if inputs.proactive_requested and not inputs.user_message:
            proposal = AskProposal(
                question="proactive check-in",
                information_gain=inputs.information_gain,
                urgency=inputs.urgency,
                proactive=True)
            decision: ProactiveDecision = self.gate.evaluate(
                proposal, self.ledger, self.threads, slow=slow, now=now)
            if decision.action == "PROACTIVE":
                return InteractionDecision(
                    action=PROACTIVE,
                    confidence=decision.confidence,
                    reasons=list(decision.reasons))
            return InteractionDecision(
                action=WAIT,
                confidence=decision.confidence,
                reasons=list(decision.reasons))

        if not inputs.user_message:
            return InteractionDecision(
                action=WAIT, confidence=0.5,
                reasons=["no_user_message_and_no_proactive_request"])

        ambiguous = inputs.task_confidence < self.CLARIFY_CONFIDENCE
        needs_fact = bool(inputs.missing_fields)
        needs_confirm = (inputs.risk_level >= self.CONFIRM_RISK
                         and (control_pref >= self.CONTROL_CONFIRM
                              or threat >= self.THREAT_CAUTION))

        # -- clear path: answer now ----------------------------------------------
        if not (ambiguous or needs_fact or needs_confirm):
            reasons = ["request_understood", "risk_below_confirm_threshold"]
            if threat >= self.THREAT_CAUTION or anxiety >= self.THREAT_CAUTION:
                reasons.append("fast_state_elevated_but_safe_request")
            confidence = min(1.0, 0.5 + 0.3 * inputs.task_confidence
                             + 0.2 * (1.0 - threat))
            return InteractionDecision(
                action=RESPOND, confidence=round(confidence, 4),
                reasons=reasons)

        # -- something is missing: ask, if the gate allows -----------------------
        proposal = self.propose_question(inputs, fast_state, slow)
        decision = self.gate.evaluate(
            proposal, self.ledger, self.threads, slow=slow, now=now)

        if decision.action == "ASK":
            if needs_confirm and not (needs_fact or ambiguous):
                return InteractionDecision(
                    action=CLARIFY,
                    confidence=decision.confidence,
                    reasons=list(decision.reasons) + ["confirm_high_risk_action"])
            if ambiguous and not needs_fact:
                return InteractionDecision(
                    action=CLARIFY,
                    confidence=decision.confidence,
                    reasons=list(decision.reasons) + ["ambiguous_request"])
            return InteractionDecision(
                action=ASK,
                confidence=decision.confidence,
                reasons=list(decision.reasons) + ["missing_required_fact"])
            # (never reached; kept for explicit structure)

        # Gate said WAIT — degrade gracefully instead of going silent.
        gate_reasons = list(decision.reasons)
        if needs_confirm:
            # High-risk + oversight-hungry + not allowed to ask ⇒ do nothing.
            return InteractionDecision(
                action=WAIT,
                confidence=decision.confidence,
                reasons=gate_reasons + ["confirmation_blocked_high_risk"])
        if ambiguous or needs_fact:
            # Answer with what we know, flagged as cautious.
            return InteractionDecision(
                action=RESPOND,
                confidence=round(0.4 + 0.3 * inputs.task_confidence, 4),
                reasons=gate_reasons + ["clarification_deferred_respond_cautiously"],
                cautious=True)
        return InteractionDecision(
            action=RESPOND,
            confidence=round(0.5 + 0.3 * inputs.task_confidence, 4),
            reasons=gate_reasons + ["question_deferred_respond_with_knowns"],
            cautious=True)
