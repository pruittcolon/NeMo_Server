# GPU Coordinator Service (Queue Service)

Manages GPU ownership and task scheduling for shared GPU resources between Transcription and Gemma services.

## Overview

Coordinates GPU access to prevent conflicts on single-GPU systems:

- **Lock Management**: Redis-based distributed locking
- **Task Persistence**: PostgreSQL for durable task queue
- **GPU Monitoring**: Resource utilization tracking
- **Pause/Resume Signaling**: Redis pub/sub for service coordination
- **Priority Scheduling**: Configurable task priorities

## Architecture

The coordinator implements a **token-based exclusive lock** system:

```
Default State: Transcription owns GPU
    ↓
Gemma requests GPU
    ↓
Coordinator sends PAUSE to Transcription via Redis
    ↓
Transcription acknowledges pause
    ↓
Coordinator grants GPU lock to Gemma
    ↓
Gemma processes task
    ↓
Gemma releases GPU lock
    ↓
Coordinator sends RESUME to Transcription
    ↓
Normal transcription resumes
```

## Key Features

### 1. Distributed Locking
- Redis-based atomic operations
- TTL-based automatic lock release
- Deadlock prevention with timeouts
- Lock status monitoring

### 2. Task Persistence
- PostgreSQL storage for reliability
- Task state tracking (pending, running, completed, failed)
- Automatic retry logic
- Task history and metrics

### 3. Service Coordination
- Redis pub/sub for real-time signaling
- Acknowledgment-based state transitions
- Graceful degradation on communication failures

### 4. GPU Monitoring
- VRAM usage tracking
- Process identification
- Utilization metrics
- Health checks

## API Endpoints

### Request GPU Lock (for Gemma)
```bash
POST /gpu/request
Content-Type: application/json

{
  "service_id": "gemma-service",
  "timeout": 30
}
```

Response:
```json
{
  "status": "granted",
  "lock_id": "uuid",
  "granted_at": 1699000000.0
}
```

### Release GPU Lock
```bash
POST /gpu/release
Content-Type: application/json

{
  "lock_id": "uuid"
}
```

### Submit Gemma Task
```bash
POST /task/gemma
Content-Type: application/json

{
  "task_id": "uuid",
  "messages": [...],
  "max_tokens": 512,
  "temperature": 0.7
}
```

### Check Task Status
```bash
GET /task/{task_id}/status
```

Response:
```json
{
  "task_id": "uuid",
  "status": "completed",
  "result": {...},
  "created_at": 1699000000.0,
  "completed_at": 1699000005.0
}
```

### GPU Status
```bash
GET /gpu/status
```

Response:
```json
{
  "current_owner": "transcription-service",
  "lock_id": null,
  "vram_used_mb": 4096,
  "vram_total_mb": 8192,
  "utilization_percent": 75
}
```

### Health Check
```bash
GET /health
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379` | Redis connection string |
| `POSTGRES_URL` | Constructed from secrets | PostgreSQL connection |
| `JWT_ONLY` | `false` | Enforce JWT authentication |

PostgreSQL is configured via Docker secrets:
- `postgres_user`
- `postgres_password`

## Database Schema

### Tasks Table
```sql
CREATE TABLE tasks (
    task_id VARCHAR(36) PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, running, completed, failed
    payload JSONB NOT NULL,
    result JSONB,
    error TEXT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    priority INTEGER DEFAULT 0
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
```

### GPU Locks Table
```sql
CREATE TABLE gpu_locks (
    lock_id VARCHAR(36) PRIMARY KEY,
    service_id VARCHAR(50) NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    released_at TIMESTAMP,
    timeout_seconds INTEGER NOT NULL
);
```

## Redis Keys

- `gpu:lock:current` - Current lock holder (string)
- `gpu:lock:id` - Current lock ID (string)
- `gpu:lock:ttl` - Lock expiration (TTL)
- `channel:transcription:control` - Pub/sub channel for PAUSE/RESUME
- `channel:gemma:control` - Pub/sub channel for Gemma signals

## Locking Protocol

### Lock Acquisition
1. Client sends `/gpu/request`
2. Coordinator checks current lock state
3. If unlocked: Grant immediately
4. If locked: Wait or reject based on timeout
5. Publish PAUSE message to transcription
6. Wait for ACK from transcription
7. Set Redis lock with TTL
8. Return lock_id to client

### Lock Release
1. Client sends `/gpu/release` with lock_id
2. Coordinator validates lock_id
3. Delete Redis lock
4. Publish RESUME message to transcription
5. Log completion metrics

### Automatic Release
- Locks have TTL (default 300s)
- Redis automatically expires stale locks
- Coordinator detects expiration and sends RESUME

## Dependencies

- **redis**: Distributed locking and pub/sub
- **asyncpg**: Async PostgreSQL client
- **fastapi**: Web framework
- **pydantic**: Data validation

## Monitoring

### Key Metrics
- Lock acquisition latency
- Lock hold duration
- Task completion rate
- GPU utilization
- Service health status

### Logging
- Lock grant/release events
- Task state transitions
- Service communication errors
- Timeout events

## Examples

### Request GPU for Inference
```python
import httpx

# Request GPU
response = httpx.post("http://gpu-coordinator:8002/gpu/request", json={
    "service_id": "gemma-service",
    "timeout": 30
})
lock_data = response.json()
lock_id = lock_data["lock_id"]

try:
    # Do GPU work
    pass
finally:
    # Always release
    httpx.post("http://gpu-coordinator:8002/gpu/release", json={
        "lock_id": lock_id
    })
```

### Submit Task
```python
task_id = str(uuid.uuid4())
response = httpx.post("http://gpu-coordinator:8002/task/gemma", json={
    "task_id": task_id,
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
})

# Poll for completion
while True:
    status = httpx.get(f"http://gpu-coordinator:8002/task/{task_id}/status")
    if status.json()["status"] in ["completed", "failed"]:
        break
    time.sleep(0.5)
```
