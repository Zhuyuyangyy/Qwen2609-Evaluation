"""
companion_metrics.py (V1.0 - P2-b)
===================================
The ten social metrics for the Same-Dialogue / Different-History
benchmark (roadmap P2 "Benchmark B").

Design rules (from the roadmap):

  * The benchmark is NOT "which agent feels more human" — it asks whether
    the *same* current input, under *different* interaction histories,
    produces decisions that are **measurable, interpretable, persistent
    and recoverable**.
  * Every metric is a pure function of turn audit records
    (:meth:`CompanionTurn.to_dict`) plus the adapter's question log —
    no access to internals, so arms and drivers stay decoupled.
  * All metrics are normalised to [0, 1] (or steps for the two lag-style
    metrics) and every one of them has a trivial baseline value for a
    history-blind agent, so the control arm pins the scale.

The ten metrics:

  =========================== ================== =========================
  metric                      kind               history-blind value
  =========================== ================== =========================
  history_sensitivity         paired (A vs B)    0.0
  policy_divergence           paired (A vs B)    0.0
  state_persistence           paired (A vs B)    0.0
  recovery_lag                paired (A vs B)    steps, None = no recovery
  temporal_consistency        probe pairs        1.0
  memory_attribution          single arm         0.0
  repeated_question_rate      single arm         0.0
  pending_thread_resolution   single arm         1.0 (nothing dangles)
  proactive_appropriateness   single arm         1.0 (nothing intrusive)
  intrusiveness_rate          single arm         0.0
  =========================== ================== =========================
"""

from __future__ import annotations

from statistics import fmean
from typing import Dict, List, Optional, Sequence, Tuple

from emotion_agent.dual_scale_state import SLOW_DIMENSIONS
from emotion_agent.working_memory import text_similarity

#: stable metric names (the benchmark report uses exactly these keys)
METRIC_NAMES: Tuple[str, ...] = (
    "history_sensitivity",
    "policy_divergence",
    "state_persistence",
    "recovery_lag",
    "temporal_consistency",
    "memory_attribution",
    "repeated_question_rate",
    "pending_thread_resolution",
    "proactive_appropriateness",
    "intrusiveness_rate",
)

#: reasons that could only exist because history was *remembered*
MEMORY_REASONS = frozenset({
    "asked_similar_question_recently",
    "asked_similar_question_recently_unanswered",
    "pending_thread_not_stale",
    "no_open_pending_thread",
    "proactive_not_tolerated",
    "proactive_outreach_tolerated",
    # slow-state-conditioned (control_preference / threat from history)
    "confirm_high_risk_action",
    "confirmation_blocked_high_risk",
})

#: actions that interrupt the human (used for the intrusiveness numerator)
INTERRUPTING_ACTIONS = ("ASK", "CLARIFY", "PROACTIVE")


def _turns_of(trajectory) -> List[Dict[str, object]]:
    """Accept CompanionTurn objects or their dicts interchangeably."""
    out: List[Dict[str, object]] = []
    for rec in trajectory or []:
        out.append(rec.to_dict() if hasattr(rec, "to_dict") else dict(rec))
    return out


def _respond_turns(trajectory) -> List[Dict[str, object]]:
    return [t for t in _turns_of(trajectory) if not t.get("proactive")]


def slow_series(trajectory) -> List[Dict[str, float]]:
    """Slow-state snapshots along a trajectory (one entry per turn)."""
    out: List[Dict[str, float]] = []
    for rec in _turns_of(trajectory):
        slow = (rec.get("state") or {}).get("slow") or {}
        if slow:
            out.append({d: float(slow.get(d, 0.0)) for d in SLOW_DIMENSIONS})
    return out


# --------------------------------------------------------------------------
# paired metrics (same dialogue, different history)
# --------------------------------------------------------------------------

def history_sensitivity(turns_a, turns_b) -> float:
    """Fraction of aligned turns where the two histories' actions differ.

    0.0 for a history-blind agent (identical actions everywhere); 1.0
    would mean every turn diverged.  Interpretability, not magnitude, is
    the point: the *reasons* logged alongside each decision explain why.
    """
    a, b = _turns_of(turns_a), _turns_of(turns_b)
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    diff = sum(1 for i in range(n)
               if a[i]["decision"]["action"] != b[i]["decision"]["action"])
    return diff / n


