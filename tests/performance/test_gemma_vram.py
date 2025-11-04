"""
Gemma VRAM Optimization Tests
Finds optimal configuration for 64k context within 6GB VRAM
"""

import subprocess
import pytest
import httpx
import time


def get_vram_usage() -> dict:
    """Get current VRAM usage from nvidia-smi"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            used, total = result.stdout.strip().split(',')
            return {
                "used_mb": int(used.strip()),
                "total_mb": int(total.strip()),
                "free_mb": int(total.strip()) - int(used.strip())
            }
    except Exception as e:
        pytest.skip(f"nvidia-smi not available: {e}")
    
    return {"used_mb": 0, "total_mb": 0, "free_mb": 0}


class TestGemmaVRAM:
    """Test Gemma VRAM usage with different configurations"""
    
    BASE_URL_GEMMA = "http://localhost:8001"
    SERVICE_KEY = "test_key"
    
    def test_baseline_vram(self):
        """
        Measure baseline VRAM (before Gemma loads to GPU)
        """
        vram = get_vram_usage()
        print(f"\n✓ Baseline VRAM: {vram['used_mb']} MB / {vram['total_mb']} MB")
        print(f"  Free VRAM: {vram['free_mb']} MB")
        
        assert vram['total_mb'] >= 6000, "Expected at least 6GB VRAM (GTX 1660 Ti)"
    
    @pytest.mark.asyncio
    async def test_gemma_64k_context_vram(self):
        """
        Test VRAM usage with 64k context (current config)
        Target: 5-5.5GB VRAM used
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get baseline
            vram_before = get_vram_usage()
            
            # Trigger Gemma request (loads to GPU)
            resp = await client.post(
                f"{self.BASE_URL_GEMMA}/chat",
                headers={"X-Service-Key": self.SERVICE_KEY},
                json={
                    "messages": [{"role": "user", "content": "Test VRAM usage"}],
                    "max_tokens": 20
                }
            )
            
            assert resp.status_code == 200
            
            # Wait for model to be on GPU
            time.sleep(2)
            
            # Get VRAM during inference
            vram_during = get_vram_usage()
            
            print(f"\n✓ VRAM with 64k context:")
            print(f"  Before: {vram_before['used_mb']} MB")
            print(f"  During: {vram_during['used_mb']} MB")
            print(f"  Increase: {vram_during['used_mb'] - vram_before['used_mb']} MB")
            print(f"  Free: {vram_during['free_mb']} MB")
            
            # Verify within limits
            assert vram_during['used_mb'] <= 6000, f"VRAM usage {vram_during['used_mb']} MB exceeds 6GB limit!"
            
            # Check we have buffer room
            buffer_mb = vram_during['free_mb']
            assert buffer_mb >= 500, f"Insufficient VRAM buffer: {buffer_mb} MB (target: >500MB)"
            
            print(f"  ✓ Within limits with {buffer_mb} MB buffer")
    
    @pytest.mark.asyncio
    async def test_gemma_sustained_load_vram(self):
        """
        Test VRAM stability under sustained load
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            vram_readings = []
            
            # Send 5 consecutive requests
            for i in range(5):
                resp = await client.post(
                    f"{self.BASE_URL_GEMMA}/chat",
                    headers={"X-Service-Key": self.SERVICE_KEY},
                    json={
                        "messages": [{"role": "user", "content": f"Request {i}"}],
                        "max_tokens": 10
                    }
                )
                
                assert resp.status_code == 200
                
                # Measure VRAM
                vram = get_vram_usage()
                vram_readings.append(vram['used_mb'])
                
                time.sleep(1)
            
            # Check for memory leaks
            avg_vram = sum(vram_readings) / len(vram_readings)
            max_vram = max(vram_readings)
            min_vram = min(vram_readings)
            
            print(f"\n✓ Sustained load VRAM (5 requests):")
            print(f"  Average: {avg_vram:.0f} MB")
            print(f"  Min: {min_vram} MB")
            print(f"  Max: {max_vram} MB")
            print(f"  Variance: {max_vram - min_vram} MB")
            
            # Variance should be small (no significant memory leak)
            assert (max_vram - min_vram) < 1000, "Possible memory leak detected"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])





