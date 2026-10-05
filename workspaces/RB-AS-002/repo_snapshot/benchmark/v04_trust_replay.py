"""v0.4 trust-aware trace replay: the Pareto question (RQ3).

v0.3 established:

    local_only                 attack 0.000   benign 1.0%
    + output inspection        attack 0.035   benign 19.6%
    + entity provenance        attack 0.160   benign 41.2%
    + intent consistency       attack 0.160   benign 41.2%

The open problem is the benign cost: with every tool response treated as
untrusted, a user-authorised payment looks the same as an injected one. This
harness adds the v0.4 rung -- tool-semantics trust policy plus explicit user
authorisation -- and reports it against the v0.3 numbers on the *same*
trajectories.

What is being asked is not "higher recall" but Pareto improvement: can the
attack signal be retained while benign blocking drops?

The trust policy and the authorisation rule were frozen before any measurement
(see app/shield/trust_policy.py and app/shield/authorization.py). Nothing here
tunes against the result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from benchmark.agentdojo_trace_replay import (
    _rank,
    build_trajectories,
    load_rows,
)

# ─── Configurations ─────────────────────────────────────────────────────────

def cfg_local_only(session_id: str):
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(session_id=session_id, enable_provenance=False)


def cfg_output_inspection(session_id: str):
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(
        session_id=session_id, enable_provenance=True, enable_taint_tracking=False
    )


def cfg_entity_provenance(session_id: str):
    from app.shield.v3_engine import V3ShieldEngine

    engine = V3ShieldEngine(session_id=session_id)
    engine._ignore_user_intent = True
    return engine


def cfg_intent(session_id: str):
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(session_id=session_id)


def cfg_trust_aware(session_id: str):
    """v0.4: provenance + tool-semantics trust + prose user authorisation."""
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(session_id=session_id, enable_trust_policy=True)


def cfg_trust_slots(session_id: str):
    """RQ3 second attempt: authorisation decided against structured slots."""
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(
        session_id=session_id,
        enable_trust_policy=True,
        use_intent_slots=True,
    )


CONFIGS: Dict[str, Callable[[str], Any]] = {
    "local_only": cfg_local_only,
    "plus_output_inspection": cfg_output_inspection,
    "plus_entity_provenance": cfg_entity_provenance,
    "plus_intent_consistency": cfg_intent,
    "plus_trust_policy_v0_4": cfg_trust_aware,
    "plus_intent_slots": cfg_trust_slots,
}

LADDER = [
    ("local_only", "single-event gate on the current call only"),
    ("plus_output_inspection", "+ reacts to untrusted content in context"),
    ("plus_entity_provenance", "+ tracks where each entity came from"),
    ("plus_intent_consistency", "+ checks the entity against the operator's request"),
    ("plus_trust_policy_v0_4", "+ tool-semantics trust prior and prose authorisation"),
    ("plus_intent_slots", "+ authorisation from structured intent slots (RQ3 retry)"),
]


def _replay(traj, engine_factory, mode: str):
    from benchmark.agentdojo_trace_replay import _replay_one

    return _replay_one(traj, engine_factory, mode)


def run(
    mode: str = "audit",
    max_trajectories: int = 400,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    rows = load_rows()
    trajectories, audit = build_trajectories(rows)
    benign = [t for t in trajectories if t.meta.label == 0]
    attack = [t for t in trajectories if t.meta.label == 1]
    if max_trajectories:
        benign = benign[:max_trajectories]
        attack = attack[:max_trajectories]

    results = []
    for name, factory in CONFIGS.items():
        b_block = b_review = 0
        b_steps = 0
        b_trace_block = 0
        a_detect = a_block = 0

        for traj in benign:
            out = _replay(traj, factory, mode)
            b_steps += out["steps_executed"]
            b_block += out["decisions"].count("block")
            b_review += out["decisions"].count("review")
            if "block" in out["decisions"]:
                b_trace_block += 1

        for traj in attack:
            out = _replay(traj, factory, mode)
            if any(_rank(d) > 0 for d in out["decisions"]):
                a_detect += 1
            if "block" in out["decisions"]:
                a_block += 1

        results.append({
            "config": name,
            "benign_traces": len(benign),
            "benign_steps": b_steps,
            "benign_step_block_fpr": round(b_block / b_steps, 5) if b_steps else 0.0,
            "benign_step_review_rate": round(b_review / b_steps, 5) if b_steps else 0.0,
            "benign_trace_block_rate": round(b_trace_block / len(benign), 5) if benign else 0.0,
            "attack_traces": len(attack),
            "attack_trace_detection_rate": round(a_detect / len(attack), 5) if attack else 0.0,
            "attack_trace_block_rate": round(a_block / len(attack), 5) if attack else 0.0,
        })

    baseline = next(r for r in results if r["config"] == "plus_entity_provenance")
    for row in results:
        row["delta_vs_v03_provenance"] = {
            "attack_trace_block_pp": round(
                (row["attack_trace_block_rate"] - baseline["attack_trace_block_rate"]) * 100, 2
            ),
            "benign_trace_block_pp": round(
                (row["benign_trace_block_rate"] - baseline["benign_trace_block_rate"]) * 100, 2
            ),
        }

    payload = {
        "experiment": "v0.4_trust_aware_pareto",
        "research_question": (
            "Can source-aware trust and explicit user authorisation retain the "
            "attack signal provided by provenance while reducing benign "
            "over-blocking?"
        ),
        "mode": mode,
        "dataset_source": "ffuuugor/agentdojo-dump",
        "detector_label_free": True,
        "trajectory_reconstructed_from_attack_metadata": False,
        "native_runtime_trace": True,
        "asr_measured": False,
        "utility_measured": False,
        "trust_policy_frozen_before_measurement": True,
        "sampling": f"{len(benign)} benign + {len(attack)} attack trajectories",
        "audit": audit,
        "ladder": [{"config": n, "adds": w} for n, w in LADDER],
        "results": results,
        "baseline_for_delta": "plus_entity_provenance (v0.3)",
    }

    if output_path:
        out = ROOT / output_path
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["audit", "enforcement"], default="audit")
    ap.add_argument("--max-trajectories", type=int, default=400)
    ap.add_argument("--out", type=str, default="benchmark/results/v0_4_trust_pareto.json")
    args = ap.parse_args()

    payload = run(args.mode, args.max_trajectories, args.out)
    print("v0.4 trust-aware replay -- RQ3 Pareto")
    print(f"  {payload['sampling']}\n")
    print(f"{'config':26s} {'atk_block':>10s} {'atk_det':>9s} {'ben_step':>10s} {'ben_trace':>11s}")
    for r in payload["results"]:
        print(
            f"{r['config']:26s} {r['attack_trace_block_rate']:>10.3f} "
            f"{r['attack_trace_detection_rate']:>9.3f} "
            f"{r['benign_step_block_fpr']:>10.4f} {r['benign_trace_block_rate']:>11.3f}"
        )
    print("\nDeltas vs v0.3 provenance baseline (percentage points):")
    for r in payload["results"]:
        d = r["delta_vs_v03_provenance"]
        print(f"  {r['config']:26s} attack {d['attack_trace_block_pp']:+.2f}   "
              f"benign {d['benign_trace_block_pp']:+.2f}")
    print(f"\nWritten to {ROOT / args.out}")


if __name__ == "__main__":
    main()
