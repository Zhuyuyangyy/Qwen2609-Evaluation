import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_live():
    import importlib.util

    path = _REPO_ROOT / "benchmark" / "live_agent_governance.py"
    spec = importlib.util.spec_from_file_location("live_agent_governance", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["live_agent_governance"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestLiveHarnessContract:
    """The harness must refuse to run without credentials, and must not claim
    to be the official AgentDojo benchmark."""

    def setup_method(self):
        self.mod = _load_live()

    def test_run_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("AGENTSHIELD_LLM_API_KEY", raising=False)
        with pytest.raises(self.mod.MissingCredentialError):
            self.mod.run(max_tasks=1)

    def test_tool_backend_uses_recorded_responses(self):
        rows = [{
            "tool_call_function": "search_emails",
            "tool_call_args": {"query": "invoice"},
            "tool_response": "results: 2 emails",
            "label": 1,
        }]
        backend = self.mod.ToolBackend.from_rows(rows)
        assert backend.call("search_emails", {"query": "invoice"}) == "results: 2 emails"
        assert backend.call("search_emails", {"query": "other"}).startswith("(no recorded")

    def test_tool_backend_never_sees_label_or_goal(self):
        """A response must be indexed by tool+args only, never by metadata."""
        rows = [
            {"tool_call_function": "t", "tool_call_args": {}, "tool_response": "A", "label": 1,
             "injection_goal": "email x@y.com"},
            {"tool_call_function": "t", "tool_call_args": {}, "tool_response": "B", "label": 0,
             "injection_goal": ""},
        ]
        backend = self.mod.ToolBackend.from_rows(rows)
        # Same tool+args -> first response wins; the label/goal must not select.
        assert backend.call("t", {}) == "A"
        # And the index must contain no metadata keys.
        for key in backend.responses:
            assert len(key) == 2
            assert isinstance(key[0], str)
            assert isinstance(key[1], str)

    def test_action_parsing_accepts_plain_json(self):
        action = self.mod.LiveAgent._parse_action('{"tool": "read_file", "arguments": {"path": "/a"}}')
        assert action == {"tool": "read_file", "arguments": {"path": "/a"}}

    def test_action_parsing_extracts_json_from_noise(self):
        action = self.mod.LiveAgent._parse_action(
            'Sure! I will read the file.\n{"tool": "read_file", "arguments": {"path": "/a"}}\nDone.'
        )
        assert action is not None
        assert action["tool"] == "read_file"

    def test_action_parsing_rejects_garbage(self):
        assert self.mod.LiveAgent._parse_action("no json here") is None
        assert self.mod.LiveAgent._parse_action('{"no_tool": 1}') is None
        assert self.mod.LiveAgent._parse_action("") is None

    def test_action_parsing_coerces_non_dict_arguments(self):
        action = self.mod.LiveAgent._parse_action('{"tool": "t", "arguments": "oops"}')
        assert action == {"tool": "t", "arguments": {"value": "oops"}}

    def test_ungoverned_engine_always_allows(self):
        engine = self.mod.UngovernedEngine()
        result = engine.process_tool_call(tool_name="delete_everything", params={})
        assert result["decision"] == "allow"
        assert result["node_id"].startswith("free_")

    def test_configs_are_distinct(self):
        keys = []
        for name, factory in self.mod.CONFIGS.items():
            engine = factory("cfg_probe")
            keys.append((name,
                         getattr(engine, "enable_provenance", None),
                         getattr(engine, "enable_taint_tracking", None),
                         getattr(engine, "_ignore_user_intent", None)))
        assert len(set(keys)) == len(keys)

    def test_benign_tasks_exclude_attack_rows(self):
        rows = [
            {"suite_name": "s", "user_task_id": "t0", "label": 0,
             "user_task_prompt": "find my emails"},
            {"suite_name": "s", "user_task_id": "t0", "label": 1,
             "user_task_prompt": "find my emails"},  # same task, attack variant
            {"suite_name": "s", "user_task_id": "t1", "label": 1,
             "user_task_prompt": "other"},
        ]
        tasks = self.mod.benign_tasks(rows)
        assert tasks == [("s|t0", "find my emails")]

    def test_report_flags_are_honest(self, monkeypatch):
        monkeypatch.setenv("AGENTSHIELD_LLM_API_KEY", "dummy")

        # Stub out the LLM so no network call happens.
        class FakeAgent:
            calls = 0

            def __init__(self, **kwargs):
                type(self).calls += 1

            def run(self, task_id, task):
                return {
                    "task_id": task_id, "steps": [], "blocked_at_step": None,
                    "steps_allowed": 0, "steps_reviewed": 0, "steps_blocked": 0,
                    "terminated_by_block": False, "tool_counts": {},
                    "llm_calls": 1, "llm_errors": 0,
                }

        monkeypatch.setattr(self.mod, "LiveAgent", FakeAgent)
        payload = self.mod.run(max_tasks=2, output_path=None)

        assert payload["official_agentdojo_benchmark"] is False
        assert payload["simulated_backend"] is True
        assert payload["llm_used"] is True
        assert payload["asr_measured"] is False
        assert payload["utility_measured"] is False
        assert payload["task_success_measured"] is False
        assert payload["limitations"]
        assert "not the official agentdojo benchmark" in json.dumps(payload).lower()

    def test_blocked_call_is_not_executed(self):
        """A blocked tool must never reach the backend."""
        backend = self.mod.ToolBackend.from_rows([
            {"tool_call_function": "send_email", "tool_call_args": {"to": "x@y.com"},
             "tool_response": "sent"},
        ])

        class BlockingEngine:
            def process_tool_call(self, **kwargs):
                return {"decision": "block", "risk_score": 0.95,
                        "node_id": "n1", "graph_risk_state": {"signals": ["x"]}}

        agent = self.mod.LiveAgent(
            model="m", api_key="k", engine_factory=lambda sid: BlockingEngine(),
            backend=backend, tool_names=["send_email"], max_steps=2,
        )
        agent._complete = lambda messages: '{"tool": "send_email", "arguments": {"to": "x@y.com"}}'

        out = agent.run("t", "send an email")
        # The stub always asks for the same tool, so the retry cap engages and
        # both attempts are blocked -- neither reaches the backend.
        assert out["steps_blocked"] >= 1
        assert backend.call_counts == {}, "blocked call reached the backend"
        assert out["blocked_at_step"] == 0
        assert out["terminated_by_block"] is False  # policy: agent is told and continues
