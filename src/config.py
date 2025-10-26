import os
from pathlib import Path
from dotenv import load_dotenv


def _ensure_dir(path: Path) -> Path:
    """Create directory if missing and return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


# Load environment variables from a local .env file if present
# Look for .env in the project root (parent of src/)
_SRC_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT_PATH = _SRC_DIR.parent
env_path = _PROJECT_ROOT_PATH / ".env"
load_dotenv(dotenv_path=env_path)

# Core filesystem layout (can be overridden via env vars)
_INSTANCE_DIR_PATH = Path(os.environ.get("INSTANCE_DIR", str(_PROJECT_ROOT_PATH / "instance")))
_MODELS_ROOT_PATH = Path(os.environ.get("MODELS_ROOT", str(_PROJECT_ROOT_PATH / "models")))
_LOGS_DIR_PATH = Path(os.environ.get("LOGS_DIR", str(_PROJECT_ROOT_PATH / "logs")))

# Debug logging for path resolution
print(f"[CONFIG] PROJECT_ROOT: {_PROJECT_ROOT_PATH}")
print(f"[CONFIG] INSTANCE_DIR from env: {os.environ.get('INSTANCE_DIR', 'NOT SET')}")
print(f"[CONFIG] Resolved INSTANCE_DIR: {_INSTANCE_DIR_PATH}")
print(f"[CONFIG] Resolved MODELS_ROOT: {_MODELS_ROOT_PATH}")
print(f"[CONFIG] Resolved LOGS_DIR: {_LOGS_DIR_PATH}")

# Don't try to create dirs at import time - they should exist as Docker volume mounts
# If they don't exist, they'll be created by main.py during initialization
# _INSTANCE_DIR_PATH = _ensure_dir(_INSTANCE_DIR_PATH)
# _MODELS_ROOT_PATH = _ensure_dir(_MODELS_ROOT_PATH)
# _LOGS_DIR_PATH = _ensure_dir(_LOGS_DIR_PATH)

_UPLOAD_DIR_PATH = Path(os.environ.get("UPLOAD_DIR", _INSTANCE_DIR_PATH / "uploads"))
_CACHE_DIR_PATH = Path(os.environ.get("CACHE_DIR", _INSTANCE_DIR_PATH / "cache"))

PROJECT_ROOT = str(_PROJECT_ROOT_PATH)
INSTANCE_DIR = str(_INSTANCE_DIR_PATH)

# ASR Backend selection
ASR_BACKEND = os.environ.get("ASR_BACKEND", "parakeet").lower()
ASR_BATCH = int(os.environ.get("ASR_BATCH", "1"))

# Speaker enrollment matching
ENROLL_MATCH_THRESHOLD = float(os.environ.get("ENROLL_MATCH_THRESHOLD", "0.30"))

# Diarization backend (lite | nemo)
DIAR_BACKEND = os.environ.get("DIAR_BACKEND", "lite").lower()

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}

# Allow huggingface model downloads when local cache is missing
ALLOW_MODEL_DOWNLOAD = _env_bool("ALLOW_MODEL_DOWNLOAD", default=True)
os.environ.setdefault("TRANSFORMERS_OFFLINE", "0" if ALLOW_MODEL_DOWNLOAD else "1")

# Single-speaker fallback: if only one diarized speaker and similarity is decent,
# map to PRIMARY_SPEAKER_LABEL to avoid SPK_00 on solo recordings
SINGLE_SPK_ENROLL_FALLBACK = (os.environ.get("SINGLE_SPK_ENROLL_FALLBACK", "1") in {"1","true","True","TRUE"})
SINGLE_SPK_MIN_SIM = float(os.environ.get("SINGLE_SPK_MIN_SIM", "0.60"))

# Server Configuration
# The host the FastAPI server will bind to.
# For WireGuard/Docker, 0.0.0.0 is standard and allows it to be reached from the private network.
# For local-only testing, you can set FASTAPI_HOST=127.0.0.1 in your .env.local file.
HOST = os.environ.get("FASTAPI_HOST", "0.0.0.0")

# The port the FastAPI server will run on.
PORT = int(os.environ.get("FASTAPI_PORT", 8000))

# Security Configuration
# SECRET_KEY: 32-byte hex string for session encryption
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY_HEX = os.environ.get("SECRET_KEY")
if SECRET_KEY_HEX:
    SECRET_KEY = bytes.fromhex(SECRET_KEY_HEX)
else:
    # Generate ephemeral key (WARNING: sessions won't persist across restarts)
    import secrets
    SECRET_KEY = secrets.token_bytes(32)
    print("[CONFIG] WARNING: No SECRET_KEY set. Using ephemeral key. Set SECRET_KEY env var for production!")

# DB_ENCRYPTION_KEY: 32-byte hex string for database encryption
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
DB_ENCRYPTION_KEY_HEX = os.environ.get("DB_ENCRYPTION_KEY")
if DB_ENCRYPTION_KEY_HEX:
    DB_ENCRYPTION_KEY = bytes.fromhex(DB_ENCRYPTION_KEY_HEX)
else:
    # Generate ephemeral key
    import secrets
    DB_ENCRYPTION_KEY = secrets.token_bytes(32)
    print("[CONFIG] WARNING: No DB_ENCRYPTION_KEY set. Using ephemeral key. Set DB_ENCRYPTION_KEY env var for production!")

# Session configuration
SESSION_DURATION_HOURS = int(os.environ.get("SESSION_DURATION_HOURS", "24"))
TOKEN_REFRESH_INTERVAL_HOURS = int(os.environ.get("TOKEN_REFRESH_INTERVAL_HOURS", "1"))

# Rate limiting
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() in {"true", "1", "yes"}

# IP Whitelist (for WireGuard)
ALLOWED_IPS = os.environ.get("ALLOWED_IPS", "").split(",") if os.environ.get("ALLOWED_IPS") else []
IP_WHITELIST_ENABLED = os.environ.get("IP_WHITELIST_ENABLED", "false").lower() in {"true", "1", "yes"}

# User database path
USERS_DB_PATH = str(_INSTANCE_DIR_PATH / "users.db")

# Model Configuration
WHISPER_MODEL = "small"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"
MODELS_ROOT = str(_MODELS_ROOT_PATH)
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", MODELS_ROOT)
os.environ.setdefault("HF_HOME", os.path.join(MODELS_ROOT, "hf_home"))
os.environ.setdefault("TRANSFORMERS_CACHE", os.environ.get("HF_HOME", os.path.join(MODELS_ROOT, "hf_home")))

GEMMA_MODEL_PATH = os.path.join(MODELS_ROOT, "gemma-3-4b-it-UD-Q4_K_XL.gguf")  # 4B quantized model

# GPU Configuration Notes:
# GTX 1660 Ti: 6 GB VRAM total
# - Parakeet TDT (ASR): ~1.5 GB (priority for transcription)
# - Gemma 3 (LLM): ~3 GB (n_gpu_layers=20 in advanced_memory_service.py)
# - Buffer: ~1.5 GB (safety margin)
#
# To adjust Gemma VRAM usage, edit advanced_memory_service.py line ~254:
#   - Increase layers (25-30) if more VRAM available and want faster responses
#   - Decrease layers (15-18) if OOM errors persist
#   - Set to -1 for all layers (dev/testing only, disables transcription)

# Diarization & Speaker Labels (removed for open-source release)
# Users can create their own speaker enrollments via the speaker service
# Default speakers are defined in auth_manager.py: admin, user1, television
SECONDARY_CONFIDENCE_THRESHOLD = 0.65

# Paths
DB_PATH = str(Path(os.environ.get("DB_PATH", _INSTANCE_DIR_PATH / "memories.db")))
UPLOAD_DIR = str(_UPLOAD_DIR_PATH)
LOGS_DIR = str(_LOGS_DIR_PATH)
CACHE_DIR = str(_CACHE_DIR_PATH)

# Model paths - Use HuggingFace cache for auto-downloads
# Don't set SENTENCE_TRANSFORMERS_HOME to models/ (let it use HF cache)
EMBEDDING_MODEL_PATH = os.environ.get(
    "EMBEDDING_MODEL_PATH",
    EMBEDDING_MODEL,  # Use model name, will download to HF cache
)
EMOTION_MODEL_PATH = os.environ.get(
    "EMOTION_MODEL_PATH",
    os.path.join(
        MODELS_ROOT,
        EMOTION_MODEL.split("/")[-1],
    ),
)

# Audio Processing
OVERLAP_SECS = float(os.environ.get("OVERLAP_SECS", "0.7"))
SEGMENT_MIN_SECONDS = 1.0

# Hugging Face Token (loaded from environment)
HF_TOKEN = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")

# --- Utility Functions ---
import socket

def _port_in_use(host: str, port: int) -> bool:
    """Checks if a port is already in use on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0
