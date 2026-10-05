"""Prediction-invariance leakage test (replaces shuffled-accuracy inference).

Why the old method was wrong
----------------------------
The previous test compared a baseline's accuracy on real labels against its
accuracy on shuffled labels and inferred ``leakage_suspected`` from a large drop.
That inference does not hold: **any** classifier with predictive power scores
lower when the ground truth is random, because correct answers stop
correlating with the input. A drop in accuracy therefore measures how much the
predictor depends on the labels being meaningful, not whether it reads them.

What is measured instead
------------------------
Leakage is a property of the *predictor's inputs*, not of its accuracy. So:

1. Take a runtime-observable input.
2. Build the normal evaluation metadata.
3. Permute / mutate every evaluation-only field.
4. Keep the runtime observation byte-identical.
5. Call the predictor again.
6. Compare the prediction itself -- label, risk score, decision.

If the prediction changes, the predictor received something derived from
evaluation metadata, which is an isolation violation regardless of accuracy.

The evaluation-only field list comes from ``benchmark/evaluation_contract.py``
so there is a single registry rather than a second blacklist.
"""

from __future__ import annotations

import json
import random
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from benchmark.evaluation_contract import FORBIDDEN_CASE_FIELDS

#: Number of independent metadata permutations applied per case.
DEFAULT_PERMUTATIONS = 8

#: Replacement pool used to mutate each evaluation-only field. Values are
#: deliberately unlike the originals so a predictor that reads them would
#: likely change its output.
_MUTATION_POOL = {
    "label": ["ALLOW", "HUMAN_REVIEW", "BLOCK"],
    "expected_label": ["0", "1", "2"],
    "expected_action": ["ALLOW", "HUMAN_REVIEW", "BLOCK"],
    "expected_risk_score": ["0.05", "0.55", "0.99"],
    "attack_stage": ["recon", "exfiltrate", "single_call", "unknown"],
    "attack_name": ["direct", "ignore_previous", "none", "rogue_value"],
    "injection_goal": ["", "email x@example.com", "delete /tmp/f", "zzz"],
    "injection_task_id": ["injection_task_0", "none", "zzz"],
    "chain_id": ["c-1", "zzz", ""],
    "step_index": ["0", "7", "99"],
    "rationale": ["", "changed rationale", "zzz"],
    "target_functions": ["[]", '["send_email"]', '["delete_file"]'],
    "grading_function": ["grade_a", "grade_z", ""],
    "category": ["benign", "sensitive_data_access", "rogue_category"],
    # Boolean-ish fixture flags. Without an entry here these fields are listed
    # in forbidden_fields_tested but never actually varied, so the "every
    # hidden field was permuted" claim would be false.
    "v3_specific": [True, False],
    "v3_standard_action": ["ALLOW", "HUMAN_REVIEW", "BLOCK", "MAYBE"],
}


def _fallback_mutations(value: Any) -> List[Any]:
    """Generic replacements for a field with no explicit pool entry.

    Without this, a newly added evaluation-only field would be listed in
    ``forbidden_fields_tested`` while never actually being varied -- the exact
    gap that let ``v3_specific`` and ``v3_standard_action`` slip through.
    """
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, (int, float)):
        return [value + 1, 0]
    if isinstance(value, (list, tuple, set)):
        return [[], ["__mutated__"]]
    if isinstance(value, dict):
        return [{"__mutated__": True}]
    return ["", "__mutated__", "__MUTATED__"]


def _mutate_metadata(
    item: Dict[str, Any], rng: random.Random, forbidden: frozenset
) -> Dict[str, Any]:
    """Return a copy of ``item`` with every evaluation-only field changed.

    Only fields listed in ``FORBIDDEN_CASE_FIELDS`` are touched, and only when
    present in the source row. Every touched field is guaranteed to change,
    either via its explicit pool or the generic fallback.
    """
    mutated = dict(item)
    for key in sorted(forbidden):
        if key not in mutated:
            continue
        pool = _MUTATION_POOL.get(key) or _fallback_mutations(mutated[key])
        candidates = [v for v in pool if v != mutated[key]]
        if candidates:
            mutated[key] = rng.choice(candidates)
    return mutated


