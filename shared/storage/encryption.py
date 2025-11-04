"""
Database Encryption Module
Implements AES-256-GCM encryption for sensitive data at rest
"""

import base64
import secrets
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend

class DataEncryption:
    """AES-256-GCM encryption for database fields"""
    
    def __init__(self, encryption_key: bytes):
        """
        Initialize encryption with 32-byte key
        
        Args:
            encryption_key: 32-byte encryption key
        """
        if len(encryption_key) != 32:
            raise ValueError("Encryption key must be exactly 32 bytes")
        
        self.key = encryption_key
        self.cipher = AESGCM(encryption_key)
    
    def encrypt_text(self, plaintext: str) -> Tuple[str, str]:
        """
        Encrypt text and return (ciphertext, iv) as base64 strings
        
        Args:
            plaintext: Text to encrypt
            
        Returns:
            Tuple of (encrypted_text_b64, iv_b64)
        """
        if not plaintext:
            return ("", "")
        
        # Generate random 96-bit nonce (12 bytes for GCM)
        nonce = secrets.token_bytes(12)
        
        # Encrypt
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext = self.cipher.encrypt(nonce, plaintext_bytes, None)
        
        # Encode to base64 for storage
        ciphertext_b64 = base64.b64encode(ciphertext).decode('utf-8')
        nonce_b64 = base64.b64encode(nonce).decode('utf-8')
        
        return (ciphertext_b64, nonce_b64)
    
    def decrypt_text(self, ciphertext_b64: str, nonce_b64: str) -> Optional[str]:
        """
        Decrypt text from base64-encoded ciphertext and nonce
        
        Args:
            ciphertext_b64: Base64-encoded ciphertext
            nonce_b64: Base64-encoded nonce
            
        Returns:
            Decrypted plaintext or None if decryption fails
        """
        if not ciphertext_b64 or not nonce_b64:
            return ""
        
        try:
            # Decode from base64
            ciphertext = base64.b64decode(ciphertext_b64)
            nonce = base64.b64decode(nonce_b64)
            
            # Decrypt
            plaintext_bytes = self.cipher.decrypt(nonce, ciphertext, None)
            
            return plaintext_bytes.decode('utf-8')
        
        except Exception as e:
            print(f"[ENCRYPTION] Decryption failed: {e}")
            return None
    
    def encrypt_dict(self, data: dict) -> dict:
        """
        Encrypt all string values in a dictionary
        
        Args:
            data: Dictionary with plaintext values
            
        Returns:
            Dictionary with encrypted values and _iv fields
        """
        encrypted = {}
        for key, value in data.items():
            if isinstance(value, str) and value:
                ciphertext, nonce = self.encrypt_text(value)
                encrypted[key] = ciphertext
                encrypted[f"{key}_iv"] = nonce
            else:
                encrypted[key] = value
        
        return encrypted
    
    def decrypt_dict(self, data: dict, encrypted_fields: list) -> dict:
        """
        Decrypt specified fields in a dictionary
        
        Args:
            data: Dictionary with encrypted values
            encrypted_fields: List of field names to decrypt
            
        Returns:
            Dictionary with decrypted values
        """
        decrypted = data.copy()
        for field in encrypted_fields:
            if field in data and f"{field}_iv" in data:
                ciphertext = data[field]
                nonce = data[f"{field}_iv"]
                
                if ciphertext and nonce:
                    plaintext = self.decrypt_text(ciphertext, nonce)
                    decrypted[field] = plaintext
                    # Remove _iv field from output
                    decrypted.pop(f"{field}_iv", None)
        
        return decrypted

# Global encryptor instance
_encryptor: Optional[DataEncryption] = None

def init_encryption(encryption_key: bytes):
    """Initialize global encryption instance"""
    global _encryptor
    _encryptor = DataEncryption(encryption_key)
    print("[ENCRYPTION] Initialized AES-256-GCM encryption")
    return _encryptor

def get_encryptor() -> DataEncryption:
    """Get global encryption instance"""
    if _encryptor is None:
        raise RuntimeError("Encryption not initialized. Call init_encryption() first.")
    return _encryptor

def encrypt_text(plaintext: str) -> Tuple[str, str]:
    """Convenience function to encrypt text"""
    return get_encryptor().encrypt_text(plaintext)

def decrypt_text(ciphertext_b64: str, nonce_b64: str) -> Optional[str]:
    """Convenience function to decrypt text"""
    return get_encryptor().decrypt_text(ciphertext_b64, nonce_b64)


