"""
companion_adapter.py (V1.0 - P2-a)
===================================
Companion Adapter — the boundary between the research core and the outer
(WeChat bot / cron / bubble planner) layer.

What this module is for: the roadmap asks for a "Companion Adapter" that
lets the existing WeChat bot drive the affective core in long-term
interaction *without* pulling scheduling or delivery concerns into the
research core.  The split enforced here:

  research core (imported, never extended by this file)
      DualScaleAffectiveState  — fast + slow affect, evidence-gated
      MemorySystem             — working / episodic / semantic memory
      AskabilityGate           — "may the agent ask / reach out?"
      InteractionPolicy        — RESPOND / ASK / WAIT / CLARIFY / PROACTIVE
      → the core only ever *outputs decisions*
        (:class:`~emotion_agent.interaction_policy.InteractionDecision`
        / :class:`~emotion_agent.working_memory.ProactiveDecision`).

  companion adapter (this file)
      SocialSignalExtractor — turns one raw dialogue turn (text, reply
          latency, explicit acceptance) into ``PolicyInputs`` +
          ``ExperienceSample`` — i.e. it *perceives* the social channel.
      CompanionAdapter      — owns the outer-layer bookkeeping the core
          must not know about: turn counter, quiet suppression after the
          human asks to be left alone, cooldowns, consolidation cadence,
          proactive-outreach bookkeeping, and the turn audit trail.
      → cron, quiet hours, 微信 delivery and bubble planning stay
        *downstream*, in the bot that calls this class.

No subjective experience is claimed anywhere: the adapter maps observable
behaviour (reply latency, refusals, acceptance) onto the same numeric
signals the core already defines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from emotion_agent.decay_clock import DecayClock, WallClock
from emotion_agent.dual_scale_state import (
    SLOW_DIMENSIONS,
    DualScaleAffectiveState,
    DualScaleDecayConfig,
    ExperienceSample,
)
from emotion_agent.interaction_policy import (
    RESPOND,
    WAIT,
    InteractionDecision,
    InteractionPolicy,
    PolicyInputs,
)
from emotion_agent.memory_system import MemorySystem
from emotion_agent.working_memory import AskabilityGate, AskProposal

# --------------------------------------------------------------------------
# Social signal vocabulary (deterministic, embedding-free — roadmap P3)
# --------------------------------------------------------------------------

#: markers of "please stop asking / leave me alone"
REFUSAL_MARKERS: Tuple[str, ...] = (
    "别问", "不用", "别烦", "安静", "别管", "懒得", "算了",
    "不需要", "我不想", "别吵", "闭嘴", "stop", "别秀",
)
#: the strongest subset: an explicit request for quiet / space
QUIET_MARKERS: Tuple[str, ...] = (
    "别烦", "安静", "别吵", "闭嘴", "别管",
)
#: markers of "yes, I accept this interaction"
ACCEPT_MARKERS: Tuple[str, ...] = (
    "好啊", "好呀", "嗯嗯", "可以", "说吧", "继续", "嗯呢", "好哦",
    "好嘛", "告诉我", "yes", "ok",
)

#: replies at/below this many characters count as weak engagement
SHORT_REPLY_CHARS = 4

#: evidence weights for the slow scale (a "嗯" must not move traits)
WEIGHT_WEAK = 0.3
WEIGHT_NORMAL = 0.5
WEIGHT_STRONG = 1.0

#: social risk implied by each signal (fed as ``risk_actual``)
RISK_REFUSAL = 0.8
RISK_QUIET = 0.7
RISK_LATE_REPLY = 0.4
RISK_SHORT_REPLY = 0.35
RISK_IGNORED_OUTREACH = 0.3
RISK_ACCEPTED = 0.1
RISK_ENGAGED = 0.2

#: default companion-domain policy inputs
DEFAULT_TASK_CONFIDENCE = 0.8
DEFAULT_RISK_LEVEL = 0.1
DEFAULT_URGENCY = 0.3
DEFAULT_INFORMATION_GAIN = 0.5

#: question text used for proactive check-ins (kept identical to the
#: proposal the policy itself synthesizes, so ledger/gate stay consistent)
PROACTIVE_QUESTION = "proactive check-in"


@dataclass(frozen=True)
class SocialSignals:
    """Perception of one dialogue turn, in the core's numeric vocabulary."""

    reply_length: int
    is_short_reply: bool
    refusal: bool
    wants_quiet: bool
    #: None = this turn carried no proactive evidence (common case)
    proactive_accepted: Optional[bool]
    latency: Optional[float]
    engaged: bool
    weight: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "reply_length": self.reply_length,
            "is_short_reply": self.is_short_reply,
            "refusal": self.refusal,
            "wants_quiet": self.wants_quiet,
            "proactive_accepted": self.proactive_accepted,
            "latency": self.latency,
            "engaged": self.engaged,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class RawTurn:
    """One raw dialogue turn as the outer layer sees it.

    Fields default to "nothing special happened"; the benchmark / bot may
    override the policy inputs when it knows more than the text does
    (e.g. a missing required field, a risky action under consideration).
    """

    text: str = ""
    #: clock units between the agent's last message and this reply
    latency: Optional[float] = None
    #: explicit verdict on the last proactive move (else inferred)
    proactive_accepted: Optional[bool] = None
    task_confidence: Optional[float] = None
    missing_fields: List[str] = field(default_factory=list)
    risk_level: Optional[float] = None
    urgency: Optional[float] = None
    information_gain: Optional[float] = None


