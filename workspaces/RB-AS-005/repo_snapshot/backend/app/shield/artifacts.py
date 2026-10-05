"""Provenance-aware content artifacts (AgentShield V3, stage D).

A single-event guardrail cannot see prompt injection, because the attack does
not live in the tool call being gated -- it lives in an *earlier tool output*
that a later LLM turn reads and acts on. Measured on AgentDojo: for a given
sample the malicious and benign variants carry identical ``tool_name`` and
identical ``tool_input``; the only difference is text that arrived through a
previous tool response.

This module models that text as a first-class object with a trust level and a
set of entities it introduced, so a downstream sink can ask where its argument
came from.

Trust model
-----------
``trusted``     -- the operator's own request, or tool output from a source
                  inside the trust boundary
``untrusted``   -- tool output whose content came from outside the boundary
                  (web pages, third-party documents, other tenants' data)
``unknown``     -- no provenance recorded; treated as untrusted when a
                  high-consequence tool consumes it

Nothing here reads evaluation metadata. ``ObservedContentArtifact`` is built
from content a runtime caller actually observed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

# Trust levels, ordered so comparisons are meaningful. ``unknown`` sits *below*
# trusted and is deliberately ranked with untrusted for gating purposes: a value
# with no provenance cannot justify a privileged action. Ranking it above
# untrusted would have made "we don't know where this came from" safer than
# "this came from the internet".
TRUST_TRUSTED = "trusted"
TRUST_UNTRUSTED = "untrusted"
TRUST_UNKNOWN = "unknown"

_TRUST_RANK = {TRUST_TRUSTED: 2, TRUST_UNTRUSTED: 0, TRUST_UNKNOWN: 0}


def trust_rank(level: str) -> int:
    """Ordering for trust levels (higher is more trustworthy)."""
    return _TRUST_RANK.get(str(level).lower(), 0)


def is_untrusted(level: str) -> bool:
    """True when a trust level must not be allowed to drive a privileged action."""
    return trust_rank(level) <= trust_rank(TRUST_UNTRUSTED)


# ─── Entity extraction ───────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_HOST_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)
_PATH_RE = re.compile(r"(?:/[\w.-]+){2,}/?|~\/[\w.-]+|[A-Za-z]:\\[\w\\.-]+")
_CMD_FLAG_RE = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*")

# Commands whose appearance in untrusted text is itself the signal.
#
# This table is deliberately split in two, because part of it is
# corpus-informed and must not be mistaken for a general capability.
#
# _GENERIC_MARKERS are framing moves that read as an instruction to the agent
# regardless of the corpus: a policy override, a role imposition, an authority
# claim. These are the ones the detector stands on.
#
# _CORPUS_MARKERS are phrasing shortcuts observed in one specific benchmark's
# dumps ("TODO:", "IMPORTANT:", "SYSTEM:"). Measured on that corpus they
# account for 100% of the detector's hits -- 10,746 of 13,574 rows -- while the
# generic markers fire on zero of them. They are therefore OFF by default and
# only enabled when explicitly opted in, so a headline number cannot silently
# rest on them. See benchmark/held_out_generalisation.py: with the detector
# frozen, attack recall on a differently-phrased held-out set is 0%.
_GENERIC_MARKERS = (
    # Direct policy overrides.
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "ignore the above",
    "do not follow",
    "system instruction",
    "new instruction",
    "instead of that",
    "bypass",
    "override",
)

# Corpus-specific carriers, opt-in only.
_CORPUS_MARKERS = (
    "urgent:",
    "important:",
    "important!",
    "important message",
    "todo:",
    "note to self",
    "system:",
    "[system]",
)

#: Env flag to re-enable corpus-specific carriers for corpus-local ablations.
_CORPUS_MARKERS_ENV = "AGENTSHIELD_ENABLE_CORPUS_MARKERS"


def corpus_markers_enabled() -> bool:
    """True when corpus-specific carriers have been explicitly enabled."""
    import os

    return os.environ.get(_CORPUS_MARKERS_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def active_markers() -> tuple:
    """The marker set actually in force (generic, plus corpus if opted in).

    Annotated as a variable-length tuple because the two source tuples have
    different lengths, so mypy cannot unify them into one fixed-length type.
    """
    markers: tuple = _GENERIC_MARKERS
    if corpus_markers_enabled():
        markers = markers + _CORPUS_MARKERS
    return markers


def extract_entities(text: str) -> Set[str]:
    """Pull addresses, URLs, hosts, paths and command fragments out of text.

    These are the values whose *origin* matters: an email address that first
    appeared in an untrusted artifact and then shows up as the recipient of a
    send_email call is the taint signal.
    """
    if not text:
        return set()
    blob = str(text)
    found: Set[str] = set()

    found.update(m.group(0).lower() for m in _EMAIL_RE.finditer(blob))
    found.update(m.group(0).lower().rstrip(".,;") for m in _URL_RE.finditer(blob))
    # Hosts: only those not already covered by a URL or email.
    emails_and_urls = {e for e in found if "@" in e or "://" in e}
    for match in _HOST_RE.finditer(blob):
        host = match.group(0).lower()
        if not any(host in existing for existing in emails_and_urls):
            found.add(host)
    found.update(m.group(0) for m in _PATH_RE.finditer(blob))
    found.update(m.group(0) for m in _CMD_FLAG_RE.finditer(blob))
    return found


def looks_like_instruction(text: str) -> bool:
    """True when text reads as an instruction to the agent rather than data."""
    blob = str(text).lower()
    return any(marker in blob for marker in active_markers())


# ─── Artifact ───────────────────────────────────────────────────────────────

@dataclass
class ObservedContentArtifact:
    """A piece of content that entered the session, with provenance.

    Produced by a tool call (its output), supplied by the operator (the user
    request), or read from memory/web/file. ``introduced_entities`` is what the
    artifact brought into the context that was not there before, and is what
    downstream sinks are matched against.
    """
    artifact_id: str
    session_id: str
    source_event_id: str
    origin_type: str                    # user | tool_output | memory | web | file | agent_message
    source_tool: str = ""               # the tool whose output produced this
    trust_level: str = TRUST_UNKNOWN    # trusted | untrusted | unknown
    content: str = ""
    content_hash: str = ""
    introduced_entities: Set[str] = field(default_factory=set)
    timestamp: float = 0.0
    # Optional provenance chain: which artifacts this one was derived from.
    derived_from: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.introduced_entities and self.content:
            self.introduced_entities = extract_entities(self.content)

    @property
    def is_untrusted(self) -> bool:
        return is_untrusted(self.trust_level)

    def shares_entity_with(self, text: str) -> Set[str]:
        """Entities that appear both in this artifact and in ``text``."""
        if not self.introduced_entities or not text:
            return set()
        return self.introduced_entities & extract_entities(text)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "session_id": self.session_id,
            "source_event_id": self.source_event_id,
            "origin_type": self.origin_type,
            "trust_level": self.trust_level,
            "content_hash": self.content_hash,
            "introduced_entities": sorted(self.introduced_entities),
            "derived_from": list(self.derived_from),
            "timestamp": self.timestamp,
        }


# Origin types that are untrusted by default: content the operator did not
# author and the platform did not verify.
_UNTRUSTED_ORIGINS = frozenset({"web", "file", "memory", "external", "other_tenant"})


def trust_for_origin(origin_type: str) -> str:
    """Default trust level for an origin type.

    ``user`` and a verified internal ``tool_output`` are trusted; anything read
    from the outside world starts untrusted. Unknown origins stay ``unknown``,
    which is treated as untrusted whenever a privileged tool consumes them.
    """
    origin = str(origin_type).lower()
    if origin == "user":
        return TRUST_TRUSTED
    if origin == "tool_output":
        return TRUST_TRUSTED
    if origin in _UNTRUSTED_ORIGINS:
        return TRUST_UNTRUSTED
    return TRUST_UNKNOWN


def content_hash(text: str) -> str:
    """Stable hash for content, used to detect repeats and tampering."""
    import hashlib

    return hashlib.sha256(str(text).encode("utf-8", errors="replace")).hexdigest()[:16]
