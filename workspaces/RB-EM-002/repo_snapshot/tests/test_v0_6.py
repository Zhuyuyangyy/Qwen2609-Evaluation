"""Tests for V0.6 Affective Benchmark Module"""

import pytest
from emotion_agent.affective_benchmark import (
    AffectiveBenchmark, TaskCategory, BenchmarkMetrics
)


class TestAffectiveBenchmark:
    """Test suite for AffectiveBenchmark class."""
    
    def test_initialization(self):
        """Test benchmark initialization."""
        benchmark = AffectiveBenchmark(seed=42)
        
        assert len(benchmark.tasks) == 100
    
    def test_task_distribution(self):
        """Test task distribution."""
        benchmark = AffectiveBenchmark(seed=42)
        dist = benchmark.get_task_distribution()
        
        assert sum(dist.values()) == 100
        assert TaskCategory.IRREVERSIBLE_FILE_OPS.value in dist
    
    def test_run_benchmark(self):
        """Test running benchmark."""
        benchmark = AffectiveBenchmark(seed=42)
        
        class DummyAgent:
            pass
        
        results = benchmark.run_benchmark(DummyAgent(), "plain")
        
        assert len(results) == 100
    
    def test_calculate_metrics(self):
        """Test calculating metrics."""
        benchmark = AffectiveBenchmark(seed=42)
        results = benchmark.run_benchmark(None, "plain")
        metrics = benchmark.calculate_metrics(results)
        
        assert isinstance(metrics, BenchmarkMetrics)
        assert 0.0 <= metrics.task_success_rate <= 1.0
    
    def test_generate_comparison_table(self):
        """Test generating comparison table."""
        benchmark = AffectiveBenchmark(seed=42)
        results = benchmark.run_benchmark(None, "plain")
        
        baseline_results = {"Plain Agent": results}
        table = benchmark.generate_comparison_table(baseline_results)
        
        assert "Plain Agent" in table
        assert "|" in table


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