@dataclass
class CompanionTurn:
    """Audit record of one processed turn (trajectory logging / metrics)."""

    at: float
    user_text: str
    signals: SocialSignals
    decision: InteractionDecision
    state: Dict[str, object]
    #: recall results available *before* deciding (memory attribution)
    memory_hits: Dict[str, object] = field(default_factory=dict)
    #: stable names of the memory writes this turn performed
    memory_writes: List[str] = field(default_factory=list)
    asked_question: Optional[str] = None
    answered_question: Optional[str] = None
    #: True when this record represents a proactive move (not a reply)
    proactive: bool = False
    pe: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "at": self.at,
            "user_text": self.user_text,
            "signals": self.signals.to_dict(),
            "decision": self.decision.to_dict(),
            "state": self.state,
            "memory_hits": self.memory_hits,
            "memory_writes": list(self.memory_writes),
            "asked_question": self.asked_question,
            "answered_question": self.answered_question,
            "proactive": self.proactive,
            "pe": self.pe,
        }


class SocialSignalExtractor:
    """Turn-level social perception: text + latency → core vocabulary.

    Deliberately heuristic and deterministic: the roadmap defers learned
    / embedding-based appraisal to P3, and a companion layer must be
    debuggable by reading one turn's signals.
    """

    def __init__(self, late_latency: float = 4.0):
        #: latency at/above this (clock units) counts as a late reply
        self.late_latency = float(late_latency)

    # -- perception ------------------------------------------------------------
    def extract(self, turn: RawTurn) -> SocialSignals:
        text = (turn.text or "").strip()
        refusal = any(m in text for m in REFUSAL_MARKERS) if text else False
        wants_quiet = any(m in text for m in QUIET_MARKERS) if text else False
        short = 0 < len(text) <= SHORT_REPLY_CHARS
        late = turn.latency is not None and turn.latency >= self.late_latency

        accepted = turn.proactive_accepted
        if accepted is None and text and any(m in text for m in ACCEPT_MARKERS):
            # an accepting reply closes whatever we last offered
            accepted = True

        engaged = bool(text) and not refusal and not short and not late
        if refusal or wants_quiet:
            weight = WEIGHT_STRONG
        elif short or late:
            weight = WEIGHT_WEAK
        else:
            weight = WEIGHT_NORMAL

        return SocialSignals(
            reply_length=len(text),
            is_short_reply=short,
            refusal=refusal,
            wants_quiet=wants_quiet,
            proactive_accepted=accepted,
            latency=turn.latency,
            engaged=engaged,
            weight=weight,
        )

    # -- translation into core inputs -------------------------------------------
    def policy_inputs(self, turn: RawTurn,
                      signals: SocialSignals) -> PolicyInputs:
        """Translate the perceived turn into :class:`PolicyInputs`."""
        text = (turn.text or "").strip()
        if turn.task_confidence is not None:
            confidence = float(turn.task_confidence)
        elif not text:
            confidence = 0.4
        elif signals.refusal or signals.wants_quiet:
            confidence = 0.75          # the intent is clear: stop
        elif signals.is_short_reply:
            confidence = 0.7
        else:
            confidence = DEFAULT_TASK_CONFIDENCE

        if turn.information_gain is not None:
            gain = float(turn.information_gain)
        elif signals.refusal or signals.wants_quiet:
            gain = 0.05                # nothing is worth asking now
        else:
            gain = DEFAULT_INFORMATION_GAIN

        return PolicyInputs(
            user_message=text,
            missing_fields=list(turn.missing_fields),
            task_confidence=confidence,
            risk_level=(DEFAULT_RISK_LEVEL if turn.risk_level is None
                        else float(turn.risk_level)),
            urgency=(DEFAULT_URGENCY if turn.urgency is None
                     else float(turn.urgency)),
            information_gain=gain,
            proactive_requested=False,
        )

    def experience(self, signals: SocialSignals) -> ExperienceSample:
        """Translate the perceived turn into an :class:`ExperienceSample`.

        The mapping keeps the core's semantics: refusals are social risk
        realised (bad news for the agent's model of this human), accepting
        a proactive move is a good outcome, terse/late replies are weak
        evidence and therefore carry low weight.
        """
        if signals.refusal:
            risk, outcome = RISK_REFUSAL, "failure"
        elif signals.wants_quiet:
            risk, outcome = RISK_QUIET, "failure"
        elif signals.proactive_accepted is True:
            risk, outcome = RISK_ACCEPTED, "success"
        elif signals.is_short_reply:
            risk, outcome = RISK_SHORT_REPLY, "partial"
        elif signals.latency is not None and signals.latency >= self.late_latency:
            risk, outcome = RISK_LATE_REPLY, "partial"
        elif signals.engaged:
            risk, outcome = RISK_ENGAGED, "success"
        else:
            risk, outcome = RISK_ENGAGED, "neutral"

        return ExperienceSample(
            risk_actual=risk,
            outcome_str=outcome,
            proactive_accepted=signals.proactive_accepted,
            weight=signals.weight,
        )


