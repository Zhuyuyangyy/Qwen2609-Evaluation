"""
companion_systems.py (V1.0 - P2-c)
===================================
The five comparable arms of the Same-Dialogue / Different-History
benchmark (roadmap P2, "Benchmark B"), sharing one interface and one
turn vocabulary.

The ablation question: *which channels of the interaction history make
the SAME current input produce different, appropriate decisions?*  Each
arm is the SAME :class:`~emotion_agent.companion_adapter.CompanionAdapter`
with different layers wired in, so no arm can win by having a different
clock, different thresholds, or a luckier decoder:

  =================== ======== ======== ======= ====== ========== =============
  arm                 affect   memory   policy  cons.  proactive  isolates
  =================== ======== ======== ======= ====== ========== =============
  ``v09_baseline``    off      off      off     off    off        control scale
  ``memory_only``     off      on       on      off    on         recall / asks
  ``affect_only``     on       off      on      off    on         slow/fast state
  ``memory_affect``   on       on       on      off    on         channels summed
  ``full``            on       on       on      on     on         + consolidation
  =================== ======== ======= ======= ====== ========== =============

Design rules that keep the comparison meaningful:

  * ``v09_baseline`` is the history-blind control (no policy layer, no
    state, no memory): every paired metric should pin to its trivial
    baseline value on it — that is what "measurable" means.
  * Every arm except the control runs the SAME InteractionPolicy with
    the SAME thresholds; the arms differ only in what the policy can see
    (ledger / threads / slow state), not in how it judges.
  * Proactive outreach is allowed in every non-control arm.  Suppressing
    it in some arms but not others would confound "did history change the
    decision" with "was the decision possible at all".
  * ``consolidation`` (semantic patterns) is only enabled in ``full``:
    it is the one channel that requires the semantic layer to have
    accumulated enough support, so testing it alone is meaningless.

Outer-layer scheduling (quiet hours, cron, delivery) is deliberately NOT
part of an arm: it lives in the bot that drives the adapter, and the
benchmark drives all arms through the same adapter-level rules.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from emotion_agent.companion_adapter import CompanionAdapter
from emotion_agent.decay_clock import DecayClock, StepClock
from emotion_agent.dual_scale_state import DualScaleDecayConfig

#: the five arms, in report order (control first, full last)
ARM_ORDER: Sequence[str] = ("v09_baseline", "memory_only", "affect_only",
                            "memory_affect", "full")

#: per-arm CompanionAdapter flags — the ONLY thing that differs between arms
ARM_SPECS: Dict[str, Dict[str, bool]] = {
    "v09_baseline": {
        "use_affect": False, "use_memory": False, "use_policy": False,
        "use_consolidation": False, "allow_proactive": False,
    },
    "memory_only": {
        "use_affect": False, "use_memory": True, "use_policy": True,
        "use_consolidation": False, "allow_proactive": True,
    },
    "affect_only": {
        "use_affect": True, "use_memory": False, "use_policy": True,
        "use_consolidation": False, "allow_proactive": True,
    },
    "memory_affect": {
        "use_affect": True, "use_memory": True, "use_policy": True,
        "use_consolidation": False, "allow_proactive": True,
    },
    "full": {
        "use_affect": True, "use_memory": True, "use_policy": True,
        "use_consolidation": True, "allow_proactive": True,
    },
}

#: one-line role of each arm, rendered into the report
ARM_ROLES: Dict[str, str] = {
    "v09_baseline": "history-blind control (no core layers engaged)",
    "memory_only": "episodic/semantic recall + ask ledger, no persistent state",
    "affect_only": "fast+slow affective state, no memory writes",
    "memory_affect": "state + memory, no consolidation",
    "full": "all channels incl. semantic consolidation",
}

#: the flags each arm exposes, for report / audit tables
ARM_FLAG_NAMES: Sequence[str] = ("use_affect", "use_memory", "use_policy",
                                 "use_consolidation", "allow_proactive")


def arm_flags(name: str) -> Dict[str, bool]:
    """Copy of one arm's flag table (the exact ablation configuration)."""
    if name not in ARM_SPECS:
        raise ValueError(f"unknown companion arm {name!r}; "
                         f"expected one of {list(ARM_SPECS)}")
    return dict(ARM_SPECS[name])


def make_companion(name: str,
                   clock: Optional[DecayClock] = None,
                   decay_config: Optional[DualScaleDecayConfig] = None,
                   **overrides) -> CompanionAdapter:
    """Build one arm with the shared experiment configuration.

    ``clock`` / ``decay_config`` and any ``overrides`` (day_length,
    quiet_cooldown, ...) are applied to EVERY arm identically; only the
    ablation flags come from :data:`ARM_SPECS`.  A StepClock is the
    default so the benchmark is deterministic — production code passes
    a WallClock.
    """
    flags = arm_flags(name)
    # a caller-supplied flag override wins over the arm spec (used by the
    # arm-integrity self-test in the benchmark: build an arm, then verify
    # the adapter reports exactly the flags that were asked for).
    flags.update({k: bool(v) for k, v in overrides.items()
                  if k in ARM_FLAG_NAMES})
    extra = {k: v for k, v in overrides.items()
             if k not in ARM_FLAG_NAMES}
    return CompanionAdapter(name=name,
                            clock=clock or StepClock(0.0),
                            decay_config=decay_config
                            or DualScaleDecayConfig(),
                            **flags, **extra)


def make_all_arms(clock: Optional[DecayClock] = None,
                  decay_config: Optional[DualScaleDecayConfig] = None,
                  **overrides) -> List[CompanionAdapter]:
    """One fresh adapter per arm, all sharing the experiment configuration."""
    return [make_companion(name, clock=clock, decay_config=decay_config,
                           **overrides) for name in ARM_ORDER]


def check_arm_integrity(arms) -> List[str]:
    """Verify each adapter carries exactly its arm's ablation flags.

    Accepts either a ``{arm_name: adapter}`` dict or a sequence of
    adapters (their ``name`` attribute identifies the arm).  Returns a
    list of human-readable problems (empty = clean).  The benchmark runs
    this before measuring, so a flag regression fails loudly instead of
    silently contaminating the ablation.
    """
    problems: List[str] = []
    items: List[tuple] = []
    if isinstance(arms, dict):
        items = list(arms.items())
    else:
        items = [(adapter.name, adapter) for adapter in arms]
    for name, adapter in items:
        if name not in ARM_SPECS:
            problems.append(f"unknown arm {name!r}")
            continue
        for flag, expected in arm_flags(name).items():
            actual = bool(getattr(adapter, flag, None))
            if actual != expected:
                problems.append(f"{name}: {flag}={actual}, "
                                f"expected {expected}")
    return problems
