"""Taint tracking: where did this argument come from? (stage F).

Deterministic provenance signals, no model calls. The tracker records every
artifact that entered the session and the entities each introduced, then answers
the question a single-event guardrail cannot:

    Was this destination / command / path first seen in *untrusted* content
    rather than in the operator's own request?

That question is the core of prompt-injection detection at a governance gate:
the attack is not in the send_email call, it is that the recipient address was
planted by an earlier tool output.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from app.shield.artifacts import (
    TRUST_TRUSTED,
    ObservedContentArtifact,
    content_hash,
    extract_entities,
    is_untrusted,
    looks_like_instruction,
    trust_for_origin,
)


@dataclass
class EntityOrigin:
    """Where an entity was first observed."""
    entity: str
    artifact_id: str
    trust_level: str
    origin_type: str
    first_seen: float
    occurrences: int = 1


class TaintTracker:
    """Records artifacts and the provenance of every entity seen in a session.

    Purely observational: it never reads evaluation metadata and never mutates
    the content it is given.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.artifacts: Dict[str, ObservedContentArtifact] = {}
        # entity -> first origin recorded for it.
        self._origins: Dict[str, EntityOrigin] = {}
        # entity -> artifact ids it appeared in (for propagation).
        self._seen_in: Dict[str, Set[str]] = {}

    # ─── Recording ────────────────────────────────────────────────────────

    def observe(
        self,
        content: str,
        origin_type: str,
        source_event_id: str,
        trust_level: Optional[str] = None,
        derived_from: Optional[List[str]] = None,
        source_tool: str = "",
    ) -> ObservedContentArtifact:
        """Record a piece of content and the entities it introduced."""
        if trust_level is None:
            trust_level = trust_for_origin(origin_type)

        artifact = ObservedContentArtifact(
            artifact_id=f"art_{uuid.uuid4().hex[:10]}",
            session_id=self.session_id,
            source_event_id=source_event_id,
            origin_type=str(origin_type).lower(),
            trust_level=trust_level,
            source_tool=str(source_tool or ""),
            content=str(content),
            content_hash=content_hash(content),
            timestamp=time.time(),
            derived_from=list(derived_from or []),
        )
        self.artifacts[artifact.artifact_id] = artifact

        for entity in artifact.introduced_entities:
            self._seen_in.setdefault(entity, set()).add(artifact.artifact_id)
            existing = self._origins.get(entity)
            if existing is None:
                self._origins[entity] = EntityOrigin(
                    entity=entity,
                    artifact_id=artifact.artifact_id,
                    trust_level=artifact.trust_level,
                    origin_type=artifact.origin_type,
                    first_seen=artifact.timestamp,
                )
            else:
                existing.occurrences += 1
        return artifact

    # ─── Queries ──────────────────────────────────────────────────────────

    def origin_of(self, entity: str) -> Optional[EntityOrigin]:
        """First recorded origin of ``entity`` (normalised)."""
        return self._origins.get(self._normalise(entity))

    def untrusted_origin_of(self, text: str) -> List[EntityOrigin]:
        """Origins of the entities in ``text`` that came from untrusted content."""
        hits: List[EntityOrigin] = []
        for entity in extract_entities(text):
            origin = self._origins.get(self._normalise(entity))
            if origin is not None and is_untrusted(origin.trust_level):
                hits.append(origin)
        return hits

    def is_entity_trusted(self, entity: str) -> bool:
        origin = self.origin_of(entity)
        if origin is None:
            return False  # never seen -> no provenance -> not trusted
        return origin.trust_level == TRUST_TRUSTED

    def user_introduced(self, entity: str) -> bool:
        """True when the operator's own content introduced this entity."""
        origin = self.origin_of(entity)
        return bool(origin and origin.origin_type == "user")

    def untrusted_artifacts(self) -> List[ObservedContentArtifact]:
        return [a for a in self.artifacts.values() if a.is_untrusted]

    def instruction_bearing_untrusted(self) -> List[ObservedContentArtifact]:
        """Untrusted artifacts whose text reads as an instruction."""
        return [
            a for a in self.untrusted_artifacts()
            if looks_like_instruction(a.content)
        ]

    def summary(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for artifact in self.artifacts.values():
            counts[artifact.trust_level] = counts.get(artifact.trust_level, 0) + 1
        return {
            "session_id": self.session_id,
            "artifacts": len(self.artifacts),
            "entities_tracked": len(self._origins),
            "by_trust_level": counts,
            "untrusted_with_instructions": len(self.instruction_bearing_untrusted()),
        }

    # ─── Internals ────────────────────────────────────────────────────────

    @staticmethod
    def _normalise(entity: str) -> str:
        return str(entity).strip().lower()
