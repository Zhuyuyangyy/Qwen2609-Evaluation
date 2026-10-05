"""
V0.4 - Motivation System Module

Goal-directed behavior system. Manages goals, drives, and motivation levels
based on emotional state and internal needs.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class Goal:
    """Represents a motivational goal."""
    
    id: str
    name: str
    description: str
    priority: float
    progress: float
    deadline: Optional[float]
    emotional_value: Dict[str, float]
    dependencies: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert goal to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "progress": self.progress,
            "deadline": self.deadline,
            "emotional_value": self.emotional_value,
            "dependencies": self.dependencies
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Goal':
        """Create goal from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            priority=data["priority"],
            progress=data["progress"],
            deadline=data.get("deadline"),
            emotional_value=data["emotional_value"],
            dependencies=data["dependencies"]
        )


@dataclass
class Drive:
    """Represents an internal drive/motivation."""
    
    name: str
    level: float  # 0-1, where 1 is highest
    threshold: float  # When drive triggers goal activation
    decay_rate: float  # Rate at which drive decreases over time
    goal_template: str  # Template for generating goals
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert drive to dictionary."""
        return {
            "name": self.name,
            "level": self.level,
            "threshold": self.threshold,
            "decay_rate": self.decay_rate,
            "goal_template": self.goal_template
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Drive':
        """Create drive from dictionary."""
        return cls(
            name=data["name"],
            level=data["level"],
            threshold=data["threshold"],
            decay_rate=data["decay_rate"],
            goal_template=data["goal_template"]
        )


class MotivationSystem:
    """
    Goal-directed behavior system.
    
    Features:
    - Drive-based motivation
    - Goal prioritization
    - Emotional influence on goals
    - Progress tracking
    """
    
    DEFAULT_DRIVES = [
        {"name": "exploration", "level": 0.5, "threshold": 0.7, "decay_rate": 0.01, "goal_template": "Explore new environment"},
        {"name": "social", "level": 0.4, "threshold": 0.6, "decay_rate": 0.02, "goal_template": "Interact with others"},
        {"name": "achievement", "level": 0.6, "threshold": 0.8, "decay_rate": 0.015, "goal_template": "Complete task"},
        {"name": "safety", "level": 0.7, "threshold": 0.5, "decay_rate": 0.005, "goal_template": "Ensure safety"},
        {"name": "curiosity", "level": 0.5, "threshold": 0.65, "decay_rate": 0.012, "goal_template": "Learn new information"}
    ]
    
    def __init__(self):
        self._goals: List[Goal] = []
        self._drives: Dict[str, Drive] = {}
        self._initialize_default_drives()
    
    def _initialize_default_drives(self) -> None:
        """Initialize default drives."""
        for drive_data in self.DEFAULT_DRIVES:
            drive = Drive.from_dict(drive_data)
            self._drives[drive.name] = drive
    
    def _generate_goal_id(self) -> str:
        """Generate a unique goal ID."""
        return f"goal_{int(time.time() * 1000)}_{len(self._goals)}"
    
    def add_goal(
        self,
        name: str,
        description: str,
        priority: float = 0.5,
        deadline: Optional[float] = None,
        emotional_value: Optional[Dict[str, float]] = None,
        dependencies: Optional[List[str]] = None
    ) -> str:
        """
        Add a new goal.
        
        Args:
            name: Goal name
            description: Goal description
            priority: Priority level (0-1)
            deadline: Optional deadline timestamp
            emotional_value: Emotional value of achieving this goal
            dependencies: List of goal IDs this goal depends on
        
        Returns:
            The ID of the added goal
        """
        goal_id = self._generate_goal_id()
        goal = Goal(
            id=goal_id,
            name=name,
            description=description,
            priority=min(1.0, max(0.0, priority)),
            progress=0.0,
            deadline=deadline,
            emotional_value=emotional_value or {},
            dependencies=dependencies or []
        )
        self._goals.append(goal)
        return goal_id
    
    def update_goal_progress(self, goal_id: str, progress: float) -> bool:
        """
        Update goal progress.
        
        Args:
            goal_id: ID of the goal to update
            progress: New progress value (0-1)
        
        Returns:
            True if goal was found and updated
        """
        for goal in self._goals:
            if goal.id == goal_id:
                goal.progress = min(1.0, max(0.0, progress))
                return True
        return False
    
    def remove_goal(self, goal_id: str) -> bool:
        """
        Remove a goal.
        
        Args:
            goal_id: ID of the goal to remove
        
        Returns:
            True if goal was found and removed
        """
        for i, goal in enumerate(self._goals):
            if goal.id == goal_id:
                del self._goals[i]
                return True
        return False
    
    def update_drive_level(self, drive_name: str, delta: float) -> None:
        """
        Update a drive level by a delta.
        
        Args:
            drive_name: Name of the drive
            delta: Change in drive level (-1 to +1)
        """
        if drive_name in self._drives:
            self._drives[drive_name].level = min(1.0, max(0.0, 
                self._drives[drive_name].level + delta))
    
    def decay_drives(self) -> None:
        """Decay all drives according to their decay rates."""
        for drive in self._drives.values():
            drive.level = max(0.0, drive.level - drive.decay_rate)
    
    def generate_goals_from_drives(self) -> List[str]:
        """
        Generate new goals from drives that exceed their thresholds.
        
        Returns:
            List of newly created goal IDs
        """
        new_goal_ids = []
        for drive in self._drives.values():
            if drive.level >= drive.threshold:
                # Check if similar goal already exists
                has_similar = any(g.name == drive.goal_template for g in self._goals)
                if not has_similar:
                    goal_id = self.add_goal(
                        name=drive.goal_template,
                        description=f"Goal generated by {drive.name} drive",
                        priority=drive.level
                    )
                    new_goal_ids.append(goal_id)
                    # Reduce drive level after goal generation
                    drive.level -= 0.2
        
        return new_goal_ids
    
    def get_priority_goal(self, emotional_state: Optional[Dict[str, float]] = None) -> Optional[Goal]:
        """
        Get the highest priority goal considering emotional state.
        
        Args:
            emotional_state: Current emotional state dictionary
        
        Returns:
            The highest priority goal, or None if no goals exist
        """
        if not self._goals:
            return None
        
        # Filter out completed goals
        active_goals = [g for g in self._goals if g.progress < 1.0]
        
        if not active_goals:
            return None
        
        # Calculate priority with emotional influence
        scored_goals = []
        for goal in active_goals:
            base_priority = goal.priority
            
            # Adjust for deadline
            if goal.deadline:
                time_left = goal.deadline - time.time()
                if time_left > 0:
                    urgency = max(0, 1.0 - (time_left / 3600))  # Normalize to hours
                    base_priority += urgency * 0.3
            
            # Adjust based on emotional state
            if emotional_state and goal.emotional_value:
                for emotion, weight in goal.emotional_value.items():
                    if emotion in emotional_state:
                        base_priority += emotional_state[emotion] * weight * 0.2
            
            scored_goals.append((goal, base_priority))
        
        # Sort by priority
        scored_goals.sort(key=lambda x: x[1], reverse=True)
        
        return scored_goals[0][0] if scored_goals else None
    
    def get_all_goals(self) -> List[Goal]:
        """Get all goals."""
        return list(self._goals)
    
    def get_drives(self) -> Dict[str, Drive]:
        """Get all drives."""
        return dict(self._drives)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get motivation system statistics."""
        active_goals = [g for g in self._goals if g.progress < 1.0]
        completed_goals = [g for g in self._goals if g.progress >= 1.0]
        
        return {
            "total_goals": len(self._goals),
            "active_goals": len(active_goals),
            "completed_goals": len(completed_goals),
            "average_progress": sum(g.progress for g in self._goals) / max(1, len(self._goals)),
            "drives": {name: drive.level for name, drive in self._drives.items()}
        }
    
    def to_json(self) -> str:
        """Serialize motivation system to JSON."""
        return json.dumps({
            "goals": [goal.to_dict() for goal in self._goals],
            "drives": {name: drive.to_dict() for name, drive in self._drives.items()},
            "statistics": self.get_statistics()
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MotivationSystem':
        """Deserialize motivation system from JSON."""
        data = json.loads(json_str)
        system = cls()
        
        # Clear default goals and drives
        system._goals = []
        system._drives = {}
        
        # Load drives
        for name, drive_data in data.get("drives", {}).items():
            system._drives[name] = Drive.from_dict(drive_data)
        
        # Load goals
        for goal_data in data.get("goals", []):
            system._goals.append(Goal.from_dict(goal_data))
        
        return system
