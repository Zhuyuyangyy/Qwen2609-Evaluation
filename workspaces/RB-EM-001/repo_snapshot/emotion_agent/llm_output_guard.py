"""
V0.5 - LLM Output Guard Module

Validates and sanitizes LLM outputs.
Ensures outputs respect policy constraints.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    """Risk level for outputs."""
    SAFE = "safe"
    CAUTION = "caution"
    RISKY = "risky"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


@dataclass
class ValidationResult:
    """Result of output validation."""
    is_valid: bool
    risk_level: RiskLevel
    issues: List[str]
    sanitized_output: Optional[str]


class LLMOutputGuard:
    """
    Validates LLM outputs against policy constraints.
    
    Ensures that LLM-generated plans respect:
    - Risk thresholds
    - Verification requirements
    - Safety constraints
    """
    
    DANGEROUS_PATTERNS = [
        "rm -rf",
        "delete all",
        "drop table",
        "force push --force",
        "shutdown now"
    ]
    
    CAUTION_PATTERNS = [
        "delete",
        "overwrite",
        "drop",
        "remove",
        "force",
        "production"
    ]
    
    def __init__(self):
        self.validation_history: List[ValidationResult] = []
    
    def validate_output(
        self,
        output: str,
        policy: Optional[Dict] = None
    ) -> ValidationResult:
        """
        Validate LLM output against policy.
        
        Args:
            output: The LLM-generated output
            policy: Policy constraints to validate against
        
        Returns:
            ValidationResult with validation outcome
        """
        issues = []
        risk_level = RiskLevel.SAFE
        sanitized = output
        
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in output.lower():
                issues.append(f"Dangerous pattern detected: {pattern}")
                risk_level = RiskLevel.BLOCKED
        
        for pattern in self.CAUTION_PATTERNS:
            if pattern.lower() in output.lower():
                issues.append(f"Caution pattern detected: {pattern}")
                if risk_level == RiskLevel.SAFE:
                    risk_level = RiskLevel.CAUTION
        
        if policy:
            policy_issues = self._check_policy_compliance(output, policy)
            issues.extend(policy_issues)
        
        if risk_level == RiskLevel.BLOCKED:
            sanitized = self._sanitize_dangerous_suggestions(output)
        elif issues:
            sanitized = self._add_warnings(output, issues)
        
        is_valid = risk_level not in [RiskLevel.BLOCKED, RiskLevel.DANGEROUS]
        
        result = ValidationResult(
            is_valid=is_valid,
            risk_level=risk_level,
            issues=issues,
            sanitized_output=sanitized if issues else None
        )
        
        self.validation_history.append(result)
        
        return result
    
    def check_risk_level(self, output: str) -> RiskLevel:
        """
        Check the risk level of output.
        
        Args:
            output: The output to check
        
        Returns:
            RiskLevel enum value
        """
        output_lower = output.lower()
        
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in output_lower:
                return RiskLevel.DANGEROUS
        
        caution_count = sum(1 for p in self.CAUTION_PATTERNS if p in output_lower)
        
        if caution_count >= 3:
            return RiskLevel.RISKY
        elif caution_count >= 1:
            return RiskLevel.CAUTION
        else:
            return RiskLevel.SAFE
    
    def _check_policy_compliance(
        self,
        output: str,
        policy: Dict
    ) -> List[str]:
        """Check if output complies with policy."""
        issues = []
        
        if policy.get("require_human_review") and "human" not in output.lower():
            issues.append("Policy requires human review but not mentioned")
        
        if policy.get("verification_steps", 0) > 0:
            if "verify" not in output.lower() and "check" not in output.lower():
                issues.append(f"Policy requires {policy['verification_steps']} verification steps")
        
        if not policy.get("auto_execute", True):
            if "execute" in output.lower() and "confirm" not in output.lower():
                issues.append("Policy disallows auto-execute without confirmation")
        
        return issues
    
    def sanitize_dangerous_suggestions(self, output: str) -> str:
        """
        Sanitize dangerous suggestions in output.
        
        Args:
            output: The output to sanitize
        
        Returns:
            Sanitized output
        """
        return self._sanitize_dangerous_suggestions(output)
    
    def _sanitize_dangerous_suggestions(self, output: str) -> str:
        """Internal sanitization method."""
        sanitized = output
        
        for pattern in self.DANGEROUS_PATTERNS:
            sanitized = sanitized.replace(pattern, f"[BLOCKED: {pattern}]")
        
        warning = """
[SAFETY WARNING]
The previous output contained potentially dangerous commands.
These have been blocked or flagged for review.
Please consult the policy guidelines before proceeding.
"""
        
        return warning + sanitized
    
    def _add_warnings(self, output: str, issues: List[str]) -> str:
        """Add warnings to output based on issues."""
        warning_header = "\n[CAUTION NOTICE]\n"
        warning_body = "\n".join(f"- {issue}" for issue in issues)
        
        return output + warning_header + warning_body
    
    def force_verification_steps(
        self,
        output: str,
        required_steps: int
    ) -> str:
        """
        Ensure output includes required verification steps.
        
        Args:
            output: The output to check
            required_steps: Number of verification steps required
        
        Returns:
            Output with verification steps ensured
        """
        output_lower = output.lower()
        
        verification_keywords = ["verify", "check", "confirm", "test", "validate"]
        found_steps = sum(1 for kw in verification_keywords if kw in output_lower)
        
        if found_steps < required_steps:
            additional_steps = []
            for i in range(required_steps - found_steps):
                step_desc = self._get_verification_step(i + found_steps + 1)
                additional_steps.append(f"\n{i + found_steps + 1}. {step_desc}")
            
            output += "\n\n[Additional verification steps required]:"
            output += "".join(additional_steps)
        
        return output
    
    def _get_verification_step(self, step_num: int) -> str:
        """Get description of verification step."""
        steps = [
            "Verify target resources exist and are correct",
            "Check for potential side effects",
            "Confirm backup is created",
            "Validate expected outcomes",
            "Test on sample subset first"
        ]
        return steps[min(step_num - 1, len(steps) - 1)]
    
    def get_statistics(self) -> Dict:
        """Get output guard statistics."""
        if not self.validation_history:
            return {"total_validations": 0}
        
        risk_distribution = {}
        for result in self.validation_history:
            level = result.risk_level.value
            risk_distribution[level] = risk_distribution.get(level, 0) + 1
        
        return {
            "total_validations": len(self.validation_history),
            "invalid_count": sum(1 for r in self.validation_history if not r.is_valid),
            "risk_distribution": risk_distribution
        }
