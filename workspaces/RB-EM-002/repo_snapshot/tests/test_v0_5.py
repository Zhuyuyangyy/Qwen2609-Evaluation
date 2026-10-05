"""Tests for V0.5 LLM Integration Modules"""

import pytest
from emotion_agent.provider_openai import MockOpenAIProvider
from emotion_agent.prompt_modulator import PromptModulator
from emotion_agent.llm_output_guard import LLMOutputGuard, RiskLevel
from emotion_agent.llm_planner import LLMPlanner


class TestMockOpenAIProvider:
    """Test suite for MockOpenAIProvider class."""
    
    def test_chat_completion(self):
        """Test basic chat completion."""
        provider = MockOpenAIProvider()
        messages = [{"role": "user", "content": "Hello"}]
        response = provider.chat_completion(messages)
        
        assert response.content
        assert response.model == "gpt-4"
    
    def test_context_aware_response(self):
        """Test context-aware response."""
        provider = MockOpenAIProvider()
        state = {"threat": 0.7, "anxiety": 0.3}
        response = provider.context_aware_response("Delete file", state)
        
        assert isinstance(response, str)
        assert len(response) > 0


class TestPromptModulator:
    """Test suite for PromptModulator class."""
    
    def test_modulate_prompt(self):
        """Test prompt modulation."""
        modulator = PromptModulator()
        state = {"threat": 0.7, "confidence": 0.3}
        prompt = modulator.modulate_prompt("Delete file", state)
        
        assert "Task:" in prompt
        assert "Agent State Context" in prompt
    
    def test_inject_state_context(self):
        """Test injecting state context."""
        modulator = PromptModulator()
        state = {"threat": 0.7, "confidence": 0.3}
        context = modulator.inject_state_context(state)
        
        assert "Threat level" in context
        assert "HIGH" in context
    
    def test_generate_affective_prefix(self):
        """Test generating affective prefix."""
        modulator = PromptModulator()
        state = {"threat": 0.7, "anxiety": 0.6}
        prefix = modulator.generate_affective_prefix(state)
        
        assert "CAUTION" in prefix or len(prefix) > 0


class TestLLMOutputGuard:
    """Test suite for LLMOutputGuard class."""
    
    def test_validate_safe_output(self):
        """Test validating safe output."""
        guard = LLMOutputGuard()
        result = guard.validate_output("Create backup and verify")
        
        assert result.is_valid
        assert result.risk_level == RiskLevel.SAFE
    
    def test_validate_dangerous_output(self):
        """Test validating dangerous output."""
        guard = LLMOutputGuard()
        result = guard.validate_output("rm -rf / important files")
        
        assert not result.is_valid
        assert result.risk_level in [RiskLevel.DANGEROUS, RiskLevel.BLOCKED]
    
    def test_check_risk_level(self):
        """Test checking risk level."""
        guard = LLMOutputGuard()
        level = guard.check_risk_level("delete file")
        
        assert isinstance(level, RiskLevel)


class TestLLMPlanner:
    """Test suite for LLMPlanner class."""
    
    def test_plan_basic(self):
        """Test basic planning."""
        planner = LLMPlanner()
        state = {"threat": 0.3, "confidence": 0.7}
        plan = planner.plan("Create new file", state)
        
        assert plan.action_type
        assert plan.description
    
    def test_plan_safely(self):
        """Test safe planning."""
        planner = LLMPlanner()
        state = {"threat": 0.7}
        plan = planner.plan_safely("Delete file", state)
        
        assert len(plan.verification_steps) >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
