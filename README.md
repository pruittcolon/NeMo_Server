# Nemo Server - Enterprise AI Voice Intelligence Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![CUDA 12.1](https://img.shields.io/badge/CUDA-12.1-green.svg)](https://developer.nvidia.com/cuda-downloads)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

> **Production-grade AI platform** for real-time voice transcription, speaker diarization, emotion analysis, and contextual memory with RAG-powered insights.

---

## 🚀 Quick Start

```bash
# Clone or navigate to the project
cd ~/Desktop/Nemo_Server

# Start the server (one command!)
./scripts/start.sh

# Access the platform
# Dashboard:  http://localhost:8000/ui/
# API Docs:   http://localhost:8000/docs
# Login:      http://localhost:8000/ui/login.html
```

> **Accounts:** Provision users via `scripts/create_user.py` or your preferred secrets manager before first run—no static passwords are stored in the repo.

---

## 📋 Features

### 🎙️ **Real-Time Voice Processing**
- **Automatic Speech Recognition (ASR)**: NVIDIA NeMo Parakeet-TDT-0.6B model
- **Speaker Diarization**: TitaNet speaker embeddings with K-means clustering
- **Emotion Analysis**: DistilRoBERTa-based sentiment detection
- **GPU-Accelerated**: Optimized for NVIDIA GTX 1660 Ti (6GB VRAM)

### 🧠 **AI-Powered Intelligence**
- **Gemma LLM Integration**: 4B parameter model (Q4_K_M quantization)
- **RAG System**: FAISS vector search with MiniLM embeddings
- **Contextual Memory**: Long-term conversation tracking
- **Personality Analysis**: Behavioral pattern recognition

### 🔒 **Security**
- **Role-Based Access Control**: Admin and User roles
- **100% Speaker-Based Data Isolation**: Users see only their speaker's data
- **Job Ownership Tracking**: Analysis jobs tracked by creator
- **Session Management**: Secure HTTP-only cookies
- **Authentication API**: Bcrypt password hashing
- **Firewall-Ready**: Docker network isolation

> ⚠️ **Production hardening note:** Access-control helpers (`require_auth`, speaker filters, role checks) are already implemented under `src/auth/permissions.py`, but not every service/router wires them in yet. Before any production deployment:
> - Protect every RAG (`/memory`, `/transcript`, `/query`) and speaker (`/enroll/*`) route with `Depends(require_auth)` / `require_admin`.
> - Pass the authenticated user into service layers and filter memories/transcripts by `speaker_id`.
> - Remove the IP-based `/transcribe` bypass, require device tokens for mobile clients, and enable HTTPS-only cookies + CSRF protection.
> - Rotate the demo credentials and load secrets from your deployment environment.

### ✅ Security TODO (pre-production)
1. Provision credentials via `scripts/create_user.py` or secrets manager before launch; force password rotation on first login.
2. Wire speaker-aware filters and ownership checks through RAG/Gemma services (routers are now protected, but filtering is still TODO).
3. Implement CSRF tokens, `secure=True` cookies, and remove the `/transcribe` IP whitelist so every client authenticates.
4. Run `pytest tests/test_speaker_isolation.py` and `tests/test_security_comprehensive.sh` as part of CI before deployment.

### 🔐 **Speaker Isolation**
- **100% Data Separation**: Users see only their speaker's transcripts and analysis
- **Admin Override**: Admin users can view all speakers
- **Secure by Default**: Backend SQL filtering + frontend UI hiding
- **Job Ownership**: Analysis jobs tracked by creator

### 🎨 **Modern UI**
- **Glassmorphism Design**: Beautiful gradient backgrounds
- **10 Dedicated Pages**: Dashboard, transcripts, speakers, emotions, memories, RAG search, Gemma chat, patterns, settings, about
- **Responsive Layout**: Works on desktop and tablet
- **Real-Time Updates**: WebSocket support for live transcription

---

## 🏗️ Architecture

```
Nemo_Server/
├── src/                    # Python source code
│   ├── main.py            # FastAPI application entry point
│   ├── auth/              # Authentication system
│   ├── services/          # Microservices (ASR, speaker, RAG, emotion, Gemma)
│   ├── models/            # ML model managers
│   ├── utils/             # GPU & audio utilities
│   └── security/          # Security helpers
├── frontend/              # HTML/CSS/JS frontend
│   ├── index.html         # Dashboard
│   ├── login.html         # Authentication
│   ├── transcripts.html   # Transcription viewer
│   └── assets/            # CSS, JS, images
├── docker/                # Docker configuration
│   ├── Dockerfile         # Production image
│   ├── docker-compose.yml # Orchestration
│   └── *.dev              # Development alternatives
├── tests/                 # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── e2e/               # End-to-end tests
├── docs/                  # Documentation
│   ├── api/               # API documentation
│   ├── deployment/        # Deployment guides
│   ├── development/       # Development notes
│   └── guides/            # User guides
└── scripts/               # Helper scripts
    └── start.sh           # One-command startup
```

---

## 📦 Requirements

### Hardware
- **GPU**: NVIDIA GTX 1660 Ti (6GB VRAM) or equivalent
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 80GB+ available
- **CPU**: 8+ cores recommended

### Software
- **OS**: Ubuntu 22.04+ or compatible Linux
- **Docker**: 24.0.0+
- **Docker Compose**: 2.20.0+
- **NVIDIA Docker Runtime**: For GPU access
- **CUDA**: 12.1+ (via Docker image)

---

