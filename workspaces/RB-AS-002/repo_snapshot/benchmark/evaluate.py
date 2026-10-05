"""
AgentShield V3 Benchmark Evaluator
评估30条测试用例的风险评分和治理动作准确性
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.shield.v3_engine import V3ShieldEngine


def load_test_cases():
    # Prefer the V3-standard 100-case set, then fall back to legacy sets.
    pv3 = Path(__file__).parent / "test_cases" / "test_cases_v3_standard.json"
    p100 = Path(__file__).parent / "test_cases" / "test_cases_100.json"
    p30 = Path(__file__).parent / "test_cases" / "test_cases.json"
    if pv3.exists():
        path = pv3
    elif p100.exists():
        path = p100
    else:
        path = p30
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_case(case: dict) -> dict:
    """对单条测试用例进行评估 - 使用V3引擎process_tool_call

    **Zero label leakage.** The engine receives only what a runtime caller
    could observe: agent id, tool name and parameters. It is handed no risk
    score, no fuse action and no other fixture field, so the measurement is
    "what does AgentShield decide on its own", not "what does it decide once
    told the answer". Ground truth is used solely to score the output.

    Each case also runs on a fresh engine. Sharing one engine meant earlier
    cases' behavior-graph state leaked into later ones, so a case's score
    depended on its position in the file.
    """
    expected_risk = case.get("expected_risk_score", 0.5)
    expected_action = case.get("expected_action", "ALLOW")

    engine = V3ShieldEngine(session_id=f"benchmark-{case['id']}")

    result = engine.process_tool_call(
        agent_id=case.get("agent_id", "benchmark_agent"),
        tool_name=case["tool_name"],
        params=case.get("tool_input", {}),
        risk_score=0.0,
        fuse_action="allow",
    )

    gate = result.get("gate_result", {})
    actual_score = gate.get("score", 0.0)
    actual_action = gate.get("action", "ALLOW")

    score_delta = abs(actual_score - expected_risk)
    action_correct = actual_action == expected_action
    score_pass = score_delta < 0.15

    return {
        "id": case["id"],
        "description": case["description"],
        "category": case["category"],
        "expected_score": expected_risk,
        "actual_score": round(actual_score, 3),
        "score_delta": round(score_delta, 3),
        "score_pass": score_pass,
        "expected_action": expected_action,
        "actual_action": actual_action,
        "action_correct": action_correct,
        "v3_specific": case.get("v3_specific", False),
    }


def run_benchmark():
    """运行完整基准测试"""
    test_cases = load_test_cases()
    print(f"\n{'='*60}")
    print(f"AgentShield V3 Benchmark - {len(test_cases)} Test Cases")
    print("(label-free: the engine is given no ground-truth risk or action)")
    print(f"{'='*60}\n")

    results = []
    for case in test_cases:
        try:
            result = evaluate_case(case)
            results.append(result)
        except Exception as e:
            results.append({
                "id": case["id"],
                "description": case["description"],
                "error": str(e),
                "score_pass": False,
                "action_correct": False,
            })

    # 汇总统计
    total = len(results)
    score_passes = sum(1 for r in results if r.get("score_pass", False))
    action_passes = sum(1 for r in results if r.get("action_correct", False))
    errors = sum(1 for r in results if "error" in r)

    v3_specific = [r for r in results if r.get("v3_specific", False)]
    v3_passes = sum(1 for r in v3_specific if r.get("score_pass", False))

    # 按类别统计
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"total": 0, "pass": 0, "action_pass": 0}
        categories[cat]["total"] += 1
        if r.get("score_pass", False):
            categories[cat]["pass"] += 1
        if r.get("action_correct", False):
            categories[cat]["action_pass"] += 1

    # 打印详细结果
    print(f"{'ID':<8} {'Category':<25} {'ExpScore':>8} {'ActScore':>8} {'Delta':>6} {'Pass':>5} {'ExpAct':<12} {'ActAct':<12}")
    print("-" * 95)
    for r in results:
        status = "PASS" if r.get("score_pass", False) else "FAIL"
        print(f"{r['id']:<8} {r.get('category',''):<25} {r.get('expected_score',0):>8.2f} {r.get('actual_score',0):>8.2f} {r.get('score_delta',0):>6.2f} {status:>5} {r.get('expected_action',''):<12} {r.get('actual_action',''):<12}")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total:     {total} cases")
    print(f"Errors:    {errors}")
    print(f"Score Acc: {score_passes}/{total} ({100*score_passes/total:.1f}%)")
    print(f"Action Acc: {action_passes}/{total} ({100*action_passes/total:.1f}%)")
    print(f"V3 Specific: {len(v3_specific)} cases, {v3_passes}/{len(v3_specific)} ({100*v3_passes/len(v3_specific):.1f}% passes)")

    print("\nBy Category:")
    for cat, stats in sorted(categories.items()):
        print(f"  {cat:<25}: {stats['pass']}/{stats['total']} score, {stats['action_pass']}/{stats['total']} action")

    # 保存详细报告
    report_path = Path(__file__).parent / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": total,
                "errors": errors,
                "score_passes": score_passes,
                "action_passes": action_passes,
                "score_accuracy": round(100 * score_passes / total, 1),
                "action_accuracy": round(100 * action_passes / total, 1),
            },
            "categories": categories,
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved: {report_path}")

    return results


if __name__ == "__main__":
    run_benchmark()
