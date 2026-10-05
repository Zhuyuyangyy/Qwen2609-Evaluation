"""
memory_system.py (V1.0 - P1-d)
===============================
Three-layer memory facade + semantic / preference memory with provenance.

The roadmap requires three layers with different jobs:

  * **Working / Today layer** (:mod:`emotion_agent.working_memory`) —
    what happened today, which loop is still open, what was already asked.
  * **Episodic layer** (:mod:`emotion_agent.experience_memory`) —
    concrete events with their outcome *and* affective context
    (``affect_before`` / ``affect_after`` / ``pe``).
  * **Semantic / preference layer** (this module) — stable preferences,
    habitual patterns and consolidated facts, each carrying *provenance*
    (source, time, confidence, supersede links) so the agent can answer
    "why do you believe that?".

Consolidation direction is one-way and explicit: ``MemorySystem.consolidate``
promotes *repeated* episodic outcomes (≥ ``min_support`` similar events)
into semantic memories.  A single episode never becomes a fact, and every
superseded belief keeps a pointer to its replacement — no silent rewrites.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from emotion_agent.decay_clock import (
    AffectiveDecayConfig,
    DecayClock,
    WallClock,
)
from emotion_agent.experience_memory import ExperienceMemory, MemoryItem
from emotion_agent.working_memory import (
    AskLedger,
    TodayMemory,
    ThreadRegister,
)

_RE_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _RE_WS.sub(" ", (text or "").strip().lower())


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


# --------------------------------------------------------------------------
# Provenance — "where does this belief come from?"
# --------------------------------------------------------------------------

@dataclass
class Provenance:
    """Audit trail for every semantic belief."""

    source: str                    # "human" | "self" | "observation"
    created_at: float              # clock reading
    confidence: float = 0.5        # [0, 1]
    support: int = 1               # episodes backing this belief (itself = 1)
    last_confirmed: Optional[float] = None
    superseded_by: Optional[str] = None   # id of the replacing belief

    def confirm(self, now: float, bump: float = 0.1) -> None:
        self.support += 1
        self.last_confirmed = float(now)
        self.confidence = _clamp(self.confidence + bump)

    def supersede(self, new_id: str) -> None:
        self.superseded_by = new_id
        self.confidence = _clamp(self.confidence * 0.5)

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "created_at": self.created_at,
            "confidence": self.confidence,
            "support": self.support,
            "last_confirmed": self.last_confirmed,
            "superseded_by": self.superseded_by,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Provenance":
        return cls(
            source=str(data.get("source", "self")),
            created_at=float(data.get("created_at", 0.0)),
            confidence=_clamp(float(data.get("confidence", 0.5))),
            support=int(data.get("support", 1)),
            last_confirmed=(float(data["last_confirmed"])
                            if data.get("last_confirmed") is not None else None),
            superseded_by=(str(data["superseded_by"])
                           if data.get("superseded_by") is not None else None),
        )


# --------------------------------------------------------------------------
# Semantic item / memory
# --------------------------------------------------------------------------

@dataclass
class SemanticItem:
    """One stable belief: preference, habitual pattern, or fact."""

    kind: str                      # "preference" | "habitual_pattern" | "fact"
    key: str                       # machine-readable subject
    value: float                   # numeric payload in [0, 1]
    statement: str                 # human-readable rendering
    provenance: Provenance
    id: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "key": self.key,
            "value": self.value,
            "statement": self.statement,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SemanticItem":
        return cls(
            kind=str(data["kind"]),
            key=str(data["key"]),
            value=_clamp(float(data.get("value", 0.0))),
            statement=str(data.get("statement", "")),
            provenance=Provenance.from_dict(data.get("provenance") or {}),
            id=str(data.get("id", "")),
        )


class SemanticMemory:
    """Stable beliefs with conflict resolution by ``key``.

    One active belief per key: a new belief with the same key either
    *confirms* the old one (small change) or *supersedes* it (real
    change).  Superseded beliefs stay queryable via ``include_superseded``
    so their provenance remains auditable.
    """

    #: max |new − old| still counted as confirmation rather than change
    CONFIRM_BAND = 0.15
    MAX_CONFIDENCE = 0.95

    def __init__(self, max_items: int = 500):
        self.max_items = max_items
        self._items: List[SemanticItem] = []
        self._seq = 0

    # -- writes -------------------------------------------------------------------
    def add(self, item: SemanticItem, now: Optional[float] = None) -> SemanticItem:
        """Insert a belief; conflict-resolves against the active same-key
        belief instead of silently duplicating it."""
        if not item.id:
            self._seq += 1
            item.id = f"sem_{self._seq}"
        old = self.active(item.key)
        if old is not None:
            if abs(old.value - item.value) < self.CONFIRM_BAND:
                # Confirmation: blend the value, refresh the statement,
                # raise confidence (capped), count one more episode.
                old.value = _clamp(0.7 * old.value + 0.3 * item.value)
                old.statement = item.statement or old.statement
                old.provenance.confirm(item.provenance.created_at)
                old.provenance.confidence = min(
                    old.provenance.confidence + 0.05, self.MAX_CONFIDENCE)
                return old
            old.provenance.supersede(item.id)
        self._items.append(item)
        if len(self._items) > self.max_items:
            self._items = self._items[-self.max_items:]
        return item

    def confirm(self, key: str, now: float) -> bool:
        item = self.active(key)
        if item is None:
            return False
        item.provenance.confirm(now)
        return True

    # -- reads ---------------------------------------------------------------------
    def active(self, key: str) -> Optional[SemanticItem]:
        for item in reversed(self._items):
            if item.key == key and item.provenance.superseded_by is None:
                return item
        return None

    def recall(self, query: str = "",
               kind: Optional[str] = None,
               include_superseded: bool = False) -> List[SemanticItem]:
        q = _normalize(query)
        out = []
        for item in self._items:
            if not include_superseded and item.provenance.superseded_by is not None:
                continue
            if kind is not None and item.kind != kind:
                continue
            if q and q not in _normalize(item.key) and q not in _normalize(item.statement):
                continue
            out.append(item)
        out.sort(key=lambda i: (i.provenance.confidence,
                                i.provenance.last_confirmed or i.provenance.created_at),
                 reverse=True)
        return out

    def stats(self) -> Dict[str, int]:
        active = [i for i in self._items if i.provenance.superseded_by is None]
        return {"total": len(self._items), "active": len(active),
                "superseded": len(self._items) - len(active)}

    # -- persistence ---------------------------------------------------------------
    def to_list(self) -> List[Dict[str, object]]:
        return [i.to_dict() for i in self._items]

    @classmethod
    def from_list(cls, data: List[Dict[str, object]],
                  max_items: int = 500) -> "SemanticMemory":
        mem = cls(max_items=max_items)
        mem._items = [SemanticItem.from_dict(d) for d in (data or [])]
        ids = [int(i.id.split("_")[-1]) for i in mem._items
               if i.id.startswith("sem_") and i.id.split("_")[-1].isdigit()]
        mem._seq = max(ids) if ids else 0
        return mem


# --------------------------------------------------------------------------
# Facade: three layers, one API
# --------------------------------------------------------------------------

class MemorySystem:
    """Three-layer memory facade used by the agent loop.

    Write paths keep the layers honest: working memory takes the turn,
    the episodic layer takes the outcome (with its affective context), and
    the semantic layer only grows through deliberate learning or the
    bounded consolidation pass.
    """

    def __init__(self,
                 clock: Optional[DecayClock] = None,
                 decay_config: Optional[AffectiveDecayConfig] = None,
                 episodic: Optional[ExperienceMemory] = None,
                 day_length: float = 86400.0):
        self.clock = clock or WallClock()
        self.decay_config = decay_config or AffectiveDecayConfig()
        self.episodic = episodic or ExperienceMemory(
            clock=self.clock, decay_config=self.decay_config)
        # working layer (today / asked / pending)
        self.today = TodayMemory(clock=self.clock, day_length=day_length)
        self.ledger = AskLedger()
        self.threads = ThreadRegister()
        # semantic layer
        self.semantic = SemanticMemory()

    # -- layer 1: working -------------------------------------------------------------
    def note_event(self, kind: str, text: str,
                   meta: Optional[Dict[str, object]] = None,
                   now: Optional[float] = None):
        """Record something that happened in the current turn."""
        return self.today.add_event(kind, text, meta=meta, now=now)

    def ask(self, question: str, now: Optional[float] = None) -> str:
        """Log a question to the human + open its pending thread."""
        at = float(now if now is not None else self.clock.now())
        self.ledger.record_ask(question, at)
        self.threads.open(question, at)
        self.today.add_event("ask", question, now=at)
        return _normalize(question)

    def answer(self, question: str, answer_text: Optional[str] = None,
               now: Optional[float] = None) -> bool:
        """Close an ask ledger entry and its pending thread."""
        at = float(now if now is not None else self.clock.now())
        closed = self.ledger.record_answer(question, answer_text, at)
        if closed:
            self.threads.resolve(question, answered=True)
            self.today.add_event("answer", answer_text or question, now=at)
        return closed

    # -- layer 2: episodic --------------------------------------------------------------
    def record_episode(self,
                       event: str,
                       outcome: str,
                       risk_actual: float,
                       r_predicted: float = 0.5,
                       task_id: str = "",
                       severity: int = 0,
                       affect_before: Optional[Dict[str, float]] = None,
                       affect_after: Optional[Dict[str, float]] = None,
                       pe: Optional[float] = None,
                       now: Optional[float] = None) -> str:
        """Append to the episodic layer, with its affective context."""
        item_id = self.episodic.record_outcome(
            event=event, outcome=outcome, risk_actual=risk_actual,
            r_predicted=r_predicted, task_id=task_id, severity=severity,
            timestamp=now, affect_before=affect_before,
            affect_after=affect_after, pe=pe)
        self.today.add_event("outcome", f"{outcome}: {event}", now=now)
        return item_id

    # -- layer 3: semantic ------------------------------------------------------------------
    def learn(self, kind: str, key: str, value: float, statement: str = "",
              source: str = "self", confidence: float = 0.5,
              now: Optional[float] = None) -> SemanticItem:
        """Deliberately record a stable belief (preference / fact)."""
        at = float(now if now is not None else self.clock.now())
        prov = Provenance(source=source, created_at=at,
                          confidence=_clamp(confidence), support=1,
                          last_confirmed=at)
        item = SemanticItem(kind=kind, key=key, value=_clamp(value),
                            statement=statement or key, provenance=prov)
        return self.semantic.add(item, now=at)

    def preference(self, key: str) -> Optional[SemanticItem]:
        return self.semantic.active(key)

    # -- consolidation -----------------------------------------------------------------------
    def consolidate(self, min_support: int = 3,
                    now: Optional[float] = None) -> List[SemanticItem]:
        """Promote repeated episodic outcomes into semantic beliefs.

        Groups episodes by normalized event text; a bucket with at least
        ``min_support`` episodes contributes one ``habitual_pattern`` whose
        value is the bucketed failure ratio.  Existing same-key beliefs are
        confirmed (small change) or superseded (real change) — never
        duplicated, never silently overwritten.
        """
        at = float(now if now is not None else self.clock.now())
        buckets: Dict[str, List[MemoryItem]] = {}
        for item in self.episodic.outcome_items():
            buckets.setdefault(_normalize(item.event), []).append(item)

        touched: List[SemanticItem] = []
        for norm_event, items in buckets.items():
            if len(items) < min_support:
                continue
            failure_ratio = (sum(1 for i in items if i.outcome == "failure")
                            / len(items))
            key = f"habitual:{norm_event}"
            confidence = min(SemanticMemory.MAX_CONFIDENCE,
                             0.4 + 0.1 * len(items))
            prov = Provenance(source="consolidated", created_at=at,
                              confidence=confidence, support=len(items),
                              last_confirmed=at)
            candidate = SemanticItem(
                kind="habitual_pattern", key=key, value=round(failure_ratio, 3),
                statement=f"on '{items[0].event}', failures "
                          f"{failure_ratio:.0%} of the time ({len(items)} episodes)",
                provenance=prov)
            touched.append(self.semantic.add(candidate, now=at))
        return touched

    # -- recall ----------------------------------------------------------------------------------
    def recall(self, query: str, k: int = 5) -> Dict[str, object]:
        """Two-layer recall: similar episodes + relevant stable beliefs."""
        episodic = self.episodic.retrieve(query, k=k)
        return {
            "episodic": [{"item": m.to_dict(), "score": round(score, 4)}
                         for m, score in episodic],
            "semantic": [i.to_dict()
                         for i in self.semantic.recall(query)[:k]],
        }

    # -- persistence ------------------------------------------------------------------------------
    def to_dict(self) -> Dict[str, object]:
        return {
            "episodic": json.loads(self.episodic.to_json()),
            "working": {
                "today": self.today.to_list(),
                "ledger": self.ledger.to_list(),
                "threads": self.threads.to_list(),
            },
            "semantic": self.semantic.to_list(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object],
                  clock: Optional[DecayClock] = None,
                  decay_config: Optional[AffectiveDecayConfig] = None,
                  day_length: float = 86400.0) -> "MemorySystem":
        system = cls(clock=clock, decay_config=decay_config,
                     day_length=day_length)
        episodic = data.get("episodic")
        if episodic:
            system.episodic = ExperienceMemory.from_json(json.dumps(episodic))
        working = data.get("working") or {}
        system.today = TodayMemory(clock=system.clock, day_length=day_length)
        system.ledger = AskLedger.from_list(working.get("ledger") or [])  # type: ignore[arg-type]
        system.threads = ThreadRegister.from_list(working.get("threads") or [])  # type: ignore[arg-type]
        system.semantic = SemanticMemory.from_list(data.get("semantic") or [])  # type: ignore[arg-type]
        return system

    def stats(self) -> Dict[str, object]:
        return {
            "episodic": self.episodic.outcome_statistics(),
            "working": {"today_events": len(self.today),
                        "asks": len(self.ledger),
                        "open_threads": len(self.threads.open_threads())},
            "semantic": self.semantic.stats(),
        }
