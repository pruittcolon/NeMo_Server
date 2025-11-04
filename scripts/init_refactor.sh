#!/usr/bin/env bash
# ================================================================================
# REFACTORED Architecture Initialization Script
# ================================================================================
# Creates clean microservice architecture with deterministic GPU ownership
# Gemma gets exclusive GPU access; all other services run on CPU
# Idempotent: safe to run multiple times
# ================================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REFACTORED_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "======================================================================"
echo "REFACTORED ARCHITECTURE INITIALIZATION"
echo "======================================================================"
echo "Target: ${REFACTORED_ROOT}"
echo ""

cd "$REFACTORED_ROOT"

# ================================================================================
# SERVICE DIRECTORIES
# ================================================================================

echo "[1/8] Creating service directories..."

SERVICES=(
    "gemma-service"
    "api-service"
    "rag-service"
    "emotion-service"
)

for service in "${SERVICES[@]}"; do
    echo "  - services/${service}/"
    mkdir -p "services/${service}"/{src,tests,config}
    touch "services/${service}"/__init__.py
done

# ================================================================================
# DOCKER CONFIGURATION
# ================================================================================

echo "[2/8] Creating Docker configuration..."

mkdir -p docker

# docker-compose.yml
cat > docker/docker-compose.yml <<'EOF'
version: '3.8'

services:
  # ============================================================================
  # GEMMA SERVICE - Exclusive GPU Access
  # ============================================================================
  gemma-service:
    build:
      context: ..
      dockerfile: docker/Dockerfile.gemma
    container_name: refactored_gemma
    environment:
      - CUDA_VISIBLE_DEVICES=0
      - NVIDIA_VISIBLE_DEVICES=all
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    volumes:
      - ../models:/app/models:ro
      - ../data/gemma:/app/data
    ports:
      - "8001:8001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    networks:
      - refactored_net

  # ============================================================================
  # API SERVICE - FastAPI Gateway (CPU)
  # ============================================================================
  api-service:
    build:
      context: ..
      dockerfile: docker/Dockerfile.api
    container_name: refactored_api
    environment:
      - CUDA_VISIBLE_DEVICES=""
      - NVIDIA_VISIBLE_DEVICES=void
      - GEMMA_SERVICE_URL=http://gemma-service:8001
      - RAG_SERVICE_URL=http://rag-service:8002
      - EMOTION_SERVICE_URL=http://emotion-service:8003
    volumes:
      - ../data/api:/app/data
      - ../frontend:/app/frontend:ro
    ports:
      - "8000:8000"
    depends_on:
      - gemma-service
      - rag-service
      - emotion-service
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - refactored_net

  # ============================================================================
  # RAG SERVICE - FAISS + MiniLM (CPU)
  # ============================================================================
  rag-service:
    build:
      context: ..
      dockerfile: docker/Dockerfile.rag
    container_name: refactored_rag
    environment:
      - CUDA_VISIBLE_DEVICES=""
      - NVIDIA_VISIBLE_DEVICES=void
    volumes:
      - ../models:/app/models:ro
      - ../data/rag:/app/data
    ports:
      - "8002:8002"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - refactored_net

  # ============================================================================
  # EMOTION SERVICE - DistilRoBERTa (CPU)
  # ============================================================================
  emotion-service:
    build:
      context: ..
      dockerfile: docker/Dockerfile.emotion
    container_name: refactored_emotion
    environment:
      - CUDA_VISIBLE_DEVICES=""
      - NVIDIA_VISIBLE_DEVICES=void
    volumes:
      - ../models:/app/models:ro
      - ../data/emotion:/app/data
    ports:
      - "8003:8003"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - refactored_net

networks:
  refactored_net:
    driver: bridge
EOF

echo "  - docker/docker-compose.yml"

# ================================================================================
# SHARED MODULES
# ================================================================================

echo "[3/8] Creating shared modules..."

mkdir -p shared/{auth,models,utils}
touch shared/__init__.py
touch shared/auth/__init__.py
touch shared/models/__init__.py
touch shared/utils/__init__.py

