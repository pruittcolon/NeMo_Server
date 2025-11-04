"""
Encryption Key Management
Handles key rotation and Docker secrets integration
"""

import os
import secrets
import logging
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class KeyManager:
    """
    Manages encryption keys for databases
    
    Keys are loaded from Docker secrets or environment variables
    Supports key rotation with version tracking
    """
    
    def __init__(self, secrets_dir: str = "/run/secrets"):
        """
        Initialize key manager
        
        Args:
            secrets_dir: Directory containing Docker secrets
        """
        self.secrets_dir = Path(secrets_dir)
        self.keys: Dict[str, str] = {}
        self.key_versions: Dict[str, int] = {}
        
        logger.info(f"Key Manager initialized (secrets_dir: {secrets_dir})")
    
    def get_key(self, key_name: str, version: int = 1) -> Optional[str]:
        """
        Get encryption key by name
        
        Priority:
        1. Docker secret file (/run/secrets/{key_name})
        2. Environment variable ({KEY_NAME})
        3. Cached key
        4. Generate new key (TEST_MODE only)
        
        Args:
            key_name: Key identifier (e.g., 'users_db_key')
            version: Key version (for rotation)
            
        Returns:
            Encryption key or None
        """
        cache_key = f"{key_name}_v{version}"
        
        # Check cache
        if cache_key in self.keys:
            return self.keys[cache_key]
        
        # Try Docker secret file
        secret_file = self.secrets_dir / key_name
        if secret_file.exists():
            try:
                key = secret_file.read_text().strip()
                self.keys[cache_key] = key
                logger.info(f"Loaded key '{key_name}' (v{version}) from Docker secret")
                return key
            except Exception as e:
                logger.error(f"Failed to read secret file {secret_file}: {e}")
        
        # Try environment variable
        env_key = key_name.upper()
        if env_key in os.environ:
            key = os.environ[env_key].strip()
            self.keys[cache_key] = key
            logger.info(f"Loaded key '{key_name}' (v{version}) from environment")
            return key
        
        # Generate new key in TEST_MODE only
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        if test_mode:
            key = self._generate_test_key()
            self.keys[cache_key] = key
            logger.warning(f"Generated TEST key for '{key_name}' (v{version}) - TEST_MODE ONLY!")
            return key
        
        logger.error(f"Key '{key_name}' (v{version}) not found!")
        return None
    
    def set_key(self, key_name: str, key_value: str, version: int = 1):
        """
        Manually set encryption key
        
        Args:
            key_name: Key identifier
            key_value: Encryption key
            version: Key version
        """
        cache_key = f"{key_name}_v{version}"
        self.keys[cache_key] = key_value
        self.key_versions[key_name] = version
        logger.info(f"Set key '{key_name}' (v{version})")
    
    def rotate_key(self, key_name: str) -> tuple[str, int]:
        """
        Rotate encryption key (increment version)
        
        Args:
            key_name: Key identifier
            
        Returns:
            (new_key, new_version)
        """
        current_version = self.key_versions.get(key_name, 1)
        new_version = current_version + 1
        
        # Generate new key
        new_key = self._generate_key()
        
        # Store new key
        self.set_key(key_name, new_key, new_version)
        
        logger.info(f"Rotated key '{key_name}' from v{current_version} to v{new_version}")
        
        return new_key, new_version
    
    def _generate_key(self, length: int = 32) -> str:
        """
        Generate secure random key
        
        Args:
            length: Key length in bytes
            
        Returns:
            Hex-encoded key
        """
        return secrets.token_hex(length)
    
    def _generate_test_key(self) -> str:
        """
        Generate predictable test key (TEST_MODE only)
        
        Returns:
            Test key
        """
        return "test_key_" + secrets.token_hex(16)
    
    def verify_key(self, key_name: str) -> bool:
        """
        Verify key exists and is valid
        
        Args:
            key_name: Key identifier
            
        Returns:
            True if key exists
        """
        key = self.get_key(key_name)
        return key is not None and len(key) >= 16
    
    def get_all_keys(self) -> Dict[str, str]:
        """
        Get all loaded keys (for debugging)
        
        Returns:
            Dictionary of keys (without values, just names)
        """
        return {name: "***" for name in self.keys.keys()}


# Singleton instance
_key_manager: Optional[KeyManager] = None


def get_key_manager() -> KeyManager:
    """Get or create key manager singleton"""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager()
    return _key_manager


def get_db_key(db_name: str) -> Optional[str]:
    """
    Convenience function to get database encryption key
    
    Args:
        db_name: Database name (e.g., 'users', 'transcripts')
        
    Returns:
        Encryption key
    """
    key_manager = get_key_manager()
    key_name = f"{db_name}_db_key"
    return key_manager.get_key(key_name)







