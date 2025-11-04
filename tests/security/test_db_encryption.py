"""
Database Encryption Security Tests
Verifies SQLCipher encryption is working correctly
"""

import os
import sqlite3
import pytest
import tempfile
from pathlib import Path

# Add parent to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.crypto.db_encryption import EncryptedDatabase, create_encrypted_db


class TestDatabaseEncryption:
    """Test database encryption with SQLCipher"""
    
    def test_encrypted_db_creation(self):
        """
        Test creating an encrypted database
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_encrypted.db")
            key = "test_encryption_key_32_chars_min"
            
            # Create encrypted database
            db = create_encrypted_db(
                db_path=db_path,
                encryption_key=key,
                use_encryption=True
            )
            
            # Create table and insert data
            with db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS secrets (
                        id INTEGER PRIMARY KEY,
                        secret_data TEXT NOT NULL
                    )
                """)
                db.execute("INSERT INTO secrets (secret_data) VALUES (?)", ("sensitive_info",))
            
            print(f"✓ Encrypted database created: {db_path}")
            
            # Verify file exists
            assert os.path.exists(db_path)
    
    def test_encryption_prevents_direct_read(self):
        """
        Test that encrypted database cannot be read without key
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_encrypted.db")
            key = "test_encryption_key_32_chars_min"
            
            # Create and populate encrypted database
            db = create_encrypted_db(db_path, key, use_encryption=True)
            with db:
                db.execute("CREATE TABLE test (data TEXT)")
                db.execute("INSERT INTO test VALUES (?)", ("secret_data",))
            
            # Try to read with standard SQLite (should fail)
            try:
                conn = sqlite3.connect(db_path)
                conn.execute("SELECT * FROM test")
                pytest.fail("Database should be encrypted and unreadable!")
            except sqlite3.DatabaseError:
                # Expected: database is encrypted
                print("✓ Direct read blocked (database encrypted)")
            finally:
                conn.close()
    
    def test_wrong_key_fails(self):
        """
        Test that wrong encryption key fails to open database
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_encrypted.db")
            correct_key = "correct_key_32_chars_minimum!!"
            wrong_key = "wrong_key_32_chars_minimum___!!"
            
            # Create with correct key
            db = create_encrypted_db(db_path, correct_key, use_encryption=True)
            with db:
                db.execute("CREATE TABLE test (data TEXT)")
                db.execute("INSERT INTO test VALUES (?)", ("secret",))
            
            # Try to open with wrong key (should fail)
            db_wrong = create_encrypted_db(db_path, wrong_key, use_encryption=True)
            
            with pytest.raises(Exception):
                # This should fail with wrong key
                db_wrong.connect()
                db_wrong.execute("SELECT * FROM test").fetchall()
            
            print("✓ Wrong key rejected")
    
    def test_unencrypted_mode_works(self):
        """
        Test that unencrypted mode works (for TEST_MODE)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_unencrypted.db")
            
            # Create unencrypted database
            db = create_encrypted_db(db_path, None, use_encryption=False)
            
            with db:
                db.execute("CREATE TABLE test (data TEXT)")
                db.execute("INSERT INTO test VALUES (?)", ("test_data",))
                
                # Read data
                result = db.execute("SELECT * FROM test").fetchone()
                assert result[0] == "test_data"
            
            # Verify can read with standard SQLite
            conn = sqlite3.connect(db_path)
            result = conn.execute("SELECT * FROM test").fetchone()
            assert result[0] == "test_data"
            conn.close()
            
            print("✓ Unencrypted mode works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])





