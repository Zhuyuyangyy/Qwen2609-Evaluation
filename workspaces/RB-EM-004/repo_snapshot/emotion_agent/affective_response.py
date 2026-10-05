"""
V0.3 - Affective Response Module

Emotional response generation system. Generates context-appropriate responses
based on current emotional state and situational context.
"""

from typing import Dict, List, Optional, Tuple
import random


class AffectiveResponse:
    """
    Generates affective responses based on emotional state.
    
    Implements rule-based response generation with emotional modulation.
    All responses are deterministic given the same input.
    """
    
    RESPONSE_TEMPLATES = {
        "joy": [
            "That's wonderful! I'm glad to hear that.",
            "Great news! I feel happy for you.",
            "Wonderful! This makes me feel joyful.",
            "I'm experiencing joy hearing this.",
            "Happy times! Let's celebrate."
        ],
        "sadness": [
            "I'm sorry to hear that. That must be difficult.",
            "This makes me feel sad too.",
            "I understand your sadness.",
            "That sounds tough. I'm here for you.",
            "Sadness is a natural response to this."
        ],
        "anger": [
            "I understand your frustration.",
            "Anger is a natural reaction to this.",
            "That's infuriating. I feel angry too.",
            "I can sense your anger about this.",
            "This situation is angering."
        ],
        "fear": [
            "That sounds scary. I'm here to support you.",
            "Fear is a normal response in this situation.",
            "I feel anxious thinking about this.",
            "This makes me feel fearful too.",
            "Let's approach this carefully."
        ],
        "disgust": [
            "That's unpleasant. I understand your reaction.",
            "This is disgusting. I share your feeling.",
            "I find this repugnant too.",
            "Disgust is an appropriate response here.",
            "That's revolting."
        ],
        "surprise": [
            "Wow, that's surprising!",
            "I didn't expect that! How interesting.",
            "Surprising news! This caught me off guard.",
            "That's unexpected! I'm surprised too.",
            "Interesting turn of events!"
        ],
        "trust": [
            "I trust that will work out.",
            "Trust is important here.",
            "I feel confident about this.",
            "This inspires trust.",
            "I have faith in this."
        ],
        "anticipation": [
            "I'm looking forward to that!",
            "Anticipation is building!",
            "Excited to see what happens!",
            "This makes me feel anticipatory.",
            "Looking ahead with excitement!"
        ],
        "neutral": [
            "I understand.",
            "Interesting point.",
            "I see.",
            "Thank you for sharing.",
            "That's good to know."
        ]
    }
    
    def __init__(self, seed: int = 42):
        """
        Initialize affective response generator.
        
        Args:
            seed: Random seed for deterministic response selection
        """
        self._rng = random.Random(seed)
    
    def generate_response(
        self,
        emotion_category: str,
        intensity: float,
        context: str = "",
        valence: float = 0.0,
        arousal: float = 0.0
    ) -> str:
        """
        Generate an affective response.
        
        Args:
            emotion_category: Current emotion category
            intensity: Emotional intensity (0-1)
            context: Optional context string
            valence: Current valence (-1 to +1)
            arousal: Current arousal (-1 to +1)
        
        Returns:
            A context-appropriate affective response
        """
        # Normalize emotion category
        emotion_category = emotion_category.lower()
        
        # Get appropriate templates
        if emotion_category not in self.RESPONSE_TEMPLATES:
            emotion_category = "neutral"
        
        templates = self.RESPONSE_TEMPLATES[emotion_category]
        
        # Determine response based on intensity
        if intensity < 0.2:
            # Low intensity - select from first 2 templates
            template_index = self._deterministic_select(templates[:2], context, valence, arousal)
        elif intensity < 0.5:
            # Medium intensity - select from first 3 templates
            template_index = self._deterministic_select(templates[:3], context, valence, arousal)
        elif intensity < 0.8:
            # High intensity - select from all but last template
            template_index = self._deterministic_select(templates[:-1], context, valence, arousal)
        else:
            # Very high intensity - select from all templates
            template_index = self._deterministic_select(templates, context, valence, arousal)
        
        return templates[template_index]
    
    def _deterministic_select(self, templates: List[str], context: str, 
                             valence: float, arousal: float) -> int:
        """
        Deterministically select a template based on input features.
        
        Args:
            templates: List of template strings to choose from
            context: Context string
            valence: Valence value
            arousal: Arousal value
        
        Returns:
            Index of selected template
        """
        if len(templates) == 0:
            return 0
        if len(templates) == 1:
            return 0
        
        # Create deterministic hash from inputs
        hash_input = f"{context}_{valence:.4f}_{arousal:.4f}_{len(templates)}"
        hash_value = self._string_hash(hash_input)
        
        return hash_value % len(templates)
    
    def _string_hash(self, s: str) -> int:
        """Simple deterministic string hash."""
        result = 0
        for char in s:
            result = (result * 31 + ord(char)) & 0xFFFFFFFF
        return result
    
    def generate_nonverbal_cues(self, emotion_category: str, intensity: float) -> Dict[str, str]:
        """
        Generate non-verbal cues corresponding to emotional state.
        
        Args:
            emotion_category: Current emotion category
            intensity: Emotional intensity (0-1)
        
        Returns:
            Dictionary of non-verbal cues (facial expression, posture, tone)
        """
        cues = {
            "joy": {
                "facial_expression": "smile",
                "posture": "upright, open",
                "tone": "bright, upbeat",
                "gesture": "open arms"
            },
            "sadness": {
                "facial_expression": "frown",
                "posture": "slumped, closed",
                "tone": "soft, slow",
                "gesture": "slumped shoulders"
            },
            "anger": {
                "facial_expression": "scowl",
                "posture": "tense, rigid",
                "tone": "loud, sharp",
                "gesture": "clenched fists"
            },
            "fear": {
                "facial_expression": "wide eyes, raised eyebrows",
                "posture": "hunched, defensive",
                "tone": "high-pitched, shaky",
                "gesture": "hands up in defense"
            },
            "disgust": {
                "facial_expression": "nose wrinkled",
                "posture": "leaning back",
                "tone": "disdainful",
                "gesture": "pushing away"
            },
            "surprise": {
                "facial_expression": "eyes wide, mouth open",
                "posture": "still, alert",
                "tone": "high-pitched, quick",
                "gesture": "hand to mouth"
            },
            "trust": {
                "facial_expression": "warm smile",
                "posture": "relaxed, open",
                "tone": "soft, reassuring",
                "gesture": "handshake"
            },
            "anticipation": {
                "facial_expression": "excited look",
                "posture": "leaning forward",
                "tone": "eager, energetic",
                "gesture": "leaning in"
            },
            "neutral": {
                "facial_expression": "neutral",
                "posture": "relaxed",
                "tone": "calm, neutral",
                "gesture": "none"
            }
        }
        
        base_cues = cues.get(emotion_category, cues["neutral"])
        
        # Adjust cues based on intensity
        intensity_modifier = "low" if intensity < 0.3 else "medium" if intensity < 0.7 else "high"
        
        return {
            **base_cues,
            "intensity": intensity_modifier
        }
    
    def generate_action_tendency(self, emotion_category: str) -> str:
        """
        Generate action tendency based on emotion category.
        
        Args:
            emotion_category: Current emotion category
        
        Returns:
            Action tendency description
        """
        tendencies = {
            "joy": "approach - seek out more positive experiences",
            "sadness": "withdraw - seek comfort",
            "anger": "approach - confront or attack",
            "fear": "avoid - escape or defend",
            "disgust": "reject - push away or avoid",
            "surprise": "orient - attend to new information",
            "trust": "approach - cooperate",
            "anticipation": "prepare - plan for future",
            "neutral": "maintain - continue current behavior"
        }
        
        return tendencies.get(emotion_category, tendencies["neutral"])
