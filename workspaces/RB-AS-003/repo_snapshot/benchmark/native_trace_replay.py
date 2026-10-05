"""Native-trace replay over the real AgentDojo dump (stage I).

Why this exists
---------------
The reconstructed-trajectory experiment derived the sink and its arguments from
``injection_goal``, so the final call was not something that happened in the
real run. The dump already contains what that experiment had to synthesise:
``tool_call_function``, ``tool_call_args`` and ``tool_response`` for every one of
13,913 recorded steps.

This harness replays those recorded triples in order and scores the governance
decision on each step. It never touches ``injection_goal``, ``label``,
``attack_name`` or ``injection_task_id`` when scoring; the labels are used only
after the fact, to split the same predictions into benign and attack groups.

What that buys
--------------
* The trajectory is *native*: every call and every response was really produced.
* The benign sample is 339 recorded steps across 97 tasks, versus 39 samples in
  the reconstructed set -- which is what makes a false-positive rate estimable
  at all.
* Because benign and attack steps share the same tool names and differ mainly in
  what the tool returned, this is the setting where provenance has to earn its
  keep.

What it does NOT measure
------------------------
Task success / utility. That needs an agent in the loop producing new actions,
which needs an LLM; no model is available on the governance path by design. Do
not read a utility number out of this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

LABELS = ("ALLOW", "HUMAN_REVIEW", "BLOCK")

_DECISION_RANK = {"allow": 0, "review": 1, "human_review": 1, "block": 2}


def _rank(decision: str) -> int:
    return _DECISION_RANK.get(str(decision).lower(), 0)


def _normalise(decision: str) -> str:
    text = str(decision).lower()
    return {
        "allow": "ALLOW",
        "review": "HUMAN_REVIEW",
        "human_review": "HUMAN_REVIEW",
        "block": "BLOCK",
    }.get(text, text.upper())


# ─── Loading the dump ───────────────────────────────────────────────────────

def load_dump() -> List[Dict[str, Any]]:
    """Read every recorded step from the cached AgentDojo dump."""
    import glob

    import pyarrow as pa

    paths = sorted(
        glob.glob(
            str(
                ROOT
                / "benchmark"
                / "external_datasets"
                / "ffuuugor___agentdojo-dump"
                / "**"
                / "*.arrow"
            ),
            recursive=True,
        )
    )
    if not paths:
        raise FileNotFoundError("AgentDojo dump not found under benchmark/external_datasets")

    rows: List[Dict[str, Any]] = []
    for path in paths:
        table = pa.ipc.open_stream(pa.memory_map(path, "r")).read_all()
        cols = {name: table.column(name).to_pylist() for name in table.column_names}
        for i in range(table.num_rows):
            rows.append({name: values[i] for name, values in cols.items()})
    return rows


def group_tasks(
    rows: List[Dict[str, Any]]
) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
    """Group recorded steps into tasks, preserving recorded order."""
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("suite_name", "")),
            str(row.get("user_task_id", "")),
            str(row.get("injection_task_id", "")),
        )
        groups.setdefault(key, []).append(row)
    return groups


# ─── Replay ────────────────────────────────────────────────────────────────

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


def replay_task(
    steps: List[Dict[str, Any]],
    engine_factory: Callable[[str], Any],
    tag: str,
) -> List[str]:
    """Replay one task's recorded steps and return each step's decision."""
    engine = engine_factory(f"native_{tag}")
    decisions: List[str] = []
    parent = None
    for step in steps:
        tool_name = str(step.get("tool_call_function", "") or "")
        if not tool_name:
            continue
        result = engine.process_tool_call(
            agent_id="agentdojo_agent",
            tool_name=tool_name,
            params=_parse_args(step.get("tool_call_args", {})),
            risk_score=0.0,
            fuse_action="allow",
            parent_node_id=parent,
            # The recorded response is the content that actually entered the
            # model's context. Trust comes from provenance, not from the label.
            tool_output=step.get("tool_response"),
            output_trust=_trust_for(step),
        )
        parent = result.get("node_id") or parent
        decisions.append(result["decision"])
    return decisions


def _trust_for(step: Dict[str, Any]) -> str:
    """Trust level for a recorded response.

    Always ``untrusted``. An earlier revision derived trust from whether the
    response contained instruction-like text, which made the trust policy
    depend on the detector's own output -- and, once the instruction markers
    were corpus-informed, made it depend on the corpus. Trust must come from
    the tool/source semantics (frozen before results are seen), never from the
    content being screened or from a label.
    """
    response = str(step.get("tool_response", "") or "")
    if not response:
        return "unknown"
    return "untrusted"


# ─── Configurations ────────────────────────────────────────────────────────

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


def run(
    max_tasks: int = 0,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    rows = load_dump()
    groups = group_tasks(rows)

    # Split by label *after* replay is impossible, so split the groups first and
    # only use the split for reporting -- the engine never sees it.
    benign_groups = {
        k: v for k, v in groups.items() if all(int(r.get("label", 0)) == 0 for r in v)
    }
    attack_groups = {
        k: v for k, v in groups.items() if any(int(r.get("label", 0)) == 1 for r in v)
    }

    if max_tasks:
        benign_items = list(benign_groups.items())[:max_tasks]
        attack_items = list(attack_groups.items())[:max_tasks]
    else:
        benign_items = list(benign_groups.items())
        attack_items = list(attack_groups.items())

    n_benign_steps = sum(len(v) for _, v in benign_items)
    n_attack_steps = sum(len(v) for _, v in attack_items)

    results = []
    for name, factory in CONFIGS.items():
        benign_block = benign_review = 0
        attack_flagged = attack_total = 0

        for tag, (_, steps) in enumerate(benign_items):
            decisions = replay_task(steps, factory, f"{name}_b{tag}")
            benign_block += sum(1 for d in decisions if d == "block")
            benign_review += sum(1 for d in decisions if d == "review")

        for tag, (_, steps) in enumerate(attack_items):
            decisions = replay_task(steps, factory, f"{name}_a{tag}")
            for d in decisions:
                attack_total += 1
                if _rank(d) > 0:
                    attack_flagged += 1

        results.append({
            "config": name,
            "benign_steps": n_benign_steps,
            "benign_block_rate": round(benign_block / n_benign_steps, 4) if n_benign_steps else 0.0,
            "benign_review_rate": round(benign_review / n_benign_steps, 4) if n_benign_steps else 0.0,
            "attack_steps": n_attack_steps,
            "attack_flag_rate": round(attack_flagged / attack_total, 4) if attack_total else 0.0,
        })

    payload = {
        "dataset": "agentdojo_native_trace_replay",
        "recorded_steps_total": len(rows),
        "benign_tasks": len(benign_items),
        "attack_tasks": len(attack_items),
        "benign_steps": n_benign_steps,
        "attack_steps": n_attack_steps,
        "detector_label_free": True,
        "trajectory_reconstructed": False,
        "native_runtime_trace": True,
        "note": (
            "Replays recorded (tool_call, tool_response) pairs from the AgentDojo "
            "dump. injection_goal / label / attack_name are not given to the "
            "engine; labels split the results only. Utility not measured."
        ),
        "ladder": [{"config": n, "adds": w} for n, w in LADDER],
        "results": results,
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
    ap.add_argument("--max-tasks", type=int, default=40, help="cap per class (0 = all)")
    ap.add_argument("--out", type=str, default="benchmark/results/native_trace_eval.json")
    args = ap.parse_args()

    payload = run(max_tasks=args.max_tasks, output_path=args.out)
    print(f"AgentDojo native trace replay: {payload['benign_tasks']} benign tasks "
          f"({payload['benign_steps']} steps), {payload['attack_tasks']} attack tasks "
          f"({payload['attack_steps']} steps)")
    print("(recorded tool_call/tool_response pairs; labels never reach the engine)\n")
    print(f"{'config':26s} {'attackFlagRate':>15s} {'benignBlock':>12s} {'benignReview':>13s}")
    for r in payload["results"]:
        print(
            f"{r['config']:26s} {r['attack_flag_rate']:>15.3f} "
            f"{r['benign_block_rate']:>12.3f} {r['benign_review_rate']:>13.3f}"
        )
    print(f"\nWritten to {ROOT / args.out}")


if __name__ == "__main__":
    main()
