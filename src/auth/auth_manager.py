"""
Enhanced Authentication and Authorization System
Role-based access control with speaker-based data isolation, encrypted sessions, and persistent storage
"""

import secrets
import hashlib
import time
import bcrypt
import sqlite3
import json
import base64
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding

class UserRole(str, Enum):
    ADMIN = "admin"  # Full system access, sees all transcripts
    USER = "user"    # Limited access, sees only own transcripts (speaker-based isolation)

@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    role: UserRole
    speaker_id: Optional[str] = None  # Maps to speaker identity for data isolation
    email: Optional[str] = None
    created_at: Optional[float] = None
    modified_at: Optional[float] = None

@dataclass
class Session:
    session_token: str
    user_id: str
    role: UserRole
    speaker_id: Optional[str]
    created_at: float
    expires_at: float
    ip_address: Optional[str] = None
    last_refresh: Optional[float] = None

class SessionEncryption:
    """Handles AES-256 encryption/decryption of session tokens"""
    
    def __init__(self, secret_key: bytes):
        """Initialize with 32-byte secret key"""
        if len(secret_key) != 32:
            raise ValueError("Secret key must be exactly 32 bytes")
        self.key = secret_key
        self.backend = default_backend()
    
    def encrypt(self, data: Dict) -> str:
        """Encrypt session data and return base64-encoded token"""
        # Convert dict to JSON
        plaintext = json.dumps(data).encode('utf-8')
        
        # Pad data to AES block size
        padder = sym_padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        
        # Generate random IV
        iv = secrets.token_bytes(16)
        
        # Encrypt
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=self.backend)
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        # Combine IV + ciphertext and encode
        combined = iv + ciphertext
        return base64.urlsafe_b64encode(combined).decode('utf-8')
    
    def decrypt(self, token: str) -> Optional[Dict]:
        """Decrypt base64-encoded token and return session data"""
        try:
            # Decode from base64
            combined = base64.urlsafe_b64decode(token.encode('utf-8'))
            
            # Split IV and ciphertext
            iv = combined[:16]
            ciphertext = combined[16:]
            
            # Decrypt
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=self.backend)
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Unpad
            unpadder = sym_padding.PKCS7(128).unpadder()
            plaintext = unpadder.update(padded_data) + unpadder.finalize()
            
            # Parse JSON
            return json.loads(plaintext.decode('utf-8'))
        except Exception as e:
            print(f"[AUTH] Token decryption failed: {e}")
            return None

