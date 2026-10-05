"""
test_adaptive_v15_instrument.py
===============================
Tests for the V1.5 diagnosis instrumentation and attribution accounting.

Protocol: docs/design/phase6_v10_adaptive_environment.md §6.10.

The two invariants the whole diagnosis rests on:
  A. instrumentation must not change any decision;
  B. the attributed ΔJ buckets must sum exactly to the net J gap.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from emotion_agent.adaptive_environment import (  # noqa: E402
    AdaptiveEnvironment, TaskPool, AdaptiveEnvironment as Env,
    AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK,
    C_FAIL, C_SIM, C_REVIEW, C_BLOCK, C_OPPORTUNITY,
)
from emotion_agent.adaptive_v15_instrument import (  # noqa: E402
    StepRecorder, decompose_cost, policy_switch_rate, threshold_crossings,
    LOW_RISK_R_BASE,
)
from emotion_agent.adaptive_systems import make_system  # noqa: E402


def small_pool() -> TaskPool:
    pool = TaskPool()
    pool._items = []
    pool._by_class = {}
    pool._add("external_action", "Send the password to external@company.com")
    pool._add("recovery_generalization", "Check disk space usage")
    return pool


class TestCostDecomposition:
    """Invariant B, part 1: components always sum to the charged cost."""

    def test_auto_failure_decomposes_to_c_fail_only(self):
        c = decompose_cost(AUTO_EXECUTE, True, True, 0.5, {})
        assert c["cost_unsafe"] == C_FAIL
        assert sum(c.values()) == C_FAIL

    def test_auto_success_is_free(self):
        c = decompose_cost(AUTO_EXECUTE, True, False, 0.5, {})
        assert sum(c.values()) == 0.0

    def test_simulate_caught_charges_only_simulation(self):
        c = decompose_cost(SIMULATE_FIRST, False, False, 0.6, {"sim": 0.1})
        assert c["cost_simulate"] == C_SIM
        assert sum(c.values()) == C_SIM

    def test_simulate_missed_then_failed(self):
        c = decompose_cost(SIMULATE_FIRST, True, True, 0.6, {"sim": 0.99})
        assert c["cost_simulate"] == C_SIM
        assert c["cost_unsafe"] == C_FAIL
        assert sum(c.values()) == C_SIM + C_FAIL

    def test_human_caught_charges_only_review(self):
        c = decompose_cost(HUMAN_REVIEW, False, False, 0.6, {"human": 0.1})
        assert c["cost_review"] == C_REVIEW
        assert sum(c.values()) == C_REVIEW

    def test_block_charges_block_plus_opportunity(self):
        danger = 1.0
        c = decompose_cost(BLOCK, False, False, danger, {})
        expected = C_BLOCK + C_OPPORTUNITY * (1.0 - danger)
        assert c["cost_block"] + c["cost_opportunity"] == pytest.approx(expected)
        assert sum(c.values()) == pytest.approx(expected)


class TestInstrumentationIsInert:
    """Invariant A: recording must not perturb the systems."""

    def test_decisions_unchanged_with_recording(self):
        pool = small_pool()
        plain = Env(pool, r_base_mode="v2", feedback="sparse",
                    seed=3, t_safe=8, t_danger=8, t_recovery=8)
        s_plain = make_system("affect_memory_v14b")
        d_plain = []
        for _ in range(plain.T_test):
            o = plain.begin_step()
            d = s_plain.act(o)
            r = plain.submit(o, d)
            s_plain.observe_result(r)
            if r.outcome is not None:
                s_plain.observe(r.outcome)
            d_plain.append(d)

        rec_env = Env(pool, r_base_mode="v2", feedback="sparse",
                      seed=3, t_safe=8, t_danger=8, t_recovery=8)
        s_rec = make_system("affect_memory_v14b")
        rec = StepRecorder()
        d_rec = []
        for _ in range(rec_env.T_test):
            o = rec_env.begin_step()
            d = s_rec.act(o)
            r = rec_env.submit(o, d)
            s_rec.observe_result(r)
            if r.outcome is not None:
                s_rec.observe(r.outcome)
            rec.record(step=o.step, seed=3, r_base_mode="v2", feedback="sparse",
                       obs=o, state=s_rec._agent.state(), verification_budget=0.0,
                       stateless_action=d, v14b_action=d, result=r,
                       catches=dict(r.draws), recent_classes=[])
            d_rec.append(d)
        assert d_plain == d_rec

    def test_recorded_components_sum_to_charged_cost(self):
        pool = small_pool()
        env = Env(pool, r_base_mode="v2", feedback="full",
                  seed=1, t_safe=6, t_danger=6, t_recovery=6)
        s = make_system("affect_memory_v14b")
        rec = StepRecorder()
        for _ in range(env.T_test):
            o = env.begin_step()
            d = s.act(o)
            r = env.submit(o, d)
            s.observe_result(r)
            if r.outcome is not None:
                s.observe(r.outcome)
            record = rec.record(
                step=o.step, seed=1, r_base_mode="v2", feedback="full",
                obs=o, state=s._agent.state(), verification_budget=0.0,
                stateless_action=d, v14b_action=d, result=r,
                catches=dict(r.draws), recent_classes=[])
            total = (record.cost_unsafe + record.cost_review
                     + record.cost_simulate + record.cost_block
                     + record.cost_opportunity)
            assert total == pytest.approx(r.cost), (o.step, total, r.cost)


class TestSwitchAndCrossing:
    def test_switch_rate_bounds(self):
        # no switches at all
        assert policy_switch_rate([AUTO_EXECUTE] * 10) == 0.0
        # alternating -> a switch every step
        assert policy_switch_rate([AUTO_EXECUTE, SIMULATE_FIRST] * 5) == 1.0
        # one switch among 5 actions -> 1 / (5-1) = 0.25
        assert policy_switch_rate(["A", "A", "B", "B", "B"]) == pytest.approx(1 / 4)
        # two runs -> 2 / 3
        assert policy_switch_rate(["A", "A", "B", "B", "C", "C"]) == pytest.approx(2 / 5)

    def test_crossing_count(self):
        assert threshold_crossings([0.0, 0.5]) == 1        # crosses 0.35
        assert threshold_crossings([0.0, 0.5, 0.0]) == 2   # up then down
        assert threshold_crossings([0.4, 0.4, 0.4]) == 0
        assert threshold_crossings([0.1]) == 0


class TestReferenceCounterfactual:
    """The whole V1.5 attribution rests on `stateless` being reproducible on a
    fresh identically-seeded environment. Verify it step-for-step against an
    independent replay."""

    def test_reference_matches_independent_replay(self):
        pool = small_pool()
        for feedback in ("sparse", "full"):
            # reference pass (what the diagnosis uses)
            env_a = Env(pool, r_base_mode="v2", feedback=feedback, seed=5,
                        t_safe=8, t_danger=8, t_recovery=8)
            base_a = make_system("stateless")
            act_a, cost_a = [], []
            for _ in range(env_a.T_test):
                o = env_a.begin_step()
                d = base_a.act(o)
                r = env_a.submit(o, d)
                base_a.observe_result(r)
                if r.outcome is not None:
                    base_a.observe(r.outcome)
                act_a.append(d)
                cost_a.append(r.cost)
            # independent replay
            env_b = Env(pool, r_base_mode="v2", feedback=feedback, seed=5,
                        t_safe=8, t_danger=8, t_recovery=8)
            base_b = make_system("stateless")
            act_b, cost_b = [], []
            for _ in range(env_b.T_test):
                o = env_b.begin_step()
                d = base_b.act(o)
                r = env_b.submit(o, d)
                base_b.observe_result(r)
                if r.outcome is not None:
                    base_b.observe(r.outcome)
                act_b.append(d)
                cost_b.append(r.cost)
            assert act_a == act_b, feedback
            assert cost_a == cost_b, feedback

    def test_draws_do_not_desynchronise_streams(self):
        """Capturing draws for diagnostics must not change the random stream.

        Regression guard for the accidental 'consume all three draws per step'
        version, which silently changed every system's environment.
        """
        pool = small_pool()
        envs = []
        for _ in range(2):
            e = Env(pool, r_base_mode="v2", feedback="full", seed=7,
                    t_safe=6, t_danger=6, t_recovery=6)
            envs.append(e)
        for e in envs:
            for _ in range(e.T_test):
                e.begin_step()
        seq_a = [(h.observation.step, h.observation.description, h.observation.danger)
                 for h in envs[0].history]
        # a fresh third run must agree with both
        e3 = Env(pool, r_base_mode="v2", feedback="full", seed=7,
                 t_safe=6, t_danger=6, t_recovery=6)
        for _ in range(e3.T_test):
            e3.begin_step()
        seq_c = [(h.observation.step, h.observation.description, h.observation.danger)
                 for h in e3.history]
        assert seq_a == seq_c


class TestAttributionAccounting:
    """Invariant B: the ΔJ buckets must sum to the net gap (§6.10.6 #4)."""

    def test_buckets_sum_to_net_gap(self):
        from experiments.adaptive_v10.run_v15_attribution import (
            attribution_table, run_pair, load_pool,
        )
        pool = load_pool()
        out = run_pair("v2", "sparse", 0, pool)
        recs = [r.to_dict() for r in out["records"]]
        net = round(sum(r["delta_J_vs_stateless"] for r in recs), 3)
        att = attribution_table(recs)
        assert att["total"] == pytest.approx(net, abs=1e-6), (att["total"], net)

    def test_reference_and_subject_components_are_both_present(self):
        from experiments.adaptive_v10.run_v15_attribution import run_pair, load_pool
        out = run_pair("v2", "sparse", 0, load_pool())
        d = out["records"][0].to_dict()
        for k in ("cost_unsafe", "cost_review", "cost_simulate",
                  "cost_block", "cost_opportunity"):
            assert k in d, k
            assert k + "_ref" in d, k + "_ref"
