"""
Service Authentication Security Tests
Tests JWT creation, verification, expiry
"""

import time
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.security.service_auth import ServiceAuth


class TestServiceAuth:
    """Test JWT service authentication"""
    
    def test_create_token(self):
        """
        Test creating a JWT token
        """
        auth = ServiceAuth("test-service", "test_secret_key_minimum_16_chars")
        
        token = auth.create_token(expires_in=300)
        
        assert token is not None
        assert len(token) > 0
        assert "." in token  # Should have payload.signature format
        
        print(f"✓ Token created: {token[:50]}...")
    
    def test_verify_valid_token(self):
        """
        Test verifying a valid token
        """
        auth = ServiceAuth("test-service", "test_secret_key_minimum_16_chars")
        
        token = auth.create_token(expires_in=300)
        payload = auth.verify_token(token)
        
        assert payload is not None
        assert payload["service_id"] == "test-service"
        assert "request_id" in payload
        assert "issued_at" in payload
        assert "expires_at" in payload
        
        print("✓ Valid token verified")
    
    def test_verify_expired_token(self):
        """
        Test that expired tokens are rejected
        """
        auth = ServiceAuth("test-service", "test_secret_key_minimum_16_chars")
        
        # Create token with 1 second expiry
        token = auth.create_token(expires_in=1)
        
        # Wait for expiry
        time.sleep(2)
        
        # Should fail verification
        with pytest.raises(ValueError, match="expired"):
            auth.verify_token(token)
        
        print("✓ Expired token rejected")
    
    def test_verify_tampered_token(self):
        """
        Test that tampered tokens are rejected
        """
        auth = ServiceAuth("test-service", "test_secret_key_minimum_16_chars")
        
        token = auth.create_token(expires_in=300)
        
        # Tamper with token (change a character)
        tampered_token = token[:-5] + "XXXXX"
        
        # Should fail verification
        with pytest.raises(ValueError):
            auth.verify_token(tampered_token)
        
        print("✓ Tampered token rejected")
    
    def test_wrong_secret_key(self):
        """
        Test that token from one secret cannot be verified with another
        """
        auth1 = ServiceAuth("service1", "secret_key_1_minimum_16_chars")
        auth2 = ServiceAuth("service2", "secret_key_2_minimum_16_chars")
        
        token = auth1.create_token(expires_in=300)
        
        # auth2 should reject auth1's token (different secret)
        with pytest.raises(ValueError):
            auth2.verify_token(token)
        
        print("✓ Cross-secret verification blocked")
    
    def test_allowed_services_filter(self):
        """
        Test that allowed_services filtering works
        """
        auth = ServiceAuth("service-a", "test_secret_key_minimum_16_chars")
        
        token = auth.create_token(expires_in=300)
        
        # Should succeed with service-a in allowed list
        payload = auth.verify_token(token, allowed_services=["service-a", "service-b"])
        assert payload["service_id"] == "service-a"
        
        # Should fail with service-a NOT in allowed list
        with pytest.raises(ValueError, match="not allowed"):
            auth.verify_token(token, allowed_services=["service-b", "service-c"])
        
        print("✓ Allowed services filter works")
    
    def test_auth_header_format(self):
        """
        Test auth header format for HTTP requests
        """
        auth = ServiceAuth("test-service", "test_secret_key_minimum_16_chars")
        
        header = auth.get_auth_header()
        
        assert "X-Service-Token" in header
        assert len(header["X-Service-Token"]) > 0
        
        print(f"✓ Auth header: {header}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])





