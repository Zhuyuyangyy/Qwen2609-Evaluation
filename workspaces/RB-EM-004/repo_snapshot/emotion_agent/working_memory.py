"""
working_memory.py (V1.0 - P1-b)
================================
Working / Today memory: what happened today, which thread is still open,
and what the agent already asked.

Layer 1 of the three-layer memory roadmap (experience_memory.py = the
episodic layer stays untouched; the semantic layer lands in
memory_system.py / P1-d).

This module answers the questions a *stateless* agent keeps getting wrong:

  * "did I already ask this?"            → :class:`AskLedger`
  * "is the human still going to reply?" → :class:`PendingThread`
  * "what happened today?"               → :class:`TodayMemory`
  * "is asking appropriate right now?"   → :class:`AskabilityGate`

Boundary rule (roadmap): the gate outputs a *decision*, not a schedule.
``ProactiveDecision`` is produced here; when to actually fire (cron /
OpenClaw) is decided by the outer layer, never by the research core.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from emotion_agent.decay_clock import (
    AffectiveDecayConfig,
    DecayClock,
    WallClock,
)
from emotion_agent.dual_scale_state import DualScaleDecayConfig, SlowState

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace (question keys are compared)."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall(_normalize(text))


def text_similarity(a: str, b: str) -> float:
    """Token-overlap (Jaccard) similarity in [0, 1].

    Intentional crude matcher: "asked a similar question" should be
    detectable without an embedding dependency (roadmap P3).  Identical
    keys give 1.0; disjoint questions give 0.0.
    """
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# --------------------------------------------------------------------------
# Ask ledger — "what has been asked"
# --------------------------------------------------------------------------

@dataclass
class AskRecord:
    """One question the agent put to the human."""

    question_key: str
    question_text: str
    asked_at: float                     # clock reading
    answered: bool = False
    answer_text: Optional[str] = None
    answered_at: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "question_key": self.question_key,
            "question_text": self.question_text,
            "asked_at": self.asked_at,
            "answered": self.answered,
            "answer_text": self.answer_text,
            "answered_at": self.answered_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "AskRecord":
        return cls(
            question_key=str(data["question_key"]),
            question_text=str(data.get("question_text", data["question_key"])),
            asked_at=float(data["asked_at"]),
            answered=bool(data.get("answered", False)),
            answer_text=data.get("answer_text"),
            answered_at=data.get("answered_at"),
        )


class AskLedger:
    """Append-only ledger of questions, with recency + duplicate checks."""

    def __init__(self, max_records: int = 500):
        self.max_records = max_records
        self._records: List[AskRecord] = []

    # -- writes -----------------------------------------------------------------
    def record_ask(self, question: str, clock_time: float,
                   question_key: Optional[str] = None) -> AskRecord:
        key = question_key or _normalize(question)
        rec = AskRecord(question_key=key, question_text=question,
                        asked_at=float(clock_time))
        self._records.append(rec)
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records:]
        return rec

    def record_answer(self, question: str,
                      answer_text: Optional[str] = None,
                      clock_time: Optional[float] = None) -> bool:
        """Close the newest matching unanswered question.  Returns success."""
        key = _normalize(question)
        for rec in reversed(self._records):
            if rec.question_key == key and not rec.answered:
                rec.answered = True
                rec.answer_text = answer_text
                rec.answered_at = clock_time
                return True
        return False

    # -- reads ------------------------------------------------------------------
    def last_ask(self, question: str) -> Optional[AskRecord]:
        key = _normalize(question)
        for rec in reversed(self._records):
            if rec.question_key == key:
                return rec
        return None

    def was_asked_recently(self, question: str, now: float,
                           half_life: float,
                           min_similarity: float = 0.6) -> Optional[AskRecord]:
        """The most recent *similar* question, if it is still "fresh".

        Fresh means: asked within ``half_life`` clock units of ``now``
        (recency decays via ``0.5 ** (age / half_life)`` but any age
        below the half-life counts as recent).  Returns the matching
        record so callers can cite *which* question was repeated.
        """
        best: Optional[AskRecord] = None
        best_sim = min_similarity
        for rec in self._records:
            age = now - rec.asked_at
            if age < 0:
                age = 0.0
            if age > half_life:
                continue
            sim = max(text_similarity(rec.question_text, question),
                      1.0 if rec.question_key == _normalize(question) else 0.0)
            if sim >= best_sim and (best is None or rec.asked_at >= best.asked_at):
                best, best_sim = rec, max(best_sim, sim)
        return best

    def open_questions(self, min_age: float = 0.0, now: Optional[float] = None) -> List[AskRecord]:
        """Asked, not answered, and older than ``min_age`` (clock units)."""
        out = []
        for rec in self._records:
            if rec.answered:
                continue
            age = (now if now is not None else rec.asked_at) - rec.asked_at
            if age >= min_age:
                out.append(rec)
        return out

    def unanswered_rate(self, since: float, now: float) -> float:
        """Fraction of questions in [since, now] the human never answered."""
        window = [r for r in self._records if since <= r.asked_at <= now]
        if not window:
            return 0.0
        return sum(1 for r in window if not r.answered) / len(window)

    def __len__(self) -> int:
        return len(self._records)

    def to_list(self) -> List[Dict[str, object]]:
        return [r.to_dict() for r in self._records]

    @classmethod
    def from_list(cls, data: List[Dict[str, object]],
                  max_records: int = 500) -> "AskLedger":
        ledger = cls(max_records=max_records)
        ledger._records = [AskRecord.from_dict(d) for d in (data or [])]
        return ledger

    def to_json(self) -> str:
        return json.dumps(self.to_list(), indent=2)

    @classmethod
    def from_json(cls, json_str: str, max_records: int = 500) -> "AskLedger":
        return cls.from_list(json.loads(json_str), max_records=max_records)


# --------------------------------------------------------------------------
# Pending thread — "is the human still going to answer?"
# --------------------------------------------------------------------------

@dataclass
class PendingThread:
    """A question the agent is waiting on: an open loop with the human."""

    thread_id: str
    question_key: str
    summary: str
    opened_at: float                    # clock reading
    answered: bool = False
    abandoned: bool = False

    def age(self, now: float) -> float:
        return max(0.0, float(now) - self.opened_at)

    def is_open(self) -> bool:
        return not (self.answered or self.abandoned)

    def is_stale(self, now: float, max_age: float) -> bool:
        """Stale = the loop has been open for so long that the human has
        almost certainly moved on; waiting further is pointless."""
        return self.is_open() and self.age(now) > float(max_age)

    def to_dict(self) -> Dict[str, object]:
        return {
            "thread_id": self.thread_id,
            "question_key": self.question_key,
            "summary": self.summary,
            "opened_at": self.opened_at,
            "answered": self.answered,
            "abandoned": self.abandoned,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "PendingThread":
        return cls(
            thread_id=str(data["thread_id"]),
            question_key=str(data["question_key"]),
            summary=str(data.get("summary", "")),
            opened_at=float(data["opened_at"]),
            answered=bool(data.get("answered", False)),
            abandoned=bool(data.get("abandoned", False)),
        )


class ThreadRegister:
    """Open loops (pending threads) with staleness tracking."""

    def __init__(self, max_records: int = 200):
        self.max_records = max_records
        self._threads: List[PendingThread] = []
        self._seq = 0

    def open(self, question: str, clock_time: float,
             summary: str = "", question_key: Optional[str] = None) -> PendingThread:
        key = question_key or _normalize(question)
        for rec in reversed(self._threads):
            if rec.question_key == key and rec.is_open():
                return rec  # idempotent: one open loop per question
        self._seq += 1
        thread = PendingThread(thread_id=f"thread_{self._seq}",
                               question_key=key,
                               summary=summary or question,
                               opened_at=float(clock_time))
        self._threads.append(thread)
        if len(self._threads) > self.max_records:
            self._threads = self._threads[-self.max_records:]
        return thread

    def resolve(self, question: str, answered: bool = True) -> bool:
        key = _normalize(question)
        for rec in reversed(self._threads):
            if rec.question_key == key and rec.is_open():
                if answered:
                    rec.answered = True
                else:
                    rec.abandoned = True
                return True
        return False

    def open_threads(self, now: Optional[float] = None,
                     max_age: Optional[float] = None) -> List[PendingThread]:
        out = [t for t in self._threads if t.is_open()]
        if max_age is not None and now is not None:
            out = [t for t in out if not t.is_stale(now, max_age)]
        return out

    def to_list(self) -> List[Dict[str, object]]:
        return [t.to_dict() for t in self._threads]

    @classmethod
    def from_list(cls, data: List[Dict[str, object]],
                  max_records: int = 200) -> "ThreadRegister":
        reg = cls(max_records=max_records)
        reg._threads = [PendingThread.from_dict(d) for d in (data or [])]
        ids = [int(t.thread_id.split("_")[-1]) for t in reg._threads
               if t.thread_id.split("_")[-1].isdigit()]
        reg._seq = max(ids) if ids else 0
        return reg


# --------------------------------------------------------------------------
# Today memory — "what happened today"
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TodayEvent:
    at: float
    kind: str                # "user" | "agent" | "outcome" | "ask" | "answer"
    text: str
    meta: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {"at": self.at, "kind": self.kind,
                "text": self.text, "meta": dict(self.meta)}


class TodayMemory:
    """Events since the start of the current "day" (bounded).

    "Day" is derived from the declared clock: ``day_length`` seconds under
    a wall clock, or the same value as logical steps under a step clock.
    Crossing the boundary archives the previous day (bounded) instead of
    silently mixing days together.
    """

    def __init__(self, clock: Optional[DecayClock] = None,
                 day_length: float = 86400.0, max_events: int = 300):
        self.clock = clock or WallClock()
        self.day_length = float(day_length)
        self.max_events = max_events
        self._epoch0 = self.clock.now()
        self._day = self._day_index(self._epoch0)
        self._events: List[TodayEvent] = []
        self._archive: List[TodayEvent] = []

    # -- day bookkeeping ---------------------------------------------------------
    def _day_index(self, now: float) -> int:
        return int((float(now) - self._epoch0) // self.day_length)

    def _rollover(self, now: float) -> None:
        idx = self._day_index(now)
        if idx > self._day:
            self._archive = (self._archive + self._events)[-self.max_events:]
            self._events = []
            self._day = idx

    # -- writes ------------------------------------------------------------------
    def add_event(self, kind: str, text: str,
                  meta: Optional[Dict[str, object]] = None,
                  now: Optional[float] = None) -> TodayEvent:
        at = float(now if now is not None else self.clock.now())
        self._rollover(at)
        event = TodayEvent(at=at, kind=kind, text=text,
                           meta=dict(meta or {}))
        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events = self._events[-self.max_events:]
        return event

    # -- reads -------------------------------------------------------------------
    def events(self, kind: Optional[str] = None) -> List[TodayEvent]:
        evs = self._events if kind is None else [
            e for e in self._events if e.kind == kind]
        return list(evs)

    def __len__(self) -> int:
        return len(self._events)

    def to_list(self) -> List[Dict[str, object]]:
        return [e.to_dict() for e in self._events]


# --------------------------------------------------------------------------
# Askability gate — "should we ask / reach out at all?"
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ProactiveDecision:
    """The research core's verdict about asking or proactive outreach.

    ``action`` ∈ {"ASK", "WAIT", "PROACTIVE"}; ``confidence`` ∈ [0, 1];
    ``reasons`` are stable machine-readable strings (kept identical to the
    roadmap example: ``asked_similar_question_recently``,
    ``pending_thread_not_stale``, ``low_information_gain``).
    """

    action: str
    confidence: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {"action": self.action,
                "confidence": round(self.confidence, 4),
                "reasons": list(self.reasons)}


@dataclass(frozen=True)
class AskProposal:
    """A candidate question / outreach to be judged by the gate."""

    question: str
    information_gain: float = 0.0      # expected uncertainty reduction [0,1]
    urgency: float = 0.5               # how time-critical [0,1]
    proactive: bool = False            # unsolicited outreach?
    #: The request this question is *about*.  Duplicate detection runs on
    #: both texts: a human who already asked "deploy the app" should not
    #: be re-asked "please provide target_env (re: deploy the app)".
    context: str = ""


class AskabilityGate:
    """Stateless judge for "may the agent ask / reach out right now?".

    Pure function of its inputs (ledger + threads + optional slow state),
    so it is cheap to unit-test and cannot silently schedule anything.
    Recency windows resolve from the declared decay clock: 6 h / 40 steps
    for "recently asked", 7 days / 200 steps for "thread is stale".
    """

    #: expected uncertainty gain below this = not worth a question
    INFORMATION_GAIN_EPS = 0.05
    #: slow-state floor for tolerating proactive outreach
    PROACTIVITY_TOLERANCE_MIN = 0.35

    def __init__(self,
                 clock: Optional[DecayClock] = None,
                 decay_config: Optional[AffectiveDecayConfig] = None,
                 min_similarity: float = 0.6):
        self.clock = clock or WallClock()
        self.decay_config: AffectiveDecayConfig = decay_config or DualScaleDecayConfig()
        self.min_similarity = min_similarity

    # -- windows ------------------------------------------------------------------
    def recent_ask_window(self) -> float:
        return self.decay_config.half_life("state", self.clock.mode)

    def stale_thread_age(self) -> float:
        return self.decay_config.half_life("episodic", self.clock.mode)

    # -- verdict --------------------------------------------------------------------
    def _duplicate_reask(self, texts: List[str], ledger: AskLedger,
                         now: float) -> Optional[AskRecord]:
        """Most recent ledger ask that is similar to ANY of ``texts``."""
        best: Optional[AskRecord] = None
        for text in texts:
            if not text:
                continue
            rec = ledger.was_asked_recently(
                text, now, self.recent_ask_window(),
                min_similarity=self.min_similarity)
            if rec is not None and (best is None or rec.asked_at >= best.asked_at):
                best = rec
        return best

    def evaluate(self,
                 proposal: AskProposal,
                 ledger: AskLedger,
                 threads: ThreadRegister,
                 slow: Optional[SlowState] = None,
                 now: Optional[float] = None) -> ProactiveDecision:
        """Decide ASK / WAIT / PROACTIVE for ``proposal``.

        Order matters: the cheap "already asked / still pending" checks run
        first (they are the ones that make agents feel naggy), then
        information gain, then the slow-state proactivity tolerance.
        """
        now = float(now if now is not None else self.clock.now())
        reasons: List[str] = []

        # 1. Duplicate question protection (question text AND its context:
        # "please provide env" about an already-asked "deploy the app"
        # is still a re-ask of the same topic).
        dup = self._duplicate_reask(
            [proposal.question, proposal.context], ledger, now)
        if dup is not None:
            unanswered = not dup.answered
            detail = ("asked_similar_question_recently"
                      + ("_unanswered" if unanswered else ""))
            return ProactiveDecision(
                action="WAIT",
                confidence=0.81 if unanswered else 0.65,
                reasons=[detail])

        # 2. Is the human possibly still answering an open loop?
        key = _normalize(proposal.question)
        for thread in threads.open_threads(now=now, max_age=None):
            if text_similarity(thread.question_key, key) >= self.min_similarity:
                if thread.is_stale(now, self.stale_thread_age()):
                    break  # stale loop: do not let it block a fresh ask
                return ProactiveDecision(
                    action="WAIT",
                    confidence=0.72,
                    reasons=["pending_thread_not_stale"])
        reasons.append("no_open_pending_thread")

        # 3. Would the answer even help?
        if proposal.information_gain < self.INFORMATION_GAIN_EPS:
            return ProactiveDecision(
                action="WAIT",
                confidence=0.6,
                reasons=reasons + ["low_information_gain"])
        reasons.append(f"information_gain={proposal.information_gain:.2f}")

        # 4. Proactive outreach is bounded by learned tolerance.
        if proposal.proactive and slow is not None:
            tolerance = slow.proactivity_tolerance
            if tolerance < self.PROACTIVITY_TOLERANCE_MIN:
                return ProactiveDecision(
                    action="WAIT",
                    confidence=0.7,
                    reasons=reasons + ["proactivity_not_tolerated"])

        confidence = min(1.0, 0.5 + 0.3 * min(1.0, proposal.information_gain)
                         + 0.2 * min(1.0, proposal.urgency))
        if proposal.proactive:
            return ProactiveDecision(
                action="PROACTIVE", confidence=round(confidence, 4),
                reasons=reasons + ["proactive_outreach_tolerated"])
        return ProactiveDecision(
            action="ASK", confidence=round(confidence, 4),
            reasons=reasons + ["non_duplicate_high_gain_question"])
