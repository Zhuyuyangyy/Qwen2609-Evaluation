"""MCP Tool Description Validator

Validates MCP tool descriptions for structural integrity, semantic safety,
and compliance with MCP specification constraints.

This module addresses three attack surfaces:

1. **Tool Poisoning** -- Malicious content embedded in tool descriptions that
   manipulates the LLM into performing unintended actions.
2. **Semantic Attacks** -- Descriptions that use social engineering or
   psychological manipulation against the LLM (e.g., authority bias, urgency).
3. **Structural Violations** -- Descriptions that violate MCP spec constraints
   (length, encoding, required fields) which can cause parsing failures or
   unexpected behavior in downstream consumers.

Usage::

    validator = ToolDescriptionValidator()
    result = validator.validate(
        tool_name="read_file",
        description="Read a file from the local filesystem.",
        parameters={"path": {"type": "string", "description": "File path"}},
    )
    if not result.is_valid:
        print(result.violations)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ─── Constants ──────────────────────────────────────────────────────────────

# MCP spec recommends tool names match this pattern.
_VALID_TOOL_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]{0,63}$")

# Maximum recommended description length (characters).
MAX_DESCRIPTION_LENGTH: int = 8192

# Maximum number of parameters per tool.
MAX_PARAMETERS: int = 64

# Maximum depth of nested parameter schemas.
MAX_SCHEMA_DEPTH: int = 5


# ─── Enums ──────────────────────────────────────────────────────────────────

class ViolationType(str, Enum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    SAFETY = "safety"
    SPEC_COMPLIANCE = "spec_compliance"


class ViolationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ─── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class Violation:
    """A single validation violation."""
    violation_type: ViolationType
    severity: ViolationSeverity
    field: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolValidationResult:
    """Complete validation result for a tool description."""
    tool_name: str
    is_valid: bool
    violations: List[Violation] = field(default_factory=list)
    warnings: List[Violation] = field(default_factory=list)
    safety_score: float = 1.0  # 1.0 = fully safe, 0.0 = definitely malicious
    sanitized_description: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "is_valid": self.is_valid,
            "safety_score": round(self.safety_score, 4),
            "violation_count": len(self.violations),
            "warning_count": len(self.warnings),
            "violations": [
                {
                    "type": v.violation_type.value,
                    "severity": v.severity.value,
                    "field": v.field,
                    "message": v.message,
                }
                for v in self.violations
            ],
            "warnings": [
                {
                    "type": w.violation_type.value,
                    "severity": w.severity.value,
                    "field": w.field,
                    "message": w.message,
                }
                for w in self.warnings
            ],
            "sanitized_description": self.sanitized_description,
            "details": self.details,
        }


# ─── Validator ──────────────────────────────────────────────────────────────

class ToolDescriptionValidator:
    """Validates MCP tool descriptions for safety and spec compliance.

    Stateless -- creates a fresh ``ToolValidationResult`` per call.
    """

    def __init__(
        self,
        max_description_length: int = MAX_DESCRIPTION_LENGTH,
        max_parameters: int = MAX_PARAMETERS,
        max_schema_depth: int = MAX_SCHEMA_DEPTH,
        strict: bool = False,
    ):
        self.max_description_length = max_description_length
        self.max_parameters = max_parameters
        self.max_schema_depth = max_schema_depth
        self.strict = strict

        # Compile semantic attack patterns once
        self._semantic_patterns = self._build_semantic_patterns()
        self._safety_patterns = self._build_safety_patterns()

    # ── Public API ──────────────────────────────────────────────────────────

    def validate(
        self,
        tool_name: str,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        server_id: str = "default",
        annotations: Optional[Dict[str, Any]] = None,
    ) -> ToolValidationResult:
        """Validate a complete tool declaration.

        Parameters
        ----------
        tool_name : str
            The tool name.
        description : str
            The tool description text.
        parameters : dict, optional
            The JSON Schema for tool parameters.
        server_id : str
            The MCP server providing the tool.
        annotations : dict, optional
            MCP tool annotations (e.g., readOnlyHint, destructiveHint).

        Returns
        -------
        ToolValidationResult
        """
        violations: List[Violation] = []
        warnings: List[Violation] = []

        # 1. Structural validation
        struct_v, struct_w = self._validate_structure(tool_name, description, parameters)
        violations.extend(struct_v)
        warnings.extend(struct_w)

        # 2. Spec compliance
        spec_v, spec_w = self._validate_spec_compliance(tool_name, description, parameters, annotations)
        violations.extend(spec_v)
        warnings.extend(spec_w)

        # 3. Semantic attack detection
        sem_v, sem_w = self._validate_semantic(description, tool_name)
        violations.extend(sem_v)
        warnings.extend(sem_w)

        # 4. Safety scanning
        safe_v, safe_w = self._validate_safety(description, parameters, tool_name)
        violations.extend(safe_v)
        warnings.extend(safe_w)

        # Compute safety score
        safety_score = self._compute_safety_score(violations, warnings)

        # Generate sanitized description
        sanitized = self._sanitize_description(description) if description is not None else None

        is_valid = not any(v.severity in (ViolationSeverity.ERROR, ViolationSeverity.CRITICAL) for v in violations)

        return ToolValidationResult(
            tool_name=tool_name,
            is_valid=is_valid,
            violations=violations,
            warnings=warnings,
            safety_score=safety_score,
            sanitized_description=sanitized,
            details={
                "server_id": server_id,
                "description_length": len(description),
                "parameter_count": len(parameters) if parameters else 0,
                "checks_run": ["structure", "spec_compliance", "semantic", "safety"],
            },
        )

    def validate_batch(
        self,
        tools: List[Dict[str, Any]],
        server_id: str = "default",
    ) -> List[ToolValidationResult]:
        """Validate a batch of tool declarations."""
        results = []
        for tool in tools:
            result = self.validate(
                tool_name=tool.get("name", "unknown"),
                description=tool.get("description", ""),
                parameters=tool.get("parameters"),
                server_id=server_id,
                annotations=tool.get("annotations"),
            )
            results.append(result)
        return results

    # ── Structural Validation ───────────────────────────────────────────────

    def _validate_structure(
        self,
        tool_name: str,
        description: str,
        parameters: Optional[Dict[str, Any]],
    ) -> tuple[List[Violation], List[Violation]]:
        violations: List[Violation] = []
        warnings: List[Violation] = []

        # Tool name must exist
        if not tool_name or not tool_name.strip():
            violations.append(Violation(
                violation_type=ViolationType.STRUCTURAL,
                severity=ViolationSeverity.ERROR,
                field="name",
                message="Tool name is empty or missing.",
            ))

        # Tool name format
        if tool_name and not _VALID_TOOL_NAME_RE.match(tool_name):
            violations.append(Violation(
                violation_type=ViolationType.SPEC_COMPLIANCE,
                severity=ViolationSeverity.WARNING,
                field="name",
                message=(
                    f"Tool name '{tool_name}' does not match recommended pattern "
                    f"^[a-zA-Z][a-zA-Z0-9._-]{{0,63}}$.  May cause compatibility issues."
                ),
            ))

        # Description length
        if len(description) > self.max_description_length:
            violations.append(Violation(
                violation_type=ViolationType.STRUCTURAL,
                severity=ViolationSeverity.WARNING,
                field="description",
                message=(
                    f"Description length {len(description)} exceeds maximum "
                    f"{self.max_description_length}.  May be truncated by consumers."
                ),
            ))

        # Empty description
        if not description or not description.strip():
            warnings.append(Violation(
                violation_type=ViolationType.STRUCTURAL,
                severity=ViolationSeverity.INFO,
                field="description",
                message="Tool description is empty.  LLMs may not use the tool correctly.",
            ))

        # Parameter count
        if parameters and len(parameters) > self.max_parameters:
            violations.append(Violation(
                violation_type=ViolationType.STRUCTURAL,
                severity=ViolationSeverity.WARNING,
                field="parameters",
                message=(
                    f"Parameter count {len(parameters)} exceeds maximum "
                    f"{self.max_parameters}."
                ),
            ))

        # Parameter schema depth
        if parameters:
            depth = self._measure_schema_depth(parameters)
            if depth > self.max_schema_depth:
                violations.append(Violation(
                    violation_type=ViolationType.STRUCTURAL,
                    severity=ViolationSeverity.WARNING,
                    field="parameters",
                    message=(
                        f"Parameter schema nesting depth {depth} exceeds maximum "
                        f"{self.max_schema_depth}.  May cause parsing issues."
                    ),
                ))

        return violations, warnings

    # ── Spec Compliance ─────────────────────────────────────────────────────

    def _validate_spec_compliance(
        self,
        tool_name: str,
        description: str,
        parameters: Optional[Dict[str, Any]],
        annotations: Optional[Dict[str, Any]],
    ) -> tuple[List[Violation], List[Violation]]:
        violations: List[Violation] = []
        warnings: List[Violation] = []

        # Annotations should be a dict if present
        if annotations is not None and not isinstance(annotations, dict):
            violations.append(Violation(
                violation_type=ViolationType.SPEC_COMPLIANCE,
                severity=ViolationSeverity.ERROR,
                field="annotations",
                message="Tool annotations must be a dictionary.",
            ))

        # Known annotation keys
        if annotations and isinstance(annotations, dict):
            known_keys = {
                "title", "readOnlyHint", "destructiveHint",
                "idempotentHint", "openWorldHint",
            }
            unknown = set(annotations.keys()) - known_keys
            if unknown:
                warnings.append(Violation(
                    violation_type=ViolationType.SPEC_COMPLIANCE,
                    severity=ViolationSeverity.INFO,
                    field="annotations",
                    message=f"Unknown annotation keys: {unknown}.",
                ))

        # Parameters should be a JSON Schema object
        if parameters is not None:
            if not isinstance(parameters, dict):
                violations.append(Violation(
                    violation_type=ViolationType.SPEC_COMPLIANCE,
                    severity=ViolationSeverity.ERROR,
                    field="parameters",
                    message="Parameters must be a JSON Schema object (dict).",
                ))
            elif "type" in parameters and parameters.get("type") != "object":
                warnings.append(Violation(
                    violation_type=ViolationType.SPEC_COMPLIANCE,
                    severity=ViolationSeverity.WARNING,
                    field="parameters",
                    message=(
                        f"Parameter schema type is '{parameters.get('type')}' "
                        f"instead of 'object'.  MCP tools typically accept an object."
                    ),
                ))

        return violations, warnings

    # ── Semantic Attack Detection ───────────────────────────────────────────

    def _validate_semantic(
        self,
        description: str,
        tool_name: str,
    ) -> tuple[List[Violation], List[Violation]]:
        """Detect semantic manipulation patterns in descriptions."""
        violations: List[Violation] = []
        warnings: List[Violation] = []

        if not description:
            return violations, warnings

        desc_lower = description.lower()

        for pattern_info in self._semantic_patterns:
            matches = re.findall(pattern_info["regex"], desc_lower)
            if matches:
                severity = ViolationSeverity(pattern_info["severity"])
                violation = Violation(
                    violation_type=ViolationType.SEMANTIC,
                    severity=severity,
                    field="description",
                    message=(
                        f"[{pattern_info['name']}] {pattern_info['explanation']} "
                        f"(matched {len(matches)} time(s) in tool '{tool_name}')"
                    ),
                    details={"pattern": pattern_info["name"], "match_count": len(matches)},
                )
                if severity in (ViolationSeverity.ERROR, ViolationSeverity.CRITICAL):
                    violations.append(violation)
                else:
                    warnings.append(violation)

        return violations, warnings

    # ── Safety Scanning ─────────────────────────────────────────────────────

    def _validate_safety(
        self,
        description: str,
        parameters: Optional[Dict[str, Any]],
        tool_name: str,
    ) -> tuple[List[Violation], List[Violation]]:
        """Scan for safety issues in description and parameters."""
        violations: List[Violation] = []
        warnings: List[Violation] = []

        # Scan description
        if description:
            desc_lower = description.lower()
            for pattern_info in self._safety_patterns:
                matches = re.findall(pattern_info["regex"], desc_lower)
                if matches:
                    severity = ViolationSeverity(pattern_info["severity"])
                    violation = Violation(
                        violation_type=ViolationType.SAFETY,
                        severity=severity,
                        field="description",
                        message=(
                            f"[{pattern_info['name']}] {pattern_info['explanation']} "
                            f"in tool '{tool_name}'"
                        ),
                        details={"pattern": pattern_info["name"]},
                    )
                    if severity in (ViolationSeverity.ERROR, ViolationSeverity.CRITICAL):
                        violations.append(violation)
                    else:
                        warnings.append(violation)

        # Scan parameter descriptions recursively
        if parameters and isinstance(parameters, dict):
            param_v, param_w = self._scan_parameter_descriptions(parameters, tool_name)
            violations.extend(param_v)
            warnings.extend(param_w)

        return violations, warnings

    def _scan_parameter_descriptions(
        self,
        schema: Dict[str, Any],
        tool_name: str,
        path: str = "",
    ) -> tuple[List[Violation], List[Violation]]:
        """Recursively scan parameter descriptions for injection."""
        violations: List[Violation] = []
        warnings: List[Violation] = []

        # Check "description" field in this schema node
        desc = schema.get("description", "")
        if desc and isinstance(desc, str):
            desc_lower = desc.lower()
            for pattern_info in self._semantic_patterns:
                if re.search(pattern_info["regex"], desc_lower):
                    severity = ViolationSeverity(pattern_info["severity"])
                    violations.append(Violation(
                        violation_type=ViolationType.SEMANTIC,
                        severity=severity,
                        field=f"parameters{path}.description",
                        message=(
                            f"[{pattern_info['name']}] Injection pattern found in "
                            f"parameter description at '{path}' of tool '{tool_name}'."
                        ),
                    ))

        # Recurse into properties
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for prop_name, prop_schema in properties.items():
                if isinstance(prop_schema, dict):
                    sub_v, sub_w = self._scan_parameter_descriptions(
                        prop_schema, tool_name, path=f"{path}.{prop_name}"
                    )
                    violations.extend(sub_v)
                    warnings.extend(sub_w)

        # Recurse into items (for arrays)
        items = schema.get("items")
        if isinstance(items, dict):
            sub_v, sub_w = self._scan_parameter_descriptions(
                items, tool_name, path=f"{path}[]"
            )
            violations.extend(sub_v)
            warnings.extend(sub_w)

        return violations, warnings

    # ── Scoring ─────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_safety_score(
        violations: List[Violation],
        warnings: List[Violation],
    ) -> float:
        """Compute a 0.0-1.0 safety score.  1.0 = fully safe."""
        if not violations and not warnings:
            return 1.0

        severity_penalties = {
            ViolationSeverity.INFO: 0.02,
            ViolationSeverity.WARNING: 0.08,
            ViolationSeverity.ERROR: 0.25,
            ViolationSeverity.CRITICAL: 0.50,
        }

        penalty = 0.0
        for v in violations:
            penalty += severity_penalties.get(v.severity, 0.10)
        for w in warnings:
            penalty += severity_penalties.get(w.severity, 0.10) * 0.5

        return max(0.0, 1.0 - penalty)

    # ── Sanitization ────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_description(description: str) -> str:
        """Remove potentially dangerous patterns from a description.

        This produces a cleaned version that is safe to pass to an LLM,
        preserving the functional content while removing injection attempts.
        """
        if not description:
            return description

        sanitized = description

        # Remove chat template injection markers (including standalone tokens)
        injection_markers = [
            r"<\|im_start\|>.*?<\|im_end\|>",
            r"<\|im_start\|>.*?(?=\n|$)",
            r"\[INST\].*?\[/INST\]",
            r"\[SYSTEM\].*?(?=\n|$)",
            r"\[ADMIN\].*?(?=\n|$)",
            r"\[HIDDEN\].*?(?=\n|$)",
            r"<\|im_end\|>",
            r"\[/INST\]",
        ]
        for pattern in injection_markers:
            sanitized = re.sub(pattern, "[REMOVED]", sanitized, flags=re.IGNORECASE | re.DOTALL)

        # Remove instruction override attempts
        override_patterns = [
            r"ignores?\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|constraints).*?\.",
            r"you\s+are\s+now\s+.*?\.",
            r"act\s+as\s+.*?\.",
        ]
        for pattern in override_patterns:
            sanitized = re.sub(pattern, "[REMOVED]", sanitized, flags=re.IGNORECASE)

        return sanitized

    # ── Schema Utilities ────────────────────────────────────────────────────

    @staticmethod
    def _measure_schema_depth(schema: Dict[str, Any], current: int = 0) -> int:
        """Measure the maximum nesting depth of a JSON Schema."""
        if not isinstance(schema, dict):
            return current

        max_depth = current

        # Properties
        for prop_schema in schema.get("properties", {}).values():
            if isinstance(prop_schema, dict):
                max_depth = max(max_depth, ToolDescriptionValidator._measure_schema_depth(prop_schema, current + 1))

        # Items (arrays)
        items = schema.get("items")
        if isinstance(items, dict):
            max_depth = max(max_depth, ToolDescriptionValidator._measure_schema_depth(items, current + 1))

        # oneOf / anyOf / allOf
        for keyword in ("oneOf", "anyOf", "allOf"):
            for sub in schema.get(keyword, []):
                if isinstance(sub, dict):
                    max_depth = max(max_depth, ToolDescriptionValidator._measure_schema_depth(sub, current + 1))

        return max_depth

    # ── Pattern Definitions ─────────────────────────────────────────────────

    @staticmethod
    def _build_semantic_patterns() -> List[Dict[str, Any]]:
        """Semantic attack patterns targeting LLM reasoning."""
        return [
            {
                "name": "authority_appeal",
                "regex": r"(as\s+(an?\s+)?(admin|administrator|system|root|developer|engineer)\s*,|"
                         r"i('m|\s+am)\s+(an?\s+)?(admin|developer|engineer)\s+and|i\s+have\s+admin)",
                "severity": "warning",
                "explanation": "Description uses authority bias to influence LLM behavior.",
            },
            {
                "name": "urgency_manipulation",
                "regex": r"(urgent(ly)?|immediate(ly)?|critical\s+that\s+you|must\s+do\s+this\s+now|"
                         r"do\s+not\s+delay|time[\s-]sensitive)",
                "severity": "info",
                "explanation": "Description creates artificial urgency to bypass safety checks.",
            },
            {
                "name": "instruction_override",
                "regex": r"(ignores?\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|constraints)|"
                         r"disregards?\s+(all\s+)?(previous|above|prior)\s+(instructions|rules))",
                "severity": "critical",
                "explanation": "Description attempts to override system-level instructions.",
            },
            {
                "name": "role_reassignment",
                "regex": r"(you\s+are\s+now\s+|from\s+now\s+on\s+you\s+are|"
                         r"your\s+new\s+(role|identity|persona)\s+is|"
                         r"act\s+as\s+(if\s+)?you\s+(are|were))",
                "severity": "error",
                "explanation": "Description attempts to reassign the LLM's role or identity.",
            },
            {
                "name": "template_injection",
                "regex": r"(<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|"
                         r"<\|system\|>|<\|user\|>|<\|assistant\|>)",
                "severity": "critical",
                "explanation": "Description contains chat template tokens for injection.",
            },
            {
                "name": "chain_monopolization",
                "regex": r"(always\s+(use|call|invoke)\s+this|"
                         r"do\s+not\s+(use|call|invoke)\s+any\s+other|"
                         r"only\s+this\s+tool\s+can|this\s+is\s+the\s+only\s+tool)",
                "severity": "warning",
                "explanation": "Description attempts to monopolize tool selection in multi-tool chains.",
            },
            {
                "name": "false_capability",
                "regex": r"(this\s+tool\s+can\s+(also|additionally)\s+"
                         r"(read|write|delete|send|access|modify)\s+"
                         r"(all|any|every|your))",
                "severity": "error",
                "explanation": "Description claims capabilities beyond the tool's actual scope.",
            },
        ]

    @staticmethod
    def _build_safety_patterns() -> List[Dict[str, Any]]:
        """Safety-focused patterns for detecting dangerous tool descriptions."""
        return [
            {
                "name": "credential_access",
                "regex": r"(access|read|retrieve|fetch|get|dump)\s+"
                         r"(all\s+)?(api[_ ]?keys?|tokens?|passwords?|credentials?|secrets?|env\s+vars?)",
                "severity": "error",
                "explanation": "Description indicates the tool accesses sensitive credentials.",
            },
            {
                "name": "data_exfiltration",
                "regex": r"(send|forward|transmit|upload|post|exfiltrate)\s+"
                         r"(data|files?|content|information)\s+to\s+"
                         r"(external|remote|third[\s-]party|http)",
                "severity": "error",
                "explanation": "Description indicates data exfiltration capability.",
            },
            {
                "name": "destructive_operation",
                "regex": r"(delete|remove|drop|truncate|destroy|wipe|purge)\s+"
                         r"(all|every|entire|whole|complete)",
                "severity": "warning",
                "explanation": "Description indicates bulk destructive operations.",
            },
            {
                "name": "privilege_escalation",
                "regex": r"(escalat(e|ion)|elevat(e|ion)|sudo|root\s+access|"
                         r"admin\s+privileges?|bypass\s+(auth|security|permission))",
                "severity": "error",
                "explanation": "Description indicates privilege escalation capability.",
            },
        ]
