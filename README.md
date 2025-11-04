# Nemo Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-24.0+-blue.svg)](https://www.docker.com/)
[![CUDA](https://img.shields.io/badge/CUDA-12.6+-green.svg)](https://developer.nvidia.com/cuda-downloads)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**AI-Powered Conversational Memory & Transcription System**

A microservices-based platform that provides real-time speech transcription, speaker diarization, emotion analysis, semantic memory search, and AI-powered conversational responses. Built for smart glasses and voice-first applications.

---

## 🎯 What It Does

Nemo Server transforms conversations into searchable, analyzable knowledge:

1. **Transcribe**: Real-time speech-to-text with speaker identification
2. **Analyze**: Emotion detection and audio quality metrics  
3. **Remember**: Semantic search across all conversations
4. **Respond**: AI assistant with full conversational context

Perfect for:
- Meeting transcription and analysis
- Smart glasses (AR/VR) voice interfaces
- Personal memory augmentation
- Conversational AI applications
- Voice-controlled systems

---

## 🏗️ Architecture

### Microservices Overview

```
┌─────────────┐
│   Client    │ (Flutter App, Web Browser)
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│  API Gateway (Port 8000)                                     │
│  • Authentication & Sessions                                 │
│  • Request Routing                                           │
│  • Frontend Serving                                          │
└──────┬───────┬───────┬───────┬────────┬──────────────────────┘
       │       │       │       │        │
    ┌──▼──┐ ┌─▼──┐ ┌──▼───┐ ┌─▼────┐ ┌▼──────────┐
    │Trans│ │Emo │ │ RAG  │ │Gemma │ │    GPU    │
    │cript│ │tion│ │Search│ │  AI  │ │Coordinator│
    └──┬──┘ └────┘ └──────┘ └──┬───┘ └───────────┘
       │                       │
       └───────┬───────────────┘
               │ Shared GPU
         ┌─────▼─────┐
         │  GPU 0    │
         │ (NVIDIA)  │
         └───────────┘

Infrastructure:
  • Redis (Pub/Sub, Caching, Locking)
  • PostgreSQL (Task Queue)
  • Encrypted SQLite (User Data, Transcripts)
```

### Service Breakdown

| Service | Port | Purpose | GPU | Key Tech |
|---------|------|---------|-----|----------|
| **API Gateway** | 8000 | Auth, routing, frontend | No | FastAPI, SQLCipher |
| **Transcription** | 8003 | Speech-to-text, diarization | Yes* | NeMo, PyTorch |
| **Emotion** | 8005 | Sentiment analysis | No | Transformers |
| **RAG** | 8004 | Semantic search | No | FAISS, Sentence Transformers |
| **Gemma AI** | 8001 | LLM chat responses | Yes* | llama.cpp, Gemma 3 |
| **GPU Coordinator** | 8002 | GPU sharing | No | Redis, PostgreSQL |

*GPU is dynamically shared via coordinator

---

## ✨ Key Features

### 🎙️ Advanced Transcription
- **Models**: NVIDIA Parakeet RNNT (600M params)
- **Speaker Diarization**: Automatic multi-speaker detection
- **Speaker Verification**: Match against enrolled voice profiles
- **Voice Activity Detection**: Intelligent speech segmentation
- **Real-time Processing**: Sub-second latency per chunk

### 😊 Emotion Analysis
- **6 Emotions**: Joy, sadness, anger, fear, surprise, neutral
- **Confidence Scores**: Per-segment sentiment analysis
- **Fast**: <100ms per segment
- **Model**: DistilRoBERTa-base

### 🔍 Semantic Memory Search
- **Natural Language Queries**: "What did Sarah say about the deadline?"
- **Vector Search**: FAISS-powered similarity search
- **Rich Filtering**: By speaker, date, emotion
- **Cross-Transcript**: Search entire conversation history

### 🤖 AI Assistant (Gemma 3)
- **64K Context Window**: Long conversation memory
- **RAG-Enhanced**: Automatic context injection from memories
- **GPU Shared**: Dynamic GPU coordination with transcription
- **Streaming**: Token-by-token response streaming

### 🔐 Enterprise Security
- **Encrypted Storage**: SQLCipher for sensitive data
- **JWT Authentication**: Service-to-service security
- **Replay Protection**: Request ID tracking
- **Session Management**: Secure cookie-based sessions
- **Docker Secrets**: No credentials in environment vars

### 🚀 GPU Coordination
- **Single GPU Support**: Intelligent sharing between services
- **Pause/Resume**: Sub-second context switching
- **No Conflicts**: Redis-based distributed locking
- **Automatic Fallback**: Graceful degradation on failures

---

## 🚀 Quick Start

### Prerequisites
- **GPU**: NVIDIA GPU with 8GB+ VRAM (recommended)
- **CUDA**: 12.6+ with cuDNN
- **Docker**: 24.0+ with Docker Compose
- **RAM**: 16GB+ system memory

### 1. Clone Repository
```bash
git clone https://github.com/pruittcolon/NeMo_Server.git
cd NeMo_Server
```

### 2. Setup Secrets
```bash
# Generate secure secrets
cd docker/secrets

# Create random keys
openssl rand -base64 32 > session_key
openssl rand -base64 32 > jwt_secret
openssl rand -base64 32 > users_db_key
openssl rand -base64 32 > rag_db_key

# Database credentials
echo "nemo_user" > postgres_user
openssl rand -base64 16 > postgres_password
openssl rand -base64 16 > redis_password

# Get Hugging Face token (optional, for model downloads)
echo "hf_your_token_here" > huggingface_token
```

### 3. Download Models
```bash
# Gemma 3 model (required for AI chat)
mkdir -p models
cd models
wget https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/resolve/main/gemma-3-4b-it-UD-Q4_K_XL.gguf

# NeMo models download automatically on first run
# Emotion model downloads automatically
```

### 4. Build llama-cpp-python Wheel (for GPU support)
```bash
# This must be done on your host machine with CUDA
CMAKE_ARGS="-DGGML_CUDA=on" pip wheel llama-cpp-python==0.3.16 \
  --wheel-dir=./docker/wheels/ \
  --no-binary llama-cpp-python

# Or use pre-built wheel if compatible with your CUDA version
```

### 5. Start Services
```bash
# Start all services
./start.sh

# Or use docker compose directly
cd docker
docker compose up -d
```

### 6. Access Web Interface
```bash
# Browser opens automatically, or visit:
open http://localhost:8000

# Default credentials:
# Username: admin
# Password: (set during first run or via API)
```

---

## 📁 Project Structure

```
Nemo_Server/
├── README.md                 # This file
├── start.sh                  # Startup script
├── .gitignore               # Git ignore rules
│
├── docker/                   # Docker configuration
│   ├── docker-compose.yml   # Service orchestration
│   ├── Dockerfile.*         # Service-specific builds
│   ├── secrets/             # Encrypted credentials (gitignored)
│   └── wheels/              # Pre-built Python wheels
│
├── services/                 # Microservices
│   ├── api-gateway/         # Main entry point
│   ├── transcription-service/  # Speech-to-text
│   ├── emotion-service/     # Sentiment analysis
│   ├── rag-service/         # Semantic search
│   ├── gemma-service/       # AI chat
│   └── queue-service/       # GPU coordinator
│
├── shared/                   # Shared Python modules
│   ├── auth/                # Authentication
│   ├── crypto/              # Encryption utilities
│   ├── security/            # Security features
│   └── storage/             # Database helpers
│
├── frontend/                 # Web UI (HTML/JS)
│   ├── index.html
│   ├── login.html
│   ├── transcripts.html
│   └── assets/
│
├── clients/                  # Client applications
│   └── even-demo-app/       # Flutter smart glasses app
│
├── models/                   # ML models (gitignored)
│   └── gemma-3-4b-it-*.gguf
│
├── docker/gateway_instance/  # Gateway runtime data (gitignored)
│   ├── users.db             # User database
│   ├── enrollment/          # Speaker audio samples
│   ├── uploads/             # Uploaded audio/files
│   └── cache/               # Temporary/cache data
│
├── docker/rag_instance/      # RAG runtime data (gitignored)
│   └── rag.db               # Memory database (created by service)
│
├── docker/faiss_index/       # Vector index store (gitignored)
│   ├── index.bin            # FAISS index
│   └── *.docs               # Metadata files
│
├── logs/                     # Application logs (gitignored)
├── scripts/                  # Utility scripts
└── tests/                    # Test suites
```

---

## 📖 Documentation

### Service Documentation
Each service has detailed documentation:
- [API Gateway](services/api-gateway/README.md) - Authentication & routing
- [Transcription Service](services/transcription-service/README.md) - Speech-to-text
- [Emotion Service](services/emotion-service/README.md) - Sentiment analysis
- [RAG Service](services/rag-service/README.md) - Semantic search
- [Gemma Service](services/gemma-service/README.md) - AI chat
- [GPU Coordinator](services/queue-service/README.md) - GPU management

### API Examples

#### Transcribe Audio
```bash
curl -X POST http://localhost:8000/api/transcribe \
  -H "Cookie: session_id=YOUR_SESSION" \
  -F "audio=@recording.wav" \
  -F "enable_diarization=true" \
  -F "enable_emotion=true"
```

#### Semantic Search
```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Cookie: session_id=YOUR_SESSION" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what did they say about the budget?",
    "top_k": 5,
    "last_n_transcripts": 10
  }'
```

#### Chat with AI
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Cookie: session_id=YOUR_SESSION" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize today's meeting"}
    ],
    "use_rag": true,
    "max_tokens": 500
  }'
