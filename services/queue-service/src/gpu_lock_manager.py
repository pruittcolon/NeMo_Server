"""
GPU Lock Manager
Coordinates exclusive GPU access between Transcription (owner) and Gemma (requester)
"""

import asyncio
import logging
import os
import time
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import json

try:
    import redis.asyncio as redis
except ImportError:
    import redis

logger = logging.getLogger(__name__)


class GPUState(Enum):
    """GPU ownership states"""
    TRANSCRIPTION_ACTIVE = "transcription"  # Default: Transcription owns GPU
    PAUSING = "pausing"                     # Waiting for transcription to finish chunk
    GEMMA_EXCLUSIVE = "gemma"               # Gemma has exclusive GPU access


class GPULockManager:
    """
    Manages GPU ownership with pause/resume coordination
    
    Strategy:
    - Transcription owns GPU by default (runs 24/7)
    - Gemma requests GPU when needed (~50x/day)
    - Only ONE service uses GPU at a time
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """
        Initialize GPU lock manager
        
        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub = None
        self.state = GPUState.TRANSCRIPTION_ACTIVE
        self.current_gemma_task: Optional[Dict[str, Any]] = None
        self.pause_ack_timeout = float(os.getenv("GPU_PAUSE_TIMEOUT", "10.0"))
        
        logger.info("GPU Lock Manager initialized")
    
    async def connect(self):
        """Connect to Redis"""
        self.redis_client = redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()
        
        # Subscribe to transcription acknowledgment
        await self.pubsub.subscribe("transcription_paused")
        
        # Set initial state
        await self.redis_client.set("gpu_state", self.state.value)
        await self.redis_client.publish("gpu_owner", "transcription")
        
        logger.info("Connected to Redis, GPU state: TRANSCRIPTION_ACTIVE")
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.pubsub:
            await self.pubsub.unsubscribe("transcription_paused")
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
    
    async def request_gpu_for_gemma(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """
        Request GPU for Gemma execution
        
        Process:
        1. Signal transcription to pause
        2. Wait for acknowledgment (default timeout 10s)
        3. Grant GPU to Gemma
        
        Args:
            task_id: Unique task identifier
            task_data: Task payload
            
        Returns:
            True if GPU acquired successfully
        """
        logger.info(f"[GPU] Gemma task {task_id} requesting GPU (immediate priority)")
        
        # Store current task
        self.current_gemma_task = {
            "task_id": task_id,
            "data": task_data,
            "requested_at": time.time()
        }
        
        # Change state to PAUSING
        self.state = GPUState.PAUSING
        await self.redis_client.set("gpu_state", self.state.value)
        
        # Signal transcription to pause
        pause_message = json.dumps({
            "reason": "gemma",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat()
        })
        
        await self.redis_client.publish("transcription_pause", pause_message)
        logger.info(f"[GPU] Pause signal sent to transcription for task {task_id}")
        
        # Wait for transcription to acknowledge pause (max 2s timeout)
        paused = await self._wait_for_transcription_pause(timeout=self.pause_ack_timeout)
        
        if not paused:
            logger.warning(f"[GPU] Transcription didn't pause in time for task {task_id}, forcing GPU takeover")
        else:
            logger.info(f"[GPU] Transcription paused successfully for task {task_id}")
        
        # Grant GPU to Gemma
        self.state = GPUState.GEMMA_EXCLUSIVE
        await self.redis_client.set("gpu_state", self.state.value)
        await self.redis_client.publish("gpu_owner", "gemma")
        
        # Store task start time for metrics
        await self.redis_client.set(f"gemma_task:{task_id}:start", time.time())
        
        logger.info(f"[GPU] Gemma has exclusive GPU access for task {task_id}")
        return True
    
    async def release_gpu_from_gemma(self, task_id: str, result: Optional[Dict[str, Any]] = None):
        """
        Release GPU after Gemma completes
        
        Process:
        1. Update state to TRANSCRIPTION_ACTIVE
        2. Signal transcription to resume
        3. Clear current task
        
        Args:
            task_id: Task identifier
            result: Optional task result for logging
        """
        logger.info(f"[GPU] Gemma task {task_id} releasing GPU")
        
        # Calculate task duration
        start_time = await self.redis_client.get(f"gemma_task:{task_id}:start")
        if start_time:
            duration = time.time() - float(start_time)
            logger.info(f"[GPU] Gemma task {task_id} duration: {duration:.2f}s")
            await self.redis_client.delete(f"gemma_task:{task_id}:start")
        
        # Return GPU to transcription
        self.state = GPUState.TRANSCRIPTION_ACTIVE
        await self.redis_client.set("gpu_state", self.state.value)
        
        # Signal transcription to resume
        resume_message = json.dumps({
            "task_id": task_id,
            "timestamp": datetime.now().isoformat()
        })
        await self.redis_client.publish("transcription_resume", resume_message)
        
        # Clear current task
        self.current_gemma_task = None
        
        logger.info(f"[GPU] GPU returned to transcription after task {task_id}")
    
    async def _wait_for_transcription_pause(self, timeout: float = 2.0) -> bool:
        """
        Wait for transcription pause acknowledgment
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if transcription paused, False if timeout
        """
        start_time = time.time()
        
        try:
            while (time.time() - start_time) < timeout:
                # Check for pause acknowledgment
                message = await asyncio.wait_for(
                    self.pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=0.1
                )
                
                if message and message['type'] == 'message':
                    if message['channel'] == 'transcription_paused':
                        data = json.loads(message['data'])
                        logger.info(f"[GPU] Transcription pause acknowledged: {data}")
                        return True
                
                await asyncio.sleep(0.05)  # Small delay between checks
            
            return False
            
        except asyncio.TimeoutError:
            return False
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get current GPU lock status
        
        Returns:
            Status dictionary
        """
        status = {
            "state": self.state.value,
            "current_owner": "gemma" if self.state == GPUState.GEMMA_EXCLUSIVE else "transcription",
            "current_task": self.current_gemma_task.get("task_id") if self.current_gemma_task else None,
            "timestamp": datetime.now().isoformat()
        }
        
        return status
    
    async def force_reset(self):
        """
        Force reset GPU to transcription (emergency recovery)
        Use with caution!
        """
        logger.warning("[GPU] FORCE RESET: Returning GPU to transcription")
        
        self.state = GPUState.TRANSCRIPTION_ACTIVE
        await self.redis_client.set("gpu_state", self.state.value)
        await self.redis_client.publish("transcription_resume", json.dumps({"force": True}))
        self.current_gemma_task = None
        
        logger.info("[GPU] Force reset complete")


# Singleton instance
_lock_manager: Optional[GPULockManager] = None


def get_lock_manager() -> GPULockManager:
    """Get or create GPU lock manager singleton"""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = GPULockManager()
    return _lock_manager





