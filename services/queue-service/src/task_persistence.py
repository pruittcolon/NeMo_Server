"""
Task Persistence
PostgreSQL storage for Gemma task recovery
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

try:
    import asyncpg
except ImportError:
    asyncpg = None
    logging.warning("asyncpg not installed - task persistence disabled")

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Gemma task statuses"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPersistence:
    """
    PostgreSQL-backed task queue for Gemma requests
    Provides crash recovery and task history
    """
    
    def __init__(self, db_url: str = "postgresql://localhost/nemo_queue"):
        """
        Initialize task persistence
        
        Args:
            db_url: PostgreSQL connection URL
        """
        self.db_url = db_url
        self.pool: Optional[asyncpg.Pool] = None
        self.enabled = asyncpg is not None
    
    async def connect(self):
        """Connect to PostgreSQL and create tables"""
        if not self.enabled:
            logger.warning("Task persistence disabled (asyncpg not installed)")
            return
        
        try:
            self.pool = await asyncpg.create_pool(
                self.db_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            
            # Create tables
            await self._create_tables()
            
            logger.info("Task persistence connected to PostgreSQL")
            
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            self.enabled = False
    
    async def disconnect(self):
        """Disconnect from PostgreSQL"""
        if self.pool:
            await self.pool.close()
    
    async def _create_tables(self):
        """Create task tables if they don't exist"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS gemma_tasks (
                    task_id VARCHAR(255) PRIMARY KEY,
                    status VARCHAR(50) NOT NULL,
                    payload JSONB NOT NULL,
                    result JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3
                )
            """)
            
            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_gemma_tasks_status 
                ON gemma_tasks(status)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_gemma_tasks_created 
                ON gemma_tasks(created_at DESC)
            """)
    
    async def add_task(
        self,
        task_id: str,
        payload: Dict[str, Any],
        max_retries: int = 3
    ) -> bool:
        """
        Add new Gemma task to queue
        
        Args:
            task_id: Unique task identifier
            payload: Task data (messages, max_tokens, etc.)
            max_retries: Maximum retry attempts
            
        Returns:
            True if added successfully
        """
        if not self.enabled:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO gemma_tasks 
                    (task_id, status, payload, max_retries)
                    VALUES ($1, $2, $3, $4)
                """, task_id, TaskStatus.QUEUED.value, json.dumps(payload), max_retries)
            
            logger.info(f"Task {task_id} added to queue")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add task {task_id}: {e}")
            return False
    
    async def mark_running(self, task_id: str) -> bool:
        """
        Mark task as running
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if updated successfully
        """
        if not self.enabled:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE gemma_tasks 
                    SET status = $1, started_at = NOW()
                    WHERE task_id = $2
                """, TaskStatus.RUNNING.value, task_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark task {task_id} as running: {e}")
            return False
    
    async def mark_completed(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Mark task as completed
        
        Args:
            task_id: Task identifier
            result: Optional task result
            
        Returns:
            True if updated successfully
        """
        if not self.enabled:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE gemma_tasks 
                    SET status = $1, completed_at = NOW(), result = $2
                    WHERE task_id = $3
                """, TaskStatus.COMPLETED.value, json.dumps(result) if result else None, task_id)
            
            logger.info(f"Task {task_id} marked completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark task {task_id} as completed: {e}")
            return False
    
    async def mark_failed(
        self,
        task_id: str,
        error: str,
        can_retry: bool = True
    ) -> bool:
        """
        Mark task as failed
        
        Args:
            task_id: Task identifier
            error: Error message
            can_retry: Whether task can be retried
            
        Returns:
            True if updated successfully
        """
        if not self.enabled:
            return False
        
        try:
            async with self.pool.acquire() as conn:
                # Get current retry count
                row = await conn.fetchrow("""
                    SELECT retry_count, max_retries FROM gemma_tasks
                    WHERE task_id = $1
                """, task_id)
                
                if row and can_retry and row['retry_count'] < row['max_retries']:
                    # Increment retry count, keep as queued
                    await conn.execute("""
                        UPDATE gemma_tasks 
                        SET retry_count = retry_count + 1, 
                            status = $1,
                            error = $2
                        WHERE task_id = $3
                    """, TaskStatus.QUEUED.value, error, task_id)
                    logger.info(f"Task {task_id} failed, queued for retry {row['retry_count'] + 1}")
                else:
                    # Mark as failed permanently
                    await conn.execute("""
                        UPDATE gemma_tasks 
                        SET status = $1, completed_at = NOW(), error = $2
                        WHERE task_id = $3
                    """, TaskStatus.FAILED.value, error, task_id)
                    logger.error(f"Task {task_id} failed permanently: {error}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark task {task_id} as failed: {e}")
            return False
    
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task by ID
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task dictionary or None
        """
        if not self.enabled:
            return None
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM gemma_tasks WHERE task_id = $1
                """, task_id)
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return None
    
    async def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """
        Get all queued tasks (for crash recovery)
        
        Returns:
            List of task dictionaries
        """
        if not self.enabled:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM gemma_tasks 
                    WHERE status = $1
                    ORDER BY created_at ASC
                """, TaskStatus.QUEUED.value)
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get pending tasks: {e}")
            return []
    
    async def get_task_stats(self) -> Dict[str, int]:
        """
        Get task statistics
        
        Returns:
            Dictionary with counts by status
        """
        if not self.enabled:
            return {}
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT status, COUNT(*) as count
                    FROM gemma_tasks
                    GROUP BY status
                """)
                
                stats = {row['status']: row['count'] for row in rows}
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get task stats: {e}")
            return {}


# Singleton instance
_persistence: Optional[TaskPersistence] = None


def get_task_persistence() -> TaskPersistence:
    """Get or create task persistence singleton"""
    global _persistence
    if _persistence is None:
        _persistence = TaskPersistence()
    return _persistence







