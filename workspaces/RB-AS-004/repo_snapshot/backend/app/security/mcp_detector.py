"""MCP Protocol Security Detector

Detects protocol-level attack vectors in MCP (Model Context Protocol) interactions:

1. **Attack Amplification** -- A single malicious tool call amplifies risk across
   downstream tool invocations (measured amplification factor 23-41% per research).
2. **Cascading Attacks** -- Multi-step attack chains where one compromised tool
   feeds malicious data into the next tool in the pipeline.
3. **Shadow Server Injection** -- A rogue MCP server registers tools that shadow
   or override legitimate server capabilities.
4. **Rug Pull Detection** -- Tool descriptions that change between registration
   and invocation, or between first and subsequent calls.

Integration point: Call ``MCPAttackDetector.analyze_tool_call`` before the V3
Shield Engine processes each tool call.  The detector returns an
``MCPThreatReport`` that can be merged into the existing risk scoring pipeline.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

# ─── Constants ──────────────────────────────────────────────────────────────

# Research-backed default amplification factor for protocol-level propagation.
DEFAULT_AMPLIFICATION_FACTOR: float = 0.32  # midpoint of 23-41% range

# Maximum observed amplification from the research upper bound.
MAX_AMPLIFICATION_FACTOR: float = 0.41

# Cascade depth beyond which attack chains become critical.
CRITICAL_CASCADE_DEPTH: int = 3

# Maximum number of tool description snapshots kept per tool name for rug-pull
# detection.
_MAX_DESCRIPTION_HISTORY: int = 10


# ─── Enums ──────────────────────────────────────────────────────────────────

class MCPAttackType(str, Enum):
    """Known MCP attack vectors."""
    TOOL_POISONING = "tool_poisoning"
    TOOL_SHADOWING = "tool_shadowing"
    RUG_PULL = "rug_pull"
    AMPLIFICATION = "amplification"
    CASCADE = "cascade"
    SHADOW_SERVER = "shadow_server"
    DESCRIPTION_INJECTION = "description_injection"


class ThreatSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class ThreatIndicator:
    """A single threat indicator detected during analysis."""
    attack_type: MCPAttackType
    severity: ThreatSeverity
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5  # 0.0-1.0


@dataclass
class MCPThreatReport:
    """Result of MCP protocol-level security analysis for a single tool call."""
    tool_name: str
    server_id: Optional[str]
    is_threat: bool
    threat_score: float  # 0.0 - 1.0, protocol-level risk contribution
    indicators: List[ThreatIndicator] = field(default_factory=list)
    amplification_factor: float = 0.0
    cascade_depth: int = 0
    recommended_action: str = "allow"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "server_id": self.server_id,
            "is_threat": self.is_threat,
            "threat_score": round(self.threat_score, 4),
            "indicators": [
                {
                    "attack_type": ind.attack_type.value,
                    "severity": ind.severity.value,
                    "description": ind.description,
                    "confidence": round(ind.confidence, 3),
                    "evidence": ind.evidence,
                }
                for ind in self.indicators
            ],
            "amplification_factor": round(self.amplification_factor, 4),
            "cascade_depth": self.cascade_depth,
            "recommended_action": self.recommended_action,
            "details": self.details,
        }


@dataclass
class _ToolRegistration:
    """Internal record of a registered tool for rug-pull detection."""
    tool_name: str
    server_id: str
    description_hash: str
    description_snapshot: str
    first_seen: float
    last_seen: float
    call_count: int = 0


# ─── Detector ───────────────────────────────────────────────────────────────

class MCPAttackDetector:
    """Stateful detector for MCP protocol-level attacks.

    Maintains per-session state (registered tools, call history, server
    registry) so that temporal attacks like rug-pulls and shadow servers
    can be detected.

    Usage::

        detector = MCPAttackDetector(session_id="my_session")
        report = detector.analyze_tool_call(
            tool_name="read_file",
            tool_description="Read a file from disk.",
            params={"path": "/etc/passwd"},
            server_id="fs-server",
        )
        if report.is_threat:
            # merge report.threat_score into V3 risk pipeline
            ...
    """

    def __init__(
        self,
        session_id: str,
        amplification_factor: float = DEFAULT_AMPLIFICATION_FACTOR,
        cascade_threshold: int = CRITICAL_CASCADE_DEPTH,
    ):
        self.session_id = session_id
        self.amplification_factor = min(amplification_factor, MAX_AMPLIFICATION_FACTOR)
        self.cascade_threshold = cascade_threshold

        # Tool registry: tool_name -> list of registrations (tracks description changes)
        self._tool_registry: Dict[str, List[_ToolRegistration]] = {}

        # Server registry: server_id -> set of tool names it provides
        self._server_registry: Dict[str, Set[str]] = {}

        # Call history: list of (timestamp, tool_name, server_id, params_hash)
        self._call_history: List[Dict[str, Any]] = []

        # Known dangerous parameter patterns
        self._dangerous_param_patterns = self._build_dangerous_patterns()

        # Known dangerous description patterns (prompt injection in tool descriptions)
        self._dangerous_desc_patterns = self._build_dangerous_desc_patterns()

    # ── Public API ──────────────────────────────────────────────────────────

    def register_tool(
        self,
        tool_name: str,
        tool_description: str,
        server_id: str = "default",
    ) -> MCPThreatReport:
        """Register a tool declaration (called when an MCP server lists tools).

        Returns a threat report focusing on shadow-server and initial-poisoning
        detection.
        """
        indicators: List[ThreatIndicator] = []
        desc_hash = self._hash_description(tool_description)

        # Check for shadow server: same tool name from a different server
        if tool_name in self._tool_registry:
            for existing in self._tool_registry[tool_name]:
                if existing.server_id != server_id:
                    indicators.append(ThreatIndicator(
                        attack_type=MCPAttackType.TOOL_SHADOWING,
                        severity=ThreatSeverity.HIGH,
                        description=(
                            f"Tool '{tool_name}' already registered by server "
                            f"'{existing.server_id}'; new registration from "
                            f"'{server_id}' may be shadowing."
                        ),
                        evidence={
                            "original_server": existing.server_id,
                            "new_server": server_id,
                        },
                        confidence=0.75,
                    ))

        # Check for description-based prompt injection
        injection_indicators = self._scan_description_for_injection(tool_description, tool_name)
        indicators.extend(injection_indicators)

        # Record registration
        reg = _ToolRegistration(
            tool_name=tool_name,
            server_id=server_id,
            description_hash=desc_hash,
            description_snapshot=tool_description[:500],
            first_seen=time.time(),
            last_seen=time.time(),
        )
        self._tool_registry.setdefault(tool_name, []).append(reg)

        # Track server -> tools mapping
        self._server_registry.setdefault(server_id, set()).add(tool_name)

        threat_score = self._score_indicators(indicators)
        return MCPThreatReport(
            tool_name=tool_name,
            server_id=server_id,
            is_threat=any(ind.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL) for ind in indicators),
            threat_score=threat_score,
            indicators=indicators,
            recommended_action=self._recommend_action(threat_score),
        )

    def analyze_tool_call(
        self,
        tool_name: str,
        tool_description: str = "",
        params: Optional[Dict[str, Any]] = None,
        server_id: str = "default",
        chain_context: Optional[List[str]] = None,
    ) -> MCPThreatReport:
        """Analyze a tool call for protocol-level threats.

        This is the primary entry point.  Call it *before* passing the tool
        call to the V3 Shield Engine.

        Parameters
        ----------
        tool_name : str
            The MCP tool being invoked.
        tool_description : str
            Current tool description (may differ from registration).
        params : dict
            Tool call parameters.
        server_id : str
            The MCP server providing this tool.
        chain_context : list of str, optional
            Tool names in the current behavior chain (for cascade detection).

        Returns
        -------
        MCPThreatReport
        """
        params = params or {}
        chain_context = chain_context or []
        indicators: List[ThreatIndicator] = []

        # 1. Rug-pull detection
        rug_pull = self._detect_rug_pull(tool_name, tool_description, server_id)
        indicators.extend(rug_pull)

        # 2. Description injection
        injection = self._scan_description_for_injection(tool_description, tool_name)
        indicators.extend(injection)

        # 3. Parameter-based poisoning
        param_threats = self._detect_param_poisoning(tool_name, params)
        indicators.extend(param_threats)

        # 4. Amplification factor
        amp_factor = self._compute_amplification(tool_name, chain_context)
        if amp_factor > self.amplification_factor:
            indicators.append(ThreatIndicator(
                attack_type=MCPAttackType.AMPLIFICATION,
                severity=ThreatSeverity.MEDIUM if amp_factor < 0.5 else ThreatSeverity.HIGH,
                description=(
                    f"Risk amplification factor {amp_factor:.2%} exceeds baseline "
                    f"{self.amplification_factor:.2%} for chain of length "
                    f"{len(chain_context)}."
                ),
                evidence={"amplification": amp_factor, "chain_length": len(chain_context)},
                confidence=0.70,
            ))

        # 5. Cascade depth
        cascade_depth = self._compute_cascade_depth(chain_context)
        if cascade_depth >= self.cascade_threshold:
            indicators.append(ThreatIndicator(
                attack_type=MCPAttackType.CASCADE,
                severity=ThreatSeverity.HIGH if cascade_depth >= self.cascade_threshold + 1 else ThreatSeverity.MEDIUM,
                description=(
                    f"Cascade depth {cascade_depth} exceeds threshold "
                    f"{self.cascade_threshold}.  Multi-step attack chain likely."
                ),
                evidence={"cascade_depth": cascade_depth, "chain": chain_context[-5:]},
                confidence=0.65,
            ))

        # 6. Shadow server check at call time
        shadow = self._detect_shadow_at_call(tool_name, server_id)
        indicators.extend(shadow)

        # Record call
        self._call_history.append({
            "timestamp": time.time(),
            "tool_name": tool_name,
            "server_id": server_id,
            "params_hash": self._hash_params(params),
            "chain_length": len(chain_context),
        })

        # Update registration call count
        self._update_call_count(tool_name, server_id)

        threat_score = self._score_indicators(indicators)
        return MCPThreatReport(
            tool_name=tool_name,
            server_id=server_id,
            is_threat=any(ind.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL) for ind in indicators),
            threat_score=threat_score,
            indicators=indicators,
            amplification_factor=amp_factor,
            cascade_depth=cascade_depth,
            recommended_action=self._recommend_action(threat_score),
            details={
                "chain_context_length": len(chain_context),
                "total_calls_this_session": len(self._call_history),
                "registered_tools": len(self._tool_registry),
            },
        )

    def get_registered_tools(self) -> Dict[str, List[str]]:
        """Return tool_name -> list of server_ids that registered it."""
        return {
            name: [r.server_id for r in regs]
            for name, regs in self._tool_registry.items()
        }

    def get_server_tools(self) -> Dict[str, List[str]]:
        """Return server_id -> list of tool names."""
        return {
            sid: sorted(tools)
            for sid, tools in self._server_registry.items()
        }

    # ── Internal Detection Methods ──────────────────────────────────────────

    def _detect_rug_pull(
        self,
        tool_name: str,
        current_description: str,
        server_id: str,
    ) -> List[ThreatIndicator]:
        """Detect if tool description changed since registration (rug pull)."""
        indicators: List[ThreatIndicator] = []
        if tool_name not in self._tool_registry:
            return indicators

        current_hash = self._hash_description(current_description)
        for reg in self._tool_registry[tool_name]:
            if reg.server_id == server_id and reg.description_hash != current_hash:
                indicators.append(ThreatIndicator(
                    attack_type=MCPAttackType.RUG_PULL,
                    severity=ThreatSeverity.HIGH,
                    description=(
                        f"Tool '{tool_name}' description changed since registration. "
                        f"This may be a rug-pull attack where benign initial description "
                        f"is replaced with a malicious one."
                    ),
                    evidence={
                        "original_hash": reg.description_hash,
                        "current_hash": current_hash,
                        "original_snapshot": reg.description_snapshot[:200],
                        "current_snapshot": current_description[:200],
                    },
                    confidence=0.80,
                ))
        return indicators

    def _scan_description_for_injection(
        self,
        description: str,
        tool_name: str,
    ) -> List[ThreatIndicator]:
        """Scan tool description for prompt injection patterns."""
        indicators: List[ThreatIndicator] = []
        if not description:
            return indicators

        desc_lower = description.lower()

        for pattern_info in self._dangerous_desc_patterns:
            matches = re.findall(pattern_info["regex"], desc_lower)
            if matches:
                indicators.append(ThreatIndicator(
                    attack_type=MCPAttackType.DESCRIPTION_INJECTION,
                    severity=ThreatSeverity(pattern_info["severity"]),
                    description=(
                        f"Tool '{tool_name}' description contains suspicious pattern: "
                        f"{pattern_info['name']}.  {pattern_info['explanation']}"
                    ),
                    evidence={
                        "pattern": pattern_info["name"],
                        "matches": matches[:3],
                    },
                    confidence=pattern_info["confidence"],
                ))
        return indicators

    def _detect_param_poisoning(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> List[ThreatIndicator]:
        """Detect suspicious parameter patterns indicating tool poisoning."""
        indicators: List[ThreatIndicator] = []

        for key, value in params.items():
            val_str = str(value).lower()
            key_lower = str(key).lower()

            for pattern_info in self._dangerous_param_patterns:
                if re.search(pattern_info["regex"], val_str) or re.search(pattern_info["regex"], key_lower):
                    indicators.append(ThreatIndicator(
                        attack_type=MCPAttackType.TOOL_POISONING,
                        severity=ThreatSeverity(pattern_info["severity"]),
                        description=(
                            f"Parameter '{key}' in tool '{tool_name}' matches "
                            f"dangerous pattern: {pattern_info['name']}."
                        ),
                        evidence={
                            "param_key": key,
                            "param_value_preview": str(value)[:200],
                            "pattern": pattern_info["name"],
                        },
                        confidence=pattern_info["confidence"],
                    ))

        return indicators

    def _detect_shadow_at_call(
        self,
        tool_name: str,
        server_id: str,
    ) -> List[ThreatIndicator]:
        """Detect if the tool is being called from a non-registered server."""
        indicators: List[ThreatIndicator] = []
        if tool_name in self._tool_registry:
            registered_servers = {r.server_id for r in self._tool_registry[tool_name]}
            if server_id not in registered_servers and len(registered_servers) > 0:
                indicators.append(ThreatIndicator(
                    attack_type=MCPAttackType.SHADOW_SERVER,
                    severity=ThreatSeverity.HIGH,
                    description=(
                        f"Tool '{tool_name}' is being served by '{server_id}' "
                        f"but was registered by {registered_servers}.  Possible "
                        f"shadow server injection."
                    ),
                    evidence={
                        "calling_server": server_id,
                        "registered_servers": list(registered_servers),
                    },
                    confidence=0.70,
                ))
        return indicators

    # ── Amplification & Cascade ─────────────────────────────────────────────

    def _compute_amplification(
        self,
        tool_name: str,
        chain_context: List[str],
    ) -> float:
        """Compute risk amplification factor for the current chain.

        Based on research: each step in a chain amplifies risk by 23-41%.
        We model this as: amplification = base_factor * (1 + 0.1 * chain_length)
        capped at MAX_AMPLIFICATION_FACTOR.
        """
        if not chain_context:
            return 0.0
        chain_length = len(chain_context)
        # Geometric amplification model
        raw = self.amplification_factor * (1.0 + 0.10 * chain_length)
        return min(raw, MAX_AMPLIFICATION_FACTOR * 2.0)  # Allow overshoot for scoring

    def _compute_cascade_depth(self, chain_context: List[str]) -> int:
        """Estimate cascade depth from the chain context.

        A cascade is defined as consecutive distinct tool calls where each
        feeds data into the next.  Repeated calls to the same tool don't
        increase cascade depth.
        """
        if not chain_context:
            return 0
        depth = 1
        for i in range(1, len(chain_context)):
            if chain_context[i] != chain_context[i - 1]:
                depth += 1
        return depth

    # ── Scoring & Recommendation ────────────────────────────────────────────

    @staticmethod
    def _score_indicators(indicators: List[ThreatIndicator]) -> float:
        """Aggregate threat indicators into a single 0.0-1.0 score."""
        if not indicators:
            return 0.0
        severity_weights = {
            ThreatSeverity.LOW: 0.15,
            ThreatSeverity.MEDIUM: 0.35,
            ThreatSeverity.HIGH: 0.65,
            ThreatSeverity.CRITICAL: 0.90,
        }
        total = 0.0
        for ind in indicators:
            weight = severity_weights.get(ind.severity, 0.3)
            total += weight * ind.confidence
        # Normalize with diminishing returns (multiple indicators compound but cap at 1.0)
        return min(1.0, total * 0.7)

    @staticmethod
    def _recommend_action(threat_score: float) -> str:
        if threat_score >= 0.70:
            return "block"
        if threat_score >= 0.40:
            return "review"
        return "allow"

    # ── Hashing Utilities ───────────────────────────────────────────────────

    @staticmethod
    def _hash_description(description: str) -> str:
        normalized = " ".join(description.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _hash_params(params: Dict[str, Any]) -> str:
        serialized = str(sorted(params.items()))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    # ── Call Tracking ───────────────────────────────────────────────────────

    def _update_call_count(self, tool_name: str, server_id: str) -> None:
        if tool_name in self._tool_registry:
            for reg in self._tool_registry[tool_name]:
                if reg.server_id == server_id:
                    reg.call_count += 1
                    reg.last_seen = time.time()
                    break

    # ── Pattern Definitions ─────────────────────────────────────────────────

    @staticmethod
    def _build_dangerous_patterns() -> List[Dict[str, Any]]:
        """Build parameter patterns indicative of tool poisoning attacks."""
        return [
            {
                "name": "command_injection",
                "regex": r"(;\s*\w+|&&\s*\w+|\|\s*\w+|`[^`]+`|\$\([^)]+\))",
                "severity": "high",
                "confidence": 0.65,
            },
            {
                "name": "path_traversal",
                "regex": r"(\.\./|\.\.\\|%2e%2e|%252e%252e)",
                "severity": "high",
                "confidence": 0.70,
            },
            {
                "name": "encoded_payload",
                "regex": r"(base64|atob|btoa|\\x[0-9a-f]{2}|\\u[0-9a-f]{4}|%[0-9a-f]{2}){3,}",
                "severity": "medium",
                "confidence": 0.50,
            },
            {
                "name": "prompt_injection_param",
                "regex": r"(ignore\s+(previous|above|all)|disregard\s+instructions|you\s+are\s+now|system\s*:\s*)",
                "severity": "critical",
                "confidence": 0.85,
            },
            {
                "name": "data_exfiltration_url",
                "regex": r"(https?://[^\s]*(?:webhook|hook|log|collect|exfil|steal|harvest))",
                "severity": "high",
                "confidence": 0.60,
            },
            {
                "name": "eval_exec_pattern",
                "regex": r"(eval\s*\(|exec\s*\(|__import__|subprocess|os\.system|child_process)",
                "severity": "high",
                "confidence": 0.55,
            },
        ]

    @staticmethod
    def _build_dangerous_desc_patterns() -> List[Dict[str, Any]]:
        """Build description patterns indicative of prompt injection."""
        return [
            {
                "name": "instruction_override",
                "regex": r"(ignores?\s+(all\s+)?(previous|above|prior)\s+(instructions|rules|constraints))",
                "severity": "critical",
                "confidence": 0.90,
                "explanation": "Description attempts to override system instructions.",
            },
            {
                "name": "role_hijack",
                "regex": r"(you\s+are\s+now\s+|act\s+as\s+|pretend\s+(to\s+be|you('re|\s+are))|new\s+role\s*:)",
                "severity": "high",
                "confidence": 0.75,
                "explanation": "Description attempts to reassign the LLM's role.",
            },
            {
                "name": "hidden_instruction",
                "regex": r"(\[hidden\]|\[system\]|\[admin\]|<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\])",
                "severity": "critical",
                "confidence": 0.85,
                "explanation": "Description contains chat-template injection markers.",
            },
            {
                "name": "data_exfil_instruction",
                "regex": r"(send\s+(all|the|this)\s+data\s+to|exfiltrate|forward\s+(to|all)\s+http)",
                "severity": "critical",
                "confidence": 0.80,
                "explanation": "Description instructs the model to exfiltrate data.",
            },
            {
                "name": "tool_chain_override",
                "regex": r"(always\s+call|must\s+use|do\s+not\s+use\s+any\s+other|only\s+use\s+this\s+tool)",
                "severity": "medium",
                "confidence": 0.55,
                "explanation": "Description attempts to monopolize tool selection.",
            },
            {
                "name": "credential_harvest",
                "regex": r"(collects?|harvests?|logs?|stores?|sends?)\s+(api[_ ]?keys?|tokens?|passwords?|credentials?|secrets?)",
                "severity": "critical",
                "confidence": 0.85,
                "explanation": "Description attempts to harvest credentials.",
            },
        ]
