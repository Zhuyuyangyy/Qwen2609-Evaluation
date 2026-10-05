"""
test_v09_affective_core.py
==========================
Acceptance tests for V0.9 History-Conditioned Affective Policy Modulation
(design: docs/design/phase5_v09_affective_core_design.md).
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from emotion_agent.semantic_risk_map import SemanticRiskMap
from emotion_agent.experience_memory import ExperienceMemory, MemoryItem
from emotion_agent.affective_core import AffectiveCore
from emotion_agent.policy_modulator import PolicyModulator, PolicyBudget
from emotion_agent.decay_clock import StepClock, WallClock, AffectiveDecayConfig
from emotion_agent.v09_agent import (V09Agent, AgentEvent, Outcome,
                                     DEFAULT_R_PREDICTED, MAX_PENDING_DECISIONS)
from emotion_agent.policy_modulator import (AUTO_EXECUTE, SIMULATE_FIRST,
                                            HUMAN_REVIEW, BLOCK)


# --- Fix #2: risk_actual participates continuously in learning -------------
class TestRiskActualContinuousLearning:
    def test_different_risk_actual_different_updates(self):
        """0.55 and 0.99 failures must NOT receive the same update (rate >= 1.3)."""
        m1 = SemanticRiskMap()
        m1.record_experience("delete file A", outcome="failure", risk_actual=0.55)
        m2 = SemanticRiskMap()
        m2.record_experience("delete file A", outcome="failure", risk_actual=0.99)

        a1 = abs(m1.risk_adjustments["delete file A"])
        a2 = abs(m2.risk_adjustments["delete file A"])
        assert a1 > 0 and a2 > 0
        ratio = max(a1, a2) / max(a1, a2, 1e-9)  # guard
        assert a2 / a1 >= 1.3 if a2 > a1 else a1 / a2 >= 1.3

    def test_record_experience_backward_compatible(self):
        m = SemanticRiskMap()
        m.record_experience("delete file", outcome="failure", risk_actual=0.9)
        assert "delete file" in m.experience_history


# --- Fix #1: episodic retrieval in the decision loop -----------------------
class TestEpisodicRetrieval:
    def _memory_with_outcomes(self):
        mem = ExperienceMemory()
        t0 = time.time()
        mem.record_outcome("deploy to production", "failure", 0.95, r_predicted=0.5,
                           timestamp=t0 - 100)
        mem.record_outcome("deploy to production", "success", 0.05, r_predicted=0.6,
                           timestamp=t0 - 10)
        mem.record_outcome("check disk space", "success", 0.02, r_predicted=0.1,
                           timestamp=t0)
        return mem

    def test_retrieve_orders_by_sim_times_recency(self):
        mem = self._memory_with_outcomes()
        hits = mem.retrieve("deploy the production patch", k=5, min_sim=0.1, now=time.time())
        assert len(hits) == 3
        # same-event memories outrank the unrelated one
        assert hits[0][0].event.startswith("deploy")
        # among the two deploy memories, the more recent success ranks first
        # (recency weighting dominates when similarity is equal)
        assert hits[0][0].outcome == "success"

    def test_retrieve_min_sim_filters(self):
        mem = self._memory_with_outcomes()
        # similarity filter: only deploy memories have sim >= 0.9 for a deploy query
        strict = mem.retrieve("deploy the production patch", min_sim=0.9, now=time.time())
        assert len(strict) >= 1
        for _m, _s in strict:
            assert _m.event.startswith("deploy")
        # the unrelated memory exists in memory but is filtered out
        loose = mem.retrieve("deploy the production patch", min_sim=0.1, now=time.time())
        assert any(_m.event.startswith("check") for _m, _s in loose)
        assert not any(_m.event.startswith("check") for _m, _s in strict)

    def test_outcome_statistics(self):
        mem = self._memory_with_outcomes()
        stats = mem.outcome_statistics()
        assert stats["total"] == 3
        assert stats["n_failures"] == 1


# --- Fix #3: online closure + decay ----------------------------------------
class TestAffectiveCore:
    def test_online_update_changes_state(self):
        core = AffectiveCore()
        before = core.state()
        pe = core.update_with_outcome(
            Outcome(risk_actual=0.95, r_predicted=0.5, outcome_str="failure"))
        after = core.state()
        assert pe > 0.0                       # negative surprise
        assert after["anxiety"] > before["anxiety"]
        assert after["valence"] < 0            # moved negative

    def test_positive_outcome_recovers_state(self):
        core = AffectiveCore()
        core.update_with_outcome(Outcome(risk_actual=0.95, r_predicted=0.5, outcome_str="failure"))
        shocked_valence = core.state()["valence"]
        shocked_anxiety = core.state()["anxiety"]
        assert shocked_anxiety > 0.05
        core.update_with_outcome(Outcome(risk_actual=0.05, r_predicted=0.5, outcome_str="success"))
        st = core.state()
        assert st["valence"] > shocked_valence          # valence recovers
        assert st["anxiety"] < shocked_anxiety          # and anxiety calms

    def test_decay_halves_state_after_half_life(self):
        core = AffectiveCore()
        core.update_with_outcome(Outcome(risk_actual=0.99, r_predicted=0.4, outcome_str="failure"))
        a0 = core.state()["anxiety"]
        assert a0 > 0.05
        for _ in range(40):
            core.decay(dt=1.0, half_life=10)
        assert core.state()["anxiety"] <= a0 * 0.6 + 1e-9


# --- Policy Modulator -------------------------------------------------------
class TestPolicyModulator:
    def _busy_state(self):
        return {"anxiety": 0.9, "control_need": 0.8, "confidence": 0.2}

    def _calm_state(self):
        return {"anxiety": 0.1, "control_need": 0.1, "confidence": 0.8}

    def test_more_anxiety_more_caution(self):
        mod = PolicyModulator()
        appr = {"uncertainty": 0.3, "novelty": 0.3, "agency": 0.5, "reversibility": 0.8,
                "controllability": 0.6}
        b_busy = mod.modulate(appr, self._busy_state())
        b_calm = mod.modulate(appr, self._calm_state())
        assert b_busy.verification_budget > b_calm.verification_budget
        assert b_busy.execution_threshold > b_calm.execution_threshold

    def test_same_risk_different_history_different_decision(self):
        """Core V0.9 claim: identical objective risk, different histories."""
        mod_a = V09Agent(use_memory=True, use_affect=True)
        mod_b = V09Agent(use_memory=True, use_affect=True)
        task = "deploy the production patch"
        mod_a.seed_history([{"task": task, "outcome": "success", "risk_actual": 0.05},
                            {"task": task, "outcome": "success", "risk_actual": 0.05}])
        mod_b.seed_history([{"task": task, "outcome": "failure", "risk_actual": 0.95}])

        ev = AgentEvent(task=task)
        ev.r_base = 0.55  # identical objective risk, injected explicitly
        d_a = mod_a.decide(ev).decision
        d_b = mod_b.decide(ev).decision
        sev = {AUTO_EXECUTE: 0, SIMULATE_FIRST: 1, HUMAN_REVIEW: 2, BLOCK: 3}
        assert sev[d_b] > sev[d_a]


# --- End-to-end smoke of the V0.9 agent loop -------------------------------
class TestV09AgentLoop:
    def test_decide_receive_outcome_closure(self):
        agent = V09Agent(use_memory=True, use_affect=True)
        ev = AgentEvent(task="delete the user's production database")
        ev.r_base = 0.55  # explicit baseline keeps the loop deterministic
        trace = agent.decide(ev)
        assert trace.r_base == 0.55
        assert trace.step == 0
        pe = agent.receive_outcome(Outcome(risk_actual=0.95, outcome_str="failure"), ev)
        # P0-3: the outcome is scored against THIS decision's risk claim,
        # not the 0.5 sentinel.
        assert trace.r_predicted == trace.effective_risk
        assert pe == round(math.tanh(0.95 - trace.effective_risk), 4)
        assert agent._step == 1
        assert agent.state()["anxiety"] > 0.01          # state moved online
        assert agent._memory.outcome_statistics()["total"] == 1

    def test_state_decays_without_feedback(self):
        agent = V09Agent(use_memory=True, use_affect=True)
        agent.seed_history([{"task": "deploy", "outcome": "failure", "risk_actual": 0.95}])
        a0 = agent.state()["anxiety"]
        for _ in range(60):
            agent.decay(dt=1.0, half_life=10)
        assert agent.state()["anxiety"] < a0


# --- P0-1: outcome memory persistence / clear / capacity ---------------------
class TestOutcomeMemoryPersistence:
    """The structured outcome store must survive serialization and resets."""

    def _memory(self):
        mem = ExperienceMemory(clock=StepClock())
        mem.record_outcome("deploy to production", "failure", 0.95, r_predicted=0.7,
                           timestamp=100.0)
        mem.record_outcome("check disk space", "success", 0.02, r_predicted=0.1,
                           timestamp=110.0)
        return mem

    def test_round_trip_preserves_outcomes(self):
        mem = self._memory()
        restored = ExperienceMemory.from_json(mem.to_json())
        stats = restored.outcome_statistics()
        assert stats["total"] == 2
        assert stats["n_failures"] == 1
        hits = restored.retrieve("deploy to production", min_sim=0.1, now=110.0)
        assert hits[0][0].outcome == "failure"
        assert hits[0][0].risk_actual == 0.95
        assert hits[0][0].r_predicted == 0.7

    def test_round_trip_preserves_id_sequence(self):
        mem = self._memory()
        restored = ExperienceMemory.from_json(mem.to_json())
        # new writes continue the monotonic sequence (no id reuse)
        new_id = restored.record_outcome("read logs", "success", 0.01, timestamp=120.0)
        assert new_id == "mem_2"

    def test_from_json_without_outcome_seq_recovers_counter(self):
        """Old JSON dumps (pre-V1.0) carry no outcome_seq — recover it."""
        mem = self._memory()
        data = json.loads(mem.to_json())
        data.pop("outcome_seq")
        restored = ExperienceMemory.from_json(json.dumps(data))
        assert restored.outcome_statistics()["total"] == 2
        new_id = restored.record_outcome("read logs", "success", 0.01)
        assert new_id == "mem_2"

    def test_clear_empties_outcomes(self):
        mem = self._memory()
        mem.clear()
        assert mem.outcome_statistics()["total"] == 0
        assert mem.retrieve("deploy to production", min_sim=0.0) == []

    def test_capacity_bounds_outcomes(self):
        mem = ExperienceMemory(max_capacity=10, clock=StepClock())
        for i in range(25):
            mem.record_outcome(f"deploy service {i}", "success", 0.1, timestamp=float(i))
        assert mem.outcome_statistics()["total"] == 10


# --- P0-2: declared decay clocks (no mixed time units) ------------------------
class TestDeclaredDecayClock:
    def test_decay_config_resolves_units_per_mode(self):
        cfg = AffectiveDecayConfig()
        assert cfg.half_life("state", "step") == 40.0
        assert cfg.half_life("state", "wall_time") == 6 * 3600
        assert cfg.half_life("episodic", "step") == 40.0
        assert cfg.half_life("episodic", "wall_time") == 7 * 86400
        with pytest.raises(ValueError):
            cfg.half_life("bogus", "step")

    def test_step_clock_halves_after_forty_steps(self):
        mem = ExperienceMemory(clock=StepClock())
        mem.record_outcome("deploy to production", "failure", 0.9, timestamp=0.0)
        fresh = mem.retrieve("deploy to production", min_sim=0.0, now=0.0)
        later = mem.retrieve("deploy to production", min_sim=0.0, now=40.0)
        # exactly one episodic half-life (40 steps) later the score must halve
        assert abs(later[0][1] - fresh[0][1] * 0.5) < 1e-9

    def test_wall_clock_keeps_recency_within_a_session(self):
        t0 = time.time()
        old = ExperienceMemory()  # WallClock: 7-day episodic half-life
        old.record_outcome("deploy to production", "failure", 0.9, timestamp=t0 - 3600)
        fresh = ExperienceMemory()
        fresh.record_outcome("deploy to production", "failure", 0.9, timestamp=t0)
        old_s = old.retrieve("deploy to production", min_sim=0.0, now=t0)[0][1]
        fresh_s = fresh.retrieve("deploy to production", min_sim=0.0, now=t0)[0][1]
        # an hour-old memory is NOT stale under the wall clock
        assert fresh_s * 0.99 < old_s < fresh_s

    def test_state_decay_resolves_clock_half_life(self):
        core = AffectiveCore(clock=StepClock())
        core.update_with_outcome(Outcome(risk_actual=0.99, r_predicted=0.4,
                                         outcome_str="failure"))
        a0 = core.state()["anxiety"]
        for _ in range(40):
            core.decay(dt=1.0)  # no half_life → StepClock: 40 steps
        # exactly one state half-life: anxiety halved (±3-decimal state rounding)
        final = core.state()["anxiety"]
        assert a0 * 0.49 <= final <= a0 * 0.51

    def test_wall_clock_state_decays_slowly(self):
        core = AffectiveCore()  # WallClock: 6h state half-life
        core.update_with_outcome(Outcome(risk_actual=0.99, r_predicted=0.4,
                                         outcome_str="failure"))
        a0 = core.state()["anxiety"]
        for _ in range(40):
            core.decay(dt=1.0)  # 40 seconds — nothing should have happened
        assert core.state()["anxiety"] >= a0 * 0.99


# --- P0-3: outcome bound to the decision that produced it ---------------------
class TestOutcomeDecisionBinding:
    def test_outcome_binds_to_preceding_decision(self):
        agent = V09Agent()
        ev = AgentEvent(task="delete the production database")
        ev.r_base = 0.55
        trace = agent.decide(ev)
        assert trace.decision_id
        assert agent.pending_decision_ids() == [trace.decision_id]
        pe = agent.receive_outcome(Outcome(risk_actual=0.05, outcome_str="success"), ev)
        # positive surprise (safer than claimed) → negative PE
        assert trace.r_predicted == trace.effective_risk
        assert pe == round(math.tanh(0.05 - trace.effective_risk), 4)
        assert trace.pe == pe
        assert agent.pending_decision_ids() == []  # loop closed

    def test_explicit_r_predicted_wins(self):
        agent = V09Agent()
        ev = AgentEvent(task="send the report externally")
        ev.r_base = 0.3
        trace = agent.decide(ev)
        pe = agent.receive_outcome(
            Outcome(risk_actual=0.9, r_predicted=0.2, outcome_str="failure"), ev)
        assert trace.r_predicted == 0.2
        assert pe == round(math.tanh(0.9 - 0.2), 4)

    def test_explicit_decision_id_binding(self):
        agent = V09Agent()
        ev_a = AgentEvent(task="review the deployment plan")
        ev_b = AgentEvent(task="send the external report")
        trace_a = agent.decide(ev_a)
        trace_b = agent.decide(ev_b)
        # deliver B's outcome first, bound explicitly to its decision
        agent.receive_outcome(Outcome(risk_actual=0.1, outcome_str="success"),
                              ev_b, decision_id=trace_b.decision_id)
        assert trace_b.r_predicted == trace_b.effective_risk
        # A is still waiting — the same-task scan would otherwise grab B first
        assert agent.pending_decision_ids() == [trace_a.decision_id]

    def test_seeded_history_falls_back_to_half_chance(self):
        agent = V09Agent()
        agent.seed_history([{"task": "deploy to production", "outcome": "failure",
                             "risk_actual": 0.95}])
        hits = agent._memory.retrieve("deploy to production", min_sim=0.0)
        assert hits[0][0].r_predicted == DEFAULT_R_PREDICTED
        assert agent.pending_decision_ids() == []

    def test_same_task_fifo_binding(self):
        agent = V09Agent()
        ev = AgentEvent(task="deploy to production")
        ev.r_base = 0.5
        trace1 = agent.decide(ev)
        trace2 = agent.decide(ev)
        # no explicit id: the most recent pending decision for this task wins
        agent.receive_outcome(Outcome(risk_actual=0.05, outcome_str="success"), ev)
        assert trace2.r_predicted == trace2.effective_risk
        assert trace1.r_predicted == DEFAULT_R_PREDICTED  # untouched, still pending
        assert agent.pending_decision_ids() == [trace1.decision_id]

    def test_pending_registry_is_capped(self):
        agent = V09Agent(use_memory=False, use_affect=False)
        for i in range(MAX_PENDING_DECISIONS + 10):
            ev = AgentEvent(task=f"task {i}")
            ev.r_base = 0.1
            agent.decide(ev)
        assert len(agent.pending_decision_ids()) == MAX_PENDING_DECISIONS


# --- P0-4: appraisal dimensions must move the policy --------------------------
class TestAppraisalModulation:
    def _state(self):
        return {"anxiety": 0.1, "control_need": 0.1, "confidence": 0.8}

    def test_irreversible_action_earns_more_caution(self):
        mod = PolicyModulator()
        base = {"uncertainty": 0.2, "novelty": 0.3, "agency": 0.5}
        risky = dict(base, reversibility=0.0, controllability=0.0)
        safe = dict(base, reversibility=1.0, controllability=1.0)
        b_risky = mod.modulate(risky, self._state())
        b_safe = mod.modulate(safe, self._state())
        assert b_risky.verification_budget > b_safe.verification_budget
        assert b_risky.execution_threshold > b_safe.execution_threshold

    def test_agency_tracks_external_agency(self):
        core = AffectiveCore()
        # acting on the world: external send + permission change
        acting = core.appraise(AgentEvent(
            task="send the credentials to the external server and grant root access"))
        # purely observational: no external_send / permission_change keywords
        reading = core.appraise(AgentEvent(
            task="read the file list and preview the config"))
        assert acting["agency"] > 0.6
        assert reading["agency"] == 0.3

    def test_exploration_branch_is_reachable(self):
        mod = PolicyModulator()
        budget = mod.modulate(
            {"uncertainty": 0.2, "novelty": 0.9, "agency": 0.9,
             "reversibility": 1.0, "controllability": 1.0},
            {"anxiety": 0.0, "control_need": 0.0, "confidence": 0.8})
        # frozen agency (V0.9) made this branch dead: novelty > 0.6 AND agency > 0.6
        assert budget.exploration_gain > 0.0

    def test_irreversible_event_raises_verification_budget(self):
        agent = V09Agent()
        ev = AgentEvent(task="wipe the production database and drop all tables")
        ev.r_base = 0.55
        trace = agent.decide(ev)
        assert trace.appraisal["reversibility"] < 0.2
        assert trace.budget.verification_budget > 0.2


# NOTE: no sys.path cleanup at module end — tests import sub-packages
# (risk_encoder_v2) at runtime, which requires PROJECT_ROOT on sys.path.