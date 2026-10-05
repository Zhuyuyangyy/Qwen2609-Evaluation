"""Chain-level benchmark: multi-event behaviour chains, label-free.

``benchmark/evaluate.py`` scores isolated tool calls. That cannot exercise the
one thing AgentShield is actually about -- risk propagating across a chain in
``AgentBehaviorGraph``. It is also how the six ``multi_step_action`` cases in
``test_cases_v3_standard.json`` came to score 0.00: they pack an entire attack
chain into a single call's parameters (``{"steps": [...]}``), so there are no
edges to propagate along and the graph never sees a chain at all.

This evaluator replays a case as a sequence of separate tool calls joined by
``parent_node_id``, exactly as a real gateway would. The engine is seeded with
``risk_score=0.0`` throughout: no expected score, action or any other fixture
field reaches the engine. Labels are used only afterwards, to score the
verdict on the final step.

Expected verdict for a chain is the label of its most severe step, which is
the conservative reading -- a chain is judged by the worst thing it does.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.shield.v3_engine import V3ShieldEngine

_SEVERITY = {"ALLOW": 0, "HUMAN_REVIEW": 1, "BLOCK": 2}
# The engine emits lower-case, short-form decisions ("allow"/"review").
_DECISION_ALIAS = {"review": "HUMAN_REVIEW", "human_review": "HUMAN_REVIEW"}


def severity(decision: str) -> int:
    """Severity rank of an engine decision string."""
    text = str(decision).strip().lower()
    return _SEVERITY.get(_DECISION_ALIAS.get(text, text.upper()), 0)


def load_chain_cases() -> List[Dict[str, Any]]:
    path = (
        Path(__file__).resolve().parent
        / "test_cases"
        / "test_cases_v3_standard.json"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def case_is_chain(case: Dict[str, Any]) -> bool:
    """True when a fixture describes multiple steps in one call."""
    return isinstance(case.get("tool_input"), dict) and "steps" in case["tool_input"]


def replay_chain(case: Dict[str, Any]) -> Dict[str, Any]:
    """Replay a multi-step fixture as separate chained tool calls."""
    engine = V3ShieldEngine(session_id=f"chain-{case['id']}")
    steps = case["tool_input"].get("steps") or []

    parent_node_id = None
    per_step: List[Dict[str, Any]] = []
    for index, step in enumerate(steps):
        text = str(step)
        result = engine.process_tool_call(
            agent_id=case.get("agent_id", "benchmark_agent"),
            tool_name=case.get("tool_name", "multi_step_action"),
            # The step text is the payload under evaluation. It goes in the
            # parameter dict so RiskSignalExtractor sees it the same way it sees
            # any other tool argument -- no ground-truth field is involved.
            params={"action": text, "step": index},
            risk_score=0.0,
            fuse_action="allow",
            parent_node_id=parent_node_id,
        )
        parent_node_id = result.get("node_id") or parent_node_id
        per_step.append(
            {
                "step": index,
                "action": text,
                "risk_score": round(float(result["risk_score"]), 3),
                "decision": result["decision"],
            }
        )

    engine.behavior_graph.compute_risk_propagation()
    graph = engine.behavior_graph
    nodes = graph.get_session_nodes()

    return {
        "per_step": per_step,
        "final_decision": per_step[-1]["decision"] if per_step else "allow",
        "max_step_risk": max((s["risk_score"] for s in per_step), default=0.0),
        "graph": {
            "total_nodes": graph.summary()["total_nodes"],
            "total_edges": len(graph.edges),
            "max_inherited_risk": round(
                max((n.inherited_risk for n in nodes), default=0.0), 3
            ),
            "amplifier_count": sum(1 for n in nodes if n.downstream_risk_amplified),
        },
    }


def main() -> None:
    cases = [c for c in load_chain_cases() if case_is_chain(c)]
    print(f"Chain cases: {len(cases)}")
    print("(label-free: engine receives only tool name and parameters)\n")

    correct = 0
    for case in cases:
        outcome = replay_chain(case)
        expected = case.get("expected_action", "ALLOW")
        # A chain is judged by its worst step.
        predicted = max(
            (s["decision"] for s in outcome["per_step"]),
            key=severity,
            default="allow",
        )
        ok = predicted.upper() == expected.upper()
        correct += int(ok)
        g = outcome["graph"]
        print(
            f"{'PASS' if ok else 'FAIL':4s} {case['id']:8s} "
            f"expect={expected:12s} worst_step={predicted:12s} "
            f"max_risk={outcome['max_step_risk']:.2f} "
            f"nodes={g['total_nodes']} edges={g['total_edges']} "
            f"inh={g['max_inherited_risk']:.2f} amp={g['amplifier_count']}"
        )

    total = len(cases)
    print(f"\nChain accuracy: {correct}/{total} ({100 * correct / total:.1f}%)" if total else "\nNo chain cases found.")


if __name__ == "__main__":
    main()
