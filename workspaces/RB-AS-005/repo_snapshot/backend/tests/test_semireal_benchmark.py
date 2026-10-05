import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_semireal_generator_produces_balanced_trace_dataset(tmp_path):
    from benchmark.generate_semireal_traces import generate_traces
    from benchmark.trace_schema import TraceLabel, validate_trace

    output = tmp_path / "semireal.json"
    traces = generate_traces(output=output, size=150, seed=20260526)

    assert output.exists()
    assert len(traces) == 150
    labels = {label.value: 0 for label in TraceLabel}
    for trace in traces:
        validate_trace(trace)
        labels[trace["chain_label"]] += 1
        assert trace["source"] == "controlled_semireal"
        assert trace["human_reviewed"] is True
        assert trace["steps"]

    assert labels["ALLOW"] == 50
    assert labels["HUMAN_REVIEW"] == 40
    assert labels["BLOCK"] == 60


def test_semireal_traces_include_required_risky_scenarios(tmp_path):
    from benchmark.generate_semireal_traces import generate_traces

    traces = generate_traces(output=tmp_path / "semireal.json", size=150, seed=20260526)
    scenarios = {trace["scenario_type"] for trace in traces}

    assert "normal_business_query" in scenarios
    assert "sensitive_query_then_compress_and_send" in scenarios
    assert "privilege_escalation" in scenarios
    assert "audit_log_bypass" in scenarios
    assert "multi_agent_delegation_risk" in scenarios


def test_semireal_evaluator_writes_report_and_table(tmp_path):
    from benchmark.evaluate_semireal import run
    from benchmark.generate_semireal_traces import generate_traces

    dataset = tmp_path / "semireal.json"
    json_out = tmp_path / "report.json"
    md_out = tmp_path / "table.md"
    generate_traces(output=dataset, size=30, seed=20260526)

    report = run(dataset=dataset, json_out=json_out, md_out=md_out)

    assert json_out.exists()
    assert md_out.exists()
    assert report["total_traces"] == 30
    assert report["total_steps"] > 30
    baseline_names = [item["name"] for item in report["baselines"]]
    assert "Tool-name rules" in baseline_names
    assert "Content keywords" in baseline_names
    assert "Local context" in baseline_names
    assert "AgentShield chain-aware" in baseline_names
    assert "AgentShield + Graph" in baseline_names
    assert "LLM-as-Judge" in baseline_names
    table = md_out.read_text(encoding="utf-8")
    assert "Semi-Real Trace Baseline Comparison" in table
    assert "AgentShield chain-aware" in table


def test_semireal_json_is_serializable(tmp_path):
    from benchmark.generate_semireal_traces import generate_traces

    output = tmp_path / "semireal.json"
    traces = generate_traces(output=output, size=30, seed=20260526)
    loaded = json.loads(output.read_text(encoding="utf-8"))

    assert loaded == traces


def test_semireal_ablation_writes_required_configs(tmp_path):
    from benchmark.ablation_semireal import run
    from benchmark.evaluate_semireal import run as run_semireal
    from benchmark.generate_semireal_traces import generate_traces

    dataset = tmp_path / "semireal.json"
    json_out = tmp_path / "ablation.json"
    md_out = tmp_path / "ablation.md"
    generate_traces(output=dataset, size=150, seed=20260526)

    report = run(dataset=dataset, json_out=json_out, md_out=md_out)
    baseline = run_semireal(
        dataset=dataset,
        json_out=tmp_path / "baseline.json",
        md_out=tmp_path / "baseline.md",
    )

    assert json_out.exists()
    assert md_out.exists()
    names = [item["name"] for item in report["ablations"]]
    assert "AgentShield + Graph" in names
    assert "AgentShield (no graph)" in names
    assert "w/o chain inference" in names
    assert "Content keywords only" in names
    assert "LLM-as-Judge" in names

    table = md_out.read_text(encoding="utf-8")
    assert "Semi-Real Trace Ablation Study" in table
    assert "| Configuration | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |" in table

    by_name = {item["name"]: item for item in report["ablations"]}
    baseline_by_name = {item["name"]: item for item in baseline["baselines"]}
    # AgentShield (no graph) in ablation should match AgentShield chain-aware in baseline
    assert by_name["AgentShield (no graph)"]["action_accuracy"] == baseline_by_name["AgentShield chain-aware"]["action_accuracy"]
    assert by_name["AgentShield (no graph)"]["macro_f1"] == baseline_by_name["AgentShield chain-aware"]["macro_f1"]
    assert by_name["AgentShield (no graph)"]["block_recall"] == baseline_by_name["AgentShield chain-aware"]["block_recall"]
    # Chain-aware should outperform local-only
    assert by_name["AgentShield (no graph)"]["block_recall"] > by_name["w/o chain inference"]["block_recall"]