echo "  - shared/{auth,models,utils}/"

# ================================================================================
# TESTS
# ================================================================================

echo "[4/8] Creating test directory..."

mkdir -p tests/{unit,integration,smoke}
touch tests/__init__.py
touch tests/conftest.py

echo "  - tests/{unit,integration,smoke}/"

# ================================================================================
# MAKEFILE
# ================================================================================

echo "[5/8] Creating Makefile..."

cat > Makefile <<'EOF'
.PHONY: help init up down restart logs test smoke clean

help:
	@echo "REFACTORED Nemo Server - Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make init   - Initialize environment (first-time setup)"
	@echo "  make up     - Start all services"
	@echo "  make down   - Stop all services"
	@echo "  make restart - Restart all services"
	@echo "  make logs   - Tail logs from all services"
	@echo "  make test   - Run full test suite"
	@echo "  make smoke  - Run smoke tests"
	@echo "  make clean  - Clean up build artifacts"

init:
	@echo "Initializing REFACTORED environment..."
	@bash scripts/healthcheck.sh
	@bash scripts/conflict_check.sh
	@echo "✅ Initialization complete"

up:
	@echo "Starting services..."
	@docker compose -f docker/docker-compose.yml up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@docker compose -f docker/docker-compose.yml ps
	@echo "✅ Services started"

down:
	@echo "Stopping services..."
	@docker compose -f docker/docker-compose.yml down
	@echo "✅ Services stopped"

restart: down up

logs:
	@docker compose -f docker/docker-compose.yml logs -f

test:
	@echo "Running test suite..."
	@pytest tests/ -v

smoke:
  @echo "Running smoke tests (pytest)..."
  @pytest -m smoke -v

clean:
	@echo "Cleaning build artifacts..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Clean complete"
EOF

echo "  - Makefile"

# ================================================================================
# SCRIPTS
# ================================================================================

echo "[6/8] Creating utility scripts..."

# Healthcheck script
cat > scripts/healthcheck.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

echo "Running pre-flight healthchecks..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found"
    exit 1
fi
echo "✅ Docker installed"

# Check GPU
if command -v nvidia-smi &> /dev/null; then
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    echo "✅ GPU available (${GPU_COUNT} device(s))"
else
    echo "⚠️  No GPU detected - Gemma service will fail"
fi

# Check models directory
if [[ ! -d "../models" ]]; then
    echo "⚠️  Models directory not found at ../models"
else
    echo "✅ Models directory exists"
fi

echo "Healthcheck complete"
EOF

chmod +x scripts/healthcheck.sh

# Conflict check script
cat > scripts/conflict_check.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

echo "Checking for port conflicts..."

PORTS=(8000 8001 8002 8003)
CONFLICTS=()

for port in "${PORTS[@]}"; do
    if lsof -Pi :${port} -sTCP:LISTEN -t >/dev/null 2>&1; then
        CONFLICTS+=("$port")
    fi
done

if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
    echo "⚠️  Port conflicts detected: ${CONFLICTS[*]}"
    echo "   Run: make down (or kill existing services)"
else
    echo "✅ No port conflicts"
fi
EOF

chmod +x scripts/conflict_check.sh

# Smoke test script (deprecated stub)
cat > scripts/smoke_test.sh <<'EOF'
#!/usr/bin/env bash
echo "This script is deprecated. Use: pytest -m smoke -v" >&2
exit 1
EOF

chmod +x scripts/smoke_test.sh

echo "  - scripts/{healthcheck,conflict_check}.sh"

# ================================================================================
# DOCUMENTATION
# ================================================================================

echo "[7/8] Creating documentation..."

cat > README.md <<'EOF'
# REFACTORED Nemo Server

Clean microservice architecture with deterministic GPU ownership.

## Architecture

### Service Separation
- **gemma-service** (port 8001): Exclusive GPU access for Gemma 3 4B inference
- **api-service** (port 8000): FastAPI gateway, authentication, routing (CPU)
- **rag-service** (port 8002): FAISS vector store + MiniLM embeddings (CPU)
- **emotion-service** (port 8003): DistilRoBERTa emotion analysis (CPU)

