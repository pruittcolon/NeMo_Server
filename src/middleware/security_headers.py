"""
Security Headers Middleware
Adds security-related HTTP headers to all responses
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    def __init__(self, app, enable_hsts: bool = False):
        """
        Initialize security headers middleware
        
        Args:
            app: FastAPI application
            enable_hsts: Enable HSTS header (only for HTTPS)
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts
    
    async def dispatch(self, request: Request, call_next):
        """Add security headers to response"""
        response = await call_next(request)
        
        # X-Content-Type-Options: Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # X-Frame-Options: Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-XSS-Protection: Enable browser XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer-Policy: Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions-Policy: Restrict browser features
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content-Security-Policy: Restrict resource loading
        # Note: Adjust based on actual needs (inline scripts, external resources)
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Strict-Transport-Security: Force HTTPS (only if HTTPS is enabled)
        # Check if request is HTTPS
        if self.enable_hsts and (request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"):
            # Enable HSTS for 1 year with subdomains
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Server: Remove or obscure server information
        response.headers["Server"] = "Nemo"
        
        return response

def create_security_headers_middleware(enable_hsts: bool = False):
    """
    Factory function to create security headers middleware
    
    Args:
        enable_hsts: Enable HSTS header (only for HTTPS deployments)
    
    Returns:
        Middleware class configured with settings
    """
    def middleware(app):
        return SecurityHeadersMiddleware(app, enable_hsts=enable_hsts)
    return middleware


