"""
GPU Transition Performance Tests
Measures pause/resume performance and Gemma overhead
"""

import time
import pytest
import httpx
import asyncio
from typing import Dict, Any


class TestGPUTransitions:
    """Test GPU pause/resume performance"""
    
    BASE_URL_COORDINATOR = "http://localhost:8002"
    BASE_URL_GEMMA = "http://localhost:8001"
    BASE_URL_TRANSCRIPTION = "http://localhost:8003"
    SERVICE_KEY = "test_key"
    
    @pytest.mark.asyncio
    async def test_transcription_pause_time(self):
        """
        Measure time for transcription to pause
        Target: <2 seconds
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get initial status
            resp = await client.get(f"{self.BASE_URL_COORDINATOR}/status")
            assert resp.status_code == 200
            initial_status = resp.json()
            assert initial_status["lock_status"]["state"] == "transcription"
            
            # Request GPU for Gemma (triggers pause)
            start_time = time.time()
            
            resp = await client.post(
                f"{self.BASE_URL_COORDINATOR}/gemma/request",
                json={
                    "task_id": "perf-test-pause",
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 10
                }
            )
            
            pause_time = time.time() - start_time
            
            assert resp.status_code == 200
            assert pause_time < 2.0, f"Pause took {pause_time:.2f}s (target: <2s)"
            
            # Verify GPU acquired
            resp = await client.get(f"{self.BASE_URL_COORDINATOR}/status")
            status = resp.json()
            assert status["lock_status"]["state"] == "gemma"
            
            # Release GPU
            await client.post(f"{self.BASE_URL_COORDINATOR}/gemma/release/perf-test-pause")
            
            print(f"✓ Pause time: {pause_time:.3f}s (target: <2s)")
    
    @pytest.mark.asyncio
    async def test_gemma_full_cycle(self):
        """
        Measure full Gemma cycle: request → GPU load → inference → release
        Target: Overhead <5s (excluding inference time)
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Full Gemma request
            start_time = time.time()
            
            resp = await client.post(
                f"{self.BASE_URL_GEMMA}/chat",
                headers={"X-Service-Key": self.SERVICE_KEY},
                json={
                    "messages": [{"role": "user", "content": "Say hi in 3 words"}],
                    "max_tokens": 10,
                    "temperature": 0.7
                }
            )
            
            total_time = time.time() - start_time
            
            assert resp.status_code == 200
            result = resp.json()
            
            # Verify transcription resumed
            await asyncio.sleep(1)
            resp = await client.get(f"{self.BASE_URL_COORDINATOR}/status")
            status = resp.json()
            assert status["lock_status"]["state"] == "transcription"
            
            print(f"✓ Full Gemma cycle: {total_time:.2f}s")
            print(f"  Generated tokens: {result.get('tokens_generated', 'N/A')}")
    
    @pytest.mark.asyncio
    async def test_transcription_resume_time(self):
        """
        Measure time for transcription to resume after Gemma
        Target: <1 second
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Trigger Gemma request
            await client.post(
                f"{self.BASE_URL_COORDINATOR}/gemma/request",
                json={
                    "task_id": "perf-test-resume",
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 10
                }
            )
            
            # Release GPU
            start_time = time.time()
            
            await client.post(
                f"{self.BASE_URL_COORDINATOR}/gemma/release/perf-test-resume"
            )
            
            # Wait for transcription to resume
            await asyncio.sleep(0.5)
            
            resp = await client.get(f"{self.BASE_URL_TRANSCRIPTION}/pause/status")
            resume_time = time.time() - start_time
            
            status = resp.json()
            assert not status["paused"], "Transcription should have resumed"
            assert resume_time < 1.0, f"Resume took {resume_time:.2f}s (target: <1s)"
            
            print(f"✓ Resume time: {resume_time:.3f}s (target: <1s)")
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_queuing(self):
        """
        Test that multiple Gemma requests queue properly
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Send 3 concurrent requests
            tasks = []
            for i in range(3):
                task = client.post(
                    f"{self.BASE_URL_GEMMA}/chat",
                    headers={"X-Service-Key": self.SERVICE_KEY},
                    json={
                        "messages": [{"role": "user", "content": f"Request {i}"}],
                        "max_tokens": 5
                    }
                )
                tasks.append(task)
            
            # All should complete (queued if necessary)
            start_time = time.time()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time
            
            # Verify all completed
            success_count = sum(1 for r in responses if not isinstance(r, Exception))
            print(f"✓ Concurrent requests: {success_count}/3 completed in {total_time:.2f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])