```

---

## 🔧 Configuration

### Environment Variables

Key variables in `docker/.env`:

```bash
# Service URLs (internal)
GEMMA_URL=http://gemma-service:8001
RAG_URL=http://rag-service:8004
EMOTION_URL=http://emotion-service:8005
TRANSCRIPTION_URL=http://transcription-service:8003

# Security
JWT_ONLY=true
SESSION_COOKIE_SECURE=false  # Set true for HTTPS
ALLOWED_ORIGINS=http://localhost,http://127.0.0.1

# Transcription
NEMO_MODEL_NAME=nvidia/parakeet-rnnt-0.6b
ENABLE_PYANNOTE=true
DIARIZATION_SPK_MAX=3

# Gemma AI
GEMMA_MODEL_PATH=/app/models/gemma-3-4b-it-UD-Q4_K_XL.gguf
GEMMA_GPU_LAYERS=25
GEMMA_CONTEXT_SIZE=65536

# RAG
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU VRAM | 8GB | 12GB+ |
| System RAM | 16GB | 32GB+ |
| Storage | 20GB | 50GB+ |
| CPU | 4 cores | 8+ cores |

---

## 🧪 Testing

```bash
# Run all tests (unit + smoke + security by default)
./scripts/run_tests.sh

# Unit tests only
pytest -m unit -v

# Integration tests (requires services running; opt-in)
RUN_INTEGRATION=1 pytest -m integration -v

# Smoke tests (gateway health)
pytest -m smoke -v
```