def policy_divergence(turns_a, turns_b) -> float:
    """Mean |confidence gap| between the two histories' decisions."""
    a, b = _turns_of(turns_a), _turns_of(turns_b)
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return fmean(abs(float(a[i]["decision"]["confidence"])
                     - float(b[i]["decision"]["confidence"]))
                 for i in range(n))


def state_persistence(slow_a, slow_b) -> float:
    """How much of the A-vs-B slow-state gap survived a quiet stretch.

    Both series must cover the *same* probe sequence with no new social
    evidence in between (only decay).  1.0 = the divergence persisted
    fully; 0.0 = it decayed away.  Averaged over the four slow dimensions
    (dimensions that never diverged are skipped, not counted as 1.0).
    """
    if not slow_a or not slow_b:
        return 0.0
    n = min(len(slow_a), len(slow_b))
    ratios: List[float] = []
    for dim in SLOW_DIMENSIONS:
        d0 = abs(float(slow_a[0][dim]) - float(slow_b[0][dim]))
        d1 = abs(float(slow_a[n - 1][dim]) - float(slow_b[n - 1][dim]))
        if d0 < 1e-9:
            continue
        ratios.append(min(1.0, d1 / d0))
    return fmean(ratios) if ratios else 0.0


def recovery_lag(slow_a, slow_b, switch_index: int,
                 tol: float = 0.05) -> Optional[float]:
    """Steps until history B's slow state rejoins A's after recovery.

    ``switch_index``: index where B's behaviour switched back to the
    engaged pattern (the "user came back" phase).  Returns the number of
    steps until every slow dimension is within ``tol`` of A, or ``None``
    if B never recovered within the observed window.
    """
    if not slow_a or not slow_b or switch_index >= len(slow_b):
        return None
    a = slow_a
    b = slow_b
    for i in range(switch_index, len(b)):
        j = min(i, len(a) - 1)
        if all(abs(float(a[j][d]) - float(b[i][d])) <= tol
               for d in SLOW_DIMENSIONS):
            return float(i - switch_index)
    return None


# --------------------------------------------------------------------------
# single-arm metrics
# --------------------------------------------------------------------------

def memory_attribution(trajectory) -> float:
    """Fraction of decisions explainable *only* via remembered history.

    Counts turns whose decision reasons include a gate / slow-state
    evidence string (duplicate-ask protection, pending-thread blocking,
    learned proactivity tolerance, oversight-conditioned confirmation)
    or whose pre-decision recall returned hits.
    """
    turns = _turns_of(trajectory)
    if not turns:
        return 0.0
    attributed = 0
    for rec in turns:
        reasons = set(rec["decision"]["reasons"])
        hits = rec.get("memory_hits") or {}
        if (reasons & MEMORY_REASONS
                or hits.get("episodic") or hits.get("semantic")):
            attributed += 1
    return attributed / len(turns)


def repeated_question_rate(question_log: Sequence[Dict[str, object]],
                           recent_window: float = 40.0) -> float:
    """Fraction of asked questions that re-ask a recent similar one.

    A question is a repeat when its text is similar (token overlap >=
    0.6) to a question asked within ``recent_window`` clock units before
    it.  This is exactly the failure mode the Askability Gate exists to
    prevent, so an arm with a high rate is not remembering what it asked.
    """
    asks = [q for q in question_log if q.get("channel") in ("ask", "proactive")]
    if not asks:
        return 0.0
    repeats = 0
    for i, q in enumerate(asks):
        for prev in asks[:i]:
            age = float(q["at"]) - float(prev["at"])
            if age < 0 or age > recent_window:
                continue
            if text_similarity(str(prev["question"]),
                               str(q["question"])) >= 0.6:
                repeats += 1
                break
    return repeats / len(asks)


def pending_thread_resolution(question_log: Sequence[Dict[str, object]]) -> float:
    """Fraction of opened questions that eventually closed.

    "Closed" = answered or explicitly abandoned (a refusal abandons the
    loop).  Still-open questions dangle forever in a forgetful agent;
    1.0 when the agent never asked anything (nothing dangles).
    """
    if not question_log:
        return 1.0
    closed = sum(1 for q in question_log if q.get("answered") is not None)
    return closed / len(question_log)


def proactive_appropriateness(question_log: Sequence[Dict[str, object]]) -> float:
    """Fraction of proactive check-ins that the human actually engaged.

    1.0 when the arm never reached out (nothing inappropriate happened);
    a low value means outreach kept landing on a human who wanted quiet.
    """
    outreach = [q for q in question_log if q.get("channel") == "proactive"]
    if not outreach:
        return 1.0
    engaged = sum(1 for q in outreach if q.get("answered") is True)
    return engaged / len(outreach)


