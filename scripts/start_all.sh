#!/bin/bash
# WhisperServer REFACTORED - Unified Startup Script
# Starts both FastAPI backend and Next.js frontend in single container

set -e  # Exit on error

echo "=========================================="
echo "WhisperServer Refactored - Starting"
echo "=========================================="

# Print environment info
echo "[STARTUP] Python version: $(python3.10 --version)"
echo "[STARTUP] Node version: $(node --version)"
echo "[STARTUP] GPU check..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "[STARTUP] WARNING: nvidia-smi not available"
fi

# Create necessary directories
mkdir -p /app/instance/uploads /app/logs /app/models

# Set Python path
export PYTHONPATH=/app:/app/src:/app/REFACTORED_SRC

echo ""
echo "=========================================="
echo "Starting FastAPI Backend (port 8000)"
echo "=========================================="

# Start FastAPI backend in background
cd /app
python3.10 -m uvicorn REFACTORED_SRC.main_refactored:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info \
    --no-access-log &

BACKEND_PID=$!
echo "[STARTUP] Backend started with PID: $BACKEND_PID"

# Wait for backend to be ready
echo "[STARTUP] Waiting for backend health check..."
RETRIES=30
for i in $(seq 1 $RETRIES); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "[STARTUP] ✅ Backend is healthy"
        break
    fi
    if [ $i -eq $RETRIES ]; then
        echo "[STARTUP] ❌ Backend failed to start after $RETRIES attempts"
        exit 1
    fi
    echo "[STARTUP] Waiting... ($i/$RETRIES)"
    sleep 4
done

echo ""
echo "=========================================="
echo "WhisperServer Refactored - READY"
echo "=========================================="
echo "Backend API:  http://localhost:8000"
echo "HTML UI:      http://localhost:8000/ui/index.html"
echo "API Docs:     http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo "=========================================="

# Trap SIGTERM and SIGINT to gracefully shut down
trap 'echo "Shutting down..."; kill $BACKEND_PID 2>/dev/null; wait; exit 0' SIGTERM SIGINT

# Wait for backend process
wait $BACKEND_PID


