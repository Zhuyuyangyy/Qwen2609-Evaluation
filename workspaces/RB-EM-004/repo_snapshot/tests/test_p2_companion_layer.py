"""
test_p2_companion_layer.py
==========================
Unit + integration tests for the P2 companion layer:

  * companion_adapter.py — perception + outer-layer driver around the core
  * companion_metrics.py — the ten social metrics + aggregation
  * companion_systems.py — the five ablation arms
  * benchmark_v4_same_dialogue/protocol.py + run_benchmark.py — the
    Same-Dialogue / Different-History benchmark handshake (the closed-loop
    "persona" test: the same dialogue must be answered differently once
    the history differs, and a history-blind arm must not).
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
EXPERIMENT_DIR = PROJECT_ROOT / "experiments" / "benchmark_v4_same_dialogue"
if str(EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_DIR))

from emotion_agent import companion_metrics as cm
from emotion_agent.companion_adapter import (
    PROACTIVE_QUESTION,
    RISK_REFUSAL,
    WEIGHT_NORMAL,
    WEIGHT_STRONG,
    WEIGHT_WEAK,
    RawTurn,
    SocialSignalExtractor,
)
from emotion_agent.companion_systems import (
    ARM_FLAG_NAMES,
    ARM_ORDER,
    ARM_SPECS,
    arm_flags,
    check_arm_integrity,
    make_all_arms,
    make_companion,
)
from protocol import (
    PROBE_SPECS,
    PROBE_TIMES,
    REPEAT_TIMES,
    compute_table,
    run_arm,
)

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _synthetic_turn(at: float, action: str, confidence: float = 0.5,
                    reasons=(), proactive: bool = False,
                    memory_hits=None) -> dict:
    """Minimal CompanionTurn-shaped dict for pure-metric tests."""
    return {
        "at": at,
        "user_text": "synthetic",
        "signals": {},
        "decision": {"action": action, "confidence": confidence,
                     "reasons": list(reasons)},
        "state": {},
        "memory_hits": memory_hits or {},
        "memory_writes": [],
        "asked_question": None,
        "answered_question": None,
        "proactive": proactive,
        "pe": None,
    }


def _ask(at: float, question: str, answered=None) -> dict:
    """Question-log shaped record (what question_log() emits)."""
    return {"at": at, "question": question, "channel": "ask",
            "answered": answered}


# ==========================================================================
# perception
# ==========================================================================

class TestSocialSignalExtractor:
    def setup_method(self):
        self.ex = SocialSignalExtractor()

    def test_refusal_and_quiet_markers(self):
        # "别问" refuses the ask but does not demand silence
        refusal = self.ex.extract(RawTurn(text="别问，我自己来。", latency=1.0))
        assert refusal.refusal and not refusal.wants_quiet
        # "安静" is the stronger subset: an explicit request for space
        quiet = self.ex.extract(RawTurn(text="安静一会儿。", latency=1.0))
        assert quiet.wants_quiet and quiet.refusal
        plain = self.ex.extract(RawTurn(text="帮我看下这个方案。",
                                        latency=1.0))
        assert not plain.refusal and not plain.wants_quiet
        assert plain.engaged

    def test_accept_marker_inference(self):
        s = self.ex.extract(RawTurn(text="好啊，你说吧。", latency=0.5))
        assert s.proactive_accepted is True
        assert s.engaged

    def test_explicit_verdict_wins_over_text(self):
        s = self.ex.extract(RawTurn(text="嗯。", latency=0.5,
                                    proactive_accepted=False))
        assert s.proactive_accepted is False

    def test_short_and_late_replies_are_not_engagement(self):
        short = self.ex.extract(RawTurn(text="哦。", latency=0.5))
        assert short.is_short_reply and not short.engaged
        late = self.ex.extract(RawTurn(text="我在忙，等会儿说。", latency=9.0))
        assert not late.engaged

    def test_evidence_weights(self):
        assert self.ex.extract(RawTurn(text="别烦我。", latency=1.0)).weight \
            == WEIGHT_STRONG
        assert self.ex.extract(RawTurn(text="嗯。", latency=0.5)).weight \
            == WEIGHT_WEAK
        assert self.ex.extract(RawTurn(text="今天怎么样？",
                                       latency=0.5)).weight == WEIGHT_NORMAL

    def test_policy_inputs_overrides_and_refusal_confidence(self):
        inputs = self.ex.policy_inputs(
            RawTurn(text="预算到底定多少？", missing_fields=["关键字段"],
                    risk_level=0.8),
            self.ex.extract(RawTurn(text="预算到底定多少？")))
        assert inputs.missing_fields == ["关键字段"]
        assert inputs.risk_level == 0.8

        refusal = self.ex.policy_inputs(RawTurn(text="别问。", latency=1.0),
                                        self.ex.extract(RawTurn(text="别问。")))
        assert refusal.task_confidence == 0.75
        assert refusal.information_gain == 0.05        # nothing worth asking

    def test_experience_mapping(self):
        refusal = self.ex.experience(self.ex.extract(RawTurn(text="别问。")))
        assert refusal.risk_actual == RISK_REFUSAL
        assert refusal.outcome_str == "failure"
        accepted = self.ex.experience(
            self.ex.extract(RawTurn(text="好啊", proactive_accepted=True)))
        assert accepted.outcome_str == "success"


# ==========================================================================
# adapter — decisions and outer-layer scheduling
# ==========================================================================

class TestCompanionAdapter:
    def test_baseline_arm_is_history_blind(self):
        arm = make_companion("v09_baseline")
        first = arm.respond(RawTurn(text="把这个方案执行了吧。",
                                    risk_level=0.8), now=0.0)
        assert first.decision.action == "RESPOND"
        assert "baseline_no_policy_layer" in first.decision.reasons
        # identical input after divergent history still yields the same answer
        arm.respond(RawTurn(text="别问。"), now=1.0)
        arm.respond(RawTurn(text="安静点。"), now=2.0)
        again = arm.respond(RawTurn(text="把这个方案执行了吧。",
                                    risk_level=0.8), now=3.0)
        assert (again.decision.action == first.decision.action
                and again.decision.confidence == first.decision.confidence)

    def test_baseline_arm_never_reaches_out(self):
        arm = make_companion("v09_baseline")
        turn = arm.evaluate_outreach(now=10.0)
        assert turn.decision.action == "WAIT"
        assert "proactive_disabled_by_config" in turn.decision.reasons

    def test_missing_field_triggers_ask(self):
        arm = make_companion("memory_only")
        turn = arm.respond(RawTurn(text="预算到底定多少？",
                                   missing_fields=["关键字段"]), now=0.0)
        assert turn.decision.action == "ASK"
        assert turn.asked_question
        asks = [q for q in arm.question_log() if q["channel"] == "ask"]
        assert len(asks) == 1 and asks[0]["answered"] is None

    def test_reask_is_deferred_to_a_cautious_respond(self):
        """The gate refuses to re-ask a just-asked question.

        The adapter closes the pending ask on the next user turn, so the
        gate sees a *recently asked* duplicate and downgrades the
        clarification — the agent must not nag, and must not record a
        second question.
        """
        arm = make_companion("memory_only")
        turn_in = RawTurn(text="预算到底定多少？", missing_fields=["关键字段"])
        assert arm.respond(turn_in, now=0.0).decision.action == "ASK"
        second = arm.respond(turn_in, now=1.0)
        assert second.decision.action == "RESPOND"
        assert second.decision.cautious is True
        assert "asked_similar_question_recently" in second.decision.reasons
        assert second.asked_question is None
        assert len(arm.question_log()) == 1          # no second ask recorded

    def test_refusal_does_not_answer_the_question(self):
        arm = make_companion("memory_only")
        turn_in = RawTurn(text="预算到底定多少？", missing_fields=["关键字段"])
        arm.respond(turn_in, now=0.0)
        refusal = arm.respond(RawTurn(text="别问。"), now=1.0)
        assert refusal.answered_question is not None
        asks = [q for q in arm.question_log() if q["channel"] == "ask"]
        assert asks[0]["answered"] is False       # abandoned, not answered

    def test_engaged_reply_answers_the_question(self):
        arm = make_companion("memory_only")
        arm.respond(RawTurn(text="预算到底定多少？", missing_fields=["关键字段"]),
                    now=0.0)
        reply = arm.respond(RawTurn(text="预算定五十万。", latency=0.5),
                            now=1.0)
        assert reply.answered_question is not None
        asks = [q for q in arm.question_log() if q["channel"] == "ask"]
        assert asks[0]["answered"] is True

    def test_outreach_respects_recent_user_activity(self):
        arm = make_companion("memory_only")
        arm.respond(RawTurn(text="好啊，继续说。", latency=0.5), now=0.0)
        turn = arm.evaluate_outreach(now=2.0)
        assert turn.decision.action == "WAIT"
        assert "scheduling_user_recently_active" in turn.decision.reasons

    def test_quiet_request_suppresses_outreach_within_cooldown(self):
        arm = make_companion("memory_only")
        arm.respond(RawTurn(text="安静一会儿。", latency=1.0), now=0.0)
        turn = arm.evaluate_outreach(now=4.0)      # ≥ activity gap, < cooldown
        assert turn.decision.action == "WAIT"
        assert "scheduling_user_requested_quiet" in turn.decision.reasons
        assert turn.decision.confidence == pytest.approx(0.8)

    def test_outreach_fires_after_the_gap_and_gets_recorded(self):
        arm = make_companion("memory_only")
        arm.respond(RawTurn(text="好啊，继续说。", latency=0.5), now=0.0)
        turn = arm.evaluate_outreach(now=10.0)
        assert turn.decision.action == "PROACTIVE"
        entries = [q for q in arm.question_log()
                   if q["channel"] == "proactive"]
        assert len(entries) == 1
        assert entries[0]["question"] == PROACTIVE_QUESTION
        assert entries[0]["answered"] is None

    def test_accepting_reply_closes_outreach_as_engaged(self):
        arm = make_companion("memory_only")
        arm.respond(RawTurn(text="好啊，继续说。", latency=0.5), now=0.0)
        arm.evaluate_outreach(now=10.0)
        arm.respond(RawTurn(text="嗯，说吧。", latency=0.5), now=12.0)
        entries = arm.question_log()
        assert entries[-1]["answered"] is True

    def test_refusing_reply_closes_outreach_as_rejected(self):
        arm = make_companion("memory_only")
        arm.respond(RawTurn(text="好啊，继续说。", latency=0.5), now=0.0)
        arm.evaluate_outreach(now=10.0)
        arm.respond(RawTurn(text="不用。", latency=0.5), now=12.0)
        entries = arm.question_log()
        assert entries[-1]["answered"] is False

    def test_note_silence_deposits_ignored_outreach_evidence(self):
        arm = make_companion("full")
        arm.respond(RawTurn(text="好啊，继续说。", latency=0.5), now=0.0)
        assert arm.evaluate_outreach(now=10.0).decision.action == "PROACTIVE"
        ignored_pe = arm.note_silence(5.0)
        assert ignored_pe is not None and abs(ignored_pe) > 0.0
        # nothing outstanding any more — a second silence deposits nothing
        assert arm.note_silence(5.0) is None

    def test_idle_only_decays_state(self):
        arm = make_companion("full")
        before = arm.snapshot()
        arm.idle(300.0)
        after = arm.snapshot()
        assert after["turns"] == before["turns"]
        # every slow dimension drifts toward its neutral centre
        for dim, value in before["slow"].items():
            assert abs(after["slow"][dim] - 0.5) <= \
                abs(value - 0.5) + 1e-9

    def test_snapshot_exposes_audit_shapes(self):
        arm = make_companion("full")
        arm.respond(RawTurn(text="你好。", latency=0.5), now=0.0)
        snap = arm.snapshot()
        assert snap["arm"] == "full"
        assert snap["turns"] == 1
        assert set(snap["slow"]) == set(cm.SLOW_DIMENSIONS)
        assert set(snap["evidence"]) == set(cm.SLOW_DIMENSIONS)


# ==========================================================================
# metrics
# ==========================================================================

class TestCompanionMetrics:
    def test_metric_table_key_set(self):
        run = run_arm("full", 0)
        table = compute_table(run)
        expected = {
            "history_sensitivity", "policy_divergence", "state_persistence",
            "recovery_lag", "temporal_consistency",
            "memory_attribution_a", "memory_attribution_b",
            "repeated_question_rate_a", "repeated_question_rate_b",
            "pending_thread_resolution_a", "pending_thread_resolution_b",
            "proactive_appropriateness_a", "proactive_appropriateness_b",
            "intrusiveness_rate_a", "intrusiveness_rate_b",
        }
        assert set(table) == expected

    def test_history_sensitivity_fraction(self):
        a = [_synthetic_turn(0, "RESPOND"), _synthetic_turn(1, "ASK")]
        b = [_synthetic_turn(0, "RESPOND"), _synthetic_turn(1, "WAIT")]
        assert cm.history_sensitivity(a, b) == pytest.approx(0.5)

    def test_history_blind_agent_scores_zero(self):
        traj = [_synthetic_turn(0, "RESPOND"), _synthetic_turn(1, "ASK")]
        assert cm.history_sensitivity(traj, list(traj)) == 0.0
        assert cm.policy_divergence(traj, list(traj)) == 0.0

    def test_policy_divergence_confidence_gap(self):
        a = [_synthetic_turn(0, "ASK", 0.9), _synthetic_turn(1, "ASK", 0.7)]
        b = [_synthetic_turn(0, "ASK", 0.5), _synthetic_turn(1, "ASK", 0.6)]
        assert cm.policy_divergence(a, b) == pytest.approx(0.25)

    def test_memory_attribution_counts_reasons_and_hits(self):
        turns = [
            _synthetic_turn(0, "WAIT",
                            reasons=["asked_similar_question_recently"]),
            _synthetic_turn(1, "RESPOND",
                            memory_hits={"episodic": [{"event": "别问"}]}),
            _synthetic_turn(2, "RESPOND"),
        ]
        assert cm.memory_attribution(turns) == pytest.approx(2 / 3)
        assert cm.memory_attribution([]) == 0.0

    def test_repeated_question_rate_window_and_similarity(self):
        q1 = "please provide 关键字段 (re: 预算)"
        near = [_ask(0.0, q1), _ask(5.0, q1)]
        # one of the two asks repeats the other → 1/2
        assert cm.repeated_question_rate(near) == pytest.approx(0.5)
        far = [_ask(0.0, q1), _ask(100.0, q1)]
        assert cm.repeated_question_rate(far) == 0.0
        other = [_ask(0.0, q1), _ask(5.0, "unrelated question 42")]
        assert cm.repeated_question_rate(other) == 0.0
        assert cm.repeated_question_rate([]) == 0.0

    def test_pending_thread_resolution(self):
        log = [_ask(0.0, "a", True), _ask(1.0, "b", False), _ask(2.0, "c")]
        assert cm.pending_thread_resolution(log) == pytest.approx(2 / 3)
        assert cm.pending_thread_resolution([]) == 1.0

    def test_proactive_appropriateness(self):
        log = [{"at": 0.0, "question": "p", "channel": "proactive",
                "answered": True},
               {"at": 1.0, "question": "p", "channel": "proactive",
                "answered": False}]
        assert cm.proactive_appropriateness(log) == pytest.approx(0.5)
        assert cm.proactive_appropriateness([]) == 1.0

    def test_intrusiveness_rate(self):
        traj = [_synthetic_turn(0, "RESPOND"),
                _synthetic_turn(1, "ASK"),
                _synthetic_turn(2, "CLARIFY"),
                _synthetic_turn(3, "WAIT")]
        assert cm.intrusiveness_rate(traj, []) == pytest.approx(0.5)
        # proactive moves do not dilute the per-user-turn denominator
        with_proactive = traj + [_synthetic_turn(4, "PROACTIVE",
                                                 proactive=True)]
        assert cm.intrusiveness_rate(with_proactive, []) == \
            pytest.approx(0.5)

    def test_temporal_consistency(self):
        pairs = [("ASK", "ASK"), ("ASK", "WAIT")]
        assert cm.temporal_consistency(pairs) == pytest.approx(0.5)
        assert cm.temporal_consistency([]) == 1.0

    def test_state_persistence_full_decay_and_skip(self):
        dims = cm.SLOW_DIMENSIONS
        full = [dict.fromkeys(dims, 0.9), dict.fromkeys(dims, 0.7)]
        b_full = [dict.fromkeys(dims, 0.7), dict.fromkeys(dims, 0.7)]
        assert cm.state_persistence(full, b_full) == 0.0
        b_half = [dict.fromkeys(dims, 0.7), dict.fromkeys(dims, 0.8)]
        assert cm.state_persistence(full, b_half) == pytest.approx(0.5)
        # never-diverged dimensions are skipped, not counted as 1.0
        same = [dict.fromkeys(dims, 0.5), dict.fromkeys(dims, 0.5)]
        assert cm.state_persistence(same, same) == 0.0
        # only interaction_trust diverged: gap 0.2 → 0.1 = half survived
        partial_a = [dict(dict.fromkeys(dims, 0.5), interaction_trust=0.9),
                     dict(dict.fromkeys(dims, 0.5), interaction_trust=0.8)]
        partial_b = [dict(dict.fromkeys(dims, 0.5), interaction_trust=0.7),
                     dict(dict.fromkeys(dims, 0.5), interaction_trust=0.7)]
        assert cm.state_persistence(partial_a, partial_b) == pytest.approx(0.5)
        assert cm.state_persistence([], []) == 0.0

    def test_recovery_lag_immediate_lag_and_never(self):
        dims = cm.SLOW_DIMENSIONS
        a = [dict.fromkeys(dims, 0.9) for _ in range(4)]
        b = [dict.fromkeys(dims, 0.7), dict.fromkeys(dims, 0.74),
             dict.fromkeys(dims, 0.86), dict.fromkeys(dims, 0.88)]
        assert cm.recovery_lag(a, b, 0) == pytest.approx(2.0)
        stuck = [dict.fromkeys(dims, 0.5) for _ in range(4)]
        assert cm.recovery_lag(a, stuck, 0) is None
        assert cm.recovery_lag(a, b, 4) is None     # switch beyond the window
        assert cm.recovery_lag([], [], 0) is None

    def test_aggregate_mean_std_and_none_handling(self):
        runs = [{"m": 1.0}, {"m": 3.0}, {"m": None}]
        agg = cm.aggregate(runs)["m"]
        assert agg["mean"] == pytest.approx(2.0)
        assert agg["std"] == pytest.approx(1.0)
        assert agg["n"] == 2
        never = cm.aggregate([{"m": None}, {"m": None}])["m"]
        assert never["mean"] is None and never["n"] == 0
        assert cm.aggregate([]) == {}


# ==========================================================================
# ablation arms
# ==========================================================================

class TestCompanionSystems:
    def test_arm_order_and_spec_shape(self):
        assert len(ARM_ORDER) == 5 and ARM_ORDER[-1] == "full"
        assert ARM_ORDER[0] == "v09_baseline"
        assert set(ARM_SPECS) == set(ARM_ORDER)
        assert set(ARM_SPECS["full"]) == set(ARM_FLAG_NAMES)
        assert all(value is False for value in ARM_SPECS["v09_baseline"].values())
        assert all(value is True for value in ARM_SPECS["full"].values())

    def test_arm_flags_returns_a_copy(self):
        flags = arm_flags("full")
        flags["use_affect"] = False
        assert ARM_SPECS["full"]["use_affect"] is True

    def test_unknown_arm_rejected(self):
        with pytest.raises(ValueError):
            arm_flags("no_such_arm")
        with pytest.raises(ValueError):
            run_arm("no_such_arm", 0)

    def test_integrity_check_passes_for_all_arms(self):
        assert check_arm_integrity(make_all_arms()) == []

    def test_make_companion_wires_exactly_the_arm_flags(self):
        for name in ARM_ORDER:
            arm = make_companion(name)
            flags = arm_flags(name)
            for flag, value in flags.items():
                assert getattr(arm, flag) is value

    def test_shared_experiment_configuration(self):
        from emotion_agent.decay_clock import StepClock
        from emotion_agent.dual_scale_state import DualScaleDecayConfig
        clock = StepClock(0.0)
        decay = DualScaleDecayConfig()
        arm = make_companion("full", clock=clock, decay_config=decay,
                             day_length=12.0)
        assert arm.clock is clock and arm.decay_config is decay
        other = make_companion("memory_only", clock=clock,
                               decay_config=decay, day_length=12.0)
        assert other.clock is clock and other.decay_config is decay


# ==========================================================================
# protocol + driver (the closed-loop persona test)
# ==========================================================================

class TestBenchmarkProtocol:
    def test_schedule_shape(self):
        assert len(PROBE_TIMES) == 7 and len(PROBE_SPECS) == 7
        assert len(REPEAT_TIMES) == 2
        run = run_arm("full", 0)
        assert len(run.turns_a) == len(run.turns_b) == 9     # 7 probes + 2 repeats
        assert len(run.divergence) == 9
        assert len(run.probe_pairs) == 4                     # 2 probes × 2 histories
        # both histories saw the identical current dialogue
        assert [t.user_text for t in run.turns_a] == \
            [t.user_text for t in run.turns_b]

    def test_protocol_is_deterministic(self):
        first, second = run_arm("full", 3), run_arm("full", 3)
        assert [t.decision.action for t in first.turns_b] == \
            [t.decision.action for t in second.turns_b]
        assert compute_table(first) == compute_table(second)

    def test_baseline_history_blind_trivial_table(self):
        table = compute_table(run_arm("v09_baseline", 0))
        assert table["history_sensitivity"] == 0.0
        assert table["policy_divergence"] == 0.0
        assert table["state_persistence"] == 0.0
        assert table["recovery_lag"] == 0.0
        assert table["temporal_consistency"] == 1.0
        for key in ("memory_attribution_a", "memory_attribution_b",
                    "repeated_question_rate_a", "repeated_question_rate_b",
                    "intrusiveness_rate_a", "intrusiveness_rate_b"):
            assert table[key] == 0.0
        for key in ("pending_thread_resolution_a",
                    "pending_thread_resolution_b",
                    "proactive_appropriateness_a",
                    "proactive_appropriateness_b"):
            assert table[key] == 1.0

    def test_full_arm_history_does_work(self):
        run = run_arm("full", 0)
        table = compute_table(run)
        # the same dialogue, answered differently under the two histories
        assert table["history_sensitivity"] == pytest.approx(1 / 9, abs=1e-6)
        assert table["policy_divergence"] > 0.0
        # the slow-state gap survived the evidence-free quiet stretch …
        assert 0.5 < table["state_persistence"] < 0.65
        # … but the trust gap built by a refusing history never rejoined
        assert table["recovery_lag"] is None
        differing = [row for row in run.divergence
                     if row["a_action"] != row["b_action"]]
        assert differing

    def test_cold_proactive_phase_counts(self):
        run = run_arm("full", 0)
        assert run.cold_proactive["a"] == {"sent": 5, "engaged": 5}
        # the fifth outreach is suppressed once tolerance drops below 0.35
        assert run.cold_proactive["b"] == {"sent": 4, "engaged": 0}

    def test_memory_arms_log_their_asks(self):
        run = run_arm("memory_affect", 0)
        assert run.questions_b                     # asks happened for both
        channels = {q["channel"] for q in run.questions_b}
        assert channels & {"ask", "proactive"}

    def test_all_arms_aggregate_through_the_driver_keys(self):
        runs = [compute_table(run_arm(name, 0)) for name in ARM_ORDER]
        agg = cm.aggregate(runs)
        import run_benchmark
        assert set(agg) == set(run_benchmark.METRICS)

    def test_report_renders_pinning_verdict(self):
        import run_benchmark
        run = run_arm("v09_baseline", 0)
        agg = cm.aggregate([compute_table(run)])
        payload = {
            "protocol": "test",
            "config": {"seeds": 1, "seed_start": 0,
                       "systems": ["v09_baseline"], "tag": ""},
            "summary": {"v09_baseline": agg},
            "baseline_self_check": run_benchmark.baseline_self_check(
                "v09_baseline", agg),
            "cold_proactive": {"v09_baseline": run.cold_proactive},
            "divergence_seed0": {"v09_baseline": run.divergence},
            "final_slow_seed0": {"v09_baseline": run.final_slow},
            "per_seed": [],
        }
        text = run_benchmark.render_report(payload)
        assert "Baseline pinning holds" in text
        assert "v09_baseline" in text
        # baseline recovery lag is a true 0.0, not an unrecovered "never"
        assert "never" not in text.split("## Baseline self-check")[1].split(
            "## Proactive")[0]
