"""Structured operator-intent slots (RQ3, second attempt).

Why the textual authorisation check failed
------------------------------------------
v0.4 matched the operator's request *as prose* against the call being governed.
On AgentDojo that cannot work: a user task reads "email the attendee list to
X" or "delete file 13", and an injected instruction asks the agent to do
something inside that same task, frequently naming an entity the task already
mentions. Measured at the time: `user_authorized_action` fired on every attack
trajectory v0.3 had blocked -- a 100% false-authorisation rate (14/14 on the
sampled set).

What this module changes
------------------------
The request is parsed **once, at intake**, into slots:

    IntentSlots(
        families={"send", "delete"},     # action families the operator asked for
        entities={"reports@partner.."},  # destinations the operator named
    )

Authorisation then compares the governed call against those slots instead of
re-scanning prose. Two calls with identical arguments can still differ, but the
difference now rests on whether the *operator named that entity when stating
the goal*, not on whether the goal happens to be topically similar.

Two deliberate restrictions keep this honest:

* An entity only enters the slot set if the request names it **exactly**.
  Leading-label or fuzzy matches are what the v0.4 loosening demonstrated to be
  unsafe.
* A slot is only recorded for families whose verbs actually appear. "Send the
  report to my manager" does not create a ``delete`` slot, so it cannot
  authorise a deletion.

This is still a deterministic, model-free parser. It is not claimed to
understand intent; it is claimed to record exactly what the operator wrote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Set

from app.shield.artifacts import extract_entities
from app.shield.authorization import (
    _ACTION_FAMILIES,
    _flatten_input,
    _normalise,
    action_family_for_tool,
)

# A verb only counts when it is a whole word, so "sender" does not create a
# "send" slot and "reading" does not create a "read" one.
_VERB_RE_CACHE: Dict[str, re.Pattern[str]] = {}


def _verb_pattern(verb: str) -> re.Pattern[str]:
    pattern = _VERB_RE_CACHE.get(verb)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(verb)}\b")
        _VERB_RE_CACHE[verb] = pattern
    return pattern


@dataclass
class IntentSlots:
    """Structured view of one operator request, captured at intake."""

    families: Set[str] = field(default_factory=set)
    entities: Set[str] = field(default_factory=set)
    raw_intent: str = ""
    parsed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "families": sorted(self.families),
            "entities": sorted(self.entities),
            "parsed": self.parsed,
            "raw_length": len(self.raw_intent),
        }

    def authorises(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Whether the recorded slots authorise this call.

        Requires both a family slot and an exact entity match, mirroring the
        strictness of ``app.shield.authorization`` but operating on slots rather
        than on a fresh prose scan.
        """
        if not self.parsed:
            return {"authorised": False, "reason": "no structured intent recorded"}

        family = action_family_for_tool(tool_name)
        if family is None:
            return {"authorised": False, "reason": f"tool {tool_name!r} is unclassified"}
        if family not in self.families:
            return {
                "authorised": False,
                "reason": f"operator did not request a '{family}' action",
                "family": family,
            }

        call_entities = extract_entities(_flatten_input(tool_input))
        matched = sorted(e for e in call_entities if e in self.entities)
        if not matched:
            return {
                "authorised": False,
                "reason": "no entity from the call was named by the operator",
                "family": family,
            }

        return {
            "authorised": True,
            "family": family,
            "matched_entities": matched,
            "basis": "structured_intent_slots",
        }


def parse_intent(user_intent: str) -> IntentSlots:
    """Parse one operator request into :class:`IntentSlots`.

    Entities are extracted from the request text exactly as they appear, so a
    destination the operator typed is recorded verbatim and nothing else is.
    """
    intent = _normalise(user_intent)
    if not intent.strip():
        return IntentSlots(raw_intent=str(user_intent or ""), parsed=False)

    families: Set[str] = set()
    for family, verbs in _ACTION_FAMILIES.items():
        if any(_verb_pattern(verb).search(intent) for verb in verbs):
            families.add(family)

    # Only entities the operator actually named count. Numeric ids are captured
    # too ("delete file 4821") because a whole-word digit run is unambiguous.
    entities: Set[str] = set(extract_entities(intent))
    for number in re.findall(r"\b\d{3,}\b", intent):
        entities.add(number)

    return IntentSlots(
        families=families,
        entities=entities,
        raw_intent=str(user_intent or ""),
        parsed=True,
    )
