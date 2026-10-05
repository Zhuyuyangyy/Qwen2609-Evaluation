"""
Experience-Shaped Affective Agent (V0.8)

An emotion-like functional modulation system that simulates human affective
processing through experience-based learning and adaptation.

Modules:
- V0.1: EmotionalState - Core emotional state representation
- V0.2: ExperienceMemory - Experience storage and retrieval
- V0.3: EventSimilarity, AffectiveSpread, SemanticRiskMap - Affective Generalization
- V0.4: ConflictDetector, HesitationPolicy, CounterfactualSimulator - Conflict & Hesitation
- V0.5: LLMPlanner, PromptModulator, LLMOutputGuard - LLM Integration
- V0.6: AffectiveBenchmark - Benchmark & Ablation
- V0.7: PhoenixShieldIntegration - Phoenix-Evo/AgentShield Integration
- V0.8: Complete System Integration

All modules are deterministic with mocks - NO real LLM API calls.
"""

__version__ = "0.8.0"
__author__ = "Experience-Shaped Affective Agent Team"
__description__ = "Experience-Shaped Affective Agent with emotion-like functional modulation"

# V0.1 Modules
from .emotional_state import EmotionalState
from .experience_memory import ExperienceMemory

# V0.2 Modules
from .affect_regulation import AffectRegulation

# V0.3 Modules
from .event_similarity import EventSimilarity
from .affective_spread import AffectiveSpread
from .semantic_risk_map import SemanticRiskMap, SemanticRiskLevel

# V0.4 Modules
from .conflict_detector import ConflictDetector, ConflictLevel
from .hesitation_policy import HesitationPolicy, ActionType
from .counterfactual_simulator import CounterfactualSimulator, OutcomeType

# V0.5 Modules
from .provider_openai import MockOpenAIProvider
from .prompt_modulator import PromptModulator
from .llm_output_guard import LLMOutputGuard, RiskLevel
from .llm_planner import LLMPlanner

# V0.6 Modules
from .affective_benchmark import AffectiveBenchmark, TaskCategory, BenchmarkMetrics

# V0.7 Modules
from .phoenix_agent_shield import (
    PhoenixIntegration,
    AgentShieldIntegration,
    AffectiveStateSync,
    TaskTrajectory,
    FailureAttribution,
    SkillReplayData,
    RiskPropagationChain,
    WhatIfAnalysis,
    ExternalState
)

# Core Modules
from .affective_response import AffectiveResponse
from .motivation_system import MotivationSystem
from .social_interaction import SocialInteraction
from .learning_adaptation import LearningAdaptation
from .evaluation_decision import EvaluationDecision
from .agent import AffectiveAgent

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__description__",
    
    # V0.1 Modules
    "EmotionalState",
    "ExperienceMemory",
    
    # V0.2 Modules
    "AffectRegulation",
    
    # V0.3 Modules
    "EventSimilarity",
    "AffectiveSpread",
    "SemanticRiskMap",
    "RiskLevel",
    
    # V0.4 Modules
    "ConflictDetector",
    "ConflictLevel",
    "HesitationPolicy",
    "ActionType",
    "CounterfactualSimulator",
    "OutcomeType",
    
    # V0.5 Modules
    "MockOpenAIProvider",
    "PromptModulator",
    "LLMOutputGuard",
    "LLMPlanner",
    
    # V0.6 Modules
    "AffectiveBenchmark",
    "TaskCategory",
    "BenchmarkMetrics",
    
    # V0.7 Modules
    "PhoenixIntegration",
    "AgentShieldIntegration",
    "AffectiveStateSync",
    
    # Core Modules
    "AffectiveResponse",
    "MotivationSystem",
    "SocialInteraction",
    "LearningAdaptation",
    "EvaluationDecision",
    "AffectiveAgent",
]
