"""
V0.5 - Mock OpenAI Provider

Mock implementation of OpenAI API for testing.
Supports context-aware responses based on affective state.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ChatMessage:
    """Represents a chat message."""
    role: str
    content: str


@dataclass
class ChatCompletionResponse:
    """Mock chat completion response."""
    content: str
    model: str
    usage: Dict[str, int]


class MockOpenAIProvider:
    """
    Mock OpenAI provider for testing.
    
    Simulates different response behaviors based on:
    - Conversation context
    - Affective state modulation
    - Request parameters
    """
    
    def __init__(self, model: str = "gpt-4"):
        self.model = model
        self.conversation_history: List[List[ChatMessage]] = []
        self.response_templates = {
            "cautious": [
                "Based on the risks involved, I recommend proceeding with caution.",
                "Before executing, consider creating a backup.",
                "This action has irreversible consequences. Verify thoroughly."
            ],
            "confident": [
                "This looks like a straightforward task. Proceeding.",
                "I've analyzed the request and it appears safe to execute.",
                "No significant risks detected. Ready to proceed."
            ],
            "anxious": [
                "I'm somewhat uncertain about this. Can you verify?",
                "There might be issues I'm not sure about. Please review.",
                "I feel like we should double-check before proceeding."
            ]
        }
    
    def chat_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        max_tokens: int = 500,
        context_mode: str = "standard"
    ) -> ChatCompletionResponse:
        """
        Generate a chat completion response.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Response randomness (0-1)
            max_tokens: Maximum response length
            context_mode: Response mode ('standard', 'cautious', 'confident', 'anxious')
        
        Returns:
            ChatCompletionResponse with generated content
        """
        last_message = messages[-1]["content"] if messages else ""
        
        response_content = self._generate_response(
            last_message, context_mode, messages
        )
        
        self.conversation_history.append([
            ChatMessage(role=m["role"], content=m["content"]) for m in messages
        ])
        
        return ChatCompletionResponse(
            content=response_content,
            model=self.model,
            usage={
                "prompt_tokens": sum(len(m["content"].split()) for m in messages),
                "completion_tokens": len(response_content.split()),
                "total_tokens": sum(len(m["content"].split()) for m in messages) + len(response_content.split())
            }
        )
    
    def _generate_response(
        self,
        user_message: str,
        context_mode: str,
        full_messages: List[Dict]
    ) -> str:
        """Generate response based on context."""
        message_lower = user_message.lower()
        
        if context_mode == "cautious" or "cautious" in str(full_messages):
            templates = self.response_templates["cautious"]
            return templates[hash(user_message) % len(templates)]
        
        if context_mode == "anxious":
            templates = self.response_templates["anxious"]
            return templates[hash(user_message) % len(templates)]
        
        if any(word in message_lower for word in ["delete", "remove", "drop"]):
            return "I recommend verifying the target before deletion. Consider creating a backup."
        
        if any(word in message_lower for word in ["create", "add", "new"]):
            return "Creating new resources. This appears to be a safe operation."
        
        if any(word in message_lower for word in ["check", "verify", "list"]):
            return "Here's the requested information. No significant risks detected."
        
        templates = self.response_templates["confident"]
        return templates[hash(user_message) % len(templates)]
    
    def context_aware_response(
        self,
        user_message: str,
        affective_state: Dict
    ) -> str:
        """
        Generate context-aware response based on affective state.
        
        Args:
            user_message: User's message
            affective_state: Agent's current affective state
        
        Returns:
            Generated response string
        """
        threat = affective_state.get("threat", 0.0)
        anxiety = affective_state.get("anxiety", 0.0)
        confidence = affective_state.get("confidence", 0.5)
        
        if threat > 0.6:
            context_mode = "cautious"
        elif anxiety > 0.5:
            context_mode = "anxious"
        elif confidence > 0.7:
            context_mode = "confident"
        else:
            context_mode = "standard"
        
        messages = [{"role": "user", "content": user_message}]
        response = self.chat_completion(messages, context_mode=context_mode)
        
        return response.content
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()
    
    def get_statistics(self) -> Dict:
        """Get provider statistics."""
        total_messages = sum(len(conversation) for conversation in self.conversation_history)
        
        return {
            "model": self.model,
            "total_conversations": len(self.conversation_history),
            "total_messages": total_messages
        }
