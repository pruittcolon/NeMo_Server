"""
Security Audit Logger
Logs all security-relevant events for compliance and monitoring
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import threading

class AuditLogger:
    """Thread-safe audit logger for security events"""
    
    def __init__(self, log_path: str = "/instance/security_audit.log"):
        """
        Initialize audit logger
        
        Args:
            log_path: Path to audit log file
        """
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        
        print(f"[AUDIT] Initialized security audit log at {log_path}")
    
    def log_event(self,
                  event_type: str,
                  user_id: Optional[str] = None,
                  ip_address: Optional[str] = None,
                  resource: Optional[str] = None,
                  action: Optional[str] = None,
                  success: bool = True,
                  details: str = "",
                  **extra):
        """
        Log a security event
        
        Args:
            event_type: Type of event (login, logout, access_attempt, etc.)
            user_id: User involved in event
            ip_address: IP address of request
            resource: Resource being accessed
            action: Action being performed
            success: Whether action succeeded
            details: Additional details
            **extra: Additional fields to include
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        event = {
            "timestamp": timestamp,
            "event_type": event_type,
            "user_id": user_id,
            "ip_address": ip_address,
            "resource": resource,
            "action": action,
            "success": success,
            "details": details,
        }
        
        # Add any extra fields
        event.update(extra)
        
        # Write to log file
        with self.lock:
            try:
                with open(self.log_path, 'a') as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                print(f"[AUDIT] Failed to write audit log: {e}")
    
    def log_login(self, username: str, ip_address: str, success: bool, details: str = ""):
        """Log login attempt"""
        self.log_event(
            event_type="login",
            user_id=username,
            ip_address=ip_address,
            action="authenticate",
            success=success,
            details=details
        )
    
    def log_logout(self, user_id: str, ip_address: str):
        """Log logout"""
        self.log_event(
            event_type="logout",
            user_id=user_id,
            ip_address=ip_address,
            action="logout",
            success=True
        )
    
    def log_password_change(self, user_id: str, ip_address: str, success: bool):
        """Log password change"""
        self.log_event(
            event_type="password_change",
            user_id=user_id,
            ip_address=ip_address,
            action="change_password",
            success=success
        )
    
    def log_data_access(self, user_id: str, resource: str, action: str, ip_address: str, success: bool, details: str = ""):
        """Log data access attempt"""
        self.log_event(
            event_type="data_access",
            user_id=user_id,
            ip_address=ip_address,
            resource=resource,
            action=action,
            success=success,
            details=details
        )
    
    def log_rate_limit(self, ip_address: str, endpoint: str, details: str = ""):
        """Log rate limit violation"""
        self.log_event(
            event_type="rate_limit_exceeded",
            ip_address=ip_address,
            resource=endpoint,
            action="rate_limit",
            success=False,
            details=details
        )
    
    def log_authorization_failure(self, user_id: str, resource: str, required_role: str, ip_address: str):
        """Log authorization failure"""
        self.log_event(
            event_type="authorization_failure",
            user_id=user_id,
            ip_address=ip_address,
            resource=resource,
            action="access",
            success=False,
            details=f"Required role: {required_role}"
        )
    
    def log_session_expired(self, user_id: str, ip_address: str):
        """Log session expiration"""
        self.log_event(
            event_type="session_expired",
            user_id=user_id,
            ip_address=ip_address,
            action="validate_session",
            success=False
        )
    
    def get_recent_events(self, limit: int = 100) -> list:
        """
        Get recent audit events
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of audit events (most recent first)
        """
        events = []
        
        try:
            if not self.log_path.exists():
                return events
            
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
            
            # Get last N lines
            for line in reversed(lines[-limit:]):
                try:
                    event = json.loads(line.strip())
                    events.append(event)
                except json.JSONDecodeError:
                    continue
            
            return events
        
        except Exception as e:
            print(f"[AUDIT] Failed to read audit log: {e}")
            return events

# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None

def init_audit_logger(log_path: str = "/instance/security_audit.log"):
    """Initialize global audit logger"""
    global _audit_logger
    _audit_logger = AuditLogger(log_path)
    return _audit_logger

def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance"""
    if _audit_logger is None:
        # Auto-initialize with default path
        return init_audit_logger()
    return _audit_logger

def log_security_event(event_type: str, **kwargs):
    """Convenience function to log security event"""
    get_audit_logger().log_event(event_type, **kwargs)


