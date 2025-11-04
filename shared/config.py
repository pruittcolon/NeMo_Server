"""
Centralized Configuration
Includes TEST_MODE for security testing
"""

import os
import logging

logger = logging.getLogger(__name__)


class SecurityConfig:
    """Security configuration"""
    
    # Test mode flag (NEVER enable in production!)
    TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
    
    # Security features - controlled by TEST_MODE
    ENABLE_DB_ENCRYPTION = not TEST_MODE
    ENABLE_SERVICE_AUTH = not TEST_MODE
    ENABLE_RATE_LIMITING = True  # Always on
    ENABLE_AUDIT_LOGGING = True  # Always on
    ENABLE_CSRF = not TEST_MODE
    ENABLE_IP_WHITELIST = not TEST_MODE
    
    # CSRF settings
    CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "ws_csrf")
    CSRF_HEADER_NAME = os.getenv("CSRF_HEADER_NAME", "X-CSRF-Token")
    
    # Session settings
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "ws_session")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    SESSION_DURATION_SECONDS = int(os.getenv("SESSION_DURATION_SECONDS", "86400"))  # 24 hours
    
    # Audit settings
    AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "90"))
    
    # Warn if TEST_MODE is enabled
    if TEST_MODE:
        logger.warning("")
        logger.warning("=" * 70)
        logger.warning("⚠️  WARNING: TEST_MODE ENABLED - SECURITY REDUCED!")
        logger.warning("=" * 70)
        logger.warning("  - Database encryption: DISABLED (using test key)")
        logger.warning("  - Service auth: DISABLED (accepts test JWT or bypass)")
        logger.warning("  - CSRF: DISABLED")
        logger.warning("  - IP Whitelist: DISABLED")
        logger.warning("=" * 70)
        logger.warning("  ❌ NEVER deploy to production with TEST_MODE=true!")
        logger.warning("=" * 70)
        logger.warning("")


class DatabaseConfig:
    """Database configuration"""
    
    # PostgreSQL (for task persistence)
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "nemo_queue")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    
    @classmethod
    def get_postgres_url(cls) -> str:
        """Get PostgreSQL connection URL"""
        return f"postgresql://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"


class RedisConfig:
    """Redis configuration"""
    
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
    
    @classmethod
    def get_redis_url(cls) -> str:
        """Get Redis connection URL"""
        if cls.REDIS_PASSWORD:
            return f"redis://:{cls.REDIS_PASSWORD}@{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"
        return f"redis://{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"


class ServiceConfig:
    """Service URLs and ports"""
    
    GPU_COORDINATOR_URL = os.getenv("GPU_COORDINATOR_URL", "http://gpu-coordinator:8002")
    GEMMA_SERVICE_URL = os.getenv("GEMMA_SERVICE_URL", "http://gemma-service:8001")
    RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service:8004")
    TRANSCRIPTION_SERVICE_URL = os.getenv("TRANSCRIPTION_SERVICE_URL", "http://transcription-service:8003")
    EMOTION_SERVICE_URL = os.getenv("EMOTION_SERVICE_URL", "http://emotion-service:8005")
    API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://api-service:8000")


class ModelConfig:
    """Model paths and configuration"""
    
    EMOTION_MODEL = os.getenv("EMOTION_MODEL", "j-hartmann/emotion-english-distilroberta-base")
    EMOTION_MODEL_PATH = os.getenv("EMOTION_MODEL_PATH", "/app/models/hf_home/models--j-hartmann--emotion-english-distilroberta-base/snapshots/0e1cd914e3d46199ed785853e12b57304e04178b")
    ALLOW_MODEL_DOWNLOAD = os.getenv("ALLOW_MODEL_DOWNLOAD", "false").lower() in ("true", "1", "yes")  # Use local cache only by default