# --------------------------------------------------------------------------
# The adapter itself
# --------------------------------------------------------------------------

class CompanionAdapter:
    """Outer-layer driver around the untouched research core.

    Layers are constructor flags so the benchmark's ablation arms
    (``companion_systems.py``) can build the same object with different
    modules wired in:

    =================== ======== ======= ======= ====== ============ =======
    arm                 affect   memory  policy  cons.  proactive     role
    =================== ======== ======= ======= ====== ============ =======
    ``v09_baseline``    off      off     off     off    off          control
    ``memory_only``     off      on      on      off    on
    ``affect_only``     on       off     on      off    on
    ``memory_affect``   on       on      on      off    on
    ``full``            on       on      on      on     on
    =================== ======== ======= ======= ====== ============ =======

    Everything else — clock, decay config, gate thresholds, policy
    thresholds — is shared, so the arms differ *only* in which channels
    of the interaction history they can perceive.
    """

    def __init__(self,
                 name: str = "companion",
                 clock: Optional[DecayClock] = None,
                 decay_config: Optional[DualScaleDecayConfig] = None,
                 use_affect: bool = True,
                 use_memory: bool = True,
                 use_policy: bool = True,
                 use_consolidation: bool = False,
                 allow_proactive: bool = True,
                 extractor: Optional[SocialSignalExtractor] = None,
                 day_length: float = 86400.0,
                 proactive_accept_window: float = 10.0,
                 min_proactive_gap: float = 3.0,
                 quiet_cooldown: float = 5.0,
                 consolidate_every: int = 4):
        self.name = name
        self.clock: DecayClock = clock or WallClock()
        self.decay_config: DualScaleDecayConfig = decay_config or DualScaleDecayConfig()
        self.use_affect = bool(use_affect)
        self.use_memory = bool(use_memory)
        self.use_policy = bool(use_policy)
        self.use_consolidation = bool(use_consolidation)
        self.allow_proactive = bool(allow_proactive)

        # -- research core (always constructed; flags gate the wiring) --
        self.dual = DualScaleAffectiveState(
            clock=self.clock, decay_config=self.decay_config)
        self.memory = MemorySystem(clock=self.clock,
                                   decay_config=self.decay_config,
                                   day_length=day_length)
        self.gate = AskabilityGate(clock=self.clock,
                                   decay_config=self.decay_config)
        # the policy judges the SAME ledger / threads the memory writes
        self.policy = InteractionPolicy(self.gate,
                                        ledger=self.memory.ledger,
                                        threads=self.memory.threads)

        # -- outer-layer configuration (scheduling lives out here) --
        self.extractor = extractor or SocialSignalExtractor()
        self.proactive_accept_window = float(proactive_accept_window)
        self.min_proactive_gap = float(min_proactive_gap)
        self.quiet_cooldown = float(quiet_cooldown)
        self.consolidate_every = max(0, int(consolidate_every))

        # -- outer-layer bookkeeping --
        self._turns = 0
        self._consolidations = 0
        self._last_user_at: Optional[float] = None
        self._last_quiet_at: Optional[float] = None
        self._outstanding: Optional[Dict[str, float]] = None   # {at, question}
        #: the adapter's own utterance log — turn-level audit trail, used by
        #: the metrics even when the core memory layers are ablated off
        self._questions: List[Dict[str, object]] = []

    # ------------------------------------------------------------------
    # main API
    # ------------------------------------------------------------------
    def respond(self, turn: RawTurn,
                now: Optional[float] = None) -> CompanionTurn:
        """Process one user turn; the core decides, the adapter records."""
        at = float(now if now is not None else self.clock.now())
        self._turns += 1
        self._last_user_at = at

        signals = self.extractor.extract(turn)
        signals = self._infer_proactive_feedback(signals)
        writes: List[str] = []
        answered_question = self._close_pending_question(turn, signals, at,
                                                         writes)

        if signals.wants_quiet:
            self._last_quiet_at = at

        inputs = self.extractor.policy_inputs(turn, signals)
        fast_state = self.dual.fast.state() if self.use_affect else None
        slow = self.dual.slow if self.use_affect else None
        fast_before = self.dual.fast.state()
        sample = self.extractor.experience(signals)

        memory_hits = (self._recall(turn.text)
                       if (self.use_memory and turn.text) else {})

        if self.use_policy:
            decision = self.policy.decide(inputs, fast_state=fast_state,
                                          slow=slow, now=at)
        else:
            decision = InteractionDecision(
                action=RESPOND, confidence=0.9,
                reasons=["baseline_no_policy_layer"])

        asked_question = self._maybe_record_ask(decision, inputs, fast_state,
                                                slow, at, writes)

        pe = self._observe(sample)
        self._maybe_record_episode(turn, sample, fast_before, pe, at, writes)
        self._maybe_learn(signals, at, writes)
        self._maybe_consolidate(at, writes)

        return CompanionTurn(
            at=at, user_text=turn.text, signals=signals,
            decision=decision, state=self.snapshot(),
            memory_hits=memory_hits, memory_writes=writes,
            asked_question=asked_question,
            answered_question=answered_question, pe=pe)

    def evaluate_outreach(self,
                          now: Optional[float] = None,
                          information_gain: float = DEFAULT_INFORMATION_GAIN,
                          urgency: float = DEFAULT_URGENCY) -> CompanionTurn:
        """A proactive opportunity (no user message).

        The core judges *whether* reaching out is appropriate; the adapter
        adds only outer-layer scheduling rules (cooldowns, quiet
        suppression).  Cron / bubble planning decide *when* to call this.
        """
        at = float(now if now is not None else self.clock.now())

        if not (self.allow_proactive and self.use_policy):
            decision = InteractionDecision(
                action=WAIT, confidence=0.5,
                reasons=["proactive_disabled_by_config"])
            return self._outreach_turn(at, decision, [])

        # -- outer-layer scheduling (never inside the core) --
        if (self._last_user_at is not None
                and at - self._last_user_at < self.min_proactive_gap):
            decision = InteractionDecision(
                action=WAIT, confidence=0.5,
                reasons=["scheduling_user_recently_active"])
            return self._outreach_turn(at, decision, [])
        if (self._last_quiet_at is not None
                and at - self._last_quiet_at < self.quiet_cooldown):
            decision = InteractionDecision(
                action=WAIT, confidence=0.8,
                reasons=["scheduling_user_requested_quiet"])
            return self._outreach_turn(at, decision, [])

        fast_state = self.dual.fast.state() if self.use_affect else None
        slow = self.dual.slow if self.use_affect else None
        inputs = PolicyInputs(
            user_message="",
            task_confidence=DEFAULT_TASK_CONFIDENCE,
            urgency=urgency,
            information_gain=information_gain,
            proactive_requested=True)
        decision = self.policy.decide(inputs, fast_state=fast_state,
                                      slow=slow, now=at)

        writes: List[str] = []
        if decision.action == "PROACTIVE":
            self._open_question(PROACTIVE_QUESTION, at, channel="proactive",
                                writes=writes)
        return self._outreach_turn(at, decision, writes)

    def note_silence(self, dt: float = 1.0) -> Optional[float]:
        """The human did not reply: decay time, close ignored outreach.

        Returns the prediction error deposited for the ignored outreach
        (None when nothing was outstanding).  This is how a quiet history
        teaches the core that outreach goes unanswered even though no
        user message ever arrives.
        """
        ignored_pe: Optional[float] = None
        if self._outstanding is not None and self.use_affect:
            sample = ExperienceSample(risk_actual=RISK_IGNORED_OUTREACH,
                                      outcome_str="failure",
                                      proactive_accepted=False,
                                      weight=WEIGHT_NORMAL)
            ignored_pe = float(self.dual.observe(sample)["pe"])
            self._outstanding = None
        self.dual.decay(dt)
        return ignored_pe

    def idle(self, dt: float = 1.0) -> None:
        """Advance time with no interaction: both scales decay only."""
        self.dual.decay(dt)

    # ------------------------------------------------------------------
    # internals — feedback, bookkeeping, core wiring
    # ------------------------------------------------------------------
    def _infer_proactive_feedback(self,
                                  signals: SocialSignals) -> SocialSignals:
        """Fold the outstanding outreach (if any) into this turn's signals.

        A reply that engages closes the loop as acceptance; a refusal /
        quiet request is not acceptance even though the human replied;
        a reply arriving later than the accept window counts as ignored.
        """
        if self._outstanding is None:
            return signals
        if signals.proactive_accepted is not None:
            return signals
        too_late = (signals.latency is not None
                    and float(signals.latency) > self.proactive_accept_window)
        accepted = not (signals.refusal or signals.wants_quiet or too_late)
        return replace(signals, proactive_accepted=accepted)

    def _close_pending_question(self, turn: RawTurn,
                                signals: SocialSignals, at: float,
                                writes: List[str]) -> Optional[str]:
        """Match this reply against the newest open question (if any).

        Chat convention: the next user message answers the most recent
        open question.  A refusal does *not* answer it — the ledger keeps
        the ask unanswered (the human never answered) and the pending
        thread is abandoned instead of going stale.
        """
        if self._outstanding is None:
            return None
        question = str(self._outstanding["question"])
        answered = not (signals.refusal or signals.wants_quiet)
        self._mark_question(question, answered=answered, at=at)
        if answered:
            if self.use_memory:
                self.memory.answer(question, turn.text or None, now=at)
            writes.append("answer")
        else:
            if self.use_memory:
                self.memory.threads.resolve(question, answered=False)
            writes.append("abandon_thread")
        self._outstanding = None
        return question

    def _open_question(self, question: str, at: float, channel: str,
                       writes: List[str]) -> None:
        """Record an ask (ledger + pending thread + utterance log)."""
        if self.use_memory:
            self.memory.ask(question, now=at)
        self._questions.append({"at": float(at), "question": question,
                                "channel": channel, "answered": None})
        self._outstanding = {"at": float(at), "question": question}
        writes.append(f"ask:{channel}")

    def _mark_question(self, question: str, answered: bool, at: float) -> None:
        for rec in reversed(self._questions):
            if rec["question"] == question and rec["answered"] is None:
                rec["answered"] = answered
                rec["answered_at"] = float(at)
                return

    def _recall(self, text: str) -> Dict[str, object]:
        try:
            return self.memory.recall(text, k=3)
        except Exception:                    # pragma: no cover - defensive
            return {}

    def _maybe_record_ask(self, decision: InteractionDecision,
                          inputs: PolicyInputs,
                          fast_state: Optional[Dict[str, float]],
                          slow, at: float,
                          writes: List[str]) -> Optional[str]:
        """ASK / CLARIFY → record exactly the proposal the gate judged."""
        if decision.action not in ("ASK", "CLARIFY"):
            return None
        if not self.use_memory:
            return None
        proposal: AskProposal = self.policy.propose_question(
            inputs, fast_state=fast_state, slow=slow)
        self._open_question(proposal.question, at, channel="ask",
                            writes=writes)
        return proposal.question

    def _observe(self, sample: ExperienceSample) -> Optional[float]:
        """Feed the perceived turn into the dual-scale state (post-decision)."""
        if not self.use_affect:
            return None
        return float(self.dual.observe(sample)["pe"])

    def _maybe_record_episode(self, turn: RawTurn,
                              sample: ExperienceSample,
                              fast_before: Dict[str, float],
                              pe: Optional[float], at: float,
                              writes: List[str]) -> None:
        """Episodic layer takes the turn + its affective context.

        The same ``ExperienceSample`` drives both scales, so the episode's
        ``risk_actual`` / ``outcome`` / ``pe`` stay consistent with the
        dual-scale audit trail.
        """
        if not self.use_memory:
            return
        severity = 2 if sample.outcome_str == "failure" else (
            1 if sample.outcome_str == "partial" else 0)
        self.memory.record_episode(
            event=turn.text or "(silent turn)",
            outcome=sample.outcome_str,
            risk_actual=sample.risk_actual,
            r_predicted=0.5,
            task_id=f"turn_{self._turns}",
            severity=severity,
            affect_before=fast_before,
            affect_after=(self.dual.fast.state() if self.use_affect
                          else fast_before),
            pe=pe, now=at)
        writes.append("record_episode")

    def _maybe_learn(self, signals: SocialSignals, at: float,
                     writes: List[str]) -> None:
        """Explicit proactive verdicts become semantic preferences."""
        if not (self.use_memory and signals.proactive_accepted is not None):
            return
        accepted = bool(signals.proactive_accepted)
        self.memory.learn(
            kind="preference", key="proactive_outreach",
            value=1.0 if accepted else 0.0,
            statement=("proactive check-ins welcome"
                       if accepted else "proactive check-ins unwelcome"),
            source="observation",
            confidence=0.6, now=at)
        writes.append("learn:proactive_outreach")

    def _maybe_consolidate(self, at: float, writes: List[str]) -> None:
        if not (self.use_consolidation and self.consolidate_every > 0):
            return
        if self._turns % self.consolidate_every:
            return
        touched = self.memory.consolidate(now=at)
        if touched:
            self._consolidations += 1
            writes.append(f"consolidate:{len(touched)}")

    def _outreach_turn(self, at: float, decision: InteractionDecision,
                       writes: List[str]) -> CompanionTurn:
        return CompanionTurn(
            at=at, user_text="",
            signals=SocialSignals(reply_length=0, is_short_reply=False,
                                  refusal=False, wants_quiet=False,
                                  proactive_accepted=None, latency=None,
                                  engaged=False, weight=0.0),
            decision=decision, state=self.snapshot(),
            memory_writes=writes,
            asked_question=(PROACTIVE_QUESTION
                            if decision.action == "PROACTIVE" else None),
            proactive=(decision.action == "PROACTIVE"))

    # ------------------------------------------------------------------
    # audit / persistence
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, object]:
        return {
            "arm": self.name,
            "turns": self._turns,
            "fast": self.dual.fast.state(),
            "slow": self.dual.slow.snapshot(),
            "evidence": {d: round(self.dual.evidence_strength(d), 4)
                         for d in SLOW_DIMENSIONS},
        }

    def question_log(self) -> List[Dict[str, object]]:
        return [dict(q) for q in self._questions]

    def open_questions(self) -> List[Dict[str, object]]:
        return [q for q in self._questions if q["answered"] is None]

    def stats(self) -> Dict[str, object]:
        return {
            "arm": self.name,
            "turns": self._turns,
            "questions": len(self._questions),
            "answered": sum(1 for q in self._questions if q["answered"]),
            "outstanding": self._outstanding is not None,
            "consolidations": self._consolidations,
            "memory": self.memory.stats(),
        }

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "flags": {
                "use_affect": self.use_affect,
                "use_memory": self.use_memory,
                "use_policy": self.use_policy,
                "use_consolidation": self.use_consolidation,
                "allow_proactive": self.allow_proactive,
            },
            "dual": self.dual.to_dict(),
            "memory": self.memory.to_dict(),
            "questions": self._questions,
            "turns": self._turns,
            "consolidations": self._consolidations,
            "last_user_at": self._last_user_at,
            "last_quiet_at": self._last_quiet_at,
            "outstanding": self._outstanding,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object],
                  clock: Optional[DecayClock] = None,
                  decay_config: Optional[DualScaleDecayConfig] = None,
                  **kwargs) -> "CompanionAdapter":
        flags = data.get("flags") or {}
        adapter = cls(name=str(data.get("name", "companion")),
                      clock=clock, decay_config=decay_config,
                      use_affect=bool(flags.get("use_affect", True)),
                      use_memory=bool(flags.get("use_memory", True)),
                      use_policy=bool(flags.get("use_policy", True)),
                      use_consolidation=bool(flags.get("use_consolidation",
                                                       False)),
                      allow_proactive=bool(flags.get("allow_proactive", True)),
                      **kwargs)
        adapter.dual = DualScaleAffectiveState.from_dict(
            data.get("dual") or {},  # type: ignore[arg-type]
            clock=adapter.clock, decay_config=adapter.decay_config)
        adapter.memory = MemorySystem.from_dict(
            data.get("memory") or {},  # type: ignore[arg-type]
            clock=adapter.clock, decay_config=adapter.decay_config)
        adapter.policy = InteractionPolicy(adapter.gate,
                                           ledger=adapter.memory.ledger,
                                           threads=adapter.memory.threads)
        adapter._questions = [dict(q) for q in (data.get("questions") or [])]
        adapter._turns = int(data.get("turns", 0))
        adapter._consolidations = int(data.get("consolidations", 0))
        adapter._last_user_at = (None if data.get("last_user_at") is None
                                 else float(data["last_user_at"]))
        adapter._last_quiet_at = (None if data.get("last_quiet_at") is None
                                  else float(data["last_quiet_at"]))
        outstanding = data.get("outstanding") or None
        adapter._outstanding = ({k: float(v) for k, v in outstanding.items()}
                                if outstanding else None)
        return adapter

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
