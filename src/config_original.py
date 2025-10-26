import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from a local .env file if present
# Look for .env in the project root (parent of src/)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
# ASR Backend selection
ASR_BACKEND = os.environ.get("ASR_BACKEND", "parakeet").lower()
ASR_BATCH = int(os.environ.get("ASR_BATCH", "1"))

# Speaker enrollment matching
ENROLL_MATCH_THRESHOLD = float(os.environ.get("ENROLL_MATCH_THRESHOLD", "0.60"))

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

# Model Configuration
WHISPER_MODEL = "small"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"
MODELS_ROOT = os.path.join(os.getcwd(), "models")
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", MODELS_ROOT)
os.environ.setdefault("HF_HOME", os.path.join(MODELS_ROOT, "hf_home"))
os.environ.setdefault("TRANSFORMERS_CACHE", os.environ.get("HF_HOME", os.path.join(MODELS_ROOT, "hf_home")))

GEMMA_MODEL_PATH = os.path.join(MODELS_ROOT, "gemma-3-4b-it-Q4_K_M.gguf")

# Diarization & Speaker Labels
PRIMARY_SPEAKER_LABEL = "Pruitt"
SECONDARY_SPEAKER_LABEL = "Ericah"
SECONDARY_CONFIDENCE_THRESHOLD = 0.65

# Paths
DB_PATH = os.path.join(os.getcwd(), "instance", "memories.db")
UPLOAD_DIR = os.path.join(os.getcwd(), "instance", "uploads")
LOGS_DIR = os.path.join(os.getcwd(), "daily_logs")
CACHE_DIR = os.path.join(os.getcwd(), "instance", "cache")

# Model paths (allow override via environment variables)
EMBEDDING_MODEL_PATH = os.environ.get(
    "EMBEDDING_MODEL_PATH",
    os.path.join(MODELS_ROOT, EMBEDDING_MODEL.replace("/", os.sep)),
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
