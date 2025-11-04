# NeMo AI Ecosystem# Nemo Server



[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)

[![Docker](https://img.shields.io/badge/docker-24.0+-blue.svg)](https://www.docker.com/)[![Docker](https://img.shields.io/badge/docker-24.0+-blue.svg)](https://www.docker.com/)

[![CUDA](https://img.shields.io/badge/CUDA-12.6+-green.svg)](https://developer.nvidia.com/cuda-downloads)[![CUDA](https://img.shields.io/badge/CUDA-12.6+-green.svg)](https://developer.nvidia.com/cuda-downloads)

[![Code Lines](https://img.shields.io/badge/code-15K+%20lines-blue)]()[![CI](https://img.shields.io/github/actions/workflow/status/pruittcolon/NeMo_Server/ci.yml?branch=main)](https://github.com/pruittcolon/NeMo_Server/actions)

[![Microservices](https://img.shields.io/badge/architecture-6%20microservices-brightgreen)]()[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)



**Production-Grade Distributed Microservices Platform for Conversational AI****AI-Powered Conversational Memory & Transcription System**



Enterprise-scale voice intelligence system integrating real-time speech recognition, speaker diarization, emotion analysis, semantic memory, and LLM-powered responses. Built for AR wearables, IoT automation, and voice-first applications with intelligent GPU coordination and defense-in-depth security.A microservices-based platform that provides real-time speech transcription, speaker diarization, emotion analysis, semantic memory search, and AI-powered conversational responses. Built for smart glasses and voice-first applications.



------



## 🎯 System Overview## 🎯 What It Does



NeMo Server is a **15,000+ line production codebase** implementing a distributed microservices architecture for conversational AI. The system processes voice input through a coordinated pipeline of specialized services, each optimized for specific AI/ML workloads.Nemo Server transforms conversations into searchable, analyzable knowledge:



### Core Capabilities1. **Transcribe**: Real-time speech-to-text with speaker identification

2. **Analyze**: Emotion detection and audio quality metrics  

```3. **Remember**: Semantic search across all conversations

Voice Input → Transcription → Emotion Analysis → Semantic Memory → LLM Response → Action4. **Respond**: AI assistant with full conversational context

     ↓            ↓                ↓                  ↓              ↓           ↓

  Audio File   Text+Speaker     Sentiment        Context Search   AI Chat    IoT ControlPerfect for:

```- Meeting transcription and analysis

- Smart glasses (AR/VR) voice interfaces

**Key Features:**- Personal memory augmentation

- **Real-time ASR**: NVIDIA NeMo Parakeet (600M params) with sub-second latency- Conversational AI applications

- **Speaker Intelligence**: TitaNet Large diarization + voice enrollment system- Voice-controlled systems

- **Emotion AI**: 6-class sentiment analysis (DistilRoBERTa)

- **Semantic Memory**: FAISS vector search with 384D embeddings---

- **LLM Chat**: Gemma 3 4B with 64K context window

- **GPU Coordination**: Intelligent pause/resume protocol for single-GPU systems## 🏗️ Architecture

- **Enterprise Security**: 5-layer defense-in-depth with encrypted databases

- **Multi-Platform**: AR glasses, Flutter mobile, web UI, IoT integration### Microservices Overview



---```

┌─────────────┐

## 🏗️ Architecture│   Client    │ (Flutter App, Web Browser)

└──────┬──────┘

### Microservices Overview       │

┌──────▼──────────────────────────────────────────────────────┐

```mermaid│  API Gateway (Port 8000)                                     │

graph TB│  • Authentication & Sessions                                 │

    subgraph "Client Layer"│  • Request Routing                                           │

        C1[AR Glasses<br/>Even Reality]│  • Frontend Serving                                          │

        C2[Mobile App<br/>Flutter]└──────┬───────┬───────┬───────┬────────┬──────────────────────┘

        C3[Web Browser]       │       │       │       │        │

    end    ┌──▼──┐ ┌─▼──┐ ┌──▼───┐ ┌─▼────┐ ┌▼──────────┐

    │Trans│ │Emo │ │ RAG  │ │Gemma │ │    GPU    │

    subgraph "API Layer"    │cript│ │tion│ │Search│ │  AI  │ │Coordinator│

        GW[API Gateway :8000<br/>Auth, Routing, RBAC]    └──┬──┘ └────┘ └──────┘ └──┬───┘ └───────────┘

    end       │                       │

       └───────┬───────────────┘

    subgraph "Service Layer"               │ Shared GPU

        T[Transcription :8003<br/>NeMo ASR + Diarization]         ┌─────▼─────┐

        G[Gemma AI :8001<br/>LLM Inference]         │  GPU 0    │

        R[RAG :8004<br/>Semantic Search]         │ (NVIDIA)  │

        E[Emotion :8005<br/>Sentiment Analysis]         └───────────┘

        Q[GPU Coordinator :8002<br/>Resource Management]

    endInfrastructure:

  • Redis (Pub/Sub, Caching, Locking)

    subgraph "Infrastructure Layer"  • PostgreSQL (Task Queue)

        Redis[(Redis<br/>Pub/Sub + Cache)]  • Encrypted SQLite (User Data, Transcripts)

        PG[(PostgreSQL<br/>Task Queue)]```

        SQLite[(SQLCipher<br/>Encrypted DBs)]

        FAISS[(FAISS<br/>Vector Index)]### Service Breakdown

    end

| Service | Port | Purpose | GPU | Key Tech |

    subgraph "GPU Layer"|---------|------|---------|-----|----------|

        GPU[NVIDIA GPU<br/>CUDA 12.6+]| **API Gateway** | 8000 | Auth, routing, frontend | No | FastAPI, SQLCipher |

    end| **Transcription** | 8003 | Speech-to-text, diarization | Yes* | NeMo, PyTorch |

| **Emotion** | 8005 | Sentiment analysis | No | Transformers |

    C1 --> GW| **RAG** | 8004 | Semantic search | No | FAISS, Sentence Transformers |

    C2 --> GW| **Gemma AI** | 8001 | LLM chat responses | Yes* | llama.cpp, Gemma 3 |

    C3 --> GW| **GPU Coordinator** | 8002 | GPU sharing | No | Redis, PostgreSQL |

    GW --> T

    GW --> G*GPU is dynamically shared via coordinator

    GW --> R

    GW --> E---

    Q -.Coordinates.-> T

    Q -.Coordinates.-> G## ✨ Key Features

    T --> Redis

    G --> Redis### 🎙️ Advanced Transcription

    Q --> Redis- **Models**: NVIDIA Parakeet RNNT (600M params)

    Q --> PG- **Speaker Diarization**: Automatic multi-speaker detection

    R --> SQLite- **Speaker Verification**: Match against enrolled voice profiles

    R --> FAISS- **Voice Activity Detection**: Intelligent speech segmentation

    GW --> SQLite- **Real-time Processing**: Sub-second latency per chunk

    T -.GPU Access.-> GPU

    G -.GPU Access.-> GPU### 😊 Emotion Analysis

- **6 Emotions**: Joy, sadness, anger, fear, surprise, neutral

    style GW fill:#00aaff,stroke:#0088cc,color:#000- **Confidence Scores**: Per-segment sentiment analysis

    style GPU fill:#76b900,stroke:#5a8f00,color:#000- **Fast**: <100ms per segment

```- **Model**: DistilRoBERTa-base



### Service Responsibilities### 🔍 Semantic Memory Search

- **Natural Language Queries**: "What did Sarah say about the deadline?"

| Service | Port | Role | GPU | Lines | Key Technologies |- **Vector Search**: FAISS-powered similarity search

|---------|------|------|-----|-------|------------------|- **Rich Filtering**: By speaker, date, emotion

| **API Gateway** | 8000 | Authentication, routing, session management, frontend serving | No | 2,445 | FastAPI, SQLCipher, bcrypt, JWT |- **Cross-Transcript**: Search entire conversation history

| **Transcription** | 8003 | ASR, speaker diarization, voice enrollment, GPU primary owner | Yes* | 2,138 | NeMo, PyTorch 2.4, TitaNet, Parakeet |

| **Gemma AI** | 8001 | LLM inference, RAG-enhanced chat, GPU requester | Yes* | 1,016 | llama.cpp 0.3.16, Gemma 3 4B |### 🤖 AI Assistant (Gemma 3)

| **RAG** | 8004 | Semantic search, memory indexing, context retrieval | No | 3,220 | FAISS, sentence-transformers, SQLCipher |- **64K Context Window**: Long conversation memory

| **Emotion** | 8005 | 6-class sentiment analysis, confidence scoring | No | 448 | Transformers 4.39, DistilRoBERTa |- **RAG-Enhanced**: Automatic context injection from memories

| **GPU Coordinator** | 8002 | Resource scheduling, pause/resume protocol, task queue | No | 1,143 | Redis Pub/Sub, PostgreSQL |- **GPU Shared**: Dynamic GPU coordination with transcription

| **Shared Modules** | - | Auth, crypto, security, storage utilities | No | 4,704 | AES-256, JWT, SQLCipher |- **Streaming**: Token-by-token response streaming



**Total: 15,114 lines of production Python code**### 🔐 Enterprise Security

- **Encrypted Storage**: SQLCipher for sensitive data

*GPU is dynamically shared via coordinator's pause/resume protocol- **JWT Authentication**: Service-to-service security

- **Replay Protection**: Request ID tracking

---- **Session Management**: Secure cookie-based sessions

- **Docker Secrets**: No credentials in environment vars

## 🔐 Security Architecture (Defense-in-Depth)

### 🚀 GPU Coordination

5-layer security model verified against OWASP Top 10:- **Single GPU Support**: Intelligent sharing between services

- **Pause/Resume**: Sub-second context switching

### Layer 1: Network Security- **No Conflicts**: Redis-based distributed locking

```- **Automatic Fallback**: Graceful degradation on failures

• CORS with explicit origin whitelisting

• Rate limiting (120 req/min global, 20 req/min auth)---

• Request size limits (100MB max)

• Docker network isolation (services on internal network)## 🚀 Quick Start

```

### Prerequisites

### Layer 2: Authentication & Sessions- **GPU**: NVIDIA GPU with 8GB+ VRAM (recommended)

```- **CUDA**: 12.6+ with cuDNN

• JWT-based session tokens (24h expiry, 1h rotation)- **Docker**: 24.0+ with Docker Compose

• bcrypt password hashing (cost factor 12)- **RAM**: 16GB+ system memory

• CSRF double-submit cookie pattern

• HttpOnly + SameSite=Strict cookies### 1. Clone Repository

• AES-256-CBC session encryption```bash

```git clone https://github.com/pruittcolon/NeMo_Server.git

cd NeMo_Server

### Layer 3: Service-to-Service Authorization```

```

• Short-lived JWT tokens (5min TTL) for inter-service auth### 2. Setup Secrets

• Request ID tracking for replay attack prevention```bash

• Service identity verification# Generate secure secrets

• Mutual TLS capable (via Docker secrets)cd docker/secrets

```

# Create random keys

### Layer 4: Data Encryptionopenssl rand -base64 32 > session_key

```openssl rand -base64 32 > jwt_secret

• SQLCipher AES-256 for databases (users.db, rag.db)openssl rand -base64 32 > users_db_key

• Encrypted session tokens (32-byte keys)openssl rand -base64 32 > rag_db_key

• Docker secrets for credential management

• No plaintext secrets in environment variables# Database credentials

```echo "nemo_user" > postgres_user

openssl rand -base64 16 > postgres_password

### Layer 5: Application Security (RBAC)openssl rand -base64 16 > redis_password

```

• Role-based access control (Admin, User)# Get Hugging Face token (optional, for model downloads)

• Speaker-based data isolationecho "hf_your_token_here" > huggingface_token

• Endpoint-level permission enforcement```

• Audit logging for sensitive operations

```### 3. Download Models

```bash

**Implementation:**# Gemma 3 model (required for AI chat)

- Authentication: `shared/auth/auth_manager.py` (SessionEncryption class)mkdir -p models

- Authorization: `shared/auth/permissions.py` (require_auth decorator)cd models

- Service Auth: `shared/security/service_jwt.py` (ServiceJWT class)wget https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/resolve/main/gemma-3-4b-it-UD-Q4_K_XL.gguf

- Database Encryption: `shared/crypto/db_encryption.py`

# NeMo models download automatically on first run

---# Emotion model downloads automatically

```

## ⚡ GPU Coordination Protocol

### 4. Build llama-cpp-python Wheel (for GPU support)

Intelligent GPU sharing enables **single-GPU systems** to run both ASR (Transcription) and LLM (Gemma) without conflicts.```bash

# This must be done on your host machine with CUDA

### ArchitectureCMAKE_ARGS="-DGGML_CUDA=on" pip wheel llama-cpp-python==0.3.16 \

  --wheel-dir=./docker/wheels/ \

```  --no-binary llama-cpp-python

Transcription Service (GPU Owner)    Gemma Service (GPU Requester)

        |                                      |# Or use pre-built wheel if compatible with your CUDA version

        | 1. Parakeet model loaded             | (idle, no GPU)```

        |                                      |

        |                            2. Chat request arrives### 5. Start Services

        |                                      |```bash

        |                            3. Publish request to Redis# Start all services

        |                                      | channel:gemma:request./start.sh

        |                                      |

    4. Receive pause request                  |# Or use docker compose directly

        | channel:transcription:control       |cd docker

        |                                      |docker compose up -d

    5. Pause ASR pipeline (save state)        |```

        | - Stop audio processing              |

        | - Keep models in VRAM                |### 6. Access Web Interface

        |                                      |```bash

    6. ACK pause complete (<100ms)            |# Browser opens automatically, or visit:

        | channel:transcription:status        |open http://localhost:8000

        |                                      |

        |                          7. Acquire GPU lock (Redis)# Default credentials:

        |                                      | SET gpu:lock:current gemma EX 300# Username: admin

        |                                      |# Password: (set during first run or via API)

        |                          8. Load Gemma model (500-800ms)```

        |                                      | llama.cpp → GPU

        |                                      |---

        |                          9. Run inference

        |                                      |## 📁 Project Structure

        |                          10. Release lock, notify complete

        |                                      |```

    11. Resume ASR pipeline                   |Nemo_Server/

        | channel:transcription:control       |├── README.md                 # This file

        |                                      | (unload model)├── start.sh                  # Startup script

```├── .gitignore               # Git ignore rules

│

### Redis Channels├── docker/                   # Docker configuration

│   ├── docker-compose.yml   # Service orchestration

| Channel | Purpose | Publisher | Subscriber |│   ├── Dockerfile.*         # Service-specific builds

|---------|---------|-----------|----------|│   ├── secrets/             # Encrypted credentials (gitignored)

| `channel:gemma:request` | Request GPU access | Gemma | GPU Coordinator |│   └── wheels/              # Pre-built Python wheels

| `channel:transcription:control` | Pause/resume commands | GPU Coordinator | Transcription |│

| `channel:transcription:status` | Acknowledgments | Transcription | GPU Coordinator |├── services/                 # Microservices

| `gpu:lock:current` | Distributed lock | GPU Coordinator | All GPU services |│   ├── api-gateway/         # Main entry point

│   ├── transcription-service/  # Speech-to-text

### Timing Guarantees│   ├── emotion-service/     # Sentiment analysis

│   ├── rag-service/         # Semantic search

- **Pause ACK**: <100ms (transcription stops processing)│   ├── gemma-service/       # AI chat

- **Model Swap**: 500-800ms (unload + load via llama.cpp)│   └── queue-service/       # GPU coordinator

- **Lock TTL**: 300s (prevents deadlock if service crashes)│

- **Total Overhead**: ~1 second for GPU handoff├── shared/                   # Shared Python modules

│   ├── auth/                # Authentication

**Implementation:** │   ├── crypto/              # Encryption utilities

- Coordinator: `services/queue-service/src/main.py`│   ├── security/            # Security features

- Transcription pause: `services/transcription-service/src/main.py` (GPUCoordinator class)│   └── storage/             # Database helpers

- Gemma coordination: `services/gemma-service/src/main.py` (pause_owner/resume_owner)│

├── frontend/                 # Web UI (HTML/JS)

---│   ├── index.html

│   ├── login.html

## 🚀 Quick Start│   ├── transcripts.html

│   └── assets/

### Prerequisites│

├── clients/                  # Client applications

| Requirement | Minimum | Recommended |│   └── even-demo-app/       # Flutter smart glasses app

|------------|---------|-------------|│

| **GPU** | NVIDIA 8GB VRAM | 12GB+ VRAM (RTX 3060+) |├── models/                   # ML models (gitignored)

| **CUDA** | 12.6+ with cuDNN | Latest stable |│   └── gemma-3-4b-it-*.gguf

| **RAM** | 16GB | 32GB+ |│

| **Storage** | 25GB free | 50GB+ SSD |├── docker/gateway_instance/  # Gateway runtime data (gitignored)

| **Docker** | 24.0+ | Latest with Docker Compose v2 |│   ├── users.db             # User database

│   ├── enrollment/          # Speaker audio samples

### Installation│   ├── uploads/             # Uploaded audio/files

│   └── cache/               # Temporary/cache data

#### 1. Clone Repository│

```bash├── docker/rag_instance/      # RAG runtime data (gitignored)

git clone https://github.com/pruittcolon/NeMo_Server.git│   └── rag.db               # Memory database (created by service)

cd NeMo_Server│

```├── docker/faiss_index/       # Vector index store (gitignored)

│   ├── index.bin            # FAISS index

#### 2. Setup Docker Secrets│   └── *.docs               # Metadata files

```bash│

cd docker/secrets├── logs/                     # Application logs (gitignored)

├── scripts/                  # Utility scripts

# Generate cryptographic keys (Linux/macOS)└── tests/                    # Test suites

openssl rand -base64 32 > session_key```

openssl rand -base64 32 > jwt_secret

openssl rand -base64 32 > users_db_key---

openssl rand -base64 32 > rag_db_key

## 📖 Documentation

# Database credentials

echo "nemo_user" > postgres_user### Service Documentation

openssl rand -base64 16 > postgres_passwordEach service has detailed documentation:

openssl rand -base64 16 > redis_password- [API Gateway](services/api-gateway/README.md) - Authentication & routing

- [Transcription Service](services/transcription-service/README.md) - Speech-to-text

# Optional: Hugging Face token for model downloads- [Emotion Service](services/emotion-service/README.md) - Sentiment analysis

echo "hf_your_token_here" > huggingface_token- [RAG Service](services/rag-service/README.md) - Semantic search

```- [Gemma Service](services/gemma-service/README.md) - AI chat

- [GPU Coordinator](services/queue-service/README.md) - GPU management

#### 3. Download AI Models

```bash### API Examples

# Gemma 3 LLM (4.5GB)

mkdir -p models#### Transcribe Audio

cd models```bash

wget https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/resolve/main/gemma-3-4b-it-UD-Q4_K_XL.ggufcurl -X POST http://localhost:8000/api/transcribe \

  -H "Cookie: session_id=YOUR_SESSION" \

# NeMo and emotion models download automatically on first run  -F "audio=@recording.wav" \

```  -F "enable_diarization=true" \

  -F "enable_emotion=true"

#### 4. Build llama-cpp-python with CUDA Support```

```bash

# Build Python wheel with GPU acceleration#### Semantic Search

CMAKE_ARGS="-DGGML_CUDA=on" pip wheel llama-cpp-python==0.3.16 \```bash

  --wheel-dir=./docker/wheels/ \curl -X POST http://localhost:8000/api/rag/search \

  --no-binary llama-cpp-python  -H "Cookie: session_id=YOUR_SESSION" \

  -H "Content-Type: application/json" \

# Verify wheel created  -d '{

ls docker/wheels/llama_cpp_python-0.3.16-*.whl    "query": "what did they say about the budget?",

```    "top_k": 5,

    "last_n_transcripts": 10

#### 5. Launch Services  }'

```bash```

# Start all 8 containers (6 services + Redis + PostgreSQL)

./start.sh#### Chat with AI

```bash

# Or manually:curl -X POST http://localhost:8000/api/chat \

cd docker  -H "Cookie: session_id=YOUR_SESSION" \

docker compose up -d  -H "Content-Type: application/json" \

  -d '{

# Verify all services healthy    "messages": [

docker compose ps      {"role": "user", "content": "Summarize today's meeting"}

```    ],

    "use_rag": true,

#### 6. Access Web Interface    "max_tokens": 500

```bash  }'

# Open browser (auto-launches)```

open http://localhost:8000

---

# Default admin credentials (change immediately):

# Username: admin## 🔧 Configuration

# Password: admin123

```### Environment Variables



### Verify InstallationKey variables in `docker/.env`:

```bash

# Check all service health endpoints```bash

curl http://localhost:8000/health  # API Gateway# Service URLs (internal)

curl http://localhost:8001/health  # Gemma AIGEMMA_URL=http://gemma-service:8001

curl http://localhost:8002/health  # GPU CoordinatorRAG_URL=http://rag-service:8004

curl http://localhost:8003/health  # TranscriptionEMOTION_URL=http://emotion-service:8005

curl http://localhost:8004/health  # RAGTRANSCRIPTION_URL=http://transcription-service:8003

curl http://localhost:8005/health  # Emotion

# Security

# Check GPU utilizationJWT_ONLY=true

nvidia-smiSESSION_COOKIE_SECURE=false  # Set true for HTTPS

ALLOWED_ORIGINS=http://localhost,http://127.0.0.1

# View logs

docker compose logs -f api-gateway# Transcription

```NEMO_MODEL_NAME=nvidia/parakeet-rnnt-0.6b

ENABLE_PYANNOTE=true

---DIARIZATION_SPK_MAX=3



## 📊 Technology Stack (Verified)# Gemma AI

GEMMA_MODEL_PATH=/app/models/gemma-3-4b-it-UD-Q4_K_XL.gguf

### Core FrameworkGEMMA_GPU_LAYERS=25

- **Python**: 3.12 (verified across all services)GEMMA_CONTEXT_SIZE=65536

- **FastAPI**: 0.110.3 (async web framework)

- **Uvicorn**: 0.30.6 (ASGI server)# RAG

- **Pydantic**: 2.7-2.10 (data validation)EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

```

### AI/ML Libraries

- **PyTorch**: 2.3.1 - 2.4.1 (deep learning)### Hardware Requirements

- **NVIDIA NeMo**: 2.5+ (speech recognition)

  - Parakeet-CTC-1.1B (ASR)| Component | Minimum | Recommended |

  - TitaNet-Large (speaker embeddings)|-----------|---------|-------------|

- **llama.cpp**: 0.3.16 (LLM inference)| GPU VRAM | 8GB | 12GB+ |

  - Gemma 3 4B Q4_K_XL quantized| System RAM | 16GB | 32GB+ |

- **Transformers**: 4.39.3 (Hugging Face)| Storage | 20GB | 50GB+ |

  - DistilRoBERTa-base (emotion)| CPU | 4 cores | 8+ cores |

- **sentence-transformers**: 2.7.0 (embeddings)

  - all-MiniLM-L6-v2 (384D vectors)---

- **FAISS**: 1.8.0 (vector search)

## 🧪 Testing

### Infrastructure

- **Redis**: 5.0.1 (Pub/Sub, caching, locks)```bash

- **PostgreSQL**: 14+ (task queue)# Run all tests (unit + smoke + security by default)

- **SQLCipher**: 1.0.4 (encrypted SQLite)./scripts/run_tests.sh

- **Docker**: 24.0+ with Compose v2

# Unit tests only

### Security & Authpytest -m unit -v

- **bcrypt**: 4.1.2 (password hashing)

- **python-jose**: 3.3.0 (JWT)# Integration tests (requires services running; opt-in)

- **cryptography**: 42.0.5 (AES-256)RUN_INTEGRATION=1 pytest -m integration -v



### Audio Processing# Smoke tests (gateway health)

- **librosa**: 0.10.2 (audio analysis)pytest -m smoke -v

- **soundfile**: 0.12.1 (I/O)```

- **pyannote.audio**: 3.1.1 (diarization)

---

---

## 🛠️ Development

## 📁 Project Structure

### Running Services Individually

```

NeMo_Server/```bash

├── services/                      # 6 microservices (15K lines)# API Gateway

│   ├── api-gateway/              # Port 8000 - Entry point (2.4K lines)cd services/api-gateway

│   │   ├── src/main.py           # FastAPI app, routing, authuvicorn src.main:app --reload --port 8000

│   │   └── requirements.txt      # Dependencies

│   ├── transcription-service/    # Port 8003 - ASR (2.1K lines)# Transcription Service

│   │   ├── src/main.py           # NeMo pipeline, GPU coordinationcd services/transcription-service

│   │   └── requirements.txt      # PyTorch, NeMo, pyannoteuvicorn src.main:app --reload --port 8003

│   ├── gemma-service/            # Port 8001 - LLM (1.0K lines)

│   │   ├── src/main.py           # llama.cpp inference, RAG# etc.

│   │   └── requirements.txt      # llama-cpp-python```

│   ├── rag-service/              # Port 8004 - Search (3.2K lines)

│   │   ├── src/main.py           # FAISS indexing, SQLCipher### Debugging

│   │   └── requirements.txt      # sentence-transformers, FAISS

│   ├── emotion-service/          # Port 8005 - Sentiment (448 lines)```bash

│   │   ├── src/main.py           # DistilRoBERTa pipeline# View logs

│   │   └── requirements.txt      # transformers, torchdocker compose logs -f api-gateway

│   └── queue-service/            # Port 8002 - GPU coordinator (1.1K lines)

│       ├── src/main.py           # Redis Pub/Sub, PostgreSQL queue# Check GPU usage

│       └── requirements.txt      # redis, asyncpgnvidia-smi -l 1

│

├── shared/                        # Shared utilities (4.7K lines)# Redis CLI

│   ├── auth/                     # Authentication & RBACdocker exec -it refactored_redis redis-cli

│   │   ├── auth_manager.py       # User management, sessions

│   │   └── permissions.py        # Role-based access control# PostgreSQL CLI

│   ├── crypto/                   # Encryption utilitiesdocker exec -it refactored_postgres psql -U nemo_user nemo_queue

│   │   └── db_encryption.py      # SQLCipher wrapper```

│   ├── security/                 # Security features

│   │   ├── service_jwt.py        # Inter-service auth---

│   │   └── secrets.py            # Docker secrets loader

│   └── storage/                  # Database helpers## 📊 Monitoring

│

├── docker/                        # Container orchestration### Health Checks

│   ├── docker-compose.yml        # 8 services definition```bash

│   ├── Dockerfile.api            # API Gateway image# All services

│   ├── Dockerfile.transcription  # Transcription image (CUDA)curl http://localhost:8000/health

│   ├── Dockerfile.gemma          # Gemma image (CUDA)curl http://localhost:8001/health

│   ├── Dockerfile.rag            # RAG imagecurl http://localhost:8003/health

│   ├── Dockerfile.emotion        # Emotion imagecurl http://localhost:8004/health

│   ├── Dockerfile.queue          # GPU Coordinator imagecurl http://localhost:8005/health

│   ├── secrets/                  # Encrypted credentials (gitignored)curl http://localhost:8002/health

│   │   ├── session_key           # 32-byte AES key```

│   │   ├── jwt_secret            # JWT signing key

│   │   ├── users_db_key          # SQLCipher key### Metrics

│   │   ├── rag_db_key            # SQLCipher key- GPU utilization: `nvidia-smi`

│   │   ├── postgres_password     # DB password- Service logs: `docker compose logs`

│   │   └── redis_password        # Redis password- Redis: `redis-cli INFO`

│   └── wheels/                   # Pre-built Python wheels- PostgreSQL: `psql` queries

│       └── llama_cpp_python-0.3.16-*-linux_x86_64.whl

│---

├── frontend/                      # Web UI (HTML/CSS/JS)

│   ├── login.html                # Authentication## 🤝 Contributing

│   ├── transcripts.html          # Conversation history

│   ├── search.html               # Semantic search1. Fork the repository

│   ├── emotions.html             # Sentiment dashboard2. Create a feature branch

│   └── gemma.html                # AI chat interface3. Make your changes

│4. Add tests

├── models/                        # AI models (gitignored)5. Submit a pull request

│   ├── gemma-3-4b-it-UD-Q4_K_XL.gguf  # 4.5GB quantized LLM

│   ├── emotion-english-distilroberta-base/  # 255MB sentimentSee `.github/PULL_REQUEST_TEMPLATE.md` for PR guidelines.

│   └── (NeMo models auto-downloaded to ~/.cache/torch/NeMo/)

│---

├── docker/gateway_instance/       # Runtime data (gitignored)

│   ├── users.db                  # SQLCipher encrypted user DB## 📄 License

│   ├── enrollment/               # Speaker voice profiles

│   └── uploads/                  # Audio filesThis project includes third-party components:

│- **NeMo**: Apache 2.0 License

├── docker/rag_instance/           # Runtime data (gitignored)- **Gemma Models**: Gemma Terms of Use

│   └── rag.db                    # SQLCipher encrypted memory DB- **Transformers**: Apache 2.0 License

│- **FAISS**: MIT License

├── docker/faiss_index/            # Vector index (gitignored)

│   ├── index.bin                 # FAISS index file---

│   └── *.docs                    # Metadata

│## 🙏 Acknowledgments

├── scripts/                       # Utility scripts

│   ├── run_tests.sh              # Test runner- **NVIDIA NeMo**: State-of-the-art ASR models

│   ├── healthcheck.sh            # Service health check- **Google**: Gemma 3 language model

│   └── security_hardening.py     # Security audit- **Hugging Face**: Model hosting and transformers

│- **llama.cpp**: Efficient LLM inference

├── tests/                         # Test suites- **Even Realities**: Smart glasses platform inspiration

│   ├── unit/                     # Unit tests

│   ├── integration/              # Integration tests---

│   ├── security/                 # Security tests

│   └── conftest.py               # Pytest configuration## 📞 Support

│

├── ARCHITECTURE.md                # Detailed architecture docs- **Issues**: [GitHub Issues](https://github.com/pruittcolon/NeMo_Server/issues)

├── README.md                      # This file- **Discussions**: [GitHub Discussions](https://github.com/pruittcolon/NeMo_Server/discussions)

├── start.sh                       # Startup script

└── docker-compose.yml             # Legacy location (points to docker/)---

```

**Built with ❤️ for the future of conversational AI**

---

## 🔌 API Reference

### Authentication
```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Response includes session cookie
```

### Transcription
```bash
# Transcribe audio with diarization and emotion
curl -X POST http://localhost:8000/api/transcription/transcribe \
  -H "Cookie: ws_session=YOUR_SESSION_TOKEN" \
  -F "audio=@recording.wav" \
  -F "enable_diarization=true" \
  -F "enable_emotion=true"

# Response:
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "text": "Hello, how are you?",
  "segments": [
    {
      "text": "Hello, how are you?",
      "speaker": "SPEAKER_00",
      "start": 0.0,
      "end": 2.5,
      "emotion": "neutral",
      "confidence": 0.89
    }
  ],
  "processing_time": 0.34
}
```

### Semantic Search
```bash
# Search memories by natural language
curl -X POST http://localhost:8000/api/memory/search \
  -H "Cookie: ws_session=YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what did Sarah say about the deadline?",
    "top_k": 5,
    "filters": {
      "speaker": "SPEAKER_00",
      "emotion": "neutral"
    }
  }'

# Response:
{
  "results": [
    {
      "text": "Sarah mentioned the deadline is next Friday",
      "score": 0.87,
      "speaker": "SPEAKER_00",
      "timestamp": "2024-11-03T14:23:10Z",
      "emotion": "neutral"
    }
  ],
  "query_time_ms": 12
}
```

### AI Chat (RAG-Enhanced)
```bash
# Chat with context from memories
curl -X POST http://localhost:8000/api/gemma/chat \
  -H "Cookie: ws_session=YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize today'\''s meeting"}
    ],
    "use_rag": true,
    "max_tokens": 500,
    "temperature": 0.7
  }'

# Response (streaming):
{
  "response": "Based on your conversation history, today's meeting covered...",
  "context_used": ["segment_id_1", "segment_id_2"],
  "tokens_generated": 127,
  "generation_time": 2.3
}
```

### Emotion Analysis
```bash
# Analyze sentiment of text
curl -X POST http://localhost:8000/api/emotion/analyze \
  -H "Cookie: ws_session=YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "I am extremely happy about this news!"}'

# Response:
{
  "emotion": "joy",
  "confidence": 0.94,
  "all_scores": {
    "joy": 0.94,
    "neutral": 0.03,
    "surprise": 0.02,
    "sadness": 0.01,
    "anger": 0.00,
    "fear": 0.00
  }
}
```

---

## 🧪 Testing

### Test Coverage

```bash
# Run all tests
./scripts/run_tests.sh

# Unit tests only (fast)
pytest -m unit -v

# Integration tests (requires running services)
RUN_INTEGRATION=1 pytest -m integration -v

# Security tests
pytest -m security -v

# Smoke tests (health checks)
pytest -m smoke -v
```

### Test Suites

| Suite | Files | Purpose | Duration |
|-------|-------|---------|----------|
| **Unit** | 25+ | Service logic, utilities | <30s |
| **Integration** | 10+ | End-to-end API flows | 2-5min |
| **Security** | 8+ | Auth, encryption, RBAC | <1min |
| **Smoke** | 5+ | Health checks, connectivity | <10s |

---

## 🔧 Configuration

### Environment Variables

Key settings in `docker/.env` or service-specific configs:

```bash
# === SERVICE URLS (Internal Docker Network) ===
GEMMA_URL=http://gemma-service:8001
RAG_URL=http://rag-service:8004
EMOTION_URL=http://emotion-service:8005
TRANSCRIPTION_URL=http://transcription-service:8003

# === SECURITY ===
JWT_ONLY=true                          # Enforce JWT for inter-service
SESSION_COOKIE_SECURE=false            # Set true for HTTPS
SESSION_COOKIE_SAMESITE=strict         # CSRF protection
ALLOWED_ORIGINS=http://localhost,http://127.0.0.1
RATE_LIMIT_DEFAULT=120                 # Requests per minute
RATE_LIMIT_AUTH=20                     # Auth requests per minute

# === TRANSCRIPTION SERVICE ===
NEMO_MODEL_NAME=nvidia/parakeet-rnnt-0.6b  # ASR model
ENABLE_PYANNOTE=true                   # Speaker diarization
DIARIZATION_SPK_MAX=3                  # Max speakers to detect
MIN_SPEECH_DURATION=0.3                # VAD threshold (seconds)

# === GEMMA SERVICE ===
GEMMA_MODEL_PATH=/app/models/gemma-3-4b-it-UD-Q4_K_XL.gguf
GEMMA_GPU_LAYERS=25                    # Layers offloaded to GPU
GEMMA_CONTEXT_SIZE=65536               # 64K context window
GEMMA_TEMPERATURE=0.7                  # Response creativity

# === RAG SERVICE ===
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
FAISS_INDEX_TYPE=IndexFlatIP           # Cosine similarity
RAG_TOP_K=5                            # Results per query

# === GPU COORDINATION ===
GPU_LOCK_TTL=300                       # Lock timeout (seconds)
PAUSE_TIMEOUT=5                        # Max pause wait (seconds)
```

---

## 🚨 Troubleshooting

### Common Issues

#### Services Won't Start
```bash
# Check Docker resources
docker system df
docker system prune -a  # Free space

# Check CUDA availability
nvidia-smi

# Verify secrets exist
ls -la docker/secrets/
```

#### GPU Out of Memory
```bash
# Reduce Gemma GPU layers in docker/.env
GEMMA_GPU_LAYERS=15  # Default: 25

# Or use CPU-only mode
GEMMA_GPU_LAYERS=0
```

#### Slow Transcription
```bash
# Check GPU utilization
nvidia-smi -l 1

# Verify NeMo model loaded
docker compose logs transcription-service | grep "Model loaded"

# Check if GPU coordinator is functioning
curl http://localhost:8002/health
```

#### Authentication Failures
```bash
# Verify secrets are valid base64
cat docker/secrets/session_key | base64 -d | wc -c  # Should be 32

# Reset admin password (if locked out)
docker compose exec api-gateway python -c "
from shared.auth.auth_manager import AuthManager
am = AuthManager(db_path='/app/instance/users.db')
user = am.get_user('admin')
user.password_hash = am._hash_password('newpassword')
am._save_user(user)
"
```

---

## 🛠️ Development

### Running Services Individually

```bash
# API Gateway
cd services/api-gateway
pip install -r requirements.txt
python -m uvicorn src.main:app --reload --port 8000

# Transcription (requires CUDA)
cd services/transcription-service
pip install -r requirements.txt
python -m uvicorn src.main:app --reload --port 8003
```

### Debugging

```bash
# Live logs with color
docker compose logs -f --tail=100 api-gateway

# Access container shell
docker compose exec api-gateway /bin/bash

# Check Redis Pub/Sub
docker compose exec redis redis-cli
> SUBSCRIBE channel:transcription:control
> PUBLISH channel:gemma:request "test"

# Query PostgreSQL
docker compose exec postgres psql -U nemo_user nemo_queue
> SELECT * FROM gpu_tasks ORDER BY created_at DESC LIMIT 10;

# GPU memory usage
nvidia-smi --query-gpu=memory.used,memory.free --format=csv -l 1
```

---

## 🤝 Contributing

Contributions welcome! This project follows production-grade standards:

1. **Fork & Branch**: Create feature branch from `v2-modular`
2. **Code Style**: Black formatting, type hints, docstrings
3. **Testing**: Add unit tests (>80% coverage required)
4. **Security**: No secrets in commits, follow OWASP guidelines
5. **Documentation**: Update README and ARCHITECTURE.md
6. **Pull Request**: Use PR template, link related issues

```bash
# Format code
black services/ shared/

# Run linters
flake8 services/ shared/
mypy services/ shared/

# Run tests
pytest -v --cov=services --cov=shared
```

---

## 📄 License & Acknowledgments

### License
MIT License - See [LICENSE](LICENSE) for details

### Third-Party Components

| Component | License | Purpose |
|-----------|---------|---------|
| **NVIDIA NeMo** | Apache 2.0 | Speech recognition models |
| **Google Gemma** | Gemma Terms | Language model |
| **PyTorch** | BSD-3-Clause | Deep learning framework |
| **llama.cpp** | MIT | LLM inference engine |
| **FAISS** | MIT | Vector similarity search |
| **FastAPI** | MIT | Web framework |

### Acknowledgments

- **NVIDIA**: NeMo Toolkit and pre-trained ASR models
- **Google DeepMind**: Gemma 3 language model
- **Hugging Face**: Model hosting and Transformers library
- **Georgi Gerganov**: llama.cpp inference engine
- **Meta Research**: FAISS vector search

---

## 📞 Support & Contact

- **GitHub Issues**: [Report bugs](https://github.com/pruittcolon/NeMo_Server/issues)
- **Discussions**: [Ask questions](https://github.com/pruittcolon/NeMo_Server/discussions)
- **Portfolio**: [whyhirepruitt.dev](https://whyhirepruitt.dev)

---

**Built with ❤️ for production AI systems**

*NeMo Server v2.0 - Enterprise-grade conversational AI platform*