## 🔧 Installation

### 1. Prerequisites

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Verify GPU access
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

### 2. Build & Start

```bash
cd ~/Desktop/Nemo_Server/docker
docker compose build
docker compose up -d
```

### 3. Verify

```bash
# Check container status
docker ps

# Check logs
docker logs -f nemo_server

# Test health endpoint
curl http://localhost:8000/health
```

---

## 🎯 Usage

### API Endpoints

**Authentication**
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `POST /api/auth/check` - Session validation

**Transcription**
- `POST /api/transcribe` - Upload audio for transcription
- `POST /api/transcribe/stream` - Real-time streaming
- `GET /api/transcripts` - List all transcripts

**Speaker Analysis**
- `POST /api/speakers/analyze` - Analyze speaker embeddings
- `GET /api/speakers` - List speakers
- `POST /api/speakers/identify` - Identify speaker

**Emotion Analysis**
- `POST /api/emotions/analyze` - Analyze text for emotions
- `GET /api/emotions/history` - Emotion history

**RAG/Memory**
- `POST /api/rag/search` - Semantic memory search
- `POST /api/rag/add` - Add memory
- `GET /api/memories` - List memories

**Gemma Chat**
- `POST /api/gemma/chat` - Chat with Gemma AI
- `POST /api/gemma/analyze` - Context analysis

See full API documentation at `http://localhost:8000/docs`

### Frontend Pages

1. **Dashboard** (`/ui/`) - System overview with stats
2. **Transcripts** (`/ui/transcripts.html`) - View all transcriptions
3. **Speakers** (`/ui/speakers.html`) - Speaker profiles and analytics
4. **Emotions** (`/ui/emotions.html`) - Emotion timeline and distribution
5. **Memories** (`/ui/memories.html`) - Long-term memory browser
6. **Search** (`/ui/search.html`) - RAG-powered semantic search
7. **Gemma** (`/ui/gemma.html`) - Chat with Gemma AI
8. **Patterns** (`/ui/patterns.html`) - Behavioral pattern analysis
9. **Settings** (`/ui/settings.html`) - User preferences
10. **About** (`/ui/about.html`) - System information

---

## ⚙️ Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Server
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info

# GPU
CUDA_VISIBLE_DEVICES=0
PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# Models
MODEL_CACHE_DIR=/app/models
HF_HOME=/root/.cache/huggingface

# Security (CHANGE IN PRODUCTION!)
SECRET_KEY=your-secret-key-here
SESSION_EXPIRATION_MINUTES=1440

# Features
ENABLE_GPU=true
ENABLE_DIARIZATION=true
ENABLE_EMOTION_ANALYSIS=true
```

### Docker Compose

```yaml
services:
  nemo-server:
    image: nemo-server:latest
    container_name: nemo_server
    ports:
      - "8000:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface:ro
      - ./models:/app/models:ro
      - ./data:/app/data
      - ./logs:/app/logs
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

---

## 🧪 Testing

```bash
# Run all tests
cd ~/Desktop/Nemo_Server
docker exec nemo_server pytest

# Run unit tests only
docker exec nemo_server pytest tests/unit/

# Run with coverage
docker exec nemo_server pytest --cov=src --cov-report=html

# Smoke test
./tests/smoke_test.sh
```

---

## 🐛 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs nemo_server

# Check GPU access
docker exec nemo_server nvidia-smi

# Restart container
cd docker
docker compose restart
```

### Port Already in Use

```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill old containers
docker stop $(docker ps -q --filter ancestor=nemo-server)
```

### GPU Not Detected

```bash
# Verify NVIDIA runtime
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi

# Check nvidia-container-toolkit
sudo systemctl status nvidia-container-runtime

# Restart Docker daemon
sudo systemctl restart docker
```

### Import Errors

```bash
# Verify Python path
docker exec nemo_server python3.10 -c "import sys; print('\n'.join(sys.path))"

# Test imports
docker exec nemo_server python3.10 -c "from src.auth.auth_manager import auth_manager; print('✅ Imports work')"
```

---

## 📚 Documentation

- **API Reference**: `docs/api/COMPREHENSIVE_FEATURE_INVENTORY.md`
- **Build Guide**: `docs/guides/BUILD_AND_TEST_GUIDE.md`
- **Deployment**: `docs/deployment/DEPLOYMENT.md`
- **Development**: `docs/development/CHANGELOG.md`
- **Quick Start**: `docs/guides/QUICKSTART.md`

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Code Standards
- Python 3.10+ with type hints
- FastAPI best practices
- 90%+ test coverage for new code
- Black code formatting
- Docstrings for all public functions

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **NVIDIA NeMo**: ASR and speaker models
- **Hugging Face**: Model hosting and transformers
- **llama.cpp**: Efficient LLM inference
- **FastAPI**: Modern Python web framework
- **FAISS**: Vector similarity search

---review the plan on the html


## 📞 Support

For issues, questions, or feature requests:
- **Issues**: [GitHub Issues](https://github.com/yourusername/nemo_server/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/nemo_server/discussions)

---

## 🗺️ Roadmap

- [ ] Multi-GPU support
- [ ] Kubernetes deployment
- [ ] Real-time audio streaming (WebRTC)
- [ ] Multi-language support
- [ ] Custom model fine-tuning
- [ ] Enhanced security (OAuth2, LDAP)
- [ ] Performance monitoring (Prometheus/Grafana)
- [ ] Mobile app integration

---

**Built with ❤️ for enterprise AI applications**
