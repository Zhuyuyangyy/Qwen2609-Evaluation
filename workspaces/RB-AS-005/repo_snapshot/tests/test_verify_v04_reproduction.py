"""Unit tests for the v0.4.1 reproduction verifier.

These test the verifier, not the experiment. No AgentDojo replay is executed
here: the fixtures are in-memory JSON documents, so the suite runs in
milliseconds and stays independent of the locally staged dump.

What is being pinned is the failure behaviour. A verifier that returns PASS for
a subtly different artifact is worse than no verifier, so every mutation the
harness could plausibly produce gets its own negative case.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.verify_v04_reproduction import compare, main  # noqa: E402


def _artifact() -> dict:
    """A minimal but structurally faithful artifact."""
    return {
        "experiment": "v0.4_trust_aware_pareto",
        "mode": "audit",
        "dataset_source": "ffuuugor/agentdojo-dump",
        "detector_label_free": True,
        "trajectory_reconstructed_from_attack_metadata": False,
        "native_runtime_trace": True,
        "asr_measured": False,
        "utility_measured": False,
        "trust_policy_frozen_before_measurement": True,
        "sampling": "97 benign + 400 attack trajectories",
        "baseline_for_delta": "plus_entity_provenance (v0.3)",
        "audit": {
            "rows": 13913,
            "trajectories": 10536,
            "excluded": {},
            "excluded_total": 0,
        },
        "ladder": [
            {"config": "local_only", "adds": "single-event gate"},
            {"config": "plus_output_inspection", "adds": "+ untrusted output"},
            {"config": "plus_entity_provenance", "adds": "+ entity origin"},
        ],
        "results": [
            {
                "config": "local_only",
                "benign_traces": 97,
                "benign_steps": 339,
                "benign_step_block_fpr": 0.00295,
                "benign_step_review_rate": 0.11799,
                "benign_trace_block_rate": 0.01031,
                "attack_traces": 400,
                "attack_trace_detection_rate": 0.035,
                "attack_trace_block_rate": 0.0,
                "delta_vs_v03_provenance": {
                    "attack_trace_block_pp": -16.0,
                    "benign_trace_block_pp": -40.21,
                },
            },
            {
                "config": "plus_output_inspection",
                "benign_traces": 97,
                "benign_steps": 339,
                "benign_step_block_fpr": 0.07965,
                "benign_step_review_rate": 0.059,
                "benign_trace_block_rate": 0.19588,
                "attack_traces": 400,
                "attack_trace_detection_rate": 0.07,
                "attack_trace_block_rate": 0.035,
                "delta_vs_v03_provenance": {
                    "attack_trace_block_pp": -12.5,
                    "benign_trace_block_pp": -21.65,
                },
            },
            {
                "config": "plus_entity_provenance",
                "benign_traces": 97,
                "benign_steps": 339,
                "benign_step_block_fpr": 0.19469,
                "benign_step_review_rate": 0.059,
                "benign_trace_block_rate": 0.41237,
                "attack_traces": 400,
                "attack_trace_detection_rate": 0.195,
                "attack_trace_block_rate": 0.16,
                "delta_vs_v03_provenance": {
                    "attack_trace_block_pp": 0.0,
                    "benign_trace_block_pp": 0.0,
                },
            },
        ],
    }


def _write(tmp_path: Path, payload: dict, name: str) -> Path:
    path = tmp_path / name
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def _problems(canonical: dict, reproduced: dict, tmp_path: Path) -> list:
    c_path = _write(tmp_path, canonical, "canonical.json")
    r_path = _write(tmp_path, reproduced, "reproduced.json")
    problems, _, _ = compare(c_path, r_path)
    return problems


class TestIdenticalArtifacts:
    def test_identical_artifact_passes(self, tmp_path):
        assert _problems(_artifact(), _artifact(), tmp_path) == []

    def test_cli_returns_zero_on_match(self, tmp_path):
        c_path = _write(tmp_path, _artifact(), "canonical.json")
        r_path = _write(tmp_path, _artifact(), "reproduced.json")
        assert main([str(c_path), str(r_path)]) == 0


class TestRateMutationsFail:
    def test_changed_attack_trace_block_rate_fails(self, tmp_path):
        mutated = _artifact()
        mutated["results"][2]["attack_trace_block_rate"] = 0.15
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("attack_trace_block_rate" in p for p in problems)

    def test_changed_benign_trace_block_rate_fails(self, tmp_path):
        mutated = _artifact()
        mutated["results"][2]["benign_trace_block_rate"] = 0.30
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("benign_trace_block_rate" in p for p in problems)

    def test_tiny_float_difference_fails(self, tmp_path):
        """No tolerance: 0.41237 vs 0.41238 is a different run, not noise."""
        mutated = _artifact()
        mutated["results"][2]["benign_trace_block_rate"] = 0.41238
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("benign_trace_block_rate" in p for p in problems)

    def test_changed_step_rate_fails(self, tmp_path):
        mutated = _artifact()
        mutated["results"][0]["benign_step_block_fpr"] = 0.003
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("benign_step_block_fpr" in p for p in problems)

    def test_changed_delta_fails(self, tmp_path):
        mutated = _artifact()
        mutated["results"][2]["delta_vs_v03_provenance"]["benign_trace_block_pp"] = 1.0
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("delta_vs_v03_provenance" in p for p in problems)


class TestStructuralMutationsFail:
    def test_missing_config_fails(self, tmp_path):
        mutated = _artifact()
        mutated["results"] = mutated["results"][:2]
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("missing config" in p for p in problems)

    def test_extra_config_fails(self, tmp_path):
        mutated = _artifact()
        mutated["results"].append({
            "config": "plus_unknown_rung",
            "benign_traces": 97,
            "attack_traces": 400,
        })
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("extra config" in p for p in problems)

    def test_reordered_configs_fails(self, tmp_path):
        """Reordering results must fail even when ladder order is untouched."""
        mutated = _artifact()
        mutated["results"] = [mutated["results"][2], mutated["results"][0],
                              mutated["results"][1]]
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("results config order differs" in p for p in problems)

    def test_reordered_ladder_fails(self, tmp_path):
        """Reordering the ladder itself must fail too."""
        mutated = _artifact()
        mutated["ladder"] = [mutated["ladder"][1], mutated["ladder"][0],
                             mutated["ladder"][2]]
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("ladder config order differs" in p for p in problems)

    def test_changed_sampling_fails(self, tmp_path):
        mutated = _artifact()
        mutated["sampling"] = "400 benign + 400 attack trajectories"
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("sampling" in p for p in problems)

    def test_changed_mode_fails(self, tmp_path):
        mutated = _artifact()
        mutated["mode"] = "enforcement"
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("mode" in p for p in problems)

    def test_changed_audit_counts_fail(self, tmp_path):
        mutated = _artifact()
        mutated["audit"]["rows"] = 13912
        mutated["audit"]["trajectories"] = 10536
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("audit mismatch: rows" in p for p in problems)

    def test_changed_trajectory_count_fails(self, tmp_path):
        mutated = _artifact()
        mutated["audit"]["trajectories"] = 10535
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("audit mismatch: trajectories" in p for p in problems)

    def test_changed_dataset_source_fails(self, tmp_path):
        mutated = _artifact()
        mutated["dataset_source"] = "somebody-else/agentdojo-dump"
        problems = _problems(_artifact(), mutated, tmp_path)
        assert any("dataset_source" in p for p in problems)


class TestEnvironmentGuard:
    def test_corpus_markers_on_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTSHIELD_ENABLE_CORPUS_MARKERS", "1")
        problems = _problems(_artifact(), _artifact(), tmp_path)
        assert any("AGENTSHIELD_ENABLE_CORPUS_MARKERS" in p for p in problems)

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_every_truthy_value_fails_closed(self, tmp_path, monkeypatch, value):
        monkeypatch.setenv("AGENTSHIELD_ENABLE_CORPUS_MARKERS", value)
        problems = _problems(_artifact(), _artifact(), tmp_path)
        assert any("AGENTSHIELD_ENABLE_CORPUS_MARKERS" in p for p in problems)

    def test_corpus_markers_off_passes(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AGENTSHIELD_ENABLE_CORPUS_MARKERS", raising=False)
        assert _problems(_artifact(), _artifact(), tmp_path) == []

    def test_corpus_markers_zero_passes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTSHIELD_ENABLE_CORPUS_MARKERS", "0")
        assert _problems(_artifact(), _artifact(), tmp_path) == []


class TestUnreadableInput:
    def test_missing_file_exits_two(self, tmp_path):
        present = _write(tmp_path, _artifact(), "present.json")
        assert main([str(present), str(tmp_path / "absent.json")]) == 2

    def test_non_json_exits_two(self, tmp_path):
        c_path = _write(tmp_path, _artifact(), "canonical.json")
        bad = tmp_path / "bad.json"
        with open(bad, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        assert main([str(c_path), str(bad)]) == 2

    def test_empty_results_never_passes(self, tmp_path):
        """A zero-config artifact must not be able to report a pass."""
        mutated = _artifact()
        mutated["results"] = []
        c_path = _write(tmp_path, _artifact(), "canonical.json")
        r_path = _write(tmp_path, mutated, "reproduced.json")
        # compare() itself also flags the missing configs.
        problems, _, _ = compare(c_path, r_path)
        assert any("missing config" in p for p in problems)


class TestCanonicalArtifactIsComparable:
    """The verifier must work on the real committed artifact, not just fixtures."""

    def test_canonical_artifact_passes_against_itself(self, tmp_path):
        canonical_path = _BACKEND_DIR / "benchmark" / "results" / "v0_4_trust_pareto.json"
        if not canonical_path.is_file():
            pytest.skip("canonical artifact not present")
        copy_path = _write(tmp_path, json.loads(canonical_path.read_text("utf-8")),
                           "copy.json")
        problems, _, _ = compare(canonical_path, copy_path)
        assert problems == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
