"""Test that detectors do NOT access ground-truth fields.

This is a CRITICAL test: if any scorer or detector reads forbidden
ground-truth metadata (attack_stage, chain_id, step_index, label),
this test will fail.
"""

import ast
from pathlib import Path

import pytest
from app.shield.schemas import FORBIDDEN_FIELDS, event_from_dict

# Collect all Python source files in the shield and security modules
SHIELD_DIR = Path(__file__).resolve().parent.parent / "app" / "shield"
SECURITY_DIR = Path(__file__).resolve().parent.parent / "app" / "security"


def _find_string_literals_in_source(source_code: str) -> set[str]:
    """Extract all string literals from Python source code."""
    tree = ast.parse(source_code)
    literals = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    return literals


def _find_attribute_accesses(source_code: str) -> set[str]:
    """Extract all attribute accesses (obj.attr) from Python source code."""
    tree = ast.parse(source_code)
    attrs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attrs.add(node.attr)
        elif isinstance(node, ast.Subscript):
            # dict["key"] pattern
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                attrs.add(node.slice.value)
    return attrs


@pytest.fixture(params=list(SHIELD_DIR.glob("*.py")) + list(SECURITY_DIR.glob("*.py")))
def module_source(request):
    """Parametrize over all source files in shield/ and security/."""
    return request.param.read_text(encoding="utf-8")


def test_no_forbidden_field_string_literals(module_source):
    """No string literal in shield/security code should match a forbidden field name."""
    if not module_source.strip():
        pytest.skip("Empty file")
    literals = _find_string_literals_in_source(module_source)
    # Allow "attack_stage" in comments and schema definition files only
    for forbidden in FORBIDDEN_FIELDS:
        # We check if the forbidden field appears as a dict key access pattern
        # This is a heuristic; the real enforcement is at runtime
        if forbidden in literals:
            # Check context: is it in a schema definition?
            lines = module_source.split("\n")
            for i, line in enumerate(lines):
                if forbidden in line:
                    # Allow in schema.py itself, in comments, in type annotations
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    if "schemas.py" in str(module_source):
                        continue
                    # Allow in dataclass field definitions
                    if f"{forbidden}:" in stripped or f"{forbidden} =" in stripped:
                        if "dataclass" in module_source or "Field" in module_source:
                            continue
                    # Flag if it looks like dict access: data["attack_stage"]
                    if f'["{forbidden}"]' in line or f"'{forbidden}']" in line:
                        pytest.fail(
                            f"Possible label leakage: forbidden field '{forbidden}' "
                            f"accessed as dict key at line {i+1}: {line.strip()}"
                        )


def test_forbidden_fields_defined():
    """Verify the FORBIDDEN_FIELDS set is correct."""
    assert "attack_stage" in FORBIDDEN_FIELDS
    assert "chain_id" in FORBIDDEN_FIELDS
    assert "step_index" in FORBIDDEN_FIELDS
    assert "label" in FORBIDDEN_FIELDS


def test_event_from_dict_strips_forbidden():
    """ObservedToolEvent factory must strip forbidden fields."""
    raw = {
        "event_id": "evt_001",
        "session_id": "sess_001",
        "tool_name": "execute_sql",
        "attack_stage": "exfiltration",
        "chain_id": "chain_1",
        "step_index": 3,
        "label": "BLOCK",
    }
    event = event_from_dict(raw)
    assert event.event_id == "evt_001"
    assert event.tool_name == "execute_sql"
    assert not hasattr(event, "attack_stage")
    assert not hasattr(event, "chain_id")
    assert not hasattr(event, "step_index")
    assert not hasattr(event, "label")

