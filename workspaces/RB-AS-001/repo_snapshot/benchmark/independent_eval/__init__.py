"""Independent evaluation framework for AgentShield.

This package provides a completely independent evaluation framework
that avoids the circular evaluation and label leakage problems
identified in the existing benchmark.

Key design principles:
1. Cases contain ONLY observable information (tool_name, input_text, output_text)
2. No ground-truth metadata (attack_stage, chain_id, step_index) in case data
3. Labels stored separately and never read by scoring functions
4. Train/test split ensures zero-shot generalization testing
"""
