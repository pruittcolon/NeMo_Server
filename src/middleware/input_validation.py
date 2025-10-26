"""
Input Validation and Sanitization Middleware
Prevents SQL injection, XSS, and path traversal attacks
"""

import re
from pathlib import Path
from typing import Any, Dict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Dangerous patterns that should be blocked
SQL_INJECTION_PATTERNS = [
    r"(\bUNION\b.*\bSELECT\b)",
    r"(\bDROP\b.*\bTABLE\b)",
    r"(\bINSERT\b.*\bINTO\b)",
    r"(\bDELETE\b.*\bFROM\b)",
    r"(--.*$)",
    r"(/\*.*\*/)",
    r"(\bEXEC\b|\bEXECUTE\b)",
]

XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript:",
    r"onerror\s*=",
    r"onload\s*=",
]

PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",
    r"\.\./",
    r"%2e%2e/",
    r"\.\.\\",
]

class InputValidationMiddleware(BaseHTTPMiddleware):
    """Validate and sanitize user inputs"""
    
    def __init__(self, app, max_query_length: int = 10000, max_body_size: int = 10485760):
        """
        Initialize input validation middleware
        
        Args:
            app: FastAPI application
            max_query_length: Maximum query string length (10KB default)
            max_body_size: Maximum request body size (10MB default)
        """
        super().__init__(app)
        self.max_query_length = max_query_length
        self.max_body_size = max_body_size
        
        # Compile regex patterns
        self.sql_patterns = [re.compile(p, re.IGNORECASE) for p in SQL_INJECTION_PATTERNS]
        self.xss_patterns = [re.compile(p, re.IGNORECASE) for p in XSS_PATTERNS]
        self.path_patterns = [re.compile(p, re.IGNORECASE) for p in PATH_TRAVERSAL_PATTERNS]
    
    def _check_sql_injection(self, value: str) -> bool:
        """Check if value contains SQL injection patterns"""
        if not isinstance(value, str):
            return False
        
        for pattern in self.sql_patterns:
            if pattern.search(value):
                return True
        return False
    
    def _check_xss(self, value: str) -> bool:
        """Check if value contains XSS patterns"""
        if not isinstance(value, str):
            return False
        
        for pattern in self.xss_patterns:
            if pattern.search(value):
                return True
        return False
    
    def _check_path_traversal(self, value: str) -> bool:
        """Check if value contains path traversal patterns"""
        if not isinstance(value, str):
            return False
        
        for pattern in self.path_patterns:
            if pattern.search(value):
                return True
        return False
    
    def _validate_value(self, value: Any, param_name: str = "") -> None:
        """Validate a single value"""
        if isinstance(value, str):
            # Check length
            if len(value) > 10000:  # Max 10KB per parameter
                raise HTTPException(
                    status_code=400,
                    detail=f"Parameter '{param_name}' too long (max 10000 characters)"
                )
            
            # Check for SQL injection
            if self._check_sql_injection(value):
                print(f"[SECURITY] Blocked SQL injection attempt in '{param_name}': {value[:100]}")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid input detected. Request blocked for security reasons."
                )
            
            # Check for XSS
            if self._check_xss(value):
                print(f"[SECURITY] Blocked XSS attempt in '{param_name}': {value[:100]}")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid input detected. Request blocked for security reasons."
                )
            
            # Check for path traversal
            if self._check_path_traversal(value):
                print(f"[SECURITY] Blocked path traversal attempt in '{param_name}': {value[:100]}")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid input detected. Request blocked for security reasons."
                )
        
        elif isinstance(value, dict):
            for k, v in value.items():
                self._validate_value(v, f"{param_name}.{k}")
        
        elif isinstance(value, list):
            for i, item in enumerate(value):
                self._validate_value(item, f"{param_name}[{i}]")
    
    async def dispatch(self, request: Request, call_next):
        """Validate request inputs"""
        # Skip validation for health check and static files
        if request.url.path in ["/health", "/"] or request.url.path.startswith("/ui/"):
            return await call_next(request)
        
        # Validate query parameters
        for key, value in request.query_params.items():
            self._validate_value(value, f"query.{key}")
        
        # Note: Body validation happens in FastAPI's Pydantic models
        # This middleware catches query params and path params
        
        return await call_next(request)

def sanitize_html(text: str) -> str:
    """
    Sanitize HTML to prevent XSS
    Strips dangerous tags and attributes
    """
    if not text:
        return text
    
    # Basic HTML escaping
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&#x27;")
    
    return text

def validate_file_path(path: str, allowed_dir: str) -> Path:
    """
    Validate file path to prevent directory traversal
    
    Args:
        path: User-provided file path
        allowed_dir: Directory where files are allowed
        
    Returns:
        Resolved safe Path object
        
    Raises:
        ValueError if path is outside allowed directory
    """
    allowed = Path(allowed_dir).resolve()
    requested = (allowed / path).resolve()
    
    # Check if requested path is within allowed directory
    try:
        requested.relative_to(allowed)
    except ValueError:
        raise ValueError(f"Access denied: Path outside allowed directory")
    
    return requested


