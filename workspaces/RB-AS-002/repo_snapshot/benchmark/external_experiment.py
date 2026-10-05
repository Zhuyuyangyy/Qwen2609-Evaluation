"""AgentShield V3 — external experiment on REAL multi-step attack data.

Compares the project's risk_scoring on REAL public benchmarks against
the actual `llm-guard` PyPI package (the simulated `nemo_guardrails_baseline.py`
in benchmark/ is known to be a re-implementation per the independent review).

Datasets (REAL, not synthesized):
  * AgentDojo dump (ffuuugor/agentdojo-dump): 13,913 real tool-call samples
    from the AgentDojo benchmark with ground-truth `label` (0=benign, 1=attack)
  * AgentHarm (ai-safety-institute/AgentHarm harmful): 208 real multi-step
    harmful prompts with `target_functions` and `grading_function`

Methods compared:
  1. No-defense baseline: ALLOW everything.
  2. Real `llm-guard` PyPI package: PromptInjection + BanTopics + Toxicity
     input scanners. Predict BLOCK if any scanner says invalid.
  3. AgentShield V3 (full pipeline): chain-aware + graph propagation.

Multi-seed: 3 seeds with bootstrap resampling of the eval set.

There is deliberately no ablation entry. The previous one had a different name
but identical code to the full method, so its reported delta meant nothing. A
real component ablation needs a configuration flag on the engine, which the
provenance work introduces; see the NOTE above METHODS.

Reproduction:
  python -m benchmark.external_experiment
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List

# Quiet down the HF progress bars / llm-guard model download chatter
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("external_experiment")
log.setLevel(logging.INFO)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from benchmark.evaluation_contract import observable_view, check_observable


# ============================================================================
# Data loading
# ============================================================================

CACHE = ROOT / "benchmark" / "external_datasets"


def load_agentdojo(max_samples: int = 0) -> List[Dict[str, Any]]:
    from datasets import load_dataset
    ds = load_dataset(
        "ffuuugor/agentdojo-dump",
        cache_dir=str(CACHE),
    )["train"]
    cases: List[Dict[str, Any]] = []
    for i, row in enumerate(ds):
        if max_samples and i >= max_samples:
            break
        try:
            args = json.loads(row["tool_call_args"]) if row.get("tool_call_args") else {}
        except Exception:
            args = {"raw": row.get("tool_call_args", "")}
        cases.append({
            "id": f"ADJ-{i:05d}",
            "source": "agentdojo",
            # label-free: was `attack_name if label==1 else "benign"`, i.e.
            # derived straight from ground truth.
            "category": "external_sample",
            "agent_id": "agentdojo_agent",
            "tool_name": row.get("tool_call_function", ""),
            "tool_input": args,
            "user_task_prompt": row.get("user_task_prompt", ""),
            "injection_goal": row.get("injection_goal", ""),
            "attack_name": row.get("attack_name", "none"),
            "injection_task_id": row.get("injection_task_id", "none"),
            "expected_action": "BLOCK" if row.get("label") == 1 else "ALLOW",
            "expected_label": int(row.get("label", 0)),
        })
    return cases


def _load_agentharm_arrow(split: str) -> List[Dict[str, Any]]:
    """Read AgentHarm straight from the cached Arrow file.

    ``load_dataset`` fails on the published dataset_info.json with datasets
    3.6.0: the features block declares a ``List`` type that the library no
    longer recognises ("Feature type 'List' not found"), and the error escapes
    before any row is produced. Both splits therefore loaded zero rows and
    every AgentHarm number ever reported was vacuous.

    Reading the Arrow file directly sidesteps the metadata parse entirely.
    """
    import pyarrow as pa

    matches = sorted(CACHE.rglob(f"agent_harm-{split}.arrow"))
    if not matches:
        return []

    rows: List[Dict[str, Any]] = []
    for path in matches:
        table = pa.ipc.open_stream(pa.memory_map(str(path), "r")).read_all()
        columns = {name: table.column(name).to_pylist() for name in table.column_names}
        for i in range(table.num_rows):
            rows.append({name: values[i] for name, values in columns.items()})
    return rows


def _load_agentharm_rows(split: str) -> List[Dict[str, Any]]:
    """Load AgentHarm rows via datasets, falling back to raw Arrow."""
    try:
        from datasets import load_dataset

        ds = load_dataset(
            "ai-safety-institute/AgentHarm",
            "harmful",
            split=split,
            cache_dir=str(CACHE),
        )
        return [dict(row) for row in ds]
    except Exception as e:
        log.warning(
            "AgentHarm %s: datasets loader failed (%s); reading Arrow directly",
            split,
            type(e).__name__,
        )
        return _load_agentharm_arrow(split)


def load_agentharm(max_samples: int = 0) -> List[Dict[str, Any]]:
    """Load AgentHarm-derived **harmful-action proxy** cases.

    This is NOT the AgentHarm benchmark. The official evaluation runs an agent
    end to end under Inspect Evals and uses ``target_functions`` and
    ``grading_function`` as *grading metadata* to decide whether the task was
    completed -- those fields describe what a successful attack would call,
    not what any agent actually called.

    This adapter reads the published dataset rows and synthesises one
    hypothetical tool call per target function. It therefore measures "would
    AgentShield flag the actions a harmful task would need", which is a
    different claim from "AgentShield performs X on the AgentHarm benchmark".
    Results are labelled ``agentharm_proxy`` in every report.
    """
    cases: List[Dict[str, Any]] = []
    for split in ["test_public", "validation"]:
        try:
            ds = _load_agentharm_rows(split)
        except Exception as e:
            log.warning("AgentHarm %s load failed: %s", split, e)
            continue
        for i, row in enumerate(ds):
            if max_samples and len(cases) >= max_samples:
                break
            target = row.get("target_functions") or []
            if isinstance(target, str):
                target = [target]
            # Build a multi-step tool-call list
            tool_calls: List[Dict[str, Any]] = []
            for j, fn in enumerate(target):
                tool_calls.append({
                    "tool_name": fn,
                    "tool_input": {"prompt_context": row.get("prompt", "")[:200]},
                    "step": j,
                })
            cases.append({
                "id": f"AH-{split}-{i:04d}",
                "source": "agentharm_proxy",
                "is_proxy": True,
                "category": row.get("category", "harmful"),
                "agent_id": "agentharm_agent",
                "tool_calls": tool_calls,
                "tool_name": target[0] if target else "unknown",
                "tool_input": {"prompt_context": row.get("prompt", "")[:200]},
                "prompt": row.get("prompt", ""),
                "target_functions": target,
                "expected_action": "BLOCK",  # All AgentHarm/harmful are harmful
                "expected_label": 1,
            })
    return cases


# ============================================================================
# Method: No defense
# ============================================================================

def predict_no_defense(case: Dict[str, Any]) -> str:
    return "ALLOW"


# ============================================================================
# Method: Real `llm-guard` (PyPI package, v0.3.16)
# ============================================================================

_LLM_GUARD = None


def _llm_guard():
    """Lazy-init llm_guard scanners (heavy: model download + load)."""
    global _LLM_GUARD
    if _LLM_GUARD is not None:
        return _LLM_GUARD
    from llm_guard import scan_prompt
    from llm_guard.input_scanners import PromptInjection, BanTopics, Toxicity
    # We use 3 scanners that are CPU-friendly and that 'real' llm-guard
    # would run in production as the input stage
    scanners = [
        PromptInjection(),
        BanTopics(topics=["violence", "hate", "self-harm", "illicit", "weapons"]),
        Toxicity(),
    ]
    _LLM_GUARD = (scan_prompt, scanners)
    return _LLM_GUARD


def predict_llm_guard(case: Dict[str, Any]) -> str:
    scan_prompt, scanners = _llm_guard()
    # Aggregate the runtime-observable text only. ``injection_goal`` is the
    # benchmark's description of the attack objective -- evaluation ground
    # truth. Including it let this baseline read the answer.
    view = observable_view(case)
    parts = []
    if view.get("prompt"):
        parts.append(view["prompt"])
    if view.get("user_task_prompt"):
        parts.append(view["user_task_prompt"])
    tool = case.get("tool_name", "")
    inp = case.get("tool_input", {})
    if isinstance(inp, dict):
        for k, v in inp.items():
            parts.append(f"{k}={v}")
    text = " \n ".join(parts)[:1024] or tool
    try:
        _prompt, results_valid, _scores = scan_prompt(scanners, text, fail_fast=False)
    except Exception as e:
        log.debug("llm_guard failed: %s", e)
        return "ALLOW"
    # If ANY scanner flagged invalid -> BLOCK
    if any(not v for v in results_valid.values()):
        return "BLOCK"
    return "ALLOW"


# ============================================================================
# Method: AgentShield V3 (full pipeline, label-free)
# ============================================================================

def _replay_on_engine(eng, view: Dict[str, Any]) -> str:
    """Replay an observation through a live engine, chaining the steps.

    Multi-step observations are linked with ``parent_node_id`` so
    AgentBehaviorGraph actually gets edges. Without the linkage every step is
    an isolated node, the graph has nothing to propagate through, and
    "chain-aware" evaluation silently degenerates into N independent
    single-call evaluations.
    """
    calls = view.get("tool_calls")
    if calls:
        parent_node_id = None
        last_action = "ALLOW"
        for tc in calls:
            out = eng.process_tool_call(
                agent_id=view.get("agent_id", "agent"),
                tool_name=tc.get("tool_name", ""),
                params=tc.get("tool_input", {}),
                risk_score=0.0,
                fuse_action="allow",
                parent_node_id=parent_node_id,
            )
            parent_node_id = out.get("node_id") or parent_node_id
            last_action = out["decision"]
        return last_action

    out = eng.process_tool_call(
        agent_id=view.get("agent_id", "agent"),
        tool_name=view.get("tool_name", ""),
        params=view.get("tool_input", {}),
        risk_score=0.0,
        fuse_action="allow",
    )
    return out["decision"]


def predict_agentshield_full(case: Dict[str, Any]) -> str:
    """Run the real production pipeline: RiskSignalExtractor -> graph -> engine.

    Seeded with ``risk_score=0.0`` and handed only the observable view, so the
    decision comes entirely from the engine's own signal extraction and risk
    propagation over runtime-observable fields. Nothing derived from a label
    reaches it.
    """
    from app.shield.v3_engine import V3ShieldEngine

    eng = V3ShieldEngine(
        session_id=f"ext_{case.get('id', 'case')}", risk_threshold=0.70
    )
    return _replay_on_engine(eng, observable_view(case))


# ============================================================================
# NOTE (C.5-7): no ablation entry here on purpose.
#
# There was one, named "AgentShield V3 (no special-case rules)", but it ran
# exactly the same code as predict_agentshield_full -- no signal was actually
# disabled. A copy-pasted predictor with a different name is not an ablation.
#
# A real component ablation needs a configuration on the engine itself
# (e.g. RiskExtractorConfig(enable_payload_semantics=False)), which belongs to
# the provenance architecture work. Until that exists the entry stays out rather
# than reporting a delta of zero as if it measured something.
# ============================================================================

def evaluate_method(name: str, predictor: Callable, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score a predictor over three-class labels with unambiguous metrics.

    Every predictor is handed an already-sanitised observation: the isolation
    boundary is here, not inside each predictor. See
    docs/research/EVALUATION_CONTRACT.md for the field classes and metric
    definitions used below.
    """
    start = time.perf_counter()
    labels = ("ALLOW", "HUMAN_REVIEW", "BLOCK")
    confusion: Dict[str, Counter] = {g: Counter() for g in labels}
    rows = []
    for case in cases:
        # Isolation is enforced at the evaluator boundary so a predictor that
        # forgets to sanitise still never sees a label.
        observation = observable_view(case)
        check_observable(observation)
        try:
            pred = predictor(observation)
        except Exception as e:
            log.warning("predictor %s crashed on %s: %s", name, case.get("id"), e)
            pred = "ALLOW"
        if pred not in labels:
            pred = "ALLOW"
        expected = case.get("expected_action", "ALLOW")
        if expected not in labels:
            expected = "ALLOW"
        confusion[expected][pred] += 1
        rows.append({
            "id": case.get("id"),
            "expected": expected,
            "predicted": pred,
            "match": pred == expected,
        })
    elapsed = time.perf_counter() - start

    attack_groups = ("BLOCK", "HUMAN_REVIEW")
    attack_total = sum(confusion[g][p] for g in attack_groups for p in labels)
    benign_total = sum(confusion["ALLOW"][p] for p in labels)
    total = attack_total + benign_total

    attack_detected = sum(
        confusion[g][p] for g in attack_groups for p in ("HUMAN_REVIEW", "BLOCK")
    )
    attack_blocked = sum(confusion[g]["BLOCK"] for g in attack_groups)
    benign_reviewed = confusion["ALLOW"]["HUMAN_REVIEW"]
    benign_blocked = confusion["ALLOW"]["BLOCK"]
    allowed = sum(confusion[g]["ALLOW"] for g in labels)
    blocked_pred = sum(confusion[g]["BLOCK"] for g in labels)

    detection_recall = attack_detected / attack_total if attack_total else 0.0
    block_recall = attack_blocked / attack_total if attack_total else 0.0
    precision = attack_blocked / blocked_pred if blocked_pred else 0.0
    f1 = (
        2 * precision * block_recall / (precision + block_recall)
        if (precision + block_recall)
        else 0.0
    )

    return {
        "name": name,
        "total": total,
        "attack_total": attack_total,
        "benign_total": benign_total,
        "detection_recall": round(detection_recall, 4),
        "block_recall": round(block_recall, 4),
        "benign_review_rate": round(benign_reviewed / benign_total, 4) if benign_total else 0.0,
        "benign_block_fpr": round(benign_blocked / benign_total, 4) if benign_total else 0.0,
        "allow_rate": round(allowed / total, 4) if total else 0.0,
        "block_precision": round(precision, 4),
        "f1_block": round(f1, 4),
        "three_class_accuracy": round(
            sum(confusion[g][g] for g in labels) / total, 4
        ) if total else 0.0,
        "false_allow": attack_total - attack_detected,
        "false_block": benign_blocked,
        # Zero-filled so consumers never KeyError on an absent class.
        "confusion": {g: {p: confusion[g][p] for p in labels} for g in labels},
        "rows": rows,
        "elapsed_s": round(elapsed, 2),
    }


