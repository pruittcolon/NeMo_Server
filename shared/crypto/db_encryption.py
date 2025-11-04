"""
Database Encryption with SQLCipher
Provides transparent AES-256 encryption for SQLite databases
"""

import os
import sqlite3
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import pysqlcipher3 for encryption
try:
    from pysqlcipher3 import dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    logger.warning("pysqlcipher3 not available - database encryption disabled")
    SQLCIPHER_AVAILABLE = False


class EncryptedDatabase:
    """
    Encrypted SQLite database wrapper using SQLCipher
    
    Provides transparent AES-256 encryption for sensitive data:
    - User credentials
    - Session data
    - Transcripts
    - Memory/RAG content
    - Audit logs
    """
    
    def __init__(
        self,
        db_path: str,
        encryption_key: Optional[str] = None,
        use_encryption: bool = True,
        connect_kwargs: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize encrypted database
        
        Args:
            db_path: Path to database file
            encryption_key: Encryption key (from Docker secrets)
            use_encryption: Whether to use encryption (disable for TEST_MODE)
        """
        self.db_path = db_path
        self.use_encryption = use_encryption and SQLCIPHER_AVAILABLE
        self.encryption_key = encryption_key
        self.connection: Optional[sqlite3.Connection] = None
        self.connect_kwargs: Dict[str, Any] = connect_kwargs or {}
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        if self.use_encryption and not self.encryption_key:
            raise ValueError("Encryption key required when use_encryption=True")
        
        if self.use_encryption:
            logger.info(f"Encrypted database initialized: {db_path}")
        else:
            logger.warning(f"Database encryption DISABLED: {db_path}")
    
    def connect(self) -> sqlite3.Connection:
        """
        Connect to encrypted database
        
        Returns:
            SQLite connection
        """
        if self.connection:
            try:
                # Verify connection is still open
                self.connection.execute("SELECT 1")
                return self.connection
            except sqlite3.ProgrammingError:
                # Connection was closed elsewhere; reset and recreate
                self.connection = None
        if self.connection:
            return self.connection
        
        if self.use_encryption:
            # Use SQLCipher for encryption
            self.connection = sqlcipher.connect(self.db_path, **self.connect_kwargs)
            
            # Set encryption key
            self.connection.execute(f"PRAGMA key = '{self.encryption_key}'")
            
            # Configure SQLCipher for AES-256
            self.connection.execute("PRAGMA cipher = 'aes-256-cbc'")
            self.connection.execute("PRAGMA kdf_iter = 64000")  # PBKDF2 iterations
            
            logger.info(f"Connected to encrypted database: {self.db_path}")
        else:
            # Use standard SQLite (no encryption)
            self.connection = sqlite3.connect(self.db_path, **self.connect_kwargs)
            logger.info(f"Connected to unencrypted database: {self.db_path}")
        
        # Enable WAL mode for better concurrency
        self.connection.execute("PRAGMA journal_mode=WAL")
        
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys=ON")
        
        return self.connection
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info(f"Closed database connection: {self.db_path}")
    
    def execute(self, query: str, params: tuple = ()):
        """
        Execute SQL query
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            Cursor
        """
        if not self.connection:
            self.connect()
        
        return self.connection.execute(query, params)
    
    def executemany(self, query: str, params_list: list):
        """
        Execute SQL query with multiple parameter sets
        
        Args:
            query: SQL query
            params_list: List of parameter tuples
        """
        if not self.connection:
            self.connect()
        
        return self.connection.executemany(query, params_list)
    
    def commit(self):
        """Commit transaction"""
        if self.connection:
            self.connection.commit()
    
    def rollback(self):
        """Rollback transaction"""
        if self.connection:
            self.connection.rollback()
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
    
    def verify_encryption(self) -> bool:
        """
        Verify database is encrypted
        
        Tries to read database file directly - should fail if encrypted
        
        Returns:
            True if encrypted (read fails), False if not encrypted
        """
        if not self.use_encryption:
            return False
        
        try:
            # Try to open database without key
            test_conn = sqlite3.connect(self.db_path)
            test_conn.execute("SELECT * FROM sqlite_master LIMIT 1")
            test_conn.close()
            
            # If we got here, database is NOT encrypted
            logger.error(f"Database verification FAILED: {self.db_path} is not encrypted!")
            return False
            
        except sqlite3.DatabaseError:
            # Good! Database is encrypted and can't be read without key
            logger.info(f"Database encryption verified: {self.db_path}")
            return True
    
    def rekey(self, new_key: str):
        """
        Change encryption key (key rotation)
        
        Args:
            new_key: New encryption key
        """
        if not self.use_encryption:
            raise RuntimeError("Cannot rekey unencrypted database")
        
        if not self.connection:
            self.connect()
        
        logger.info(f"Rotating encryption key for: {self.db_path}")
        
        # Change key
        self.connection.execute(f"PRAGMA rekey = '{new_key}'")
        self.connection.commit()
        
        # Update stored key
        self.encryption_key = new_key
        
        logger.info(f"Encryption key rotated successfully: {self.db_path}")


def create_encrypted_db(
    db_path: str,
    encryption_key: Optional[str] = None,
    use_encryption: bool = True,
    connect_kwargs: Optional[Dict[str, Any]] = None
) -> EncryptedDatabase:
    """
    Factory function to create encrypted database
    
    Args:
        db_path: Path to database file
        encryption_key: Encryption key (from Docker secrets)
        use_encryption: Whether to use encryption
        
    Returns:
        EncryptedDatabase instance
    """
    return EncryptedDatabase(
        db_path=db_path,
        encryption_key=encryption_key,
        use_encryption=use_encryption,
        connect_kwargs=connect_kwargs
    )