### GPU Ownership
- Gemma service: `CUDA_VISIBLE_DEVICES=0`, `NVIDIA_VISIBLE_DEVICES=all`
- All other services: `CUDA_VISIBLE_DEVICES=""`, `NVIDIA_VISIBLE_DEVICES=void`

## Quick Start

```bash
# 1. Initialize (first time only)
make init

# 2. Start all services
make up

# 3. Verify health
make smoke

# 4. View logs
make logs

# 5. Stop services
make down
```

## Development Workflow

```bash
# Run tests
make test

# Restart after code changes
make restart

# Clean up
make clean
```

## Service URLs

- API Gateway: http://localhost:8000
- Gemma Service: http://localhost:8001
- RAG Service: http://localhost:8002
- Emotion Service: http://localhost:8003

## Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Smoke tests
make smoke
```

## Requirements

- Docker with GPU support (nvidia-docker2)
- NVIDIA GPU (GTX 1660 Ti or better)
- CUDA 12.5+
- 52GB free disk space (from cleanup)

## Phase Plan Template

Before implementing each service, create a phase plan:

1. **Requirements**: What this service must do
2. **Dependencies**: External services/models required
3. **API Contract**: Endpoints, request/response schemas
4. **Verification**: How to test it works
5. **Conflict Checks**: Potential issues with other services

See `services/*/README.md` for per-service plans.
EOF

echo "  - README.md"

# ================================================================================
# SERVICE PLACEHOLDERS
# ================================================================================

echo "[8/8] Creating service placeholder files..."

for service in "${SERVICES[@]}"; do
    # Service README with phase plan template
    cat > "services/${service}/README.md" <<EOF
# ${service}

## Phase Plan

### 1. Requirements
- [ ] TODO: Define what this service must do

### 2. Dependencies
- [ ] TODO: List required models, libraries, external services

### 3. API Contract
- [ ] TODO: Define endpoints with request/response schemas

### 4. Verification Steps
- [ ] TODO: How to test this service works correctly

### 5. Conflict Checks
- [ ] TODO: Potential conflicts with other services
- [ ] TODO: Resource requirements (CPU, memory, GPU)

## Implementation Status

- [ ] Dockerfile created
- [ ] Requirements defined
- [ ] Service code implemented
- [ ] Tests written
- [ ] Health check endpoint working
- [ ] Integrated with docker-compose

## Notes

(Add implementation notes here)
EOF

    # requirements.txt placeholder
    cat > "services/${service}/requirements.txt" <<EOF
# ${service} Python dependencies
# TODO: Add required packages
fastapi==0.110.3
uvicorn[standard]==0.30.6
pydantic==2.10.6
EOF

    # Dockerfile placeholder
    cat > "docker/Dockerfile.${service%-service}" <<EOF
FROM python:3.12-slim

WORKDIR /app

# TODO: Add system dependencies
RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/${service}/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/${service}/src /app/src
COPY shared /app/shared

# Set Python path
ENV PYTHONPATH=/app:\$PYTHONPATH

# Expose service port
EXPOSE 800X

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \\
    CMD curl -f http://localhost:800X/health || exit 1

# Run service
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "800X"]
EOF

done

echo ""
echo "======================================================================"
echo "✅ REFACTORED ARCHITECTURE INITIALIZED"
echo "======================================================================"
echo ""
echo "Structure created:"
echo "  - services/ (gemma, api, rag, emotion)"
echo "  - docker/ (compose + Dockerfiles)"
echo "  - shared/ (auth, models, utils)"
echo "  - tests/ (unit, integration, smoke)"
echo "  - Makefile"
echo "  - README.md"
echo ""
echo "Next steps:"
echo "  1. Review service phase plans in services/*/README.md"
echo "  2. Implement each service following the phase plan"
echo "  3. Build Docker images: make up"
echo "  4. Run smoke tests: make smoke"
echo ""
echo "======================================================================"



