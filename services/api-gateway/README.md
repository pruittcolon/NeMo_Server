# API Gateway Service

The main entry point for the Nemo Server system. Handles user authentication, session management, request routing, and serves the frontend application.

## Overview

The API Gateway acts as a reverse proxy and authentication layer between clients and backend microservices. It provides:

- **Authentication & Authorization**: JWT-based session management with encrypted SQLite storage
- **Request Routing**: Proxies requests to appropriate backend services
- **Frontend Serving**: Hosts static HTML/JS frontend files
- **Speaker Enrollment**: Manages audio samples for speaker verification
- **Security**: Rate limiting, CORS, replay attack protection

## Architecture

```
Client → API Gateway → Backend Services
         │
         ├─→ Transcription Service (audio processing)
         ├─→ Emotion Service (sentiment analysis)
         ├─→ RAG Service (semantic search)
         ├─→ Gemma Service (LLM inference)
         └─→ Queue Service (GPU coordination)
```

## Key Features

### Authentication System
- **User Management**: Role-based access control (admin/user)
- **Session Storage**: Encrypted SQLite database (`/app/instance/users.db`)
- **Secure Cookies**: HttpOnly, SameSite cookies for session management
- **Service-to-Service Auth**: JWT tokens for internal service communication

### API Endpoints

#### Public Routes
- `GET /` - Serve frontend application
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/session` - Check session status

#### Protected Routes (require authentication)
- `POST /api/transcribe` - Submit audio for transcription
- `POST /api/chat` - Send message to Gemma AI
- `GET /api/transcripts` - Retrieve transcription history
- `POST /api/rag/search` - Semantic search across memories
- `POST /api/speaker/enroll` - Enroll speaker audio sample
- `GET /api/speaker/list` - List enrolled speakers

### Frontend Serving
- Serves static files from `/app/frontend/`
- Single-page application routing
- Asset handling (CSS, JavaScript, images)

### Speaker Enrollment
- Stores speaker audio samples in `/app/instance/enrollment/{speaker_name}/`
- Used by transcription service for speaker verification
- Audio format validation and normalization

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMMA_URL` | `http://gemma-service:8001` | Gemma AI service URL |
| `RAG_URL` | `http://rag-service:8004` | RAG service URL |
| `EMOTION_URL` | `http://emotion-service:8005` | Emotion analysis URL |
| `TRANSCRIPTION_URL` | `http://transcription-service:8003` | Transcription service URL |
| `ALLOWED_ORIGINS` | `http://127.0.0.1,http://localhost` | CORS allowed origins |
| `SESSION_COOKIE_SECURE` | `false` | Use secure cookies (HTTPS only) |
| `SESSION_COOKIE_SAMESITE` | `strict` | Cookie SameSite policy |
| `MAX_UPLOAD_MB` | `100` | Maximum upload file size |

Secrets (Docker secrets or `/run/secrets/`):
- `session_key` - 32-byte base64 encryption key for session storage
- `jwt_secret` - JWT signing key for service authentication

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'admin' or 'user'
    created_at REAL NOT NULL,
    metadata TEXT  -- JSON blob for additional data
);
```

### Sessions Table
```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## Security Features

1. **Password Hashing**: bcrypt with salt
2. **Database Encryption**: pysqlcipher3 for encrypted SQLite
3. **Session Expiration**: Configurable TTL for sessions
4. **Rate Limiting**: Login attempt throttling by IP
5. **Replay Protection**: Request ID tracking for service-to-service calls
6. **CORS**: Configurable allowed origins
7. **Input Validation**: Pydantic models for request validation

## Dependencies

See `requirements.txt` for full list. Key dependencies:
- **fastapi** - Web framework
- **httpx** - Async HTTP client for proxying
- **bcrypt** - Password hashing
- **cryptography** - Encryption utilities
- **pysqlcipher3** - Encrypted SQLite
- **python-jose** - JWT handling
- **librosa, soundfile** - Audio processing for enrollment

## Development

Run standalone (for testing):
```bash
cd services/api-gateway
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Run in Docker:
```bash
docker compose up api-gateway
```

## API Examples

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your_password"}'
```

### Transcribe Audio
```bash
curl -X POST http://localhost:8000/api/transcribe \
  -H "Cookie: session_id=your_session_cookie" \
  -F "audio=@recording.wav"
```

### Semantic Search
```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Cookie: session_id=your_session_cookie" \
  -H "Content-Type: application/json" \
  -d '{"query": "what did they say about wireless?", "top_k": 5}'
```

## Monitoring

Health check endpoint:
```bash
curl http://localhost:8000/health
```

Logs include:
- Authentication events
- Request routing
- Service communication errors
- Performance metrics
