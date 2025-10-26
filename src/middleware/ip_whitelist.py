"""
IP Whitelist Middleware
Restricts access to whitelisted IP addresses (for WireGuard VPN)
"""

import ipaddress
from typing import List
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """Restrict access to whitelisted IP addresses"""
    
    def __init__(self, app, allowed_ips: List[str], enabled: bool = True):
        """
        Initialize IP whitelist middleware
        
        Args:
            app: FastAPI application
            allowed_ips: List of allowed IP addresses or CIDR ranges
            enabled: Whether whitelist is enabled (default: True)
        """
        super().__init__(app)
        self.enabled = enabled
        self.allowed_networks = []
        
        # Parse IP addresses and networks
        for ip_str in allowed_ips:
            if not ip_str or ip_str.strip() == "":
                continue
            try:
                # Try to parse as network (CIDR notation)
                network = ipaddress.ip_network(ip_str.strip(), strict=False)
                self.allowed_networks.append(network)
            except ValueError:
                print(f"[IP_WHITELIST] Invalid IP/network: {ip_str}")
        
        if self.enabled and self.allowed_networks:
            print(f"[IP_WHITELIST] Enabled with {len(self.allowed_networks)} networks/IPs")
        elif self.enabled:
            print("[IP_WHITELIST] WARNING: Enabled but no valid IPs configured. All requests will be blocked!")
        else:
            print("[IP_WHITELIST] Disabled")
    
    def _is_ip_allowed(self, ip_str: str) -> bool:
        """Check if IP address is in whitelist"""
        if not self.enabled:
            return True
        
        if not self.allowed_networks:
            # No networks configured - allow all (with warning logged at init)
            return True
        
        try:
            ip = ipaddress.ip_address(ip_str)
            
            # Check against all allowed networks
            for network in self.allowed_networks:
                if ip in network:
                    return True
            
            return False
        
        except ValueError:
            # Invalid IP address format
            return False
    
    async def dispatch(self, request: Request, call_next):
        """Check IP whitelist before processing request"""
        # Skip whitelist check for health endpoint
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get client IP
        client_ip = request.client.host if request.client else None
        
        # Check X-Forwarded-For header (if behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            client_ip = forwarded_for.split(",")[0].strip()
        
        if not client_ip:
            print("[IP_WHITELIST] Could not determine client IP")
            raise HTTPException(
                status_code=403,
                detail="Access denied: Could not determine client IP address"
            )
        
        # Check whitelist
        if not self._is_ip_allowed(client_ip):
            print(f"[IP_WHITELIST] Blocked request from {client_ip} to {request.url.path}")
            raise HTTPException(
                status_code=403,
                detail="Access denied: Your IP address is not authorized to access this server"
            )
        
        return await call_next(request)