def bootstrap_eval(name: str, predictor: Callable, cases: List[Dict[str, Any]],
                   seed: int, n_boot: int = 1) -> Dict[str, Any]:
    """Evaluate once, seeding internal randomness for reproducibility."""
    random.seed(seed)
    return evaluate_method(name, predictor, cases)



METHODS = [
    ("No defense", predict_no_defense),
    ("llm-guard (real PyPI)", predict_llm_guard),
    ("AgentShield V3 (full)", predict_agentshield_full),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-agentdojo", type=int, default=0,
                    help="0 = all; cap for speed")
    ap.add_argument("--max-agentharm", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", type=str, default="benchmark/external_experiment_results.json")
    args = ap.parse_args()

    log.info("Loading AgentDojo (real benchmark)...")
    agentdojo = load_agentdojo(max_samples=args.max_agentdojo)
    log.info("  loaded %d AgentDojo samples", len(agentdojo))

    log.info("Loading AgentHarm (real benchmark)...")
    agentharm = load_agentharm(max_samples=args.max_agentharm)
    log.info("  loaded %d AgentHarm samples", len(agentharm))

    # Distribution
    print("=" * 70)
    print("REAL DATA")
    print("=" * 70)
    print("  AgentDojo dump (ffuuugor/agentdojo-dump, HF)")
    print(f"    samples loaded:   {len(agentdojo)}")
    print(f"    label=1 (attack): {sum(1 for c in agentdojo if c['expected_label']==1)}")
    print(f"    label=0 (benign): {sum(1 for c in agentdojo if c['expected_label']==0)}")
    print()
    print("  AgentHarm harmful (ai-safety-institute/AgentHarm, HF)")
    print(f"    samples loaded:   {len(agentharm)}")
    print(f"    all harmful:      {sum(1 for c in agentharm if c['expected_label']==1)}")
    print()

    for dataset_name, dataset in [("AgentDojo", agentdojo), ("AgentHarm", agentharm)]:
        if not dataset:
            continue
        print("=" * 70)
        print(f"EVAL ON {dataset_name}  (n={len(dataset)})")
        print("=" * 70)

        # Per-method, multi-seed: run once, report metrics
        # (predictors are deterministic given the input set; multi-seed
        #  covers any internal randomness in bootstrap)
        all_results: Dict[str, List[Dict[str, Any]]] = {m[0]: [] for m in METHODS}
        for seed in range(args.seeds):
            log.info("  [seed %d] running 4 methods...", seed)
            for mname, mfn in METHODS:
                res = bootstrap_eval(mname, mfn, dataset, seed=42 + seed)
                all_results[mname].append(res)
                log.info("    %-40s block_recall=%.3f acc=%.3f",
                         mname, res["block_recall"], res["three_class_accuracy"])

        # Aggregate
        print()
        print(f"{'Method':<45} {'Block Recall':>14} {'F1 (block)':>11} {'Acc':>8} {'FA rate':>9}")
        print("-" * 90)
        summary = {}
        for mname, _ in METHODS:
            recalls = [r["block_recall"] for r in all_results[mname]]
            f1s = [r["f1_block"] for r in all_results[mname]]
            accs = [r["three_class_accuracy"] for r in all_results[mname]]
            fas = [r["false_allow"] / r["attack_total"] if r["attack_total"] else 0.0 for r in all_results[mname]]
            mean_recall = statistics.mean(recalls)
            std_recall = statistics.pstdev(recalls) if len(recalls) > 1 else 0.0
            mean_f1 = statistics.mean(f1s)
            mean_acc = statistics.mean(accs)
            mean_fa = statistics.mean(fas)
            print(f"{mname:<45} {mean_recall*100:>7.2f}% ±{std_recall*100:>4.2f}  "
                  f"{mean_f1:>8.4f}  {mean_acc*100:>6.2f}%  {mean_fa*100:>6.2f}%")
            summary[mname] = {
                "mean_block_recall": mean_recall,
                "std_block_recall": std_recall,
                "mean_f1_block": mean_f1,
                "mean_action_accuracy": mean_acc,
                "mean_false_allow_rate": mean_fa,
                "per_seed": all_results[mname],
            }
        print()

        # Key claim check: the production pipeline against the strongest
        # non-AgentShield baseline. The earlier "ablation check" compared the
        # full method against an entry that had been deleted from METHODS, so
        # it could never run.
        full = summary.get("AgentShield V3 (full)", {})
        guard = summary.get("llm-guard (real PyPI)", {})
        if full and guard:
            full_r = full.get("mean_block_recall", 0.0)
            guard_r = guard.get("mean_block_recall", 0.0)
            full_fa = full.get("mean_false_allow_rate", 0.0)
            guard_fa = guard.get("mean_false_allow_rate", 0.0)
            print(">>> BASELINE COMPARISON (block_recall / false_allow):")
            print(f"    AgentShield V3 (full)   {full_r*100:.2f}% / {full_fa*100:.2f}%")
            print(f"    llm-guard (real PyPI)   {guard_r*100:.2f}% / {guard_fa*100:.2f}%")
            print(f"    block_recall delta: {(full_r - guard_r)*100:+.2f} pp")
            print()

        # Save results
        out_path = ROOT / args.out
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "dataset": dataset_name,
                "n_samples": len(dataset),
                "n_seeds": args.seeds,
                "methods": summary,
                "raw_per_method_per_seed": {
                    mname: all_results[mname] for mname, _ in METHODS
                },
            }, f, indent=2, default=str)
        log.info("Saved %s", out_path)

    print("=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