---

## 🛠️ Development

### Running Services Individually

```bash
# API Gateway
cd services/api-gateway
uvicorn src.main:app --reload --port 8000

# Transcription Service
cd services/transcription-service
uvicorn src.main:app --reload --port 8003

# etc.
```

### Debugging

```bash
# View logs
docker compose logs -f api-gateway

# Check GPU usage
nvidia-smi -l 1

# Redis CLI
docker exec -it refactored_redis redis-cli

# PostgreSQL CLI
docker exec -it refactored_postgres psql -U nemo_user nemo_queue
```

---

## 📊 Monitoring

### Health Checks
```bash
# All services
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health
curl http://localhost:8002/health
```

### Metrics
- GPU utilization: `nvidia-smi`
- Service logs: `docker compose logs`
- Redis: `redis-cli INFO`
- PostgreSQL: `psql` queries

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

See `.github/PULL_REQUEST_TEMPLATE.md` for PR guidelines.

---

## 📄 License

This project includes third-party components:
- **NeMo**: Apache 2.0 License
- **Gemma Models**: Gemma Terms of Use
- **Transformers**: Apache 2.0 License
- **FAISS**: MIT License

---

## 🙏 Acknowledgments

- **NVIDIA NeMo**: State-of-the-art ASR models
- **Google**: Gemma 3 language model
- **Hugging Face**: Model hosting and transformers
- **llama.cpp**: Efficient LLM inference
- **Even Realities**: Smart glasses platform inspiration

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/pruittcolon/NeMo_Server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/pruittcolon/NeMo_Server/discussions)

---

**Built with ❤️ for the future of conversational AI**
