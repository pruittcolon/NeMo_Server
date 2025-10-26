# WhisperServer REFACTORED - Deployment Guide

## Quick Start

### Prerequisites
- Docker with GPU support (NVIDIA Container Toolkit)
- 80GB+ disk space
- NVIDIA GPU with 6GB+ VRAM
- Models already downloaded at `/home/pruittcolon/Downloads/WhisperServer/models/`

### 1. Build Container
```bash
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
docker compose build
```
**Note:** Initial build takes 15-25 minutes (compiling llama-cpp-python with CUDA)

### 2. Start Services
```bash
docker compose up -d
```

### 3. Access Interfaces
- **HTML UI:** http://localhost:8001/ui/index.html
- **API Docs:** http://localhost:8001/docs
- **Health Check:** http://localhost:8001/health

---

## Architecture

### Single Container Design
- **FastAPI Backend:** Port 8001
- **HTML Frontend:** Served at `/ui/`
- **Shared Models:** Mounted read-only from parent directory

### GPU Allocation
- **ASR (Parakeet-CTC-1.1B):** ~2GB VRAM
- **Gemma AI (3-4B Q4_K_M):** ~4GB VRAM
- **Other Services:** CPU only

### Services on CPU
- Speaker Diarization (TitaNet)
- Emotion Analysis (DistilRoBERTa)
- RAG/Memory (FAISS + MiniLM)

---

## Differences from Original

| Feature | Original (Port 8000) | Refactored (Port 8001) |
|---------|---------------------|------------------------|
| Frontend | Next.js/React | Pure HTML/CSS/JS |
| Pages | ~50 .tsx files | 10 HTML pages |
| GPU Management | Mixed/unpredictable | Deterministic |
| Speaker Logic | 3x duplicate code | Consolidated |
| Model Loading | Eager | Lazy with fallbacks |
| Architecture | Monolithic | Service-based |

---

## Testing

### Smoke Test
```bash
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
./tests/smoke_test.sh
```

### Manual Tests
1. **Health:** `curl http://localhost:8001/health`
2. **Latest Transcription:** `curl http://localhost:8001/latest_result`
3. **Search:** `curl "http://localhost:8001/transcript/search?query=test"`
4. **HTML UI:** Open browser to http://localhost:8001/ui/

---

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker compose logs -f

# Check GPU access
docker exec whisperserver_refactored nvidia-smi
```

### Out of Disk Space
```bash
# Clean up old images
docker image prune -a

# Check usage
docker system df
```

### Models Not Loading
```bash
# Verify models directory
ls -lh /home/pruittcolon/Downloads/WhisperServer/models/

# Check mount
docker exec whisperserver_refactored ls -lh /app/models/
```

---

## Side-by-Side Testing

Both original and refactored can run simultaneously:
- **Original:** http://localhost:8000
- **Refactored:** http://localhost:8001

Compare performance, accuracy, and GPU usage in real-time.

---

## Stopping Services

```bash
# Stop refactored
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
docker compose down

# Stop original (if needed)
cd /home/pruittcolon/Downloads/WhisperServer
docker-compose -f docker-compose.dev.yml down
```

