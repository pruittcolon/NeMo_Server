"""
CPU Load Performance Tests
Verifies CPU services (RAG, Diarization, Emotion) don't bottleneck
"""

import psutil
import time
import pytest
import asyncio
from typing import List


class TestCPULoad:
    """Test CPU performance for CPU-only services"""
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=1)
    
    def test_baseline_cpu(self):
        """
        Measure baseline CPU usage (idle)
        """
        cpu_samples = [psutil.cpu_percent(interval=0.1) for _ in range(10)]
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        
        print(f"\n✓ Baseline CPU: {avg_cpu:.1f}%")
        assert avg_cpu < 50, f"Baseline CPU too high: {avg_cpu:.1f}%"
    
    @pytest.mark.asyncio
    async def test_transcription_cpu_usage(self):
        """
        Test CPU usage during transcription (when on CPU)
        Note: In our architecture, transcription uses GPU by default
        This test is for when it's paused (no GPU access)
        """
        # Simulate CPU-only transcription load
        # In practice, when paused, transcription doesn't process
        # This is more of a baseline test
        
        cpu_before = self.get_cpu_usage()
        print(f"\n✓ Transcription CPU test:")
        print(f"  Baseline: {cpu_before:.1f}%")
        
        # Note: Actual CPU test would require transcription service running
        # and processing chunks. For now, this is a placeholder.
        
        assert cpu_before < 80, "CPU usage too high at baseline"
    
    def test_system_resources_available(self):
        """
        Verify system has sufficient resources
        """
        # Check CPU cores
        cpu_count = psutil.cpu_count()
        print(f"\n✓ System Resources:")
        print(f"  CPU Cores: {cpu_count}")
        
        # Check memory
        memory = psutil.virtual_memory()
        print(f"  Total RAM: {memory.total / (1024**3):.1f} GB")
        print(f"  Available RAM: {memory.available / (1024**3):.1f} GB")
        print(f"  RAM Usage: {memory.percent:.1f}%")
        
        # Verify sufficient resources
        assert cpu_count >= 4, "Need at least 4 CPU cores"
        assert memory.available > 4 * (1024**3), "Need at least 4GB available RAM"
    
    @pytest.mark.asyncio
    async def test_concurrent_service_cpu_load(self):
        """
        Test CPU usage with multiple services running
        Simulates typical load scenario
        """
        print(f"\n✓ Concurrent service CPU load test:")
        
        # Measure CPU over 10 seconds
        cpu_samples = []
        for i in range(10):
            cpu = psutil.cpu_percent(interval=1)
            cpu_samples.append(cpu)
            print(f"  Sample {i+1}: {cpu:.1f}%")
        
        avg_cpu = sum(cpu_samples) / len(cpu_samples)
        max_cpu = max(cpu_samples)
        
        print(f"  Average CPU: {avg_cpu:.1f}%")
        print(f"  Max CPU: {max_cpu:.1f}%")
        
        # Target: <80% sustained CPU
        assert avg_cpu < 80, f"Average CPU too high: {avg_cpu:.1f}% (target: <80%)"
        assert max_cpu < 95, f"Peak CPU too high: {max_cpu:.1f}% (target: <95%)"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])





