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
TEST_MODE = os.getenv("TEST_MODE", "false").lower() in {"1", "true", "yes"}
ALLOW_PLAINTEXT_FALLBACK = os.getenv("ALLOW_PLAINTEXT_FALLBACK", "false").lower() in {"1", "true", "yes"}

# Try to import SQLCipher DB-API. Prefer pysqlcipher3, fall back to sqlcipher3.
SQLCIPHER_AVAILABLE = False
sqlcipher = None
try:
    from pysqlcipher3 import dbapi2 as sqlcipher  # type: ignore
    SQLCIPHER_AVAILABLE = True
except Exception:
    try:
        from sqlcipher3 import dbapi2 as sqlcipher  # type: ignore
        SQLCIPHER_AVAILABLE = True
    except Exception:
        SQLCIPHER_AVAILABLE = False
        logger.warning("SQLCipher not available (pysqlcipher3/sqlcipher3 not found) - database encryption disabled")


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
        self.requested_encryption = bool(use_encryption)
        self.use_encryption = bool(use_encryption)
        self.encryption_key = encryption_key
        self.connection: Optional[sqlite3.Connection] = None
        self.connect_kwargs: Dict[str, Any] = connect_kwargs or {}
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        if self.use_encryption and not SQLCIPHER_AVAILABLE:
            if TEST_MODE or ALLOW_PLAINTEXT_FALLBACK:
                logger.warning(
                    "SQLCipher not available but encryption requested for %s – falling back to plaintext (TEST_MODE=%s, ALLOW_PLAINTEXT_FALLBACK=%s)",
                    db_path,
                    TEST_MODE,
                    ALLOW_PLAINTEXT_FALLBACK,
                )
                self.use_encryption = False
            else:
                raise RuntimeError(
                    "SQLCipher is required for encrypted database access but is not installed. "
                    "Install pysqlcipher3/sqlcipher3 or disable encryption explicitly."
                )
        
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
            except Exception:
                self.connection = None
        if self.connection:
            return self.connection
        
        if self.use_encryption:
            try:
                # Use SQLCipher for encryption
                self.connection = sqlcipher.connect(self.db_path, **self.connect_kwargs)
                # Set encryption key
                self.connection.execute(f"PRAGMA key = '{self.encryption_key}'")
                # Configure SQLCipher for AES-256
                self.connection.execute("PRAGMA cipher = 'aes-256-cbc'")
                self.connection.execute("PRAGMA kdf_iter = 64000")  # PBKDF2 iterations
                logger.info(f"Connected to encrypted database: {self.db_path}")
            except Exception as exc:
                # Common when an existing plaintext DB is opened with a key
                msg = str(exc).lower()
                if "file is not a database" in msg or "not a database" in msg or "hmac" in msg:
                    logger.warning("Encrypted open failed; attempting plaintext->encrypted migration: %s", exc)
                    try:
                        self._migrate_plain_to_encrypted()
                        # Reconnect after migration
                        self.connection = sqlcipher.connect(self.db_path, **self.connect_kwargs)
                        self.connection.execute(f"PRAGMA key = '{self.encryption_key}'")
                        self.connection.execute("PRAGMA cipher = 'aes-256-cbc'")
                        self.connection.execute("PRAGMA kdf_iter = 64000")
                        logger.info("Plaintext database migrated to SQLCipher successfully")
                    except Exception as mexc:
                        logger.error("Plaintext->encrypted migration failed: %s; falling back to plaintext", mexc)
                        self.use_encryption = False
                        self.connection = None  # force plaintext connection below
                else:
                    raise
        if not self.connection:
            # Use standard SQLite (no encryption)
            self.connection = sqlite3.connect(self.db_path, **self.connect_kwargs)
            logger.info(f"Connected to unencrypted database: {self.db_path}")
        
        # Enable WAL mode for better concurrency. If encryption was requested but
        # the underlying file is plaintext, SQLCipher may raise here. Attempt
        # one-time migration and retry.
        try:
            self.connection.execute("PRAGMA journal_mode=WAL")
        except Exception as exc:
            if self.use_encryption and ("not a database" in str(exc).lower() or "hmac" in str(exc).lower()):
                logger.warning("WAL pragma failed under SQLCipher; attempting migration: %s", exc)
                # Close broken handle and migrate
                try:
                    self.connection.close()
                except Exception:
                    pass
                self.connection = None
                try:
                    self._migrate_plain_to_encrypted()
                    # Reconnect encrypted
                    self.connection = sqlcipher.connect(self.db_path, **self.connect_kwargs)
                    self.connection.execute(f"PRAGMA key = '{self.encryption_key}'")
                    self.connection.execute("PRAGMA cipher = 'aes-256-cbc'")
                    self.connection.execute("PRAGMA kdf_iter = 64000")
                    self.connection.execute("PRAGMA journal_mode=WAL")
                    logger.info("Post-migration WAL enabled")
                except Exception as mexc:
                    logger.error("Migration on WAL fail also failed: %s; falling back to plaintext", mexc)
                    self.use_encryption = False
                    self.connection = sqlite3.connect(self.db_path, **self.connect_kwargs)
                    self.connection.execute("PRAGMA journal_mode=WAL")
            else:
                raise
        
        # Enable foreign keys
        self.connection.execute("PRAGMA foreign_keys=ON")
        
        return self.connection

    def _migrate_plain_to_encrypted(self) -> None:
        """Migrate existing plaintext SQLite DB to SQLCipher in-place.

        Creates a temporary encrypted copy using sqlcipher3/pysqlcipher3 and sqlcipher_export,
        then atomically replaces the original file.
        """
        if not SQLCIPHER_AVAILABLE:
            raise RuntimeError("SQLCipher not available for migration")
        src_path = self.db_path
        tmp_path = f"{src_path}.enc_tmp"
        # Remove any stale temp
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        # Create encrypted DB and export from plaintext
        conn = sqlcipher.connect(tmp_path)
        try:
            conn.execute(f"PRAGMA key = '{self.encryption_key}'")
            conn.execute("PRAGMA cipher = 'aes-256-cbc'")
            conn.execute("PRAGMA kdf_iter = 64000")
            # Attach plaintext DB with empty key
            # Escape single quotes in path
            esc_src = str(src_path).replace("'", "''")
            conn.execute(f"ATTACH DATABASE '{esc_src}' AS plaintext KEY ''")
            conn.execute("SELECT sqlcipher_export('main', 'plaintext')")
            conn.execute("DETACH DATABASE plaintext")
            conn.commit()
        finally:
            conn.close()
        # Replace original DB
        backup = f"{src_path}.bak"
        try:
            if os.path.exists(backup):
                os.remove(backup)
        except Exception:
            pass
        os.replace(src_path, backup)
        os.replace(tmp_path, src_path)
        try:
            os.chmod(src_path, 0o600)
        except Exception:
            pass
    
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
