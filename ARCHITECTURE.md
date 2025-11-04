# Nemo Server Architecture

Comprehensive technical architecture documentation for the Nemo Server microservices platform.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Microservices Architecture](#microservices-architecture)
3. [Data Flow](#data-flow)
4. [GPU Coordination](#gpu-coordination)
5. [Security Architecture](#security-architecture)
6. [Database Design](#database-design)
7. [Networking](#networking)
8. [Deployment](#deployment)

---

## System Overview

Nemo Server is a distributed microservices system designed for real-time conversational AI with memory and context awareness.

### Core Capabilities

```
┌─────────────────────────────────────────────────────────────┐
│                    Nemo Server Platform                     │
├─────────────────────────────────────────────────────────────┤
│  Speech → Text → Emotion → Memory → AI Response → Output   │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | HTML5, JavaScript, CSS3 |
| **API Gateway** | FastAPI, Python 3.12 |
| **Microservices** | FastAPI, Docker, Python 3.12 |
| **ML/AI** | NeMo, PyTorch, Transformers, llama.cpp |
| **Databases** | SQLite (SQLCipher), PostgreSQL, Redis, FAISS |
| **Infrastructure** | Docker Compose, NVIDIA Docker, CUDA 12.6+ |
| **Security** | JWT, bcrypt, AES-256, TLS |

---

## Microservices Architecture

### Service Map

```
                        ┌─────────────────┐
                        │   API Gateway   │
                        │   (Port 8000)   │
                        └────────┬────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
    ┌────▼────┐           ┌─────▼──────┐         ┌─────▼─────┐
    │Transc.  │           │   Gemma    │         │    RAG    │
    │(8003)   │◄─────────►│   (8001)   │◄────────┤  (8004)   │
    └────┬────┘           └─────┬──────┘         └───────────┘
         │                      │
         │           ┌──────────▼────────────┐
         │           │  GPU Coordinator      │
         │           │     (8002)            │
         │           └───────────────────────┘
         │
    ┌────▼────┐
    │Emotion  │
    │(8005)   │
    └─────────┘

Infrastructure:
    Redis (6379) ────► Pub/Sub, Caching, Locks
    PostgreSQL (5432) ► Task Queue, Persistence
```

### Service Responsibilities

#### API Gateway (Port 8000)
- **Role**: Entry point, authentication, routing
- **Dependencies**: All backend services
- **Database**: Encrypted SQLite (`/app/instance/users.db`)
- **Key Functions**:
  - User authentication & session management
  - Request routing to backend services
  - Frontend static file serving
  - Speaker enrollment management
  - CORS & security middleware

#### Transcription Service (Port 8003)
- **Role**: Speech-to-text with diarization
- **Dependencies**: Emotion Service, RAG Service, GPU Coordinator
- **Database**: None (stateless)
- **Key Functions**:
  - ASR using NVIDIA NeMo Parakeet
  - Speaker diarization (NeMo + Pyannote)
  - Voice activity detection (VAD)
  - Speaker verification
  - Audio quality metrics extraction
- **GPU**: Primary GPU owner (with pause/resume)

#### Gemma AI Service (Port 8001)
- **Role**: LLM inference with RAG
- **Dependencies**: RAG Service, GPU Coordinator
- **Database**: None (stateless)
- **Key Functions**:
  - Chat completion with Gemma 3 4B
  - RAG context injection
  - Streaming response generation
  - Conversation history management
- **GPU**: On-demand GPU access

#### Emotion Service (Port 8005)
- **Role**: Sentiment analysis
- **Dependencies**: None
- **Database**: None (stateless)
- **Key Functions**:
  - Text emotion classification (6 classes)
  - Batch processing support
  - DistilRoBERTa model inference
- **GPU**: CPU-only

#### RAG Service (Port 8004)
- **Role**: Semantic memory search
- **Dependencies**: None
- **Database**: 
  - Encrypted SQLite (`/app/instance/rag.db`)
  - FAISS index (`/app/faiss_index/`)
- **Key Functions**:
  - Vector embedding generation
  - FAISS similarity search
  - Transcript indexing
  - Memory management
  - Temporal filtering

#### GPU Coordinator (Port 8002)
- **Role**: GPU resource management
- **Dependencies**: Redis, PostgreSQL
- **Database**: PostgreSQL (task queue)
- **Key Functions**:
  - GPU lock management
  - Pause/resume signaling
  - Task queuing & persistence
  - Resource monitoring

---

## Data Flow

### Transcription Flow

```
1. Client uploads audio → API Gateway
2. Gateway authenticates → forwards to Transcription Service
3. Transcription Service:
   ├─ VAD segments audio
   ├─ ASR transcribes text
   ├─ Diarization identifies speakers
   ├─ Sends segments to Emotion Service → emotion labels
   └─ Sends complete transcript to RAG Service → indexed
4. Return results to client
```

### Chat Flow with RAG

```
1. Client sends message → API Gateway
2. Gateway authenticates → forwards to Gemma Service
3. Gemma Service:
   ├─ Queries RAG Service for relevant context
   ├─ Builds prompt with RAG context + message
   ├─ Requests GPU from Coordinator
   ├─ Waits for GPU lock (Transcription pauses)
   ├─ Performs LLM inference
   ├─ Releases GPU (Transcription resumes)
   └─ Returns response (streaming or complete)
4. Return response to client
```

### Semantic Search Flow

```
1. Client sends query → API Gateway
2. Gateway authenticates → forwards to RAG Service
3. RAG Service:
   ├─ Embeds query text
   ├─ FAISS similarity search
   ├─ Fetches metadata from SQLite
   ├─ Applies filters (date, speaker, emotion)
   └─ Returns ranked results
4. Return results to client
```

---

## GPU Coordination

### Problem Statement

Single GPU systems cannot run both ASR and LLM simultaneously due to VRAM constraints. Nemo Server implements intelligent GPU sharing.

### Solution: Pause/Resume Protocol

#### State Machine

```
┌─────────────────────┐
│  Transcription      │
│  Owns GPU           │
│  (Default State)    │
└──────────┬──────────┘
           │
           │ Gemma Request
           ▼
┌─────────────────────┐
│  Coordinator        │
│  Sends PAUSE        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Transcription      │
│  Pauses, ACKs       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Gemma Acquires     │
│  GPU Lock           │
└──────────┬──────────┘
           │
           │ Inference Complete
           ▼
┌─────────────────────┐
│  Gemma Releases     │
│  GPU Lock           │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Coordinator        │
│  Sends RESUME       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Transcription      │
│  Resumes Processing │
└─────────────────────┘
```

#### Implementation Details

**Redis Pub/Sub Channels:**
- `channel:transcription:control` - PAUSE/RESUME signals
- `channel:gemma:control` - Gemma notifications

**Lock Mechanism:**
- Redis key: `gpu:lock:current`
- TTL: 300 seconds (auto-expire)
- Atomic operations with SETNX

**Timings:**
- Pause acknowledgment: <100ms
- GPU model swap: 500-800ms
- Total overhead: ~1-2 seconds

---

## Security Architecture

### Defense in Depth

```
┌─────────────────────────────────────────────────┐
│  Layer 1: Network (CORS, Firewall)             │
├─────────────────────────────────────────────────┤
│  Layer 2: Authentication (JWT, Sessions)        │
├─────────────────────────────────────────────────┤
│  Layer 3: Authorization (RBAC, Permissions)     │
├─────────────────────────────────────────────────┤
│  Layer 4: Data Encryption (SQLCipher, TLS)     │
├─────────────────────────────────────────────────┤
│  Layer 5: Container Isolation (Docker)          │
└─────────────────────────────────────────────────┘
```

### Authentication Flow

```
User Login:
    ↓
Bcrypt password hash verification
    ↓
Generate session ID + session token
    ↓
Encrypt session data (AES-256)
    ↓
Store in SQLCipher database
    ↓
Return HttpOnly cookie
    ↓
Subsequent requests validate session
```

### Service-to-Service Authentication

```
Service A → Service B:
    ↓
Generate JWT with:
  - service_id: "service-a"
  - request_id: UUID (replay protection)
  - expires_at: timestamp + 60s
  - aud: "internal"
    ↓
Sign with jwt_secret
    ↓
Send in X-Service-Token header
    ↓
Service B verifies:
  - JWT signature valid
  - Not expired
  - service_id in allowed list
  - request_id not seen (Redis cache)
    ↓
Process request
```

---

## Database Design

### User Database (SQLCipher)

**Location**: `/app/instance/users.db`

```sql
-- Users table
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at REAL NOT NULL,
    metadata TEXT
);

-- Sessions table
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### RAG Database (SQLCipher)

**Location**: `/app/instance/rag.db`

```sql
-- Documents table (transcript segments)
CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    text_content TEXT NOT NULL,
    embedding_id INTEGER NOT NULL,
    speaker TEXT,
    timestamp REAL,
    metadata TEXT,
    created_at REAL NOT NULL
);

-- Sessions table (transcription sessions)
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    job_id TEXT,
    full_text TEXT,
    audio_duration REAL,
    created_at REAL NOT NULL
);

-- Memories table (user-created notes)
CREATE TABLE memories (
    memory_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    embedding_id INTEGER NOT NULL,
    metadata TEXT,
    created_at REAL NOT NULL
);
```

### Task Queue (PostgreSQL)

**Database**: `nemo_queue`

```sql
-- Tasks table
CREATE TABLE tasks (
    task_id VARCHAR(36) PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    payload JSONB NOT NULL,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- GPU locks table
CREATE TABLE gpu_locks (
    lock_id VARCHAR(36) PRIMARY KEY,
    service_id VARCHAR(50) NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    released_at TIMESTAMP,
    timeout_seconds INTEGER NOT NULL
);
```

---

## Networking

### Docker Networks

```yaml
networks:
  nemo_network:
    driver: bridge
    internal: false
```

All services communicate via the `nemo_network` bridge network.

### Port Mapping

| Service | Internal Port | External Port | Public? |
|---------|--------------|---------------|---------|
| API Gateway | 8000 | 8000 | ✅ Yes |
| Gemma | 8001 | - | ❌ No |
| GPU Coordinator | 8002 | - | ❌ No |
| Transcription | 8003 | - | ❌ No |
| RAG | 8004 | - | ❌ No |
| Emotion | 8005 | - | ❌ No |
| Redis | 6379 | 127.0.0.1:6379 | ⚠️ Localhost only |
| PostgreSQL | 5432 | 127.0.0.1:5432 | ⚠️ Localhost only |

### Service Discovery

Services use Docker's internal DNS:
- `http://api-gateway:8000`
- `http://gemma-service:8001`
- `redis://redis:6379`
- `postgresql://postgres:5432`

---

## Deployment

### Development

```bash
./start.sh
```

### Production Considerations

1. **Reverse Proxy** (Nginx/Traefik)
   ```nginx
   server {
       listen 443 ssl;
       server_name nemo.example.com;
       
       location / {
           proxy_pass http://localhost:8000;
       }
   }
   ```

2. **Docker Compose Production Override**
   ```yaml
   # docker-compose.prod.yml
   services:
     api-gateway:
       environment:
         - SESSION_COOKIE_SECURE=true
         - ALLOWED_ORIGINS=https://nemo.example.com
   ```

3. **Monitoring**
   - Prometheus metrics endpoints
   - Grafana dashboards
   - ELK stack for logs

4. **Scaling**
   - Horizontal: Multiple API Gateway instances (load balanced)
   - Vertical: Larger GPU for faster inference
   - Sharding: Separate RAG databases per tenant

---

## Performance Characteristics

| Operation | Latency | Throughput |
|-----------|---------|------------|
| ASR (1 min audio) | 20-30s | 2-3x realtime |
| Emotion analysis | <100ms | 1000 req/s |
| Semantic search | <50ms | 500 req/s |
| LLM inference | 2-5s | 20-30 tok/s |
| GPU context switch | 1-2s | - |

---

## Failure Modes & Recovery

### Service Failures

| Failure | Impact | Recovery |
|---------|--------|----------|
| API Gateway down | No access | Docker restart, health checks |
| Transcription down | No ASR | Queue requests, restart |
| Gemma down | No AI chat | Fallback messages, restart |
| RAG down | No search/context | Degraded mode, restart |
| GPU Coordinator down | GPU conflicts | Manual intervention |
| Redis down | No coordination | All services affected |
| PostgreSQL down | Task queue lost | Persistent tasks survive |

### Data Loss Prevention

- SQLite databases: Volume-mounted, persistent
- FAISS index: Volume-mounted, persistent
- Task queue: PostgreSQL with WAL
- Regular backups recommended

---

## Future Enhancements

1. **Multi-GPU Support**: Dedicated GPUs per service
2. **Kubernetes**: Container orchestration
3. **Message Queue**: RabbitMQ/Kafka for async processing
4. **Streaming Pipeline**: Real-time audio streaming
5. **Multi-tenancy**: Isolated resources per tenant
6. **Model Registry**: Centralized model management

---

For implementation details, see service-specific README files.
