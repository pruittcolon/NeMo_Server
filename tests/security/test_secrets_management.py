"""
Secrets Management Security Tests
Tests Docker secrets loading and fallback
"""

import os
import tempfile
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.security.secrets import SecretsManager


class TestSecretsManagement:
    """Test secrets management"""
    
    def test_load_from_file(self):
        """
        Test loading secret from file (Docker secrets)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create secret file
            secret_file = Path(tmpdir) / "test_secret"
            secret_file.write_text("my_secret_value")
            
            # Load secret
            manager = SecretsManager(secrets_dir=tmpdir)
            value = manager.get_secret("test_secret")
            
            assert value == "my_secret_value"
            print("✓ Secret loaded from file")
    
    def test_fallback_to_env(self):
        """
        Test fallback to environment variable
        """
        # Set environment variable
        os.environ["TEST_SECRET_VAR"] = "env_secret_value"
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                manager = SecretsManager(secrets_dir=tmpdir)
                value = manager.get_secret("test_secret_var")
                
                assert value == "env_secret_value"
                print("✓ Secret loaded from environment")
        finally:
            del os.environ["TEST_SECRET_VAR"]
    
    def test_test_mode_default(self):
        """
        Test that TEST_MODE provides defaults
        """
        os.environ["TEST_MODE"] = "true"
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                manager = SecretsManager(secrets_dir=tmpdir)
                value = manager.get_secret("nonexistent_secret", default="default_value")
                
                assert value == "default_value"
                print("✓ TEST_MODE default works")
        finally:
            if "TEST_MODE" in os.environ:
                del os.environ["TEST_MODE"]
    
    def test_secret_not_found_no_default(self):
        """
        Test that missing secret without default returns None
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SecretsManager(secrets_dir=tmpdir)
            value = manager.get_secret("nonexistent_secret")
            
            assert value is None
            print("✓ Missing secret returns None")
    
    def test_secret_caching(self):
        """
        Test that secrets are cached after first load
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create secret file
            secret_file = Path(tmpdir) / "cached_secret"
            secret_file.write_text("original_value")
            
            manager = SecretsManager(secrets_dir=tmpdir)
            
            # Load first time
            value1 = manager.get_secret("cached_secret")
            assert value1 == "original_value"
            
            # Change file
            secret_file.write_text("new_value")
            
            # Load again (should use cache)
            value2 = manager.get_secret("cached_secret")
            assert value2 == "original_value"  # Still cached
            
            print("✓ Secret caching works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])