class AuthManager:
    """Handles authentication, sessions, and authorization with persistent storage"""
    
    def __init__(self, 
                 db_path: str = "/instance/users.db",
                 secret_key: Optional[bytes] = None,
                 session_duration_hours: int = 24,
                 refresh_interval_hours: int = 1):
        """
        Initialize auth manager with persistent database
        
        Args:
            db_path: Path to SQLite database for user storage
            secret_key: 32-byte key for session encryption (generated if not provided)
            session_duration_hours: Session validity duration
            refresh_interval_hours: Token refresh interval
        """
        self.db_path = db_path
        self.session_duration = session_duration_hours * 3600
        self.refresh_interval = refresh_interval_hours * 3600
        
        # Initialize encryption
        if secret_key is None:
            # Generate and print warning - in production, load from env
            secret_key = secrets.token_bytes(32)
            print(f"[AUTH] WARNING: Generated ephemeral secret key. Set SECRET_KEY in environment for persistence!")
        self.encryptor = SessionEncryption(secret_key)
        
        # In-memory sessions (could be moved to Redis for distributed systems)
        self.sessions: Dict[str, Session] = {}
        
        # Initialize database
        self._init_database()
        self._create_default_users()
        
        print(f"[AUTH] Initialized with database at {db_path}")
    
    def _init_database(self):
        """Create users table if it doesn't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                speaker_id TEXT,
                email TEXT,
                created_at REAL NOT NULL,
                modified_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        print(f"[AUTH] Database initialized at {self.db_path}")
    
    def _create_default_users(self):
        """Create default users if they don't exist"""
        now = time.time()
        
        default_users = [
            User(
                user_id="admin",
                username="admin",
                password_hash=self._hash_password("admin123"),  # CHANGE IN PRODUCTION
                role=UserRole.ADMIN,
                speaker_id=None,  # Admin sees all speakers
                email="admin@nemoserver.local",
                created_at=now,
                modified_at=now
            ),
            User(
                user_id="user1",
                username="user1",
                password_hash=self._hash_password("user1pass"),
                role=UserRole.USER,
                speaker_id="user1",  # Only sees "user1" speaker transcripts
                email="user1@nemoserver.local",
                created_at=now,
                modified_at=now
            ),
            User(
                user_id="television",
                username="television",
                password_hash=self._hash_password("tvpass123"),
                role=UserRole.USER,
                speaker_id="television",  # Only sees "television" speaker transcripts
                email="television@nemoserver.local",
                created_at=now,
                modified_at=now
            )
        ]
        
        for user in default_users:
            if not self.get_user(user.username):
                self._save_user(user)
                print(f"[AUTH] Created default user: {user.username} (role={user.role.value}, speaker={user.speaker_id})")
    
    def _save_user(self, user: User):
        """Save or update user in database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO users 
            (user_id, username, password_hash, role, speaker_id, email, created_at, modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user.user_id,
            user.username,
            user.password_hash,
            user.role.value,
            user.speaker_id,
            user.email,
            user.created_at,
            user.modified_at
        ))
        conn.commit()
        conn.close()
    
    def get_user(self, username: str) -> Optional[User]:
        """Load user from database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return User(
            user_id=row['user_id'],
            username=row['username'],
            password_hash=row['password_hash'],
            role=UserRole(row['role']),
            speaker_id=row['speaker_id'],
            email=row['email'],
            created_at=row['created_at'],
            modified_at=row['modified_at']
        )
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Load user by ID from database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return User(
            user_id=row['user_id'],
            username=row['username'],
            password_hash=row['password_hash'],
            role=UserRole(row['role']),
            speaker_id=row['speaker_id'],
            email=row['email'],
            created_at=row['created_at'],
            modified_at=row['modified_at']
        )
    
    def list_users(self) -> List[Dict]:
        """List all users (without password hashes)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, role, speaker_id, email, created_at, modified_at FROM users")
        rows = cur.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt with cost factor 12"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against bcrypt hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False
    
    def authenticate(self, username: str, password: str, ip_address: Optional[str] = None) -> Optional[str]:
        """
        Authenticate user and create encrypted session
        Returns encrypted session token if successful, None otherwise
        """
        user = self.get_user(username)
        if not user:
            # Prevent timing attacks
            bcrypt.hashpw(b"dummy", bcrypt.gensalt())
            return None
        
        if not self._verify_password(password, user.password_hash):
            return None
        
        # Create session data
        now = time.time()
        session_data = {
            "user_id": user.user_id,
            "role": user.role.value,
            "speaker_id": user.speaker_id,
            "created_at": now,
            "expires_at": now + self.session_duration,
            "ip": ip_address,
            "last_refresh": now
        }
        
        # Encrypt session data to create token
        session_token = self.encryptor.encrypt(session_data)
        
        # Store session in memory
        session = Session(
            session_token=session_token,
            user_id=user.user_id,
            role=user.role,
            speaker_id=user.speaker_id,
            created_at=now,
            expires_at=session_data["expires_at"],
            ip_address=ip_address,
            last_refresh=now
        )
        
        self.sessions[session_token] = session
        
        print(f"[AUTH] User '{username}' authenticated (role={user.role.value}, speaker={user.speaker_id})")
        return session_token
    
    def validate_session(self, session_token: str) -> Optional[Session]:
        """Validate encrypted session token and check expiration"""
        # Check in-memory cache first
        session = self.sessions.get(session_token)
        if session:
            # Check expiration
            if time.time() > session.expires_at:
                del self.sessions[session_token]
                return None
            return session
        
        # Decrypt and validate token
        session_data = self.encryptor.decrypt(session_token)
        if not session_data:
            return None
        
        # Check expiration
        if time.time() > session_data["expires_at"]:
            return None
        
        # Reconstruct session object
        session = Session(
            session_token=session_token,
            user_id=session_data["user_id"],
            role=UserRole(session_data["role"]),
            speaker_id=session_data.get("speaker_id"),
            created_at=session_data["created_at"],
            expires_at=session_data["expires_at"],
            ip_address=session_data.get("ip"),
            last_refresh=session_data.get("last_refresh", session_data["created_at"])
        )
        
        # Cache in memory
        self.sessions[session_token] = session
        return session
    
    def refresh_token(self, session_token: str, ip_address: Optional[str] = None) -> Optional[str]:
        """
        Refresh session token if needed (rotate every refresh_interval)
        Returns new token if refreshed, same token if not needed, None if invalid
        """
        session = self.validate_session(session_token)
        if not session:
            return None
        
        now = time.time()
        
        # Check if refresh is needed
        if now - session.last_refresh < self.refresh_interval:
            return session_token  # No refresh needed
        
        # Create new token with extended expiration
        user = self.get_user_by_id(session.user_id)
        if not user:
            return None
        
        # Invalidate old token
        self.logout(session_token)
        
        # Create new session
        return self.authenticate(user.username, user.password_hash, ip_address or session.ip_address)
    
    def logout(self, session_token: str) -> bool:
        """End session and invalidate token"""
        if session_token in self.sessions:
            del self.sessions[session_token]
            return True
        return False
    
    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Change user password with verification"""
        user = self.get_user(username)
        if not user:
            return False
        
        # Verify old password
        if not self._verify_password(old_password, user.password_hash):
            return False
        
        # Hash new password
        user.password_hash = self._hash_password(new_password)
        user.modified_at = time.time()
        
        # Save to database
        self._save_user(user)
        
        print(f"[AUTH] Password changed for user '{username}'")
        return True
    
    def check_permission(self, session_token: str, required_role: UserRole) -> bool:
        """Check if session has required role or higher"""
        session = self.validate_session(session_token)
        if not session:
            return False
        
        # Role hierarchy: admin > user
        role_levels = {
            UserRole.USER: 1,
            UserRole.ADMIN: 2
        }
        
        user_level = role_levels.get(session.role, 0)
        required_level = role_levels.get(required_role, 999)
        
        return user_level >= required_level
    
    def get_user_info(self, session_token: str) -> Optional[Dict]:
        """Get user info from session"""
        session = self.validate_session(session_token)
        if not session:
            return None
        
        user = self.get_user_by_id(session.user_id)
        if not user:
            return None
        
        return {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role.value,
            "speaker_id": user.speaker_id,
            "email": user.email
        }
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions (call periodically)"""
        now = time.time()
        expired = [token for token, session in self.sessions.items() if session.expires_at < now]
        for token in expired:
            del self.sessions[token]
        
        if expired:
            print(f"[AUTH] Cleaned up {len(expired)} expired sessions")
        return len(expired)

# Global auth manager instance
# Secret key should be loaded from environment in production
auth_manager = None

def init_auth_manager(secret_key: Optional[bytes] = None, db_path: str = "/instance/users.db"):
    """Initialize global auth manager"""
    global auth_manager
    auth_manager = AuthManager(secret_key=secret_key, db_path=db_path)
    return auth_manager

def get_auth_manager() -> AuthManager:
    """Get global auth manager instance"""
    if auth_manager is None:
        raise RuntimeError("Auth manager not initialized. Call init_auth_manager() first.")
    return auth_manager
