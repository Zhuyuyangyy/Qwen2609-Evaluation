"""Single source of truth for evaluation field isolation.

Every benchmark adapter, scorer and evaluator must use the definitions here
rather than keeping its own list. Two copies of the forbidden-field set had
already drifted apart in ``benchmark/baselines.py`` before this module existed.

The field classes and the rules that go with them are documented in
``docs/research/EVALUATION_CONTRACT.md``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

# ─── Evaluation-only hidden fields ──────────────────────────────────────────
# No detector, scorer, engine or predictor may read these. Ever.
FORBIDDEN_CASE_FIELDS = frozenset({
    # direct labels
    "label",
    "expected_label",
    "expected_action",
    "expected_risk_score",
    # grading / attack metadata
    "attack_stage",
    "attack_name",
    "injection_goal",
    "injection_task_id",
    "target_functions",
    "grading_function",
    "rationale",
    # fixture bookkeeping that is not runtime observable
    "chain_id",
    "step_index",
    "v3_specific",
    "v3_standard_action",
    # derived from a label -- the rule that is easiest to miss
    "category",
})

# Keys that are safe: kept so adapters can carry provenance notes without
# handing them to a predictor.
NON_PREDICTOR_KEYS = frozenset({"source", "is_proxy"})


def observable_view(case: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of ``case`` holding only runtime-observable fields.

    Scorers and predictors must consume this rather than the raw fixture dict.
    Anything derived from an evaluation-only field must be stripped here too --
    ``category`` is the worked example, since at least one adapter computed it
    as ``attack_name if label == 1 else "benign"``.
    """
    return {k: v for k, v in case.items() if k not in FORBIDDEN_CASE_FIELDS}


def check_observable(view: Dict[str, Any]) -> None:
    """Raise if a supposedly-observable view still carries hidden fields.

    Used by the evaluator boundary and by tests that deliberately hand a
    predictor something it must never see.
    """
    leaked = sorted(FORBIDDEN_CASE_FIELDS & set(view))
    if leaked:
        raise ValueError(
            "evaluation-only field(s) reached a detector: " + ", ".join(leaked)
        )


def leaked_fields(view: Dict[str, Any]) -> Iterable[str]:
    """Names of hidden fields present in ``view`` (empty when clean)."""
    return sorted(FORBIDDEN_CASE_FIELDS & set(view))
