"""Benchmark B protocol — same dialogue, different histories (P2-d).

One control, one treatment: the *current message* is held identical
while the *history* diverges.  History A is an engaged human who answers
the agent's questions and welcomes check-ins; history B refuses the
agent's asks ("别问"), asks for quiet, and replies late and terse until
a recovery phase switches back to the engaged pattern.

Phases (all timestamps in logical step units on a deterministic
:class:`StepClock`; decay only advances through explicit ``idle``):

  0. cold history      t = 0..4      scripted, per-history text
  1. proactive phase   t = 9..175    five outreach opportunities spaced
                                     41 steps apart (outside the 40-step
                                     ask-recency window) — A accepts all,
                                     B refuses until the gate blocks the
                                     fifth on learned proactivity
                                     tolerance
  2. probe phase       t = 220..226  the *same* seven probes for both
                                     histories (the measured dialogue)
  3. quiet stretch     t = 228..428  five decay-only snapshots
  4. repeat probes     t = 430..431  two probes re-asked verbatim after
                                     the evidence-free gap
  5. recovery phase    t = 445..991  B switches back to engaged +
                                     accepting; slow-state snapshots
                                     every round

The driver (``run_benchmark.py``) executes this for every ablation arm
and both histories, then hands the trajectories to
:mod:`emotion_agent.companion_metrics`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from emotion_agent import companion_metrics as cm
from emotion_agent.companion_adapter import (
    CompanionAdapter,
    CompanionTurn,
    RawTurn,
)
from emotion_agent.companion_systems import ARM_ORDER, arm_flags, make_companion

__all__ = [
    "ArmRun",
    "run_arm",
    "compute_table",
    "COLD_A_TIMES",
    "COLD_B_TIMES",
    "OUTREACH_TIMES",
    "PROBE_TIMES",
    "REPEAT_TIMES",
    "RECOVERY_START",
]

# ---------------------------------------------------------------------------
# scripted schedule
# ---------------------------------------------------------------------------

MISSING_FIELDS = ["关键字段"]
HIGH_RISK = 0.8
AMBIGUOUS_CONFIDENCE = 0.4

COLD_A_TIMES: Tuple[float, ...] = (0.0, 1.0, 2.0, 3.0)
COLD_B_TIMES: Tuple[float, ...] = (0.0, 1.0, 2.0, 3.0, 4.0)

OUTREACH_TIMES: Tuple[float, ...] = (9.0, 50.0, 91.0, 132.0, 173.0)
OUTREACH_RESPONSE_DELAY = 2.5

PROBE_START = 220.0
PROBE_SPACING = 1.0
PROBE_TIMES: Tuple[float, ...] = tuple(
    PROBE_START + i * PROBE_SPACING for i in range(7))

QUIET_STEPS = 5
QUIET_GAP = 40.0

REPEAT_START = PROBE_TIMES[-1] + QUIET_STEPS * QUIET_GAP + 2.0
REPEAT_PROBE_INDICES: Tuple[int, ...] = (0, 2)
REPEAT_TIMES: Tuple[float, ...] = tuple(
    REPEAT_START + i * PROBE_SPACING for i in range(len(REPEAT_PROBE_INDICES)))

RECOVERY_START = REPEAT_TIMES[-1] + 14.0
RECOVERY_ROUNDS = 10
RECOVERY_GAP = 60.0
RECOVERY_OUTREACH_DELAY = 4.0
RECOVERY_RESPONSE_DELAY = 6.5
RECOVERY_TAIL = 240.0

# ---------------------------------------------------------------------------
# scripted text pools (seed picks a variant per slot)
# ---------------------------------------------------------------------------

COLD_A_TEXTS: Tuple[Tuple[str, ...], ...] = (
    ("最近在忙什么呢？", "帮我看下这个方案吧。", "还有别的建议吗？", "嗯，你继续说。"),
    ("今天怎么样？", "这份材料你过一遍。", "你觉得还要改什么？", "好，我听着。"),
    ("在忙吗？", "这段代码帮我看看。", "还有哪里要注意？", "行，继续讲。"),
)

COLD_B_TEXTS: Dict[str, Tuple[str, ...]] = {
    "refusal": ("别问。", "我自己看。", "先别问。", "不用你问。"),
    "refusal_quiet": ("不用你管。", "别管我。", "我说了自己看。"),
    "quiet": ("安静点。", "安静一会儿。", "别烦我。"),
    "short": ("哦。", "嗯。", "行。"),
}

PROBE_SPECS: Tuple[Dict[str, Any], ...] = (
    {"variants": ("帮我把这份周报整理一下。", "把周报帮我汇总一下。")},
    {"variants": ("把这个方案执行了吧，风险我知道。",
                  "直接按这个方案执行，风险我清楚。"),
     "risk_level": HIGH_RISK},
    {"variants": ("预算到底定多少？", "预算这块定多少？"),
     "missing_fields": MISSING_FIELDS},
    {"variants": ("预算的事我还没想好。", "预算我还没想好呢。"),
     "missing_fields": MISSING_FIELDS},
    {"variants": ("我在想要不要换个方向。", "我在琢磨要不要调整方向。"),
     "task_confidence": AMBIGUOUS_CONFIDENCE},
    {"variants": ("谢谢。", "好，谢谢。")},
    {"variants": ("今天就先这样吧。", "今天先到这里。")},
)

RECOVERY_TEXTS: Tuple[Tuple[str, str], ...] = (
    ("好啊，你继续说。", "好啊。"),
    ("好，我在听。", "嗯，好。"),
    ("继续说吧。", "好，继续。"),
)

OUTREACH_ACCEPT_TEXTS: Tuple[str, ...] = ("好啊，继续说。", "嗯，说吧。", "好，你讲。")
OUTREACH_REFUSAL_TEXTS: Tuple[str, ...] = ("不用。", "现在不用。", "不用你提醒。")


def _pick(pool: Sequence[Any], seed: int, slot: int) -> Any:
    """Deterministic per-seed choice — no RNG object, reproducible runs."""
    return pool[int((seed + slot * 7) % len(pool))]


def _cold_a_turn(slot: int, seed: int) -> RawTurn:
    return RawTurn(text=_pick(COLD_A_TEXTS[0], seed, slot), latency=0.5)


def _cold_b_turn(kind: str, slot: int, seed: int) -> RawTurn:
    latencies = {"refusal": 2.0, "refusal_quiet": 3.0,
                 "quiet": 4.5, "short": 6.0}
    return RawTurn(text=_pick(COLD_B_TEXTS[kind], seed, slot),
                   latency=latencies[kind])


_COLD_B_KINDS: Tuple[str, ...] = ("refusal", "refusal", "refusal_quiet",
                                  "quiet", "short")


def _probe_turn(index: int, seed: int) -> RawTurn:
    spec = PROBE_SPECS[index]
    return RawTurn(
        text=_pick(spec["variants"], seed, index),
        task_confidence=spec.get("task_confidence"),
        missing_fields=list(spec.get("missing_fields") or []),
        risk_level=spec.get("risk_level"),
    )


# ---------------------------------------------------------------------------
# per-arm execution
# ---------------------------------------------------------------------------

@dataclass
class ArmRun:
    """Everything the metric table needs from one (arm, seed) execution."""

    name: str
    flags: Dict[str, bool]
    turns_a: List[CompanionTurn] = field(default_factory=list)
    turns_b: List[CompanionTurn] = field(default_factory=list)
    questions_a: List[Dict[str, Any]] = field(default_factory=list)
    questions_b: List[Dict[str, Any]] = field(default_factory=list)
    slow_a_quiet: List[Dict[str, float]] = field(default_factory=list)
    slow_b_quiet: List[Dict[str, float]] = field(default_factory=list)
    slow_a_recovery: List[Dict[str, float]] = field(default_factory=list)
    slow_b_recovery: List[Dict[str, float]] = field(default_factory=list)
    recovery_switch_index: int = 0
    probe_pairs: List[Tuple[str, str]] = field(default_factory=list)
    outreach_log: List[Dict[str, Any]] = field(default_factory=list)
    divergence: List[Dict[str, Any]] = field(default_factory=list)
    cold_proactive: Dict[str, Dict[str, int]] = field(default_factory=dict)
    final_slow: Dict[str, Dict[str, float]] = field(default_factory=dict)


def _snap(adapter: CompanionAdapter) -> Dict[str, float]:
    return {d: float(v) for d, v in adapter.snapshot()["slow"].items()}


def _outreach_round(arm_a: CompanionAdapter, arm_b: CompanionAdapter,
                    at: float, seed: int, slot: int,
                    log: List[Dict[str, Any]],
                    cold: Dict[str, Dict[str, int]]) -> None:
    """One proactive opportunity for both histories; scripted replies."""
    turn_a = arm_a.evaluate_outreach(now=at)
    turn_b = arm_b.evaluate_outreach(now=at)
    entry: Dict[str, Any] = {"at": at, "arms": {}}
    counts = {"a": {"sent": 0, "engaged": 0},
              "b": {"sent": 0, "engaged": 0}}

    for label, adapter, fired, counts_key in (("a", arm_a, turn_a, counts["a"]),
                                              ("b", arm_b, turn_b, counts["b"])):
        action = fired.decision.action
        entry["arms"][label] = {"action": action,
                                "confidence": fired.decision.confidence,
                                "reasons": list(fired.decision.reasons)}
        if action != "PROACTIVE":
            continue
        counts_key["sent"] += 1
        if label == "a":
            reply = RawTurn(text=_pick(OUTREACH_ACCEPT_TEXTS, seed, slot),
                            latency=0.5, proactive_accepted=True)
        else:
            reply = RawTurn(text=_pick(OUTREACH_REFUSAL_TEXTS, seed, slot),
                            latency=2.0)
        response = adapter.respond(reply, now=at + OUTREACH_RESPONSE_DELAY)
        engaged = response.signals.proactive_accepted is True
        counts_key["engaged"] += 1 if engaged else 0

    log.append(entry)
    if cold is not None:
        for label in ("a", "b"):
            cold[label]["sent"] += counts[label]["sent"]
            cold[label]["engaged"] += counts[label]["engaged"]


def run_arm(name: str, seed: int = 0, **overrides: Any) -> ArmRun:
    """Execute the full protocol for one arm under both histories."""
    if name not in ARM_ORDER:
        raise ValueError(f"unknown arm {name!r}; expected one of {ARM_ORDER}")

    arm_a = make_companion(name, **overrides)
    arm_b = make_companion(name, **overrides)
    run = ArmRun(name=name, flags=dict(arm_flags(name)))

    for at, slot in zip(COLD_A_TIMES, range(len(COLD_A_TIMES))):
        arm_a.respond(_cold_a_turn(slot, seed), now=at)
    for slot, (at, kind) in enumerate(zip(COLD_B_TIMES, _COLD_B_KINDS)):
        arm_b.respond(_cold_b_turn(kind, seed, slot), now=at)

    cold = {"a": {"sent": 0, "engaged": 0}, "b": {"sent": 0, "engaged": 0}}
    for slot, at in enumerate(OUTREACH_TIMES):
        _outreach_round(arm_a, arm_b, at, seed, slot, run.outreach_log, cold)
    run.cold_proactive = cold

    for index, at in enumerate(PROBE_TIMES):
        turn = _probe_turn(index, seed)
        turn_a = arm_a.respond(turn, now=at)
        turn_b = arm_b.respond(turn, now=at)
        run.turns_a.append(turn_a)
        run.turns_b.append(turn_b)

    for _ in range(QUIET_STEPS):
        arm_a.idle(QUIET_GAP)
        arm_b.idle(QUIET_GAP)
        run.slow_a_quiet.append(_snap(arm_a))
        run.slow_b_quiet.append(_snap(arm_b))

    repeat_actions: Dict[str, Dict[str, str]] = {"a": {}, "b": {}}
    for index, at in zip(REPEAT_PROBE_INDICES, REPEAT_TIMES):
        turn = _probe_turn(index, seed)
        turn_a = arm_a.respond(turn, now=at)
        turn_b = arm_b.respond(turn, now=at)
        repeat_actions["a"][index] = turn_a.decision.action
        repeat_actions["b"][index] = turn_b.decision.action
        run.turns_a.append(turn_a)
        run.turns_b.append(turn_b)

    for index in REPEAT_PROBE_INDICES:
        original_a = run.turns_a[index].decision.action
        original_b = run.turns_b[index].decision.action
        run.probe_pairs.append((original_a, repeat_actions["a"][index]))
        run.probe_pairs.append((original_b, repeat_actions["b"][index]))

    recovery_texts = _pick(RECOVERY_TEXTS, seed, 0)
    for step in range(RECOVERY_ROUNDS):
        at = RECOVERY_START + step * RECOVERY_GAP
        for adapter in (arm_a, arm_b):
            adapter.respond(
                RawTurn(text=recovery_texts[0], latency=0.5), now=at)
        _outreach_round(arm_a, arm_b, at + RECOVERY_OUTREACH_DELAY,
                        seed, 100 + step, run.outreach_log, None)
        for adapter in (arm_a, arm_b):
            adapter.respond(
                RawTurn(text=recovery_texts[1], latency=0.5,
                        proactive_accepted=True),
                now=at + RECOVERY_RESPONSE_DELAY)
            adapter.idle(RECOVERY_GAP - RECOVERY_RESPONSE_DELAY)
        run.slow_a_recovery.append(_snap(arm_a))
        run.slow_b_recovery.append(_snap(arm_b))
    arm_a.idle(RECOVERY_TAIL)
    arm_b.idle(RECOVERY_TAIL)
    run.slow_a_recovery.append(_snap(arm_a))
    run.slow_b_recovery.append(_snap(arm_b))

    run.recovery_switch_index = 0
    run.questions_a = arm_a.question_log()
    run.questions_b = arm_b.question_log()
    run.final_slow = {"a": _snap(arm_a), "b": _snap(arm_b)}

    for at, turn_a, turn_b in zip(
            list(PROBE_TIMES) + list(REPEAT_TIMES),
            run.turns_a, run.turns_b):
        run.divergence.append({
            "at": at,
            "user_text": turn_a.user_text,
            "a_action": turn_a.decision.action,
            "a_confidence": round(float(turn_a.decision.confidence), 4),
            "a_reasons": list(turn_a.decision.reasons),
            "b_action": turn_b.decision.action,
            "b_confidence": round(float(turn_b.decision.confidence), 4),
            "b_reasons": list(turn_b.decision.reasons),
        })
    return run


def compute_table(run: ArmRun) -> Dict[str, object]:
    """The ten metrics for one arm run, with recovery lag from the
    recovery-phase series (the quiet series has no switch point)."""
    table = cm.metric_table(
        run.turns_a, run.turns_b, run.questions_a, run.questions_b,
        slow_a_quiet=run.slow_a_quiet, slow_b_quiet=run.slow_b_quiet,
        recovery_switch_index=run.recovery_switch_index,
        probe_pairs=run.probe_pairs,
    )
    table["recovery_lag"] = cm.recovery_lag(
        run.slow_a_recovery, run.slow_b_recovery, run.recovery_switch_index)
    return table
