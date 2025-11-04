"""
Audit Logging Security Tests
Tests comprehensive event logging
"""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.security.audit_logger import AuditLogger, AuditEventType


class TestAuditLogging:
    """Test audit logging functionality"""
    
    def test_log_api_request(self):
        """
        Test logging API requests
        """
        logger = AuditLogger(log_to_stdout=True)
        
        logger.log_api_request(
            endpoint="/api/test",
            method="POST",
            user_id="test_user",
            ip_address="127.0.0.1",
            duration_ms=150.5,
            status_code=200
        )
        
        print("✓ API request logged")
    
    def test_log_login_success(self):
        """
        Test logging successful login
        """
        logger = AuditLogger(log_to_stdout=True)
        
        logger.log_login(
            username="test_user",
            ip_address="192.168.1.100",
            success=True,
            details={"method": "password"}
        )
        
        print("✓ Login success logged")
    
    def test_log_login_failure(self):
        """
        Test logging failed login
        """
        logger = AuditLogger(log_to_stdout=True)
        
        logger.log_login(
            username="attacker",
            ip_address="10.0.0.1",
            success=False,
            details={"reason": "invalid_password", "attempts": 3}
        )
        
        print("✓ Login failure logged")
    
    def test_log_security_event(self):
        """
        Test logging security events
        """
        logger = AuditLogger(log_to_stdout=True)
        
        logger.log_security_event(
            event_description="Suspicious activity detected",
            ip_address="10.0.0.1",
            details={"reason": "too_many_requests", "count": 100}
        )
        
        print("✓ Security event logged")
    
    def test_log_gpu_event(self):
        """
        Test logging GPU state transitions
        """
        logger = AuditLogger(log_to_stdout=True)
        
        logger.log_gpu_event(
            event_description="GPU ownership transferred",
            state_from="transcription",
            state_to="gemma",
            task_id="gemma-task-123"
        )
        
        print("✓ GPU event logged")
    
    def test_log_gemma_task(self):
        """
        Test logging Gemma task execution
        """
        logger = AuditLogger(log_to_stdout=True)
        
        logger.log_gemma_task(
            task_id="gemma-task-456",
            status="completed",
            vram_used_mb=5200,
            tokens_generated=150,
            duration_seconds=8.5
        )
        
        print("✓ Gemma task logged")
    
    def test_log_transcription_event(self):
        """
        Test logging transcription pause/resume
        """
        logger = AuditLogger(log_to_stdout=True)
        
        logger.log_transcription_event(
            event_description="Transcription paused for Gemma",
            paused=True,
            queued_chunks=3
        )
        
        print("✓ Transcription event logged")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])





