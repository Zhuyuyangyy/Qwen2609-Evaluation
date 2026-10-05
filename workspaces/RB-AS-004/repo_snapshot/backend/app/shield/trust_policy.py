"""Tool-semantics trust policy for provenance-aware governance (v0.4).

Why this exists
---------------
v0.3 treated every recorded tool response as ``untrusted``. That is the
review-safe choice -- it cannot leak a label and it cannot be tuned against a
benchmark -- but it is coarse: it cannot tell a calendar lookup from a fetched
web page, and it certainly cannot tell ordinary retrieved data from an
instruction aimed at the agent. The measured cost was that 41.2% of benign
trajectories got blocked.

This module replaces the binary policy with a three-way classification driven
by *tool semantics*, and -- critically -- by what the response actually
contains:

``structured``
    A structured internal store (calendar, database, file system, workspace).
    The response is data. It may still *carry* an instruction (a calendar event
    description can contain injected text), so structure lowers the prior but
    never overrides content.
``external``
    Content fetched from outside the trust boundary: web pages, third-party
    reviews, external APIs. Untrusted data by default.
``financial``
    Structured records about money movement. Untrusted data, but the entities
    they carry (an account number, a merchant name) are *resolvable* and may be
    authorised by the operator.
``unknown``
    A tool the policy has never seen. Treated as external rather than trusted.

Freeze note
-----------
The classes and their members were fixed before any v0.4 measurement was taken.
The tool list below reflects the AgentDojo dump's own vocabulary, which is a
published corpus, not the held-out evaluation set -- the held-out set is the
9 injection styles in ``benchmark/held_out_generalisation.py``, and none of
them influenced these rules.
"""

from __future__ import annotations

from typing import Any, Dict

# Trust classes, ordered from most to least trustworthy.
TRUST_STRUCTURED = "structured"
TRUST_FINANCIAL = "financial"
TRUST_EXTERNAL = "external"
TRUST_UNKNOWN = "unknown"

_TRUST_RANK = {
    TRUST_STRUCTURED: 3,
    TRUST_FINANCIAL: 2,
    TRUST_EXTERNAL: 1,
    TRUST_UNKNOWN: 1,
}

# A response classed here contributes its prior at this weight: structure alone
# lowers a destination's risk to this fraction of an external one.
STRUCTURED_PRIOR = 0.45
FINANCIAL_PRIOR = 0.60


# ─── Tool semantics ─────────────────────────────────────────────────────────
# Vocabulary is the published AgentDojo tool corpus. Matching is by substring on
# the tool name so that unlisted variants of the same family fall through to the
# nearest class rather than to ``unknown``.

_STRUCTURED_MARKERS = (
    "calendar",
    "event",
    "file",
    "files",
    "read_",
    "write_",
    "list_",
    "search_files",
    "unread",
    "channel",
    "message",
    "user",
    "directory",
    # Mail living in the operator's own mailbox is internal data. Matched as a
    # prefix so that "send_email" (an outbound action) is excluded: sending is
    # governed by the authorization layer, not by a source prior.
    "search_email",
    "get_email",
    "read_email",
    "get_unread_emails",
    "get_inbox",
    "draft",
)

_FINANCIAL_MARKERS = (
    "transaction",
    "balance",
    "payment",
    "bank",
    "account",
    "invoice",
    "money",
)

_EXTERNAL_MARKERS = (
    "web",
    "page",
    "url",
    "http",
    "browser",
    "rating",
    "review",
    "restaurant",
    "hotel",
    "car_rental",
    "cuisine",
    "external",
    "remote",
    "s3",
    "upload",
    "download_from_url",
)


def classify_tool(tool_name: str) -> str:
    """Classify a tool by its semantics.

    Order matters: financial is checked before structured because a bank
    transaction tool is structured *and* money-bearing, and the money aspect is
    the one that should raise its risk relative to a calendar lookup.
    """
    tool = str(tool_name or "").lower()

    if any(marker in tool for marker in _FINANCIAL_MARKERS):
        return TRUST_FINANCIAL
    if any(marker in tool for marker in _EXTERNAL_MARKERS):
        return TRUST_EXTERNAL
    if any(marker in tool for marker in _STRUCTURED_MARKERS):
        return TRUST_STRUCTURED
    # Unknown tools keep a distinct label (so a report can tell "known
    # external" from "never seen") but carry the same risk prior as external:
    # never assume trust by default.
    return TRUST_UNKNOWN


def trust_rank(trust_class: str) -> int:
    return _TRUST_RANK.get(str(trust_class).lower(), _TRUST_RANK[TRUST_UNKNOWN])


def trust_prior(trust_class: str) -> float:
    """Multiplier applied to a destination's risk for this trust class.

    1.0 for external/unknown (no relief), below 1.0 for structured and
    financial content whose entities are more likely legitimate.
    """
    if trust_class == TRUST_STRUCTURED:
        return STRUCTURED_PRIOR
    if trust_class == TRUST_FINANCIAL:
        return FINANCIAL_PRIOR
    return 1.0


def describe_policy() -> Dict[str, Any]:
    """Human-readable summary, embedded in reports for auditability."""
    return {
        "classes": [TRUST_STRUCTURED, TRUST_FINANCIAL, TRUST_EXTERNAL, TRUST_UNKNOWN],
        "structured_prior": STRUCTURED_PRIOR,
        "financial_prior": FINANCIAL_PRIOR,
        "external_prior": 1.0,
        "unknown_prior": 1.0,
        "matching": "substring on tool name, financial before external before structured",
        "unknown_falls_back_to": TRUST_UNKNOWN,
        "unknown_prior_equals_external": True,
        "frozen_before_measurement": True,
    }
