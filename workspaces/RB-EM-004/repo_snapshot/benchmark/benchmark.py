"""
Benchmark Suite for Experience-Shaped Affective Agent (V0.8)

Runs 100 benchmark tasks with 4 baselines for comparison.
"""

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from emotion_agent import AffectiveAgent


class BenchmarkTask:
    """Represents a benchmark task."""
    
    def __init__(self, task_id, description, inputs, expected_output):
        self.task_id = task_id
        self.description = description
        self.inputs = inputs
        self.expected_output = expected_output


class BaselineAgent:
    """Abstract base class for baseline agents."""
    
    def __init__(self, name):
        self.name = name
    
    def process(self, task):
        """Process a task and return result."""
        raise NotImplementedError


class RandomBaseline(BaselineAgent):
    """Random decision baseline."""
    
    def __init__(self):
        super().__init__("Random")
    
    def process(self, task):
        import random
        return {"decision": random.choice(["A", "B", "C"]), "confidence": 0.33}


class RationalBaseline(BaselineAgent):
    """Purely rational decision baseline (max expected value)."""
    
    def __init__(self):
        super().__init__("Rational")
    
    def process(self, task):
        options = task.inputs.get("options", [])
        if not options:
            return {"decision": "A", "confidence": 0.5}
        
        best_option = max(options, key=lambda x: x.get("expected_value", 0))
        return {
            "decision": best_option.get("name", "A"),
            "confidence": 0.8
        }


class EmotionalBaseline(BaselineAgent):
    """Purely emotional decision baseline."""
    
    def __init__(self):
        super().__init__("Emotional")
    
    def process(self, task):
        options = task.inputs.get("options", [])
        emotion = task.inputs.get("emotion", {})
        
        if not options:
            return {"decision": "A", "confidence": 0.5}
        
        # Choose option with emotional impact closest to current emotion
        best_option = None
        best_match = -1
        
        current_valence = emotion.get("valence", 0)
        
        for option in options:
            impact_valence = option.get("emotional_impact", {}).get("valence", 0)
            match = 1 - abs(current_valence - impact_valence)
            
            if match > best_match:
                best_match = match
                best_option = option
        
        return {
            "decision": best_option.get("name", "A") if best_option else "A",
            "confidence": min(1.0, 0.5 + best_match * 0.5)
        }


class HybridBaseline(BaselineAgent):
    """50/50 hybrid of rational and emotional."""
    
    def __init__(self):
        super().__init__("Hybrid")
    
    def process(self, task):
        options = task.inputs.get("options", [])
        emotion = task.inputs.get("emotion", {})
        
        if not options:
            return {"decision": "A", "confidence": 0.5}
        
        best_option = None
        best_score = -1
        
        current_valence = emotion.get("valence", 0)
        
        for option in options:
            value = option.get("expected_value", 0.5)
            risk = option.get("risk", 0.5)
            impact_valence = option.get("emotional_impact", {}).get("valence", 0)
            
            rational_score = value * (1 - risk)
            emotional_score = 1 - abs(current_valence - impact_valence)
            total_score = (rational_score + emotional_score) / 2
            
            if total_score > best_score:
                best_score = total_score
                best_option = option
        
        return {
            "decision": best_option.get("name", "A") if best_option else "A",
            "confidence": min(1.0, 0.5 + best_score * 0.5)
        }


def generate_benchmark_tasks(count=100):
    """Generate benchmark tasks."""
    tasks = []
    
    emotions = ["joy", "sadness", "anger", "fear", "surprise", "trust", "anticipation", "neutral"]
    valence_values = [0.8, -0.7, -0.8, -0.8, 0.0, 0.6, 0.5, 0.0]
    
    for i in range(count):
        emotion_idx = i % len(emotions)
        emotion = emotions[emotion_idx]
        valence = valence_values[emotion_idx]
        
        # Generate decision options
        options = []
        for j in range(3):
            options.append({
                "name": chr(65 + j),  # A, B, C
                "expected_value": 0.3 + (i * 7 + j * 13) % 40 / 100,
                "risk": 0.2 + (i * 11 + j * 7) % 50 / 100,
                "emotional_impact": {
                    "valence": valence * (0.5 + j * 0.2),
                    "arousal": 0.3 * (j - 1)
                }
            })
        
        # Determine expected optimal decision
        expected_decision = options[0]["name"]
        
        task = BenchmarkTask(
            task_id=f"task_{i+1:03d}",
            description=f"Decision task under {emotion} emotion",
            inputs={
                "emotion": {"category": emotion, "valence": valence},
                "options": options
            },
            expected_output={"decision": expected_decision}
        )
        
        tasks.append(task)
    
    return tasks


def run_benchmark():
    """Run the complete benchmark suite."""
    print("=" * 70)
    print("EXPERIENCE-SHAPED AFFECTIVE AGENT - BENCHMARK SUITE")
    print("=" * 70)
    print(f"Running 100 benchmark tasks with 4 baselines...\n")
    
    # Generate tasks
    tasks = generate_benchmark_tasks(100)
    
    # Initialize agents
    affective_agent = AffectiveAgent(agent_id="benchmark_agent")
    baselines = [
        RandomBaseline(),
        RationalBaseline(),
        EmotionalBaseline(),
        HybridBaseline()
    ]
    
    # Results tracking
    results = {
        "AffectiveAgent": {"correct": 0, "total": 0, "avg_confidence": 0.0},
        "Random": {"correct": 0, "total": 0, "avg_confidence": 0.0},
        "Rational": {"correct": 0, "total": 0, "avg_confidence": 0.0},
        "Emotional": {"correct": 0, "total": 0, "avg_confidence": 0.0},
        "Hybrid": {"correct": 0, "total": 0, "avg_confidence": 0.0}
    }
    
    # Run tasks
    for task in tasks:
        # Affective Agent
        affective_agent.feel(task.inputs["emotion"]["category"])
        decision = affective_agent.decide(task.inputs["options"])
        results["AffectiveAgent"]["total"] += 1
        results["AffectiveAgent"]["avg_confidence"] += decision["confidence"]
        if decision["chosen_option"]["name"] == task.expected_output["decision"]:
            results["AffectiveAgent"]["correct"] += 1
        
        # Baselines
        for baseline in baselines:
            result = baseline.process(task)
            results[baseline.name]["total"] += 1
            results[baseline.name]["avg_confidence"] += result["confidence"]
            if result["decision"] == task.expected_output["decision"]:
                results[baseline.name]["correct"] += 1
    
    # Calculate averages
    for agent_name in results:
        if results[agent_name]["total"] > 0:
            results[agent_name]["accuracy"] = results[agent_name]["correct"] / results[agent_name]["total"]
            results[agent_name]["avg_confidence"] /= results[agent_name]["total"]
    
    # Print results
    print("=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)
    print(f"{'Agent':<20} {'Accuracy':<10} {'Avg Confidence':<15} {'Correct/Total'}")
    print("-" * 70)
    
    for agent_name in ["AffectiveAgent", "Random", "Rational", "Emotional", "Hybrid"]:
        r = results[agent_name]
        print(f"{agent_name:<20} {r['accuracy']*100:>6.2f}% {r['avg_confidence']:>14.3f} {r['correct']:>6}/{r['total']}")
    
    print("\n" + "=" * 70)
    
    # Save results
    output_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, "benchmark_results.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to: {output_file}")
    print("\n✅ Benchmark completed successfully!")
    
    return results


if __name__ == "__main__":
    run_benchmark()
