"""AgentShield V3 - Risk Signal and Graph Risk State models.

These types replace the old approach where risk_score was passed in
externally. Now the engine computes risk from behavior graph signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Ceiling applied to the *suppressible* band when the operator explicitly
# authorised the action. Authorisation may explain provenance-derived
# suspicion; it cannot authorise away independently dangerous behaviour, so it
# never touches the structural band.
AUTHORISED_ACTION_CEILING = 0.55


class RiskSignalType(str, Enum):
    """Types of risk signals that can be detected from a tool event."""
    SENSITIVE_SOURCE = "sensitive_source"
    EXTERNAL_SINK = "external_sink"
    PRIVILEGE_CHANGE = "privilege_change"
    AUDIT_TAMPER = "audit_tamper"
    BULK_OPERATION = "bulk_operation"
    CREDENTIAL_ACCESS = "credential_access"
    CROSS_AGENT_DELEGATION = "cross_agent_delegation"
    POLICY_EVASION = "policy_evasion"
    # ── Provenance / taint signals (stage D-F) ──────────────────────────
    # These look at *where content came from*, which is what a single-event
    # guardrail structurally cannot see.
    UNTRUSTED_INSTRUCTION = "untrusted_instruction"
    DESTINATION_PROVENANCE = "destination_provenance"
    INTENT_ORIGIN_MISMATCH = "intent_origin_mismatch"
    SENSITIVE_TO_EXTERNAL_FLOW = "sensitive_to_external_flow"
    UNTRUSTED_TO_PRIVILEGED_ACTION = "untrusted_to_privileged_action"
    # An entity introduced by untrusted content reaching this call. This is a
    # *propagation* fact, not a delegation: cross-agent delegation is a
    # structural relationship between agents, and conflating the two meant that
    # tempering taint would also have tempered genuine delegation risk.
    TAINT_PROPAGATION = "taint_propagation"
    # ── Trust calibration signals (v0.4) ────────────────────────────────
    # These *temper* risk rather than raise it: they record why a call the
    # presence-based rules would flag is in fact authorised or benign.
    USER_AUTHORIZED_ACTION = "user_authorized_action"
    TRUSTED_ENTITY_RESOLUTION = "trusted_entity_resolution"


# ─── Signal classification ────────────────────────────────────────────────
# ``combined_risk`` splits into two bands that authorisation may not bridge:
#
#   unsuppressible -- danger that is true regardless of who asked. A bulk
#                     delete, a privilege change, an instruction that arrived
#                     untrusted, sensitive material leaving the boundary.
#                     Authorisation explains provenance; it cannot pardon an
#                     independently dangerous action.
#   suppressible   -- provenance alarms whose whole content is "this came from
#                     somewhere the operator did not name": destination
#                     provenance, intent-origin mismatch, taint propagation.
#                     These are what authorisation legitimately tempers.
#
# The design invariant of v0.4.1: authorization may explain provenance-derived
# suspicion, but it cannot authorize away independently dangerous behavior.

UNSUPPRESSIBLE_SIGNALS = frozenset({
    # Hard structural violations of the call itself. The operator asking for
    # them does not make them safe.
    RiskSignalType.PRIVILEGE_CHANGE,
    RiskSignalType.AUDIT_TAMPER,
    RiskSignalType.BULK_OPERATION,
    RiskSignalType.CREDENTIAL_ACCESS,
    RiskSignalType.POLICY_EVASION,
    # Content that arrived untrusted and reads as an instruction is evidence of
    # manipulation, not of provenance.
    RiskSignalType.UNTRUSTED_INSTRUCTION,
    RiskSignalType.UNTRUSTED_TO_PRIVILEGED_ACTION,
    # The exfiltration is the harm, whoever named the destination.
    RiskSignalType.SENSITIVE_TO_EXTERNAL_FLOW,
    # A delegation relationship is structural, not a provenance accident.
    RiskSignalType.CROSS_AGENT_DELEGATION,
})

SUPPRESSIBLE_PROVENANCE_SIGNALS = frozenset({
    RiskSignalType.DESTINATION_PROVENANCE,
    RiskSignalType.INTENT_ORIGIN_MISMATCH,
    RiskSignalType.TAINT_PROPAGATION,
})

# Suppression evidence: these may lower the suppressible band. They are *not*
# risk themselves -- a "this is a trusted resolution" observation must never be
# able to manufacture a score out of nothing.
SUPPRESSION_EVIDENCE_SIGNALS = frozenset({
    RiskSignalType.USER_AUTHORIZED_ACTION,
    RiskSignalType.TRUSTED_ENTITY_RESOLUTION,
})

_CLASSIFIED_SIGNALS = (
    UNSUPPRESSIBLE_SIGNALS
    | SUPPRESSIBLE_PROVENANCE_SIGNALS
    | SUPPRESSION_EVIDENCE_SIGNALS
)


@dataclass
class RiskSignal:
    """A single risk signal detected from a tool event or graph context.

    Signals are the atomic units of risk evidence. Multiple signals
    are combined by the GraphRiskState to produce a final risk score.
    """
    signal_type: RiskSignalType
    score: float  # 0.0 - 1.0
    evidence: List[str] = field(default_factory=list)
    source_event_id: str = ""
    # Artifacts this signal was derived from. Provenance signals use it so a
    # decision can be explained as "destination X first appeared in artifact Y".
    artifact_ids: List[str] = field(default_factory=list)
    # Kept for construction compatibility. ``combined_risk`` derives the
    # suppression band from the classification frozensets above rather than
    # from per-signal fields, so a cap cannot be attached to a signal that
    # ought to be unsuppressible.
    caps_risk: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type.value,
            "score": round(self.score, 4),
            "evidence": self.evidence,
            "source_event_id": self.source_event_id,
        }


@dataclass
class GraphRiskState:
    """Risk state derived from the behavior graph.

    This replaces the old approach of using a single externally-provided
    risk_score. The final risk is computed from multiple graph-derived signals.
    """
    local_risk: float = 0.0         # Risk from the current event alone
    inherited_risk: float = 0.0     # Risk propagated from upstream nodes
    downstream_exposure: float = 0.0  # Risk exposure to downstream nodes
    path_risk: float = 0.0          # Max risk along the critical path
    intervention_value: float = 0.0  # Value of intervening at this point
    confidence: float = 1.0         # Confidence in the risk assessment
    signals: List[RiskSignal] = field(default_factory=list)

    @property
    def combined_risk(self) -> float:
        """Compute the final combined risk score from all components.

        The score is the **maximum** of the individual components, so a single
        decisive signal is never diluted by unrelated ones that happen to be
        zero. The previous weighted sum gave local_risk only 0.35 of the total
        and then multiplied by ``confidence``, which is a measure of *how much
        evidence* was seen, not of how dangerous the event is. A lone bulk
        delete scored local_risk=0.5 and came out at 0.14 -- under the 0.60
        review threshold -- so destructive operations were allowed.

        ``confidence`` now scales the result only mildly and never below the
        floor implied by the evidence: with no signals at all the score is 0
        regardless of confidence.

        Preserved invariant: when every component equals ``x`` and
        ``confidence == 1.0``, ``combined_risk == x``.
        """
        # ---------------------------------------------------------------
        # Two bands, with one gate between them and no bridge across it.
        # ---------------------------------------------------------------
        # Runtime and graph structural risk is never suppressible, whatever
        # the signals say.
        structural_components = [
            self.local_risk,
            self.inherited_risk,
            self.path_risk,
            self.downstream_exposure,
        ]

        hard_signal_scores: List[float] = []
        suppressible_scores: List[float] = []
        for signal in self.signals:
            if signal.signal_type in SUPPRESSIBLE_PROVENANCE_SIGNALS:
                suppressible_scores.append(signal.score)
            elif signal.signal_type in SUPPRESSION_EVIDENCE_SIGNALS:
                # Evidence, not risk. Recording that the operator authorised a
                # call must not, by itself, raise the score above zero.
                continue
            elif signal.signal_type in UNSUPPRESSIBLE_SIGNALS:
                hard_signal_scores.append(signal.score)
            else:
                # Fail closed for any future risk signal type: an unknown
                # signal is hard unless it is explicitly classified otherwise.
                hard_signal_scores.append(signal.score)

        hard_peak = max(
            [*structural_components, *hard_signal_scores],
            default=0.0,
        )
        suppressible_peak = max(suppressible_scores, default=0.0)

        # Authorisation caps the provenance band only. The lowest explicit
        # cap wins, so an authorisation still overrides a weaker
        # trusted-entity ceiling if that ablation is ever re-enabled.
        caps = [
            s_.caps_risk for s_ in self.signals
            if s_.caps_risk is not None
            and s_.signal_type in SUPPRESSION_EVIDENCE_SIGNALS
        ]
        if caps:
            suppressible_peak = min([suppressible_peak, *caps])

        peak = max(hard_peak, suppressible_peak)

        # Counterfactual / intervention risk must not be pardoned by
        # authorisation: it measures the value of stopping here, not who asked.
        if self.intervention_value > peak:
            peak = self.intervention_value

        # No confidence discount and no intervention bonus in the base case, so
        # that "all components equal x, confidence 1.0" yields exactly x -- the
        # invariant test_api_routes._make_risk_state relies on.
        #
        # ``confidence`` measures how much evidence was seen, not how dangerous
        # the event is. Discounting by it meant a single decisive signal
        # (confidence 0.6, i.e. "one signal, short chain") could never reach
        # the BLOCK threshold, which is exactly the thin-evidence case where
        # over-blocking is the safer error. It is therefore reported but does
        # not reduce the score.
        return max(0.0, min(1.0, peak))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "local_risk": round(self.local_risk, 4),
            "inherited_risk": round(self.inherited_risk, 4),
            "downstream_exposure": round(self.downstream_exposure, 4),
            "path_risk": round(self.path_risk, 4),
            "intervention_value": round(self.intervention_value, 4),
            "confidence": round(self.confidence, 4),
            "combined_risk": round(self.combined_risk, 4),
            "signals": [s.to_dict() for s in self.signals],
        }
