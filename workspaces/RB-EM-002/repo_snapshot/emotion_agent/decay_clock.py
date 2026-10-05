"""
decay_clock.py (V1.0)
=====================
Explicit decay semantics — one declared clock per consumer.

The bug this fixes: ``ExperienceMemory.retrieve()`` named its recency
parameter ``half_life_steps`` while production timestamps are Unix seconds
(``time.time()``), so the effective production half-life was 40 *seconds*
(outcome memory went stale in under a minute), while the benchmark fed
step-valued timestamps and silently obtained 40 *steps*. One float must not
mean both "step index" and "Unix timestamp":

  * production / long-running agents declare :class:`WallClock` — readings
    are Unix seconds and half-lives are in seconds
    (``AffectiveDecayConfig`` defaults: state 6h, episodic 7 days);
  * experiments / simulations declare :class:`StepClock` — readings are
    logical step indices and half-lives are in steps (40 steps, the frozen
    V0.9 benchmark semantics).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class DecayClock(Protocol):
    """Time source for recency decay.

    ``now()`` returns the current reading in the clock's own units: a step
    index for step clocks, Unix seconds for the wall clock. ``mode`` is the
    stable string used to resolve half-life units in
    :class:`AffectiveDecayConfig`.
    """

    mode: str

    def now(self) -> float:
        ...


class StepClock:
    """Logical step clock for experiments / simulations.

    ``advance(dt)`` moves logical time forward (default: one step) and
    returns the new reading; ``now()`` reads without advancing. Fully
    deterministic — independent of the host clock, so benchmarks are
    reproducible.
    """

    mode = "step"

    def __init__(self, start: float = 0.0):
        self._t = float(start)

    def now(self) -> float:
        return self._t

    def advance(self, dt: float = 1.0) -> float:
        self._t += float(dt)
        return self._t


class WallClock:
    """Unix wall-clock time (seconds) — production / long-running agents.

    Wall time cannot be advanced logically; ``advance`` exists only for
    interface symmetry with :class:`StepClock` and simply re-reads the host
    clock.
    """

    mode = "wall_time"

    def now(self) -> float:
        return time.time()

    def advance(self, dt: float = 0.0) -> float:
        return self.now()


@dataclass(frozen=True)
class AffectiveDecayConfig:
    """Half-life defaults per clock mode.

    Fast affective state recovers within hours; episodic outcome memory
    stays useful for about a week. The step-mode values freeze the V0.9
    benchmark numbers (40 steps) so experiments stay comparable.
    """

    state_half_life_seconds: float = 6 * 3600.0
    episodic_half_life_seconds: float = 7 * 86400.0
    state_half_life_steps: float = 40.0
    episodic_half_life_steps: float = 40.0

    def half_life(self, kind: str, mode: str) -> float:
        """Resolve the half-life for ``kind`` ("state" | "episodic")
        under a clock ``mode`` ("step" | "wall_time")."""
        if kind == "state":
            return (self.state_half_life_steps if mode == "step"
                    else self.state_half_life_seconds)
        if kind == "episodic":
            return (self.episodic_half_life_steps if mode == "step"
                    else self.episodic_half_life_seconds)
        raise ValueError(f"unknown decay kind: {kind!r}")
