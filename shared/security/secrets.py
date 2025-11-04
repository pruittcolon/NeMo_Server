"""
Secrets Management
Loads secrets from Docker secrets or environment variables
"""

import os
import logging
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretsManager:
    """
    Manages application secrets
    
    Priority:
    1. Docker secrets (/run/secrets/)
    2. Environment variables
    3. Default values (TEST_MODE only)
    """
    
    def __init__(self, secrets_dir: str = "/run/secrets"):
        """
        Initialize secrets manager
        
        Args:
            secrets_dir: Directory containing Docker secrets
        """
        self.secrets_dir = Path(secrets_dir)
        self.cache: Dict[str, str] = {}
        self.test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        
        logger.info(f"Secrets Manager initialized (dir: {secrets_dir}, test_mode: {self.test_mode})")
    
    def get_secret(self, secret_name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get secret by name
        
        Args:
            secret_name: Secret identifier
            default: Default value if secret not found
            
        Returns:
            Secret value or None
        """
        logger.debug(f"🔍 SECRET GET: Requesting '{secret_name}'")
        
        # Check cache
        if secret_name in self.cache:
            logger.debug(f"✅ SECRET GET: '{secret_name}' found in cache")
            return self.cache[secret_name]
        
        logger.debug(f"🔍 SECRET GET: '{secret_name}' not in cache, trying sources...")
        
        # Try Docker secret file
        secret_file = self.secrets_dir / secret_name
        if secret_file.exists():
            try:
                logger.debug(f"📂 SECRET GET: Reading '{secret_name}' from {secret_file}")
                value = secret_file.read_text().strip()
                if not value:
                    logger.warning(f"⚠️ SECRET GET: '{secret_name}' file is empty at {secret_file}")
                    value = None
                else:
                    self.cache[secret_name] = value
                    value_preview = value[:8] + "..." if len(value) > 8 else "***"
                    logger.info(f"✅ SECRET GET: Loaded '{secret_name}' from Docker secrets ({len(value)} chars, preview: {value_preview})")
                    return value
            except Exception as e:
                logger.error(f"❌ SECRET GET: Failed to read secret file {secret_file}: {e}")
        else:
            logger.debug(f"📂 SECRET GET: File {secret_file} does not exist")
        
        # Try environment variable
        env_var = secret_name.upper()
        if env_var in os.environ:
            value = os.environ[env_var].strip()
            if not value:
                logger.warning(f"⚠️ SECRET GET: '{secret_name}' env var is empty")
            else:
                self.cache[secret_name] = value
                value_preview = value[:8] + "..." if len(value) > 8 else "***"
                logger.info(f"✅ SECRET GET: Loaded '{secret_name}' from environment ({len(value)} chars, preview: {value_preview})")
                return value
        else:
            logger.debug(f"🔍 SECRET GET: Environment variable {env_var} not set")
        
        # Use default in TEST_MODE
        if default and self.test_mode:
            logger.warning(f"⚠️ SECRET GET: Using DEFAULT value for '{secret_name}' (TEST_MODE enabled)")
            self.cache[secret_name] = default
            return default
        
        # Secret not found
        if default is None:
            logger.error(f"❌ SECRET GET: '{secret_name}' not found and no default provided!")
            return None
        else:
            logger.warning(f"⚠️ SECRET GET: '{secret_name}' not found, using provided default")
            return default
    
    def set_secret(self, secret_name: str, value: str):
        """
        Manually set secret (for testing)
        
        Args:
            secret_name: Secret identifier
            value: Secret value
        """
        self.cache[secret_name] = value
        logger.info(f"Manually set secret '{secret_name}'")
    
    def has_secret(self, secret_name: str) -> bool:
        """
        Check if secret exists
        
        Args:
            secret_name: Secret identifier
            
        Returns:
            True if secret exists
        """
        return self.get_secret(secret_name) is not None
    
    def list_secrets(self) -> list:
        """
        List all loaded secrets (names only, not values)
        
        Returns:
            List of secret names
        """
        return list(self.cache.keys())


# Singleton instance
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get or create secrets manager singleton"""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_secret(secret_name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Convenience function to get secret
    
    Args:
        secret_name: Secret identifier
        default: Default value
        
    Returns:
        Secret value
    """
    manager = get_secrets_manager()
    return manager.get_secret(secret_name, default)







