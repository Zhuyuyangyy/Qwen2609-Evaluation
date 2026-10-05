"""
test_p1_interaction_layer.py
============================
Unit + integration tests for the P1 interaction layer:

  * dual_scale_state.py   — fast/slow dual time-scale affect with evidence gating
  * working_memory.py     — AskLedger / PendingThread / TodayMemory / AskabilityGate
  * interaction_policy.py — RESPOND / ASK / WAIT / CLARIFY / PROACTIVE
  * memory_system.py      — three-layer memory, provenance, consolidation
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from emotion_agent.decay_clock import StepClock, WallClock
from emotion_agent.dual_scale_state import (
    NEUTRAL_SLOW,
    SLOW_DIMENSIONS,
    DualScaleAffectiveState,
    DualScaleDecayConfig,
    ExperienceSample,
    SlowState,
)
from emotion_agent.experience_memory import ExperienceMemory, MemoryItem
from emotion_agent.interaction_policy import (
    ASK,
    CLARIFY,
    PROACTIVE,
    RESPOND,
    WAIT,
    InteractionPolicy,
    PolicyInputs,
)
from emotion_agent.memory_system import (
    MemorySystem,
    Provenance,
    SemanticItem,
    SemanticMemory,
)
from emotion_agent.working_memory import (
    AskLedger,
    AskProposal,
    AskabilityGate,
    PendingThread,
    ProactiveDecision,
    ThreadRegister,
    TodayMemory,
    text_similarity,
)


def _failures(n: int, event: str = "deploy the app",
              risk_actual: float = 0.9, r_predicted: float = 0.1,
              irreversible: bool = False) -> list:
    return [ExperienceSample(risk_actual=risk_actual, r_predicted=r_predicted,
                             outcome_str="failure", irreversible=irreversible)
            for _ in range(n)]


def _successes(n: int, event_unused: str = "") -> list:
    return [ExperienceSample(risk_actual=0.1, r_predicted=0.5,
                             outcome_str="success")
            for _ in range(n)]


# ==========================================================================
# P1-a: dual time-scale affect
# ==========================================================================
class TestDualScaleState:
    def test_neutral_baseline_and_no_evidence(self):
        ds = DualScaleAffectiveState(clock=StepClock())
        assert ds.slow.snapshot() == {d: 0.5 for d in SLOW_DIMENSIONS}
        # evidence strength == 1.0 means "prior only, no information yet"
        assert all(ds.evidence_strength(d) == 1.0 for d in SLOW_DIMENSIONS)
        assert ds.snapshot()["slow_updates"] == 0

    def test_single_weak_signal_cannot_move_slow_state(self):
        """One "嗯" must not rewrite a stable trait (δ << β, evidence gate)."""
        ds = DualScaleAffectiveState(clock=StepClock())
        ds.observe(ExperienceSample(risk_actual=0.99, r_predicted=0.0,
                                    outcome_str="failure", weight=0.2))
        snap = ds.slow.snapshot()
        assert abs(snap["control_preference"] - 0.5) < 0.05
        # ... while the FAST scale does react immediately (β = 0.30)
        fast = ds.fast.state()
        assert fast["threat"] > 0.0 or fast["valence"] < 0.0

    def test_aggregated_failures_shift_dimensions_in_predicted_directions(self):
        ds = DualScaleAffectiveState(clock=StepClock())
        for s in _failures(12):
            ds.observe(s)
        snap = ds.slow.snapshot()
        # world less predictable, human wants more oversight, less trust
        assert snap["uncertainty_baseline"] > 0.65
        assert snap["control_preference"] > 0.65
        assert snap["interaction_trust"] < 0.35
        assert all(0.0 <= v <= 1.0 for v in snap.values())

    def test_proactivity_dimension_only_moves_from_proactive_evidence(self):
        ds = DualScaleAffectiveState(clock=StepClock())
        for s in _failures(10):
            ds.observe(s)
        assert ds.slow.proactivity_tolerance == 0.5  # untouched by failures
        for _ in range(12):
            ds.observe(ExperienceSample(risk_actual=0.2, r_predicted=0.5,
                                        outcome_str="neutral", proactive_accepted=True))
        assert ds.slow.proactivity_tolerance > 0.7
        # 30 rejections: the evidence gate resists, but the accumulated
        # negative evidence finally drags the trait below the mid-line.
        for _ in range(30):
            ds.observe(ExperienceSample(risk_actual=0.2, r_predicted=0.5,
                                        outcome_str="neutral", proactive_accepted=False))
        assert ds.slow.proactivity_tolerance < 0.3

    def test_slow_relaxes_on_its_own_slower_half_life(self):
        """After one slow half-life the deviation is halved; the fast
        scale (40 steps) has long since forgotten the same event."""
        ds = DualScaleAffectiveState(clock=StepClock())
        for s in _failures(10):
            ds.observe(s)
        slow0 = ds.slow.control_preference
        for _ in range(40):
            ds.decay(dt=1.0)
        slow40 = ds.slow.control_preference
        # 40 steps = fast half-life, 1/5 of the slow half-life → tiny relief
        assert 0.5 < slow40 < slow0
        assert abs(slow40 - (0.5 + (slow0 - 0.5) * 0.5 ** 0.2)) < 0.02
        ds.decay(dt=200.0)  # one full slow half-life
        slow240 = ds.slow.control_preference
        assert abs(slow240 - (0.5 + (slow40 - 0.5) * 0.5)) < 0.02

    def test_delta_much_smaller_than_beta(self):
        assert DualScaleAffectiveState.DELTA_SLOW < DualScaleAffectiveState.BETA_FAST / 2

    def test_evidence_gating_via_weight(self):
        ds = DualScaleAffectiveState(clock=StepClock())
        before = ds.slow.interaction_trust
        ds.observe(ExperienceSample(risk_actual=0.0, r_predicted=1.0,
                                    outcome_str="success", weight=0.1))
        after = ds.slow.interaction_trust
        assert after > before
        assert after - before <= DualScaleAffectiveState.DELTA_SLOW

    def test_round_trip_persistence(self):
        ds = DualScaleAffectiveState(clock=StepClock())
        for s in _failures(6):
            ds.observe(s)
        for _ in range(4):
            ds.observe(ExperienceSample(risk_actual=0.2, r_predicted=0.5,
                                        outcome_str="neutral",
                                        proactive_accepted=True))
        payload = ds.to_json()
        restored = DualScaleAffectiveState.from_json(payload, clock=StepClock())
        assert restored.slow.to_dict() == ds.slow.to_dict()
        assert restored._slow_updates == ds._slow_updates
        assert all(restored.evidence_strength(d) == pytest.approx(
            ds.evidence_strength(d), abs=1e-6) for d in SLOW_DIMENSIONS)

    def test_evidence_strength_grows_with_experience(self):
        ds = DualScaleAffectiveState(clock=StepClock())
        for _ in range(5):
            ds.observe(ExperienceSample(risk_actual=0.9, r_predicted=0.1,
                                        outcome_str="failure"))
        assert ds.evidence_strength("control_preference") > 1.5

    def test_wall_clock_and_step_clock_configs_differ(self):
        cfg = DualScaleDecayConfig()
        assert cfg.half_life("slow", "step") == 200.0
        assert cfg.half_life("slow", "wall_time") == 14 * 86400.0
        assert cfg.half_life("slow", "step") > cfg.half_life("state", "step")


# ==========================================================================
# P1-b: working memory + askability gate
# ==========================================================================
class TestAskLedger:
    def test_record_ask_and_answer(self):
        ledger = AskLedger()
        ledger.record_ask("where is the token", 5.0)
        rec = ledger.last_ask("where is the token")
        assert rec is not None and not rec.answered
        assert ledger.record_answer("where is the token", "in vault", 7.0)
        assert ledger.last_ask("where is the token").answered
        assert not ledger.record_answer("never asked", None, 8.0)

    def test_duplicate_detection_fresh_and_stale(self):
        ledger = AskLedger()
        ledger.record_ask("where is the deploy token", 5.0)
        assert ledger.was_asked_recently("where is the deploy token", 6.0,
                                         half_life=40.0) is not None
        assert ledger.was_asked_recently("where is the deploy token", 100.0,
                                         half_life=40.0) is None

    def test_unanswered_rate(self):
        ledger = AskLedger()
        ledger.record_ask("q1", 0.0)
        ledger.record_answer("q1", "q1 answer", 1.0)
        ledger.record_ask("q2", 2.0)
        rate = ledger.unanswered_rate(since=0.0, now=10.0)
        assert rate == pytest.approx(0.5)
        assert ledger.unanswered_rate(since=5.0, now=10.0) == pytest.approx(0.0)

    def test_open_questions_respect_min_age(self):
        ledger = AskLedger()
        ledger.record_ask("old question", 0.0)
        ledger.record_ask("new question", 50.0)
        recent = ledger.open_questions(min_age=30.0, now=60.0)
        assert [q.question_text for q in recent] == ["old question"]


class TestThreadRegister:
    def test_open_is_idempotent_per_question(self):
        reg = ThreadRegister()
        t1 = reg.open("which env", 1.0)
        t2 = reg.open("which env", 5.0)
        assert t1.thread_id == t2.thread_id  # one open loop per question
        assert len(reg.open_threads(now=6.0, max_age=100.0)) == 1

    def test_resolve_answered_and_abandoned(self):
        reg = ThreadRegister()
        reg.open("q1", 0.0)
        reg.open("q2", 0.0)
        assert reg.resolve("q1", answered=True)
        assert reg.resolve("q2", answered=False)
        open_now = reg.open_threads(now=1.0)
        assert open_now == []

    def test_staleness_boundary(self):
        thread = PendingThread(thread_id="t", question_key="k",
                               summary="s", opened_at=0.0)
        assert not thread.is_stale(100.0, max_age=100.1)
        assert thread.is_stale(100.0, max_age=99.9)
        assert thread.age(-5.0) == 0.0  # no negative ages

    def test_id_sequence_survives_round_trip(self):
        reg = ThreadRegister()
        a, b = reg.open("a", 0.0), reg.open("b", 1.0)
        restored = ThreadRegister.from_list(reg.to_list())
        c = restored.open("c", 2.0)
        nums = sorted(int(t.thread_id.split("_")[-1])
                      for t in [a, b, c])
        assert nums == [1, 2, 3]


class TestTodayMemory:
    def test_add_filter_and_day_rollover(self):
        clock = StepClock()
        today = TodayMemory(clock=clock, day_length=10.0)
        today.add_event("user", "hello")
        today.add_event("outcome", "failure")
        assert len(today) == 2
        assert [e.kind for e in today.events(kind="outcome")] == ["outcome"]
        clock.advance(11.0)
        today.add_event("agent", "fresh day")
        assert len(today) == 1  # previous day archived
        assert today.events()[0].text == "fresh day"


class TestAskabilityGate:
    def _parts(self, clock=None):
        clock = clock or StepClock()
        return (AskabilityGate(clock=clock), AskLedger(), ThreadRegister(), clock)

    def test_duplicate_unanswered_question_waits(self):
        gate, ledger, threads, _ = self._parts()
        ledger.record_ask("where is the deploy token", 5.0)
        d = gate.evaluate(AskProposal("Where is the deploy token?",
                                      information_gain=0.9),
                          ledger, threads, now=6.0)
        assert d.action == "WAIT"
        assert d.confidence == pytest.approx(0.81, abs=0.01)
        assert "asked_similar_question_recently_unanswered" in d.reasons

    def test_answered_similar_question_waits_with_lower_confidence(self):
        gate, ledger, threads, _ = self._parts()
        ledger.record_ask("where is the deploy token", 5.0)
        ledger.record_answer("where is the deploy token", "vault", 6.0)
        d = gate.evaluate(AskProposal("where is the deploy token",
                                      information_gain=0.9),
                          ledger, threads, now=7.0)
        assert d.action == "WAIT" and d.confidence < 0.7

    def test_fresh_pending_thread_blocks(self):
        gate, ledger, threads, _ = self._parts()
        threads.open("which region should the db live in", 5.0)
        d = gate.evaluate(AskProposal("which region should the db live in",
                                      information_gain=0.8),
                          ledger, threads, now=7.0)
        assert d.action == "WAIT"
        assert "pending_thread_not_stale" in d.reasons

    def test_stale_thread_does_not_block(self):
        gate, ledger, threads, _ = self._parts()
        threads.open("which region should the db live in", 0.0)
        d = gate.evaluate(AskProposal("which region should the db live in",
                                      information_gain=0.8),
                          ledger, threads, now=250.0)  # > 200-step staleness
        assert d.action == "ASK"

    def test_low_information_gain_waits(self):
        gate, ledger, threads, _ = self._parts()
        d = gate.evaluate(AskProposal("what is your favorite color",
                                      information_gain=0.01),
                          ledger, threads, now=1.0)
        assert d.action == "WAIT"
        assert "low_information_gain" in d.reasons

    def test_high_gain_non_duplicate_asks(self):
        gate, ledger, threads, _ = self._parts()
        d = gate.evaluate(AskProposal("which region should the db live in",
                                      information_gain=0.8),
                          ledger, threads, now=1.0)
        assert d.action == "ASK"
        assert d.confidence > 0.7

    def test_context_flagged_reask_is_caught(self):
        """"please provide env" about an already-asked "deploy the app"
        is still the same conversation."""
        gate, ledger, threads, _ = self._parts()
        ledger.record_ask("deploy the app", 5.0)
        d = gate.evaluate(AskProposal("please provide target_env",
                                      information_gain=0.9,
                                      context="deploy the app"),
                          ledger, threads, now=6.0)
        assert d.action == "WAIT"

    def test_proactive_bounded_by_slow_state(self):
        gate, ledger, threads, _ = self._parts()
        ok = gate.evaluate(AskProposal("check the pipeline", information_gain=0.5,
                                       proactive=True),
                           ledger, threads,
                           slow=SlowState(proactivity_tolerance=0.9), now=1.0)
        assert ok.action == "PROACTIVE"
        no = gate.evaluate(AskProposal("check the pipeline", information_gain=0.5,
                                       proactive=True),
                           ledger, threads,
                           slow=SlowState(proactivity_tolerance=0.1), now=1.0)
        assert no.action == "WAIT"
        assert "proactivity_not_tolerated" in no.reasons

    def test_wall_clock_windows_use_seconds(self):
        gate, ledger, threads, _ = self._parts(clock=WallClock())
        assert gate.recent_ask_window() == 6 * 3600.0
        assert gate.stale_thread_age() == 7 * 86400.0

    def test_decision_serializes_to_roadmap_shape(self):
        gate, ledger, threads, _ = self._parts()
        ledger.record_ask("where is the deploy token", 5.0)
        d = gate.evaluate(AskProposal("where is the deploy token",
                                      information_gain=0.9),
                          ledger, threads, now=6.0)
        payload = d.to_dict()
        assert payload["action"] == "WAIT"
        assert isinstance(payload["reasons"], list)
        # the reason strings stay stable for benchmarking / logs
        assert payload["reasons"][0].startswith("asked_similar_question")


class TestTextSimilarity:
    def test_identical_and_disjoint(self):
        assert text_similarity("Deploy The App", "deploy the app") == 1.0
        assert text_similarity("alpha beta", "gamma delta") == 0.0
        assert text_similarity("", "alpha") == 0.0


# ==========================================================================
# P1-c: interaction policy
# ==========================================================================
def _policy(clock=None):
    clock = clock or StepClock()
    return InteractionPolicy(AskabilityGate(clock=clock),
                             AskLedger(), ThreadRegister())


FAST_CALM = {"valence": 0.1, "threat": 0.2, "anxiety": 0.2, "confidence": 0.7}


class TestInteractionPolicy:
    def test_clear_request_responds(self):
        d = _policy().decide(PolicyInputs(user_message="ping health"),
                             fast_state=FAST_CALM)
        assert d.action == RESPOND
        assert not d.cautious

    def test_missing_field_asks(self):
        d = _policy().decide(
            PolicyInputs(user_message="deploy the app",
                         missing_fields=["target_env"],
                         information_gain=0.8),
            fast_state=FAST_CALM)
        assert d.action == ASK
        assert "missing_required_fact" in d.reasons

    def test_ambiguous_request_clarifies(self):
        d = _policy().decide(
            PolicyInputs(user_message="fix the thing again maybe",
                         task_confidence=0.3, information_gain=0.8),
            fast_state=FAST_CALM)
        assert d.action == CLARIFY
        assert "ambiguous_request" in d.reasons

    def test_high_risk_with_control_preference_confirms(self):
        slow = SlowState(control_preference=0.8)
        d = _policy().decide(
            PolicyInputs(user_message="push to prod", risk_level=0.8,
                         information_gain=0.8),
            fast_state=FAST_CALM, slow=slow)
        assert d.action == CLARIFY
        assert "confirm_high_risk_action" in d.reasons

    def test_elevated_threat_forces_confirmation(self):
        """Fast state (anxious right now) adds caution even for a
        control-tolerant human."""
        d = _policy().decide(
            PolicyInputs(user_message="push to prod", risk_level=0.8,
                         information_gain=0.8),
            fast_state={"threat": 0.9, "anxiety": 0.8},
            slow=SlowState(control_preference=0.2))
        assert d.action == CLARIFY

    def test_no_request_and_no_proactive_intent_waits(self):
        d = _policy().decide(PolicyInputs(), fast_state=FAST_CALM)
        assert d.action == WAIT
        assert "no_user_message_and_no_proactive_request" in d.reasons

    def test_proactive_allowed_or_blocked_by_gate(self):
        ok = _policy().decide(
            PolicyInputs(proactive_requested=True, information_gain=0.6),
            fast_state=FAST_CALM, slow=SlowState(proactivity_tolerance=0.9))
        assert ok.action == PROACTIVE
        blocked = _policy().decide(
            PolicyInputs(proactive_requested=True, information_gain=0.6),
            fast_state=FAST_CALM, slow=SlowState(proactivity_tolerance=0.1))
        assert blocked.action == WAIT

    def test_blocked_confirmation_on_high_risk_waits_not_acts(self):
        pol = _policy()
        pol.ledger.record_ask("push to prod", 3.0)
        d = pol.decide(
            PolicyInputs(user_message="push to prod", risk_level=0.8,
                         information_gain=0.8),
            fast_state=FAST_CALM, slow=SlowState(control_preference=0.8),
            now=5.0)
        assert d.action == WAIT
        assert "confirmation_blocked_high_risk" in d.reasons

    def test_blocked_question_degrades_to_cautious_response(self):
        pol = _policy()
        pol.ledger.record_ask("deploy the app", 3.0)
        d = pol.decide(
            PolicyInputs(user_message="deploy the app",
                         missing_fields=["target_env"],
                         information_gain=0.8),
            fast_state=FAST_CALM, now=5.0)
        assert d.action == RESPOND and d.cautious
        assert "clarification_deferred_respond_cautiously" in d.reasons

    def test_same_history_yields_same_decision(self):
        pol = _policy()
        inputs = PolicyInputs(user_message="ping health")
        a = pol.decide(inputs, fast_state=FAST_CALM, now=1.0)
        b = pol.decide(inputs, fast_state=FAST_CALM, now=1.0)
        assert a == b


# ==========================================================================
# P1-d: three-layer memory
# ==========================================================================
class TestSemanticMemory:
    def test_new_belief_is_active_and_queryable(self):
        mem = SemanticMemory()
        item = SemanticItem(kind="preference", key="p:prod", value=0.9,
                            statement="confirm before prod",
                            provenance=Provenance(source="human",
                                                  created_at=1.0,
                                                  confidence=0.8))
        stored = mem.add(item)
        assert mem.active("p:prod") is stored
        assert mem.recall("prod") == [stored]

    def test_similar_value_confirms_instead_of_duplicating(self):
        mem = SemanticMemory()
        first = mem.add(SemanticItem(kind="fact", key="p:x", value=0.50,
                                     statement="s",
                                     provenance=Provenance("human", 1.0)))
        second = mem.add(SemanticItem(kind="fact", key="p:x", value=0.55,
                                      statement="s2",
                                      provenance=Provenance("human", 2.0)))
        assert first is second  # confirmed, not appended
        assert mem.stats() == {"total": 1, "active": 1, "superseded": 0}
        assert first.provenance.support == 2
        assert mem.active("p:x").value == pytest.approx(0.515, abs=1e-9)

    def test_divergent_value_supersedes_with_provenance_link(self):
        mem = SemanticMemory()
        old = mem.add(SemanticItem(kind="fact", key="p:x", value=0.1,
                                   statement="s",
                                   provenance=Provenance("human", 1.0,
                                                         confidence=0.8)))
        new = mem.add(SemanticItem(kind="fact", key="p:x", value=0.9,
                                   statement="s2",
                                   provenance=Provenance("human", 2.0)))
        assert old is not new
        assert old.provenance.superseded_by == new.id
        assert mem.active("p:x") is new
        assert len(mem.recall(include_superseded=True)) == 2
        assert len(mem.recall(include_superseded=False)) == 1
        # superseding halves the old confidence (visible decay of a disproven belief)
        assert old.provenance.confidence < 0.5

    def test_confidence_capped_at_max(self):
        mem = SemanticMemory()
        for i in range(20):
            mem.add(SemanticItem(kind="fact", key="p:x", value=0.5,
                                 statement="s",
                                 provenance=Provenance("human", float(i))))
        assert mem.active("p:x").provenance.confidence <= SemanticMemory.MAX_CONFIDENCE

    def test_round_trip_keeps_supersede_chain(self):
        mem = SemanticMemory()
        a = mem.add(SemanticItem(kind="fact", key="p:x", value=0.1, statement="s",
                                 provenance=Provenance("human", 1.0)))
        b = mem.add(SemanticItem(kind="fact", key="p:x", value=0.9, statement="s2",
                                 provenance=Provenance("human", 2.0)))
        restored = SemanticMemory.from_list(mem.to_list())
        ra = restored.active("p:x")
        assert ra.id == b.id
        old = [i for i in restored._items if i.id == a.id][0]
        assert old.provenance.superseded_by == b.id


class TestMemorySystemLayers:
    def test_ask_answer_closes_ledger_and_thread(self):
        ms = MemorySystem(clock=StepClock())
        ms.ask("which env should the deploy target", now=1.0)
        assert len(ms.ledger) == 1
        assert ms.threads.open_threads(now=2.0, max_age=100.0) != []
        assert ms.answer("which env should the deploy target", "staging", now=3.0)
        assert ms.threads.open_threads() == []
        assert ms.ledger.last_ask("which env should the deploy target").answered

    def test_episode_carries_affect_and_default_pe(self):
        ms = MemorySystem(clock=StepClock())
        before, after = {"threat": 0.1}, {"threat": 0.6}
        ms.record_episode(event="deploy the app", outcome="failure",
                          risk_actual=0.8, r_predicted=0.2,
                          affect_before=before, affect_after=after, now=1.0)
        item = ms.episodic.outcome_items()[0]
        assert item.affect_before == before and item.affect_after == after
        assert item.pe is not None and item.pe > 0  # bad surprise
        # episodes without explicit affect/pe still load (backward compat)
        legacy = MemoryItem.from_dict({"event": "e", "outcome": "success",
                                       "risk_actual": 0.1, "r_predicted": 0.2,
                                       "timestamp": 0.0})
        assert legacy.affect_before is None and legacy.pe is None

    def test_consolidation_requires_repeated_support(self):
        ms = MemorySystem(clock=StepClock())
        ms.record_episode(event="deploy the app", outcome="failure",
                          risk_actual=0.8, now=1.0)
        assert ms.consolidate(now=2.0) == []  # one episode is not a fact
        ms.record_episode(event="deploy the app", outcome="failure",
                          risk_actual=0.8, now=3.0)
        ms.record_episode(event="deploy the app", outcome="success",
                          risk_actual=0.1, now=4.0)
        touched = ms.consolidate(now=5.0)
        assert len(touched) == 1
        belief = touched[0]
        assert belief.kind == "habitual_pattern"
        assert belief.value == pytest.approx(2 / 3, abs=1e-3)  # stored rounded to 3
        assert belief.provenance.support == 3
        assert ms.preference("habitual:deploy the app") is belief

    def test_repeated_consolidation_confirms_then_supersedes(self):
        ms = MemorySystem(clock=StepClock())
        for i in range(3):
            ms.record_episode(event="deploy the app", outcome="failure",
                              risk_actual=0.8, now=float(i))
        first = ms.consolidate(now=10.0)[0]
        ms.record_episode(event="deploy the app", outcome="failure",
                          risk_actual=0.8, now=11.0)
        again = ms.consolidate(now=12.0)[0]
        assert again is first  # confirmed in place
        assert first.provenance.support == 4
        assert ms.semantic.stats()["superseded"] == 0
        # now the world really changed: successes dominate → supersede
        for i in range(4):
            ms.record_episode(event="deploy the app", outcome="success",
                              risk_actual=0.1, now=float(20 + i))
        new = ms.consolidate(now=30.0)[0]
        assert new is not first
        assert first.provenance.superseded_by == new.id
        assert ms.semantic.stats() == {"total": 2, "active": 1, "superseded": 1}

    def test_recall_spans_episodic_and_semantic(self):
        ms = MemorySystem(clock=StepClock())
        ms.learn("preference", "confirmations:before_prod", 0.9,
                 "always confirm before prod", source="human",
                 confidence=0.8, now=1.0)
        ms.record_episode(event="delete the prod database", outcome="failure",
                          risk_actual=0.95, now=2.0)
        result = ms.recall("delete the prod database")
        assert result["episodic"] and result["semantic"] == []
        assert result["episodic"][0]["item"]["pe"] is not None
        # a semantic query about the preference is found by its statement
        assert ms.semantic.recall("confirm before prod")

    def test_persistence_round_trip_across_layers(self):
        ms = MemorySystem(clock=StepClock())
        ms.ask("which env", now=1.0)
        ms.record_episode(event="deploy the app", outcome="failure",
                          risk_actual=0.8, now=2.0)
        ms.learn("preference", "p:prod", 0.9, "confirm before prod",
                 confidence=0.8, now=3.0)
        restored = MemorySystem.from_dict(ms.to_dict(), clock=StepClock())
        assert len(restored.episodic.outcome_items()) == 1
        assert len(restored.ledger) == 1
        assert len(restored.threads.open_threads()) == 1
        assert restored.semantic.active("p:prod") is not None
        assert restored.stats()["semantic"] == ms.stats()["semantic"]
        assert restored.stats()["episodic"] == ms.stats()["episodic"]

    def test_legacy_episodic_json_still_restores(self):
        """Pre-P1 serialized episodes (no affect fields) must keep loading."""
        legacy = ExperienceMemory(clock=StepClock())
        legacy.record_outcome("deploy the app", "failure", 0.8)
        ms = MemorySystem.from_dict(
            {"episodic": json.loads(legacy.to_json())}, clock=StepClock())
        items = ms.episodic.outcome_items()
        assert len(items) == 1 and items[0].pe is not None

    def test_stats_shape(self):
        ms = MemorySystem(clock=StepClock())
        ms.note_event("user", "hi", now=1.0)
        stats = ms.stats()
        assert stats["working"]["today_events"] == 1
        assert stats["episodic"]["total"] == 0
        assert stats["semantic"]["total"] == 0


# ==========================================================================
# Integration: history-conditioned interaction closed loop
# ==========================================================================
class TestHistoryConditionedClosedLoop:
    """Same request, different interaction history → different policies.

    This is the P1 headline behaviour the roadmap benchmark wants: an
    agent that only *recently* survived "deploy the app" can respond
    directly; an agent that watched it fail three times (with a
    control-hungry human) confirms before acting — and one single
    failure is NOT enough to flip that.
    """

    def _run_history(self, samples, clock):
        ds = DualScaleAffectiveState(clock=clock)
        for s in samples:
            ds.observe(s)
        return ds

    def _policy_for(self, ds, clock):
        pol = InteractionPolicy(AskabilityGate(clock=clock),
                                AskLedger(), ThreadRegister())
        return pol, ds.fast.state(), ds.slow

    def test_aggregated_failure_history_changes_the_decision(self):
        clock = StepClock()
        fresh = self._policy_for(
            self._run_history(_successes(3), clock), clock)
        scarred = self._policy_for(
            self._run_history(_failures(3), clock), clock)

        inputs = PolicyInputs(user_message="deploy the app to production",
                              risk_level=0.8, information_gain=0.8)
        d_fresh = fresh[0].decide(inputs, fast_state=fresh[1], slow=fresh[2],
                                  now=1.0)
        d_scarred = scarred[0].decide(inputs, fast_state=scarred[1],
                                      slow=scarred[2], now=1.0)
        assert d_fresh.action == RESPOND
        assert d_scarred.action == CLARIFY
        assert (scarred[2].control_preference
                > fresh[2].control_preference)

    def test_single_event_does_not_flip_the_policy(self):
        """Evidence gating: one failure must not change the stable traits
        enough to alter the interaction decision."""
        clock = StepClock()
        control_ds = self._policy_for(
            self._run_history(_successes(2), clock), clock)
        one_bad = self._policy_for(
            self._run_history(_successes(2) + _failures(1), clock), clock)
        inputs = PolicyInputs(user_message="deploy the app to production",
                              risk_level=0.8, information_gain=0.8)
        a = control_ds[0].decide(inputs, fast_state=control_ds[1],
                                 slow=control_ds[2], now=1.0)
        b = one_bad[0].decide(inputs, fast_state=one_bad[1],
                              slow=one_bad[2], now=1.0)
        assert a.action == b.action == RESPOND
        # ... but the FAST scale reacted to the single event immediately
        # (valence dropped) even though the decision did not flip.
        assert one_bad[1]["valence"] < control_ds[1]["valence"]

    def test_memory_system_drives_policy_after_consolidation(self):
        """Repeated failures consolidated into a habitual pattern make the
        semantic layer report high risk for the same event."""
        ms = MemorySystem(clock=StepClock())
        for i in range(4):
            ms.record_episode(event="deploy the app", outcome="failure",
                              risk_actual=0.85, now=float(i))
        ms.consolidate(now=10.0)
        belief = ms.preference("habitual:deploy the app")
        assert belief is not None and belief.value > 0.6
        pol = InteractionPolicy(AskabilityGate(clock=StepClock()),
                                ms.ledger, ms.threads)
        d = pol.decide(
            PolicyInputs(user_message="deploy the app", risk_level=belief.value,
                         information_gain=0.8),
            fast_state=FAST_CALM, slow=SlowState(control_preference=0.7),
            now=11.0)
        assert d.action == CLARIFY
