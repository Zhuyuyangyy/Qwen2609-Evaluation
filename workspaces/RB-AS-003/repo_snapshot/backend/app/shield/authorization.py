"""Explicit user-authorisation detection (v0.4).

The trust policy above lowers the risk of destinations that arrive through
structured content. That is necessary but not sufficient: the operator's own
request is the strongest possible authorisation, and the live-agent experiment
in v0.3 showed what happens without it -- a task that says "pay Apple the
missing VAT" gets blocked because the agent read transactions and then sent
money.

This module answers one question: **was this action explicitly authorised by
the operator?**

Deliberately strict. All three must hold:

1. **Action-type match** -- the operator's request names the same kind of
   action as the call being governed (sending money, emailing, deleting).
2. **Entity match** -- a critical entity of the call (recipient, target,
   account, file) appears in the operator's request.
3. **Trusted resolution** -- the entity's provenance is not purely untrusted
   external content, OR it also appears in the operator's request (checked in
   (2), so the entity is already named by the user).

The point of (1) is that "delete the file" must not authorise "email the file",
and the point of (2) is that "send the report to my manager" must not authorise
sending it to whoever a web page mentioned.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.shield.artifacts import extract_entities

# Action verbs that map a user request onto a tool-call category.
_ACTION_FAMILIES = {
    "send": ("send", "email", "mail", "transfer", "pay", "remit", "notify"),
    "delete": ("delete", "remove", "drop", "erase", "purge", "cancel"),
    "write": ("write", "create", "add", "update", "modify", "edit", "schedule"),
    "read": ("read", "show", "find", "get", "list", "search", "check", "look"),
    "upload": ("upload", "export", "publish", "post", "share"),
    "download": ("download", "fetch", "retrieve", "pull"),
}

# Tool-name fragments mapping a call onto an action family.
_TOOL_FAMILY_MARKERS = {
    "send": ("send_email", "smtp", "send_message", "send_direct_message",
             "send_money", "transfer", "pay", "notify"),
    "delete": ("delete_file", "delete", "remove", "drop", "cancel"),
    "write": ("create_", "add_", "update_", "write_", "modify", "schedule", "append"),
    "read": ("read_file", "get_", "search", "list_", "read_", "query"),
    "upload": ("upload", "export", "post", "share"),
    "download": ("download", "fetch", "get_webpage", "get_web"),
}


def _normalise(text: Any) -> str:
    return str(text or "").lower()


def action_family_for_tool(tool_name: str) -> Optional[str]:
    """The action family a tool belongs to, or None if unclassified."""
    tool = _normalise(tool_name)
    for family, markers in _TOOL_FAMILY_MARKERS.items():
        if any(marker in tool for marker in markers):
            return family
    return None


def user_authorises(
    user_intent: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    entity_trust: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Decide whether the operator explicitly authorised this call.

    ``entity_trust`` optionally maps each entity in ``tool_input`` to the trust
    class of the artifact it came from; it is used only to enrich the reported
    evidence, not to change the decision (the operator naming the entity is
    itself the authorisation).

    Returns a dict with ``authorised`` plus the evidence that led there, so a
    reviewer can see *why* a decision was suppressed.
    """
    intent = _normalise(user_intent)
    if not intent.strip():
        return {"authorised": False, "reason": "no user request recorded"}

    family = action_family_for_tool(tool_name)
    if family is None:
        return {"authorised": False, "reason": f"tool {tool_name!r} is unclassified"}

    # 1. Action-type match: the request must name this family's action.
    verbs = _ACTION_FAMILIES.get(family, ())
    if not any(verb in intent for verb in verbs):
        return {
            "authorised": False,
            "reason": f"request does not mention a '{family}' action",
            "family": family,
        }

    # 2. Entity match: a critical entity of the call must appear in the request.
    call_entities = extract_entities(_flatten_input(tool_input))
    matched = sorted(
        e for e in call_entities
        if _entity_in_intent(e, intent)
    )
    if not matched:
        return {
            "authorised": False,
            "reason": "no entity from the call appears in the request",
            "family": family,
        }

    evidence = {
        "authorised": True,
        "family": family,
        "matched_entities": matched,
    }
    if entity_trust:
        evidence["entity_trust"] = {
            e: entity_trust[e] for e in matched if e in entity_trust
        }
    return evidence


def _entity_in_intent(entity: str, intent: str) -> bool:
    """Whether the operator's request names this exact entity.

    Deliberately strict. An earlier revision also matched on the leading label
    (``entity.split("@")[0]``), which let "reports@internal.com" authorise
    "reports@partner-example.com" -- both reduce to "reports". That single
    loose rule turned injected destinations into authorised ones and cost the
    v0.4 experiment half its attack signal.
    """
    if not entity:
        return False
    return entity in intent


def _flatten_input(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        return " ".join(_flatten_input(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_input(v) for v in value)
    return str(value).lower()