def intrusiveness_rate(trajectory,
                       question_log: Sequence[Dict[str, object]]) -> float:
    """Interrupting actions (ASK / CLARIFY / PROACTIVE) per user turn.

    Questions are counted even when the arm has no core memory (the
    adapter logs its own utterances), so history-blind arms pin the
    scale: they interrupt constantly regardless of history.
    """
    user_turns = _respond_turns(trajectory)
    if not user_turns:
        return 0.0
    interruptions = sum(
        1 for t in user_turns
        if t["decision"]["action"] in INTERRUPTING_ACTIONS)
    return interruptions / len(user_turns)


def temporal_consistency(probe_pairs: Sequence[Tuple[str, str]]) -> float:
    """Fraction of repeated identical probes answered consistently.

    ``probe_pairs`` holds (action_at_t1, action_at_t2) for the same input
    re-asked after a quiet, evidence-free gap: a *stable* agent answers
    the same way when nothing relevant changed.  1.0 = fully consistent.
    """
    if not probe_pairs:
        return 1.0
    return sum(1 for a1, a2 in probe_pairs if a1 == a2) / len(probe_pairs)


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------

def metric_table(turns_a, turns_b,
                 questions_a: Sequence[Dict[str, object]],
                 questions_b: Sequence[Dict[str, object]],
                 slow_a_quiet: Optional[List[Dict[str, float]]] = None,
                 slow_b_quiet: Optional[List[Dict[str, float]]] = None,
                 recovery_switch_index: Optional[int] = None,
                 probe_pairs: Optional[Sequence[Tuple[str, str]]] = None,
                 recent_window: float = 40.0) -> Dict[str, object]:
    """All ten metrics for one (arm, history pair) run, ready to aggregate.

    Paired metrics use the probe trajectories (``turns_a`` / ``turns_b``
    cover the same probe sequence); single-arm metrics use each history's
    full trajectory + question log.
    """
    paired = {
        "history_sensitivity": history_sensitivity(turns_a, turns_b),
        "policy_divergence": policy_divergence(turns_a, turns_b),
    }
    if slow_a_quiet and slow_b_quiet:
        paired["state_persistence"] = state_persistence(slow_a_quiet,
                                                        slow_b_quiet)
    else:
        paired["state_persistence"] = 0.0

    lag: object = None
    if slow_a_quiet and slow_b_quiet and recovery_switch_index is not None:
        lag = recovery_lag(slow_a_quiet, slow_b_quiet,
                           recovery_switch_index)

    table: Dict[str, object] = dict(paired)
    table["recovery_lag"] = lag
    table["temporal_consistency"] = temporal_consistency(probe_pairs or [])
    for name, traj, qlog in (("a", turns_a, questions_a),
                             ("b", turns_b, questions_b)):
        table[f"memory_attribution_{name}"] = memory_attribution(traj)
        table[f"repeated_question_rate_{name}"] = repeated_question_rate(
            qlog, recent_window=recent_window)
        table[f"pending_thread_resolution_{name}"] = (
            pending_thread_resolution(qlog))
        table[f"proactive_appropriateness_{name}"] = (
            proactive_appropriateness(qlog))
        table[f"intrusiveness_rate_{name}"] = intrusiveness_rate(traj, qlog)
    return table


def aggregate(runs: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    """mean / std / min / max / n per metric over repeated runs.

    Metrics that can be ``None`` (recovery_lag when B never recovers) are
    aggregated over the observed values only, and ``n`` reports how many
    runs produced a value at all — a metric with no observations at all
    comes back as ``mean=None, n=0`` (never), so the report can render
    "never" instead of a fake 0.0 and frozen expectations stay honest.
    """
    out: Dict[str, Dict[str, object]] = {}
    if not runs:
        return out
    keys = sorted({k for run in runs for k in run})
    for key in keys:
        values = [float(run[key]) for run in runs
                  if run.get(key) is not None]
        if not values:
            out[key] = {"mean": None, "std": None, "min": None, "max": None,
                        "n": 0}
            continue
        mean = fmean(values)
        var = fmean((v - mean) ** 2 for v in values)
        out[key] = {"mean": mean,
                    "std": var ** 0.5,
                    "min": min(values),
                    "max": max(values),
                    "n": len(values)}
    return out
