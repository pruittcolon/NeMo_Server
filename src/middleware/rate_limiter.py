"""
Global Rate Limiter Middleware
Implements sliding window rate limiting per IP address and per user
"""

import time
import threading
from collections import defaultdict, deque
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class RateLimitRule:
    """Defines rate limit parameters for a route or pattern"""
    
    def __init__(self, requests: int, window_seconds: int):
        """
        Args:
            requests: Maximum number of requests allowed
            window_seconds: Time window in seconds
        """
        self.requests = requests
        self.window_seconds = window_seconds

class RateLimiter:
    """
    Sliding window rate limiter with per-IP and per-user tracking
    """
    
    def __init__(self):
        """Initialize rate limiter with default rules"""
        # Track requests: key=(identifier, rule_name), value=deque of timestamps
        self.requests: Dict[Tuple[str, str], deque] = defaultdict(lambda: deque())
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Define rate limit rules for different endpoints
        self.rules = {
            "/api/auth/login": RateLimitRule(requests=5, window_seconds=300),  # 5 per 5 min
            "/transcribe": RateLimitRule(requests=20, window_seconds=60),  # 20 per minute
            "/analyze": RateLimitRule(requests=5, window_seconds=3600),  # 5 per hour
            "/memory/search": RateLimitRule(requests=30, window_seconds=60),  # 30 per minute
            "/memory/list": RateLimitRule(requests=30, window_seconds=60),  # 30 per minute
            "default": RateLimitRule(requests=100, window_seconds=60)  # 100 per minute
        }
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        
        print("[RATE_LIMITER] Initialized with sliding window tracking")
    
    def _cleanup_loop(self):
        """Periodically clean up old request timestamps"""
        while True:
            time.sleep(60)  # Run every minute
            self._cleanup_old_requests()
    
    def _cleanup_old_requests(self):
        """Remove request timestamps older than the longest window"""
        with self.lock:
            now = time.time()
            max_window = max(rule.window_seconds for rule in self.rules.values())
            cutoff = now - max_window
            
            # Clean up old timestamps
            for key in list(self.requests.keys()):
                timestamps = self.requests[key]
                while timestamps and timestamps[0] < cutoff:
                    timestamps.popleft()
                
                # Remove empty entries
                if not timestamps:
                    del self.requests[key]
    
    def _get_rule_for_path(self, path: str) -> Tuple[str, RateLimitRule]:
        """Get rate limit rule for a given path"""
        # Check for exact match
        for pattern, rule in self.rules.items():
            if pattern == "default":
                continue
            if path.startswith(pattern):
                return (pattern, rule)
        
        # Return default rule
        return ("default", self.rules["default"])
    
    def check_rate_limit(self, identifier: str, path: str) -> Tuple[bool, Optional[dict]]:
        """
        Check if request is within rate limit
        
        Args:
            identifier: Unique identifier (IP address or user_id)
            path: Request path
            
        Returns:
            Tuple of (allowed, limit_info)
            - allowed: True if within limit, False if exceeded
            - limit_info: Dict with limit details or None
        """
        rule_name, rule = self._get_rule_for_path(path)
        
        with self.lock:
            now = time.time()
            key = (identifier, rule_name)
            timestamps = self.requests[key]
            
            # Remove timestamps outside the window
            cutoff = now - rule.window_seconds
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            
            # Check if limit exceeded
            if len(timestamps) >= rule.requests:
                # Calculate retry_after
                oldest = timestamps[0]
                retry_after = int(oldest + rule.window_seconds - now) + 1
                
                return (False, {
                    "limit": rule.requests,
                    "window_seconds": rule.window_seconds,
                    "current_count": len(timestamps),
                    "retry_after": retry_after,
                    "rule": rule_name
                })
            
            # Add current request timestamp
            timestamps.append(now)
            
            return (True, {
                "limit": rule.requests,
                "window_seconds": rule.window_seconds,
                "current_count": len(timestamps),
                "remaining": rule.requests - len(timestamps),
                "rule": rule_name
            })
    
    def get_status(self, identifier: str) -> Dict[str, dict]:
        """Get rate limit status for all rules"""
        with self.lock:
            now = time.time()
            status = {}
            
            for rule_name, rule in self.rules.items():
                key = (identifier, rule_name)
                timestamps = self.requests[key]
                
                # Remove old timestamps
                cutoff = now - rule.window_seconds
                while timestamps and timestamps[0] < cutoff:
                    timestamps.popleft()
                
                status[rule_name] = {
                    "limit": rule.requests,
                    "window_seconds": rule.window_seconds,
                    "current_count": len(timestamps),
                    "remaining": max(0, rule.requests - len(timestamps))
                }
            
            return status

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting"""
    
    def __init__(self, app, limiter: RateLimiter):
        super().__init__(app)
        self.limiter = limiter
    
    async def dispatch(self, request: Request, call_next):
        """Check rate limit before processing request"""
        # Skip rate limiting for health check
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get identifier (IP address)
        client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limit
        allowed, limit_info = self.limiter.check_rate_limit(client_ip, request.url.path)
        
        if not allowed:
            # Rate limit exceeded
            retry_after = limit_info.get("retry_after", 60)
            
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={
                    "X-RateLimit-Limit": str(limit_info["limit"]),
                    "X-RateLimit-Window": str(limit_info["window_seconds"]),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(retry_after)
                }
            )
        
        # Add rate limit headers to response
        response = await call_next(request)
        
        if limit_info:
            response.headers["X-RateLimit-Limit"] = str(limit_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(limit_info.get("remaining", 0))
            response.headers["X-RateLimit-Window"] = str(limit_info["window_seconds"])
        
        return response

# Global rate limiter instance
_rate_limiter = None

def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


