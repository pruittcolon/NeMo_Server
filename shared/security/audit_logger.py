"""
Enhanced Audit Logging
Comprehensive event logging with encryption
"""

import time
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Audit event types"""
    API_REQUEST = "api_request"
    AUTH_LOGIN = "auth_login"
    AUTH_LOGOUT = "auth_logout"
    AUTH_FAILED = "auth_failed"
    DATA_ACCESS = "data_access"
    DATA_MODIFY = "data_modify"
    SECURITY_EVENT = "security_event"
    GPU_EVENT = "gpu_event"
    GEMMA_TASK = "gemma_task"
    TRANSCRIPTION_EVENT = "transcription_event"
    SYSTEM_EVENT = "system_event"


class AuditLogger:
    """
    Enhanced audit logger
    
    Logs all significant events:
    - API requests
    - Authentication events
    - Data access/modification
    - Security events
    - GPU state transitions
    - Gemma tasks
    - Transcription pause/resume
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        use_encryption: bool = True,
        log_to_stdout: bool = False
    ):
        """
        Initialize audit logger
        
        Args:
            db_path: Path to encrypted audit database
            use_encryption: Whether to encrypt audit logs
            log_to_stdout: Also log to stdout (for TEST_MODE)
        """
        self.db_path = db_path
        self.use_encryption = use_encryption
        self.log_to_stdout = log_to_stdout
        
        # In production: initialize encrypted database here
        # For now: just log to stdout
        
        logger.info("Audit Logger initialized")
    
    def log_event(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        service_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True
    ):
        """
        Log audit event
        
        Args:
            event_type: Type of event
            user_id: User identifier (if applicable)
            service_id: Service identifier (if applicable)
            ip_address: Client IP address
            endpoint: API endpoint
            details: Additional event details
            success: Whether event succeeded
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type.value,
            "user_id": user_id,
            "service_id": service_id,
            "ip_address": ip_address,
            "endpoint": endpoint,
            "details": details or {},
            "success": success
        }
        
        # Log to stdout if enabled
        if self.log_to_stdout:
            logger.info(f"[AUDIT] {json.dumps(event)}")
        
        # In production: store in encrypted database
        # For now: just stdout
    
    def log_api_request(
        self,
        endpoint: str,
        method: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        duration_ms: Optional[float] = None,
        status_code: Optional[int] = None
    ):
        """Log API request"""
        self.log_event(
            event_type=AuditEventType.API_REQUEST,
            user_id=user_id,
            ip_address=ip_address,
            endpoint=endpoint,
            details={
                "method": method,
                "duration_ms": duration_ms,
                "status_code": status_code
            },
            success=status_code < 400 if status_code else True
        )
    
    def log_login(
        self,
        username: str,
        ip_address: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log login attempt"""
        self.log_event(
            event_type=AuditEventType.AUTH_LOGIN if success else AuditEventType.AUTH_FAILED,
            user_id=username,
            ip_address=ip_address,
            details=details or {},
            success=success
        )
    
    def log_logout(self, user_id: str, ip_address: str):
        """Log logout"""
        self.log_event(
            event_type=AuditEventType.AUTH_LOGOUT,
            user_id=user_id,
            ip_address=ip_address
        )
    
    def log_data_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str = "read"
    ):
        """Log data access"""
        self.log_event(
            event_type=AuditEventType.DATA_ACCESS,
            user_id=user_id,
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action
            }
        )
    
    def log_security_event(
        self,
        event_description: str,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log security event"""
        self.log_event(
            event_type=AuditEventType.SECURITY_EVENT,
            ip_address=ip_address,
            details={"description": event_description, **(details or {})},
            success=False
        )
    
    def log_gpu_event(
        self,
        event_description: str,
        state_from: Optional[str] = None,
        state_to: Optional[str] = None,
        task_id: Optional[str] = None
    ):
        """Log GPU state transition"""
        self.log_event(
            event_type=AuditEventType.GPU_EVENT,
            service_id="gpu-coordinator",
            details={
                "description": event_description,
                "state_from": state_from,
                "state_to": state_to,
                "task_id": task_id
            }
        )
    
    def log_gemma_task(
        self,
        task_id: str,
        status: str,
        vram_used_mb: Optional[int] = None,
        tokens_generated: Optional[int] = None,
        duration_seconds: Optional[float] = None,
        error: Optional[str] = None
    ):
        """Log Gemma task"""
        self.log_event(
            event_type=AuditEventType.GEMMA_TASK,
            service_id="gemma-service",
            details={
                "task_id": task_id,
                "status": status,
                "vram_used_mb": vram_used_mb,
                "tokens_generated": tokens_generated,
                "duration_seconds": duration_seconds,
                "error": error
            },
            success=status == "completed"
        )
    
    def log_transcription_event(
        self,
        event_description: str,
        paused: bool,
        queued_chunks: int = 0
    ):
        """Log transcription pause/resume"""
        self.log_event(
            event_type=AuditEventType.TRANSCRIPTION_EVENT,
            service_id="transcription-service",
            details={
                "description": event_description,
                "paused": paused,
                "queued_chunks": queued_chunks
            }
        )


# Singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(
    db_path: Optional[str] = None,
    use_encryption: bool = True
) -> AuditLogger:
    """Get or create audit logger singleton"""
    global _audit_logger
    if _audit_logger is None:
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        _audit_logger = AuditLogger(
            db_path=db_path,
            use_encryption=use_encryption and not test_mode,
            log_to_stdout=test_mode or True  # Always log to stdout for now
        )
    return _audit_logger


import os  # Add missing import







