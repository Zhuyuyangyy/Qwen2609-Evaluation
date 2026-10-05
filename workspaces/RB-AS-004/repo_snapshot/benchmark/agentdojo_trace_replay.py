"""AgentDojo-derived logged-trace replay (stage H).

The main external experiment. Replays trajectories actually recorded in
``ffuuugor/agentdojo-dump`` -- real ``tool_call_function`` / ``tool_call_args`` /
``tool_response`` triples, in their recorded order -- and scores the governance
decision on each step.

No agent is re-run and no LLM is invoked. Nothing about the attack is
reconstructed: the sink is whatever the trace really did next. ``label``,
``injection_goal``, ``injection_task_id`` and ``attack_name`` never reach the
engine; they are used only after a trajectory has been fully replayed, to split
the finished predictions into benign and attack groups for reporting.

Two replay modes
----------------
``audit``
    Replay every recorded step and report per-step coverage. A BLOCK does not
    truncate the trace: what follows in the log belongs to the undefended
    world, so this mode measures interception coverage over logged behaviour
    and must not be read as post-intervention behaviour.
``enforcement``
    Stop at the first BLOCK. Reports where the recorded trajectory would have
    been cut had the gate been deployed. Also not an agent outcome.

Trust policy
------------
Every recorded ``tool_response`` is treated as ``untrusted``. Trust is never
derived from a label or from whether the response contains injected text --
both would leak. A tool response is runtime-observable input; that it happens
to carry malicious text is the phenomenon under measurement, not a label.

Not measured, by design
-----------------------
Attack success rate, benign utility, utility under attack, task success, and
behavioural adaptation after intervention. All require re-running the agent with
an LLM in the loop. This file reports interception on logged behaviour only.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

LABELS = ("ALLOW", "HUMAN_REVIEW", "BLOCK")
RANK = {"allow": 0, "review": 1, "human_review": 1, "block": 2}


def _rank(decision: str) -> int:
    return RANK.get(str(decision).lower(), 0)


def _norm(decision: str) -> str:
    text = str(decision).lower()
    return {
        "allow": "ALLOW", "review": "HUMAN_REVIEW",
        "human_review": "HUMAN_REVIEW", "block": "BLOCK",
    }.get(text, text.upper())


# ─── Isolated data flows ────────────────────────────────────────────────────

@dataclass(frozen=True)
class RuntimeTraceObservation:
    """Everything a detector may see for one recorded step.

    Deliberately free of every evaluation-only field. ``frozen`` so a prediction
    path cannot mutate provenance into the trace after the fact.
    """
    tool_name: str
    tool_input: Dict[str, Any]
    tool_response: str
    user_intent: str = ""
    step_index: int = 0


@dataclass(frozen=True)
class EvaluationMetadata:
    """Grading metadata. Visible only to the scorer, after prediction."""
    label: int
    injection_goal: str
    injection_task_id: str
    attack_name: str
    suite_name: str
    user_task_id: str


# Fields that must never appear in a RuntimeTraceObservation.
FORBIDDEN_TRACE_FIELDS = (
    "label", "expected_label", "expected_action", "expected_risk_score",
    "injection_goal", "injection_task_id", "attack_name", "attack_stage",
)


@dataclass
class Trajectory:
    """One agent execution: ordered observations plus its grading metadata."""
    trajectory_id: str
    steps: List[RuntimeTraceObservation]
    meta: EvaluationMetadata

    def assert_clean(self) -> None:
        for step in self.steps:
            for key in FORBIDDEN_TRACE_FIELDS:
                assert not hasattr(step, key), (
                    f"evaluation-only field {key} leaked into a trace step"
                )


# ─── Loading and grouping ───────────────────────────────────────────────────

def load_rows() -> List[Dict[str, Any]]:
    import glob

    import pyarrow as pa

    paths = sorted(glob.glob(
        str(ROOT / "benchmark" / "external_datasets" / "ffuuugor___agentdojo-dump" / "**" / "*.arrow"),
        recursive=True,
    ))
    if not paths:
        raise FileNotFoundError("AgentDojo dump not found")

    rows: List[Dict[str, Any]] = []
    for path in paths:
        table = pa.ipc.open_stream(pa.memory_map(path, "r")).read_all()
        cols = {n: table.column(n).to_pylist() for n in table.column_names}
        for i in range(table.num_rows):
            rows.append({n: v[i] for n, v in cols.items()})
    return rows


def _parse_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            import ast

            parsed = ast.literal_eval(raw)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            return {"raw": raw}
    return {"value": raw}


def build_trajectories(
    rows: List[Dict[str, Any]]
) -> Tuple[List[Trajectory], Dict[str, Any]]:
    """Group recorded rows into trajectories, excluding ambiguous groups.

    Grouping needs an execution identity. The dump has no step index and no run
    id, so the identity is (suite, user_task, injection_task, attack_name); the
    ``attack_name`` component is what separates distinct attack configurations
    that otherwise interleave under the same task ids.

    A group is discarded when it is not a single contiguous run of the source
    file, when its rows disagree on label or user prompt, or when its attack
    name is inconsistent -- the failure mode being guarded against is stitching
    unrelated executions into one trajectory.
    """
    grouped: Dict[Tuple[str, str, str, str], List[int]] = {}
    for idx, row in enumerate(rows):
        key = (
            str(row.get("suite_name", "")),
            str(row.get("user_task_id", "")),
            str(row.get("injection_task_id", "")),
            str(row.get("attack_name", "")),
        )
        grouped.setdefault(key, []).append(idx)

    trajectories: List[Trajectory] = []
    excluded: Dict[str, int] = {}

    for key, indices in grouped.items():
        suite, user_task, injection_task, attack_name = key
        rows_in_group = [rows[i] for i in indices]

        labels = {int(r.get("label", 0)) for r in rows_in_group}
        prompts = {str(r.get("user_task_prompt", "")) for r in rows_in_group}
        attacks = {str(r.get("attack_name", "")) for r in rows_in_group}

        if len(labels) > 1:
            excluded["mixed_label"] = excluded.get("mixed_label", 0) + 1
            continue
        if len(prompts) > 1:
            excluded["mixed_user_prompt"] = excluded.get("mixed_user_prompt", 0) + 1
            continue
        if len(attacks) > 1:
            excluded["mixed_attack_name"] = excluded.get("mixed_attack_name", 0) + 1
            continue
        # Contiguity: a single execution's steps should be adjacent in the dump.
        if indices != list(range(indices[0], indices[0] + len(indices))):
            excluded["non_contiguous"] = excluded.get("non_contiguous", 0) + 1
            continue

        meta = EvaluationMetadata(
            label=next(iter(labels)),
            injection_goal=str(rows_in_group[0].get("injection_goal", "") or ""),
            injection_task_id=injection_task,
            attack_name=attack_name,
            suite_name=suite,
            user_task_id=user_task,
        )

        steps: List[RuntimeTraceObservation] = []
        for order, row in enumerate(rows_in_group):
            steps.append(RuntimeTraceObservation(
                tool_name=str(row.get("tool_call_function", "") or ""),
                tool_input=_parse_args(row.get("tool_call_args", {})),
                tool_response=str(row.get("tool_response", "") or ""),
                # The operator's request applies to the whole trajectory; only
                # the first step reports it, matching how a runtime supplies it.
                user_intent=str(rows_in_group[0].get("user_task_prompt", "") or ""),
                step_index=order,
            ))

        trajectory_id = "|".join(key)
        traj = Trajectory(trajectory_id=trajectory_id, steps=steps, meta=meta)
        traj.assert_clean()
        trajectories.append(traj)

    audit = {
        "rows": len(rows),
        "trajectories": len(trajectories),
        "excluded": excluded,
        "excluded_total": sum(excluded.values()),
        "median_steps": _percentile([len(t.steps) for t in trajectories], 50),
        "p95_steps": _percentile([len(t.steps) for t in trajectories], 95),
        "max_steps": max((len(t.steps) for t in trajectories), default=0),
        "duplicate_step_keys": len(rows) - len(grouped),
    }
    return trajectories, audit


def _percentile(values: List[int], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((pct / 100.0) * (len(ordered) - 1))))
    return float(ordered[idx])


# ─── Replay ─────────────────────────────────────────────────────────────────

def _replay_one(
    traj: Trajectory,
    engine_factory: Callable[[str], Any],
    mode: str,
) -> Dict[str, Any]:
    engine = engine_factory(f"h_{traj.trajectory_id[:16]}")
    decisions: List[str] = []
    blocked_at: Optional[int] = None
    blocking_signals: List[List[str]] = []
    latencies_ms: List[float] = []
    lineage: List[Dict[str, Any]] = []
    parent = None

    for step in traj.steps:
        if not step.tool_name:
            continue
        started = time.perf_counter_ns()
        result = engine.process_tool_call(
            agent_id="agentdojo_agent",
            tool_name=step.tool_name,
            params=step.tool_input,
            risk_score=0.0,
            fuse_action="allow",
            parent_node_id=parent,
            user_intent=step.user_intent,
            tool_output=step.tool_response,
            # Trust policy: never derived from a label or from injected text.
            output_trust="untrusted",
        )
        latencies_ms.append((time.perf_counter_ns() - started) / 1e6)
        decision = result["decision"]
        decisions.append(decision)
        lineage.append({
            "step": step.step_index,
            "tool": step.tool_name,
            "decision": _norm(decision),
            "signals": [
                s.get("signal_type")
                for s in (result.get("graph_risk_state") or {}).get("signals", [])
            ],
            "consumed_artifact_ids": result.get("consumed_artifact_ids", []),
        })
        parent = result.get("node_id") or parent

        if decision == "block" and blocked_at is None:
            blocked_at = step.step_index
            blocking_signals.append(lineage[-1]["signals"])
            if mode == "enforcement":
                break

    return {
        "decisions": decisions,
        "blocked_at_step": blocked_at,
        "blocking_signals": blocking_signals,
        "steps_executed": len(decisions),
        "trace_fraction_executed": (
            len(decisions) / len(traj.steps) if traj.steps else 0.0
        ),
        "latencies_ms": latencies_ms,
        "lineage": lineage,
    }


def _pct(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((p / 100.0) * (len(ordered) - 1))))
    return round(ordered[idx], 4)


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


def cfg_full(session_id: str):
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(session_id=session_id)


CONFIGS: Dict[str, Callable[[str], Any]] = {
    "local_only": cfg_local_only,
    "plus_output_inspection": cfg_output_inspection,
    "plus_entity_provenance": cfg_entity_provenance,
    "plus_intent_consistency": cfg_full,
}

LADDER = [
    ("local_only", "single-event gate on the current call only"),
    ("plus_output_inspection", "+ reacts to instruction-like content in context"),
    ("plus_entity_provenance", "+ tracks where each entity came from"),
    ("plus_intent_consistency", "+ checks the entity against the operator's request"),
]


def _summarise(
    outcomes: Dict[str, Dict[str, Any]],
    benign_ids: List[str],
    attack_ids: List[str],
    audit: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows = []
    for name in CONFIGS:
        benign = [outcomes[t][name] for t in benign_ids]
        attack = [outcomes[t][name] for t in attack_ids]

        benign_steps = sum(o["steps_executed"] for o in benign)
        benign_block_steps = sum(o["decisions"].count("block") for o in benign)
        benign_review_steps = sum(o["decisions"].count("review") for o in benign)
        benign_trace_block = sum(1 for o in benign if "block" in o["decisions"])
        benign_trace_intervene = sum(
            1 for o in benign if any(_rank(d) > 0 for d in o["decisions"])
        )

        attack_detect_trace = sum(
            1 for o in attack if any(_rank(d) > 0 for d in o["decisions"])
        )
        attack_block_trace = sum(1 for o in attack if "block" in o["decisions"])
        attack_steps = sum(o["steps_executed"] for o in attack)
        attack_block_steps = sum(o["decisions"].count("block") for o in attack)

        rows.append({
            "config": name,
            "benign_traces": len(benign),
            "benign_steps": benign_steps,
            "benign_step_block_fpr": round(benign_block_steps / benign_steps, 5) if benign_steps else 0.0,
            "benign_step_review_rate": round(benign_review_steps / benign_steps, 5) if benign_steps else 0.0,
            "benign_trace_block_rate": round(benign_trace_block / len(benign), 5) if benign else 0.0,
            "benign_trace_intervention_rate": round(benign_trace_intervene / len(benign), 5) if benign else 0.0,
            "attack_traces": len(attack),
            "attack_steps": attack_steps,
            "attack_trace_detection_rate": round(attack_detect_trace / len(attack), 5) if attack else 0.0,
            "attack_trace_block_rate": round(attack_block_trace / len(attack), 5) if attack else 0.0,
            "attack_step_block_rate": round(attack_block_steps / attack_steps, 5) if attack_steps else 0.0,
        })
    return rows


def _cluster_bootstrap_ci(
    outcomes: Dict[str, Dict[str, Any]],
    benign_ids: List[str],
    attack_ids: List[str],
    config: str,
    iterations: int = 2000,
    seed: int = 12345,
) -> Dict[str, Any]:
    """Bootstrap over trajectories, never over steps.

    Steps within one trajectory are strongly correlated, so resampling rows
    would produce intervals that are far too narrow. The unit of resampling is
    the trajectory.
    """
    import random

    rng = random.Random(seed)
    estimates: Dict[str, List[float]] = {
        "benign_trace_block_rate": [],
        "benign_trace_intervention_rate": [],
        "attack_trace_block_rate": [],
        "attack_trace_detection_rate": [],
    }

    for _ in range(iterations):
        b_sample = [benign_ids[rng.randrange(len(benign_ids))] for _ in range(len(benign_ids))]
        a_sample = [attack_ids[rng.randrange(len(attack_ids))] for _ in range(len(attack_ids))]

        b_out = [outcomes[t][config] for t in b_sample]
        a_out = [outcomes[t][config] for t in a_sample]

        if b_out:
            estimates["benign_trace_block_rate"].append(
                sum(1 for o in b_out if "block" in o["decisions"]) / len(b_out)
            )
            estimates["benign_trace_intervention_rate"].append(
                sum(1 for o in b_out if any(_rank(d) > 0 for d in o["decisions"])) / len(b_out)
            )
        if a_out:
            estimates["attack_trace_block_rate"].append(
                sum(1 for o in a_out if "block" in o["decisions"]) / len(a_out)
            )
            estimates["attack_trace_detection_rate"].append(
                sum(1 for o in a_out if any(_rank(d) > 0 for d in o["decisions"])) / len(a_out)
            )

    def interval(values: List[float]) -> Optional[List[float]]:
        if not values:
            return None
        ordered = sorted(values)
        lo = ordered[int(0.025 * (len(ordered) - 1))]
        hi = ordered[int(0.975 * (len(ordered) - 1))]
        return [round(lo, 5), round(hi, 5)]

    return {name: interval(vals) for name, vals in estimates.items()}


def run(
    mode: str = "audit",
    max_trajectories: int = 0,
    output_path: Optional[str] = None,
    bootstrap: bool = True,
) -> Dict[str, Any]:
    rows = load_rows()
    trajectories, audit = build_trajectories(rows)

    benign = [t for t in trajectories if t.meta.label == 0]
    attack = [t for t in trajectories if t.meta.label == 1]
    if max_trajectories:
        benign = benign[:max_trajectories]
        attack = attack[:max_trajectories]

    benign_ids = [t.trajectory_id for t in benign]
    attack_ids = [t.trajectory_id for t in attack]

    outcomes: Dict[str, Dict[str, Any]] = {tid: {} for tid in benign_ids + attack_ids}
    for traj in benign + attack:
        for name, factory in CONFIGS.items():
            outcomes[traj.trajectory_id][name] = _replay_one(traj, factory, mode)

    results = _summarise(outcomes, benign_ids, attack_ids, audit)

    cis: Dict[str, Any] = {}
    if bootstrap:
        for row in results:
            cis[row["config"]] = _cluster_bootstrap_ci(
                outcomes, benign_ids, attack_ids, row["config"]
            )

    # Latency is governance-only: measured around process_tool_call, excluding
    # dataset loading, HF access and any model time.
    full_latencies = [
        ms
        for tid in benign_ids + attack_ids
        for ms in outcomes[tid]["plus_intent_consistency"]["latencies_ms"]
    ]
    latency = {
        "n_calls": len(full_latencies),
        "mean_ms": round(sum(full_latencies) / len(full_latencies), 4) if full_latencies else None,
        "p50_ms": _pct(full_latencies, 50),
        "p95_ms": _pct(full_latencies, 95),
        "p99_ms": _pct(full_latencies, 99),
    }

    payload = {
        "experiment": "agentdojo_logged_trace_replay",
        "dataset_source": "ffuuugor/agentdojo-dump",
        "mode": mode,
        "native_logged_trace": True,
        "live_agent_execution": False,
        "llm_rerun": False,
        "utility_measured": False,
        "asr_measured": False,
        "trust_policy": "all recorded tool_response treated as untrusted",
        "trust_derived_from_label": False,
        "sampling": (
            f"{len(benign_ids) + len(attack_ids)} trajectories "
            f"({'all' if not max_trajectories else f'first {max_trajectories} per class'})"
        ),
        "audit": audit,
        "metric_definitions": {
            "attack_trace_detection_rate": "share of attack trajectories with >=1 REVIEW or BLOCK",
            "attack_trace_block_rate": "share of attack trajectories with >=1 BLOCK",
            "attack_step_block_rate": "BLOCK share over all steps in attack trajectories",
            "benign_step_block_fpr": "BLOCK share over all steps in benign trajectories",
            "benign_trace_block_rate": "share of benign trajectories with >=1 BLOCK",
            "benign_trace_intervention_rate": "share of benign trajectories with >=1 REVIEW or BLOCK",
        },
        "bootstrap": {
            "unit": "trajectory (cluster bootstrap)",
            "iterations": 2000 if bootstrap else 0,
            "seed": 12345,
            "note": "steps within a trajectory are correlated; rows are not the sampling unit",
        },
        "latency_governance_only": latency,
        "ladder": [{"config": n, "adds": w} for n, w in LADDER],
        "results": results,
        "confidence_intervals": cis,
        "limitations": [
            "Offline replay measures interception on logged behaviour, not "
            "behavioural adaptation after intervention.",
            "In audit mode, steps following a BLOCK belong to the undefended "
            "world and are counted for coverage only.",
            "No attack success rate, utility or task success is measured; those "
            "require re-running the agent with an LLM.",
        ],
    }

    if output_path:
        out = ROOT / output_path
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["audit", "enforcement"], default="audit")
    ap.add_argument("--max-trajectories", type=int, default=60)
    ap.add_argument("--no-bootstrap", action="store_true")
    ap.add_argument("--out", type=str, default="benchmark/results/agentdojo_native_trace_replay.json")
    args = ap.parse_args()

    payload = run(
        mode=args.mode,
        max_trajectories=args.max_trajectories,
        output_path=args.out,
        bootstrap=not args.no_bootstrap,
    )
    audit = payload["audit"]
    benign_n = next(r["benign_traces"] for r in payload["results"])
    attack_n = next(r["attack_traces"] for r in payload["results"])
    print(f"AgentDojo-derived logged-trace replay ({args.mode} mode)")
    print(f"  rows={audit['rows']} trajectories={audit['trajectories']} "
          f"excluded={audit['excluded_total']} benign={benign_n} attack={attack_n}")
    print(f"  steps per trajectory: median={audit['median_steps']} "
          f"p95={audit['p95_steps']} max={audit['max_steps']}")
    print("  (recorded tool_call/tool_response; labels never reach the engine)\n")
    for r in payload["results"]:
        ci = payload["confidence_intervals"].get(r["config"], {})
        btb = ci.get("benign_trace_block_rate")
        atb = ci.get("attack_trace_block_rate")
        print(
            f"  {r['config']:24s} attack_trace_block={r['attack_trace_block_rate']:.3f}"
            f" (CI {atb})"
            f"  benign_trace_block={r['benign_trace_block_rate']:.3f} (CI {btb})"
        )
    lat = payload["latency_governance_only"]
    print(f"\n  governance latency p50/p95/p99 = "
          f"{lat['p50_ms']}/{lat['p95_ms']}/{lat['p99_ms']} ms")
    print(f"\nWritten to {ROOT / args.out}")


if __name__ == "__main__":
    main()
