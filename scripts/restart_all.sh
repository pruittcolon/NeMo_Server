#!/bin/bash
# Complete restart script - kills everything and starts fresh

set -e  # Exit on error

cd "$(dirname "$0")/../docker"

echo "=========================================="
echo "🔴 STOPPING ALL SERVICES"
echo "=========================================="

# Stop all containers
docker compose down

echo ""
echo "=========================================="
echo "🧹 CLEANING UP"
echo "=========================================="

# Kill any hanging Python processes on our ports
for port in 8000 8001 8002 8003 8004 8005; do
    echo "Checking port $port..."
    lsof -ti:$port | xargs kill -9 2>/dev/null || true
done

# Clear GPU memory
echo "Clearing GPU memory..."
nvidia-smi --gpu-reset 2>/dev/null || true

# Optional: Clear Docker cache if low on memory
# Uncomment if needed:
# docker system prune -f

echo ""
echo "=========================================="
echo "🚀 STARTING ALL SERVICES (FRESH)"
echo "=========================================="

# Start services
docker compose up -d

echo ""
echo "=========================================="
echo "⏳ WAITING FOR SERVICES TO BE HEALTHY"
echo "=========================================="

# Wait for services to be healthy
max_wait=120  # 2 minutes
waited=0

while [ $waited -lt $max_wait ]; do
    # Check if all containers are healthy
    unhealthy=$(docker compose ps --format json | jq -r 'select(.Health != "healthy") | .Name' 2>/dev/null | wc -l)
    
    if [ "$unhealthy" -eq "0" ]; then
        echo "✅ All services are healthy!"
        break
    fi
    
    echo "⏳ Waiting for services... ($waited/$max_wait seconds)"
    sleep 5
    waited=$((waited + 5))
done

echo ""
echo "=========================================="
echo "📊 SERVICE STATUS"
echo "=========================================="

docker compose ps --format "table {{.Name}}\t{{.Status}}"

echo ""
echo "=========================================="
echo "💾 GPU MEMORY"
echo "=========================================="

nvidia-smi --query-gpu=memory.used,memory.total --format=csv

echo ""
echo "=========================================="
echo "🎉 READY TO USE!"
echo "=========================================="
echo ""
echo "Gateway:  http://localhost:8000"
echo "Gemma UI: http://localhost:8000/ui/gemma.html"
echo "Login:    http://localhost:8000/ui/login.html"
echo ""
echo "To view logs: docker compose logs -f [service-name]"
echo "To stop all:  docker compose down"
echo ""
