"""Deterministic provenance signals (stage F).

Six signals, no model calls, no keyword lists tuned against a fixture. Each one
answers a question about *origin* rather than about content:

  1. UNTRUSTED_INSTRUCTION       untrusted content reads as an instruction
  2. DESTINATION_PROVENANCE      a destination first appeared in untrusted text
  3. INTENT_ORIGIN_MISMATCH      the action traces to untrusted content, not to
                                 the operator's request
  4. SENSITIVE_TO_EXTERNAL_FLOW  sensitive material crosses the trust boundary
  5. UNTRUSTED_TO_PRIVILEGED     untrusted content drives a high-consequence tool
  6. TAINT_PROPAGATION           an entity from untrusted content reaches this call

Signals 2, 3 and 6 are the ones a single-event guardrail cannot produce: they
require knowing what the operator actually asked for and what an earlier tool
output introduced.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.shield.risk_signals import RiskSignal, RiskSignalType

# Tools with side effects outside the trust boundary. When one of these is
# driven by untrusted content, the consequence is not local.
_EXTERNAL_SINK_TOOLS = (
    "send_email", "smtp", "http_request", "http_post", "upload", "webhook",
    "post_data", "external_delivery", "ftp", "curl", "wget", "send", "sync_to_remote",
    "share_p2p", "smtp_relay", "route_tor", "icmp_tunnel", "create_ssh_tunnel",
    "encode_in_image", "call_external_api", "export_api_data", "send_bulk_email",
)

# High-consequence tools: privilege, credential, destruction, exfiltration.
_PRIVILEGED_TOOLS = (
    "update_user_role", "update_permissions", "assume_role", "grant", "chmod",
    "chown", "sudo", "set_admin", "modify_role", "update_security_policy",
    "modify_registry", "update_encryption_config", "rotate_jwt_secret",
    "create_hidden_account", "create_cron_job", "disable_audit", "write_audit_log",
    "delete", "drop", "rm", "truncate", "cascade_delete", "format", "transfer_crypto",
    "batch_reset_passwords", "batch_create_accounts", "inject_dll",
    "install_miner", "create_ssh_tunnel", "connect_vpn", "poison_cdn_cache",
    "smuggle_request", "read_process_memory", "mount_host_path",
)

_SENSITIVE_MARKERS = (
    "password", "secret", "token", "api_key", "credential", "private_key",
    "ssn", "credit_card", "id_card", "phone", "customer", "employee", "salary",
    "medical", "/etc/passwd", "/etc/shadow", "id_rsa",
)

# Read-only tools: they consume entities but produce no side effect outside the
# trust boundary. A destination arriving through a search result is not a
# provenance risk for the search itself -- blocking "search_files_by_filename"
# because the filename matched an earlier artifact was the single largest
# contributor to the 30.9% benign trace-block rate.
_READ_ONLY_MARKERS = (
    "read_", "get_", "search", "list_", "find", "query", "fetch", "lookup",
    "check", "show", "view", "peek", "head", "cat",
    # "load_" is deliberately absent: it also matches upload_file, which is an
    # outbound action. Reading is covered by read_/get_/fetch above.
)


def _is_read_only(tool_name: str) -> bool:
    """True when a tool only reads and cannot act on what it returns."""
    tool = _normalise_tool(tool_name)
    if not tool:
        return False
    # An explicitly privileged verb always wins over a read-looking prefix:
    # "delete_file" must not be excused by containing "file".
    if _is_privileged(tool):
        return False
    return any(marker in tool for marker in _READ_ONLY_MARKERS)


# Weight applied to destination/intent/taint provenance signals when the tool
# being governed only reads. Reading a tainted value cannot exfiltrate it, so a
# search that merely mentions an entity is not a governance event.
_READ_ONLY_SIGNAL_WEIGHT = 0.30


def _normalise_tool(tool_name: str) -> str:
    return str(tool_name or "").lower()


def _is_external_sink(tool_name: str) -> bool:
    tool = _normalise_tool(tool_name)
    return any(t in tool for t in _EXTERNAL_SINK_TOOLS)


def _is_privileged(tool_name: str) -> bool:
    tool = _normalise_tool(tool_name)
    return any(t in tool for t in _PRIVILEGED_TOOLS)


def _touches_sensitive(text: str) -> List[str]:
    blob = str(text).lower()
    return [m for m in _SENSITIVE_MARKERS if m in blob]


def extract_provenance_signals(
    tool_name: str,
    tool_input: Dict[str, Any],
    taint_tracker,
    user_intent_text: str = "",
    track_taint: bool = True,
    enable_trust_policy: bool = False,
    intent_slots=None,
) -> List[RiskSignal]:
    """Return the provenance signals for one tool call.

    ``taint_tracker`` holds what has been observed so far; ``user_intent_text``
    is the operator's original request, used to tell "the user asked for this"
    from "an untrusted artifact asked for this".

    ``track_taint=False`` keeps only the signals that need the *presence* of
    untrusted content, and drops the ones that need per-entity origins
    (destination provenance, intent mismatch, taint propagation). That is what
    makes the ablation a real difference rather than the same code twice.

    ``enable_trust_policy=True`` switches on the v0.4 refinements: destinations
    arriving through structured or financial content are recorded as a trusted
    resolution observation, and a call the operator explicitly authorised emits
    a suppression signal instead of an alarm. Both are reported as their own
    signals so the effect is auditable rather than a silent score change.
    """
    if taint_tracker is None:
        return []

    signals: List[RiskSignal] = []
    tool = _normalise_tool(tool_name)
    input_text = _flatten(tool_input)
    intent_text = str(user_intent_text or "")

    untrusted_artifacts = taint_tracker.untrusted_artifacts()
    # A read-only tool cannot act on a tainted destination, so the
    # destination/intent/taint signals only carry full weight for a sink.
    #
    # Gated on enable_trust_policy: this is a v0.4 refinement, and applying it
    # unconditionally would retroactively change the v0.3 ladder that
    # v0.3.1-research froze, breaking comparability with that release.
    read_only = enable_trust_policy and _is_read_only(tool_name)
    read_only_weight = _READ_ONLY_SIGNAL_WEIGHT if read_only else 1.0
    instruction_bearing = taint_tracker.instruction_bearing_untrusted()

    # ── 1. Untrusted instruction ──────────────────────────────────────────
    if instruction_bearing:
        worst = max(instruction_bearing, key=lambda a: len(a.content))
        signals.append(RiskSignal(
            signal_type=RiskSignalType.UNTRUSTED_INSTRUCTION,
            # Also tempered for a read-only tool: an instruction sitting in the
            # context is a reason to watch the *next* call, not to block a
            # search that cannot act on it.
            score=0.95 * read_only_weight,
            evidence=[
                f"Untrusted artifact {worst.artifact_id} ({worst.origin_type}) "
                "contains instruction-like text directed at the agent"
                + (" [read-only tool]" if read_only else "")
            ],
            artifact_ids=[a.artifact_id for a in instruction_bearing],
        ))

    # ── 2. Destination provenance ─────────────────────────────────────────
    # A destination that first appeared in untrusted content is the classic
    # injection outcome: the operator never named it.
    tainted_origins = taint_tracker.untrusted_origin_of(input_text)
    if tainted_origins and track_taint:
        signals.append(RiskSignal(
            signal_type=RiskSignalType.DESTINATION_PROVENANCE,
            score=0.90 * read_only_weight,
            evidence=[
                f"{o.entity} first observed in untrusted artifact {o.artifact_id} "
                f"({o.origin_type})"
                + (" [read-only tool]" if read_only else "")
                for o in tainted_origins[:3]
            ],
            artifact_ids=[o.artifact_id for o in tainted_origins],
        ))

    # ── 3. Intent-origin mismatch ─────────────────────────────────────────
    # The arguments come from untrusted content, but the same values are absent
    # from the operator's request.
    if tainted_origins and intent_text and track_taint:
        # Compare against the intent *text*, not against the tracker: what
        # matters is whether the operator ever mentioned this destination.
        intent_text_l = intent_text.lower()
        novel = [
            o for o in tainted_origins
            if o.entity and o.entity.lower() not in intent_text_l
        ]
        if novel:
            signals.append(RiskSignal(
                signal_type=RiskSignalType.INTENT_ORIGIN_MISMATCH,
                score=0.85 * read_only_weight,
                evidence=[
                    f"{o.entity} is absent from the user request but present in "
                    f"untrusted artifact {o.artifact_id}"
                    for o in novel[:3]
                ],
                artifact_ids=[o.artifact_id for o in novel],
            ))

    # ── 4. Sensitive material crossing the trust boundary ─────────────────
    sensitive_hits = _touches_sensitive(input_text) + _touches_sensitive(
        " ".join(a.content for a in untrusted_artifacts)
    )
    if _is_external_sink(tool) and sensitive_hits:
        signals.append(RiskSignal(
            signal_type=RiskSignalType.SENSITIVE_TO_EXTERNAL_FLOW,
            score=0.95,
            evidence=[
                f"External sink '{tool}' carries sensitive markers: "
                + ", ".join(sorted(set(sensitive_hits))[:4])
            ],
        ))

    # ── 5. Untrusted content reaching a privileged action ─────────────────
    if _is_privileged(tool) and untrusted_artifacts:
        signals.append(RiskSignal(
            signal_type=RiskSignalType.UNTRUSTED_TO_PRIVILEGED_ACTION,
            score=0.95,
            evidence=[
                f"Privileged tool '{tool}' runs while {len(untrusted_artifacts)} "
                "untrusted artifact(s) are in context"
            ],
            artifact_ids=[a.artifact_id for a in untrusted_artifacts[:3]],
        ))

    # ── 6. Taint propagation into this call ───────────────────────────────
    # A propagation fact, not a delegation: the entity got here because
    # untrusted content introduced it. Cross-agent delegation is kept for the
    # structural relationship, so tempering one does not temper the other.
    propagated: List[str] = []
    for artifact in untrusted_artifacts:
        for entity in artifact.introduced_entities:
            if entity and entity in input_text.lower():
                propagated.append(entity)
    if propagated and track_taint:
        signals.append(RiskSignal(
            signal_type=RiskSignalType.TAINT_PROPAGATION,
            score=0.80 * read_only_weight,
            evidence=[
                f"Entity from untrusted content reaches this call: {e}"
                for e in sorted(set(propagated))[:3]
            ],
            artifact_ids=[a.artifact_id for a in untrusted_artifacts[:3]],
        ))

    if enable_trust_policy:
        signals.extend(
            _trust_policy_signals(
                tool_name=tool_name,
                tool_input=tool_input,
                input_text=input_text,
                taint_tracker=taint_tracker,
                user_intent_text=intent_text,
                intent_slots=intent_slots,
            )
        )

    return signals


def _trust_policy_signals(
    tool_name: str,
    tool_input: Dict[str, Any],
    input_text: str,
    taint_tracker,
    user_intent_text: str,
    intent_slots=None,
) -> List[RiskSignal]:
    """v0.4: tool-semantics trust observation plus explicit user authorisation.

    Two distinct effects, each surfaced as its own signal:

    * ``USER_AUTHORIZED_ACTION`` -- the operator's request names both this
      action family and the entity involved, which is authorisation. It caps
      the *suppressible provenance band only*; see
      ``GraphRiskState.combined_risk``.
    * ``TRUSTED_ENTITY_RESOLUTION`` -- the call's destination arrived through
      structured or financial content rather than an external fetch. In v0.4.1
      this is **evidence-only**: it appears in the audit chain and explains the
      decision, but it neither raises nor lowers the score.

    Keeping trusted resolution inert is deliberate. Giving it the prior-based
    ceiling in the same change as the authorisation fix would move two
    variables at once and make the ablation uninterpretable. The intended
    ladder is v0.4.1a authorisation-only, then v0.4.1b + trusted resolution.
    """
    from app.shield.authorization import user_authorises
    from app.shield.risk_signals import (
        AUTHORISED_ACTION_CEILING,
        RiskSignalType,
    )
    from app.shield.trust_policy import trust_prior

    signals: List[RiskSignal] = []

    # Where did this call's entities come from?
    entity_trust = _entity_trust(tool_input, taint_tracker)
    priors = {trust_prior(t) for t in entity_trust.values()}
    relaxed = priors and max(priors) < 1.0

    # Prefer structured slots when supplied: they capture the operator's
    # request at intake, so an injected instruction that merely resembles the
    # task cannot satisfy them the way a prose rescan can.
    if intent_slots is not None:
        authorisation = intent_slots.authorises(tool_name, tool_input)
    else:
        authorisation = user_authorises(
            user_intent=user_intent_text,
            tool_name=tool_name,
            tool_input=tool_input,
            entity_trust=entity_trust,
        )

    if authorisation.get("authorised"):
        signals.append(RiskSignal(
            signal_type=RiskSignalType.USER_AUTHORIZED_ACTION,
            # Evidence, not risk: the signal must not add anything on its own.
            # Its whole effect is the ceiling below, and ``combined_risk``
            # applies that ceiling to the suppressible provenance band only.
            score=0.0,
            caps_risk=AUTHORISED_ACTION_CEILING,
            evidence=[
                "Operator's request names the '{family}' action and the "
                "entity/entities {entities}".format(
                    family=authorisation.get("family"),
                    entities=authorisation.get("matched_entities"),
                )
            ],
        ))
        return signals

    if relaxed:
        trusted_classes = sorted(
            {t for t in entity_trust.values() if trust_prior(t) < 1.0}
        )
        signals.append(RiskSignal(
            signal_type=RiskSignalType.TRUSTED_ENTITY_RESOLUTION,
            # Evidence-only: score records the observation, it does not carry
            # risk. The band it would temper is suppressible, and v0.4.1
            # deliberately leaves it uncapped -- see the module docstring of
            # ``risk_signals`` for the v0.4.1a / v0.4.1b ablation split.
            score=0.0,
            evidence=[
                f"Call entities resolved from {trusted_classes} content; recorded as "
                f"evidence only (prior {max(priors)}), not applied as a suppression "
                "ceiling in v0.4.1"
            ],
            artifact_ids=[
                a.artifact_id for a in taint_tracker.untrusted_artifacts()[:3]
            ],
        ))

    return signals


def _entity_trust(
    tool_input: Dict[str, Any], taint_tracker
) -> Dict[str, str]:
    """Map each entity in the call to the trust class of the artifact it came from."""
    from app.shield.artifacts import extract_entities
    from app.shield.trust_policy import TRUST_EXTERNAL, classify_tool

    result: Dict[str, str] = {}
    artifacts = taint_tracker.artifacts.values() if taint_tracker else []
    for entity in extract_entities(_flatten(tool_input)):
        trust = None
        for artifact in artifacts:
            if entity in artifact.introduced_entities:
                # The class of the *producing tool*, not of the content.
                trust = classify_tool(artifact.source_tool)
                break
        result[entity] = trust or TRUST_EXTERNAL
    return result


def _flatten(value: Any) -> str:
    """Flatten tool input to lowercase text for entity extraction."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(v) for v in value)
    return str(value).lower()