def _prediction_signature(prediction: Any) -> Tuple:
    """A comparable signature for one prediction.

    Covers the decision, the risk score and any label the predictor emits, so a
    change in any of them is detected.
    """
    if prediction is None:
        return ("none",)
    if isinstance(prediction, dict):
        label = prediction.get("predicted_label", prediction.get("action"))
        score = prediction.get("confidence")
        if score is None:
            score = prediction.get("risk_score")
        extra = prediction.get("reasoning")
        return (
            str(label),
            None if score is None else round(float(score), 9),
            None if extra is None else str(extra)[:120],
        )
    return (str(prediction),)


class _ProductionPredictor:
    """Runs the real AgentShield engine over one observed event.

    The engine sees only the runtime-observable fields; evaluation metadata is
    never passed to it.
    """

    name = "agentshield_production"

    def __init__(self, engine_kwargs: Optional[Dict[str, Any]] = None):
        self._kwargs = engine_kwargs or {}

    def predict(self, event) -> Dict[str, Any]:
        from app.shield.v3_engine import V3ShieldEngine

        # A unique session per call. Sharing one session id makes the behavior
        # graph accumulate across cases, so case N's prediction depends on
        # cases 0..N-1 -- which shows up as a false isolation violation.
        engine = V3ShieldEngine(
            session_id=f"leakage_probe_{uuid.uuid4().hex[:10]}", **self._kwargs
        )
        result = engine.process_tool_call(
            agent_id=event.agent_id,
            tool_name=event.tool_name,
            params=dict(event.tool_input),
            risk_score=0.0,
            fuse_action="allow",
        )
        return {
            "predicted_label": result["decision"].upper(),
            "confidence": result["risk_score"],
            "reasoning": result.get("reasoning", ""),
        }


def _baseline_predictors() -> List[Tuple[str, Any]]:
    """Every baseline used in the SCI-600 comparison, behind one boundary.

    ``ALL_BASELINES`` maps names to *classes*, so each must be instantiated
    before ``evaluate`` can be called -- passing the class straight through
    makes every prediction raise ``AttributeError`` and the invariance test
    silently reports zero checks.
    """
    from benchmark.strong_baselines import ALL_BASELINES

    predictors: List[Tuple[str, Any]] = []
    for name, cls in ALL_BASELINES.items():
        try:
            baseline = cls()
        except Exception:
            continue
        predictors.append((name, _BaselinePredictor(baseline)))
    return predictors


class _BaselinePredictor:
    """Adapts a Baseline instance to the ``predict(event)`` callable interface.

    Being a plain callable (not a bare function) matters: the caller does
    ``predictor.predict(event)``, which every other predictor here supports and
    a returned closure does not.
    """

    def __init__(self, baseline):
        self._baseline = baseline
        self.name = getattr(baseline, "name", type(baseline).__name__)

    def predict(self, event):
        result = self._baseline.evaluate(event)
        return {
            "predicted_label": getattr(result, "predicted_label", None),
            "confidence": getattr(result, "confidence", None),
            "reasoning": getattr(result, "reasoning", None),
        }


def run_invariance_test(
    dataset_path: str,
    output_path: Optional[str] = None,
    permutations: int = DEFAULT_PERMUTATIONS,
    seed: int = 20260923,
    max_cases: int = 60,
) -> Dict[str, Any]:
    """Assert that perturbing evaluation metadata never moves a prediction."""
    from app.shield.schemas import event_from_dict

    with open(dataset_path, encoding="utf-8") as f:
        raw_items = json.load(f)

    sample = raw_items[:max_cases]
    rng = random.Random(seed)

    # ``agentshield_production`` is deliberately NOT taken from
    # _baseline_predictors(): that baseline reuses one engine instance across
    # every event, so its behaviour graph accumulates and case N's prediction
    # depends on cases 0..N-1. For an invariance test that is contamination --
    # it would report a violation for state carry-over, not for leakage.
    # _ProductionPredictor builds a fresh engine per call, which is what the
    # invariance property requires.
    predictors: List[Tuple[str, Any]] = [("agentshield_production", _ProductionPredictor())]
    for name, baseline in _baseline_predictors():
        if name == "agentshield_production":
            continue
        predictors.append((name, baseline))

    per_method: Dict[str, Dict[str, Any]] = {}

    for method_name, predictor in predictors:
        checked = 0
        changed = 0
        cases_tested = 0
        violations: List[Dict[str, Any]] = []

        for item in sample:
            # The runtime observation is built once and never mutated.
            event = event_from_dict(item)
            try:
                base_signature = _prediction_signature(predictor.predict(event))
            except Exception:
                continue

            for _ in range(permutations):
                mutated_item = _mutate_metadata(item, rng, FORBIDDEN_CASE_FIELDS)
                # The observation must be identical: rebuilding it from the
                # mutated row has to yield the same observable fields.
                mutated_event = event_from_dict(mutated_item)
                if _observable_fingerprint(mutated_event) != _observable_fingerprint(event):
                    violations.append({
                        "case": item.get("id"),
                        "kind": "observation_changed",
                    })
                    changed += 1
                    continue

                try:
                    signature = _prediction_signature(predictor.predict(mutated_event))
                except Exception as exc:
                    violations.append({
                        "case": item.get("id"),
                        "kind": "predictor_error",
                        "error": type(exc).__name__,
                    })
                    changed += 1
                    continue

                checked += 1
                if signature != base_signature:
                    changed += 1
                    if len(violations) < 10:
                        violations.append({
                            "case": item.get("id"),
                            "kind": "prediction_changed",
                            "baseline": base_signature,
                            "mutated": signature,
                        })

            cases_tested += 1

        per_method[method_name] = {
            "cases": cases_tested,
            "metadata_permutations": checked,
            "changed_predictions": changed,
            "prediction_invariance_rate": round(1 - changed / checked, 6) if checked else 0.0,
            "isolated": changed == 0,
            "violations": violations,
        }

    total_checks = sum(m["metadata_permutations"] for m in per_method.values())
    total_changes = sum(m["changed_predictions"] for m in per_method.values())

    payload = {
        "experiment": "prediction_invariance_isolation",
        "method": (
            "Permute evaluation-only metadata, hold the runtime observation "
            "constant, and require the prediction to be unchanged. An accuracy "
            "drop under shuffled labels is not evidence of leakage."
        ),
        "dataset": Path(dataset_path).stem,
        "forbidden_fields_tested": sorted(FORBIDDEN_CASE_FIELDS),
        "permutations_per_case": permutations,
        "seed": seed,
        "cases_tested": len(sample),
        "methods_tested": len(per_method),
        "total_permutation_checks": total_checks,
        "changed_predictions": total_changes,
        "prediction_invariance_rate": round(1 - total_changes / total_checks, 6) if total_checks else 0.0,
        "per_method": per_method,
        "retired_metrics": [
            "accuracy_delta",
            "leakage_suspected",
            "shuffled_accuracy",
        ],
    }

    if output_path:
        out = ROOT / output_path
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload


def _observable_fingerprint(event) -> tuple:
    """Fingerprint of the observable fields only.

    Used to prove that mutating metadata left the runtime observation alone.
    """
    return (
        event.event_id,
        event.session_id,
        event.tool_name,
        repr(sorted(event.tool_input.items())),
        event.agent_id,
        str(event.parent_event_id),
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=str,
                    default="benchmark/test_cases/test_cases_sci_600.json")
    ap.add_argument("--out", type=str,
                    default="benchmark/results/leakage_invariance.json")
    ap.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    ap.add_argument("--max-cases", type=int, default=60)
    args = ap.parse_args()

    payload = run_invariance_test(
        args.dataset, args.out, permutations=args.permutations, max_cases=args.max_cases
    )
    print("Prediction-invariance leakage test")
    print(f"  cases            {payload['cases_tested']}")
    print(f"  methods          {payload['methods_tested']}")
    print(f"  permutation runs {payload['total_permutation_checks']}")
    print(f"  changed          {payload['changed_predictions']}")
    print(f"  invariance rate  {payload['prediction_invariance_rate']:.6f}")
    print()
    for name, m in payload["per_method"].items():
        flag = "isolated" if m["isolated"] else "VIOLATION"
        print(f"  {name:26s} {flag:9s} rate={m['prediction_invariance_rate']:.4f} "
              f"changed={m['changed_predictions']}")
    print(f"\nWritten to {ROOT / args.out}")


if __name__ == "__main__":
    main()
