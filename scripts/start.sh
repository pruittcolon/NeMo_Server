#!/bin/bash
set -e

echo "================================================="
echo "Starting Nemo Server"
echo "================================================="
echo ""

cd "$(dirname "$0")/.."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running"
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Check if GPU is available
if ! nvidia-smi > /dev/null 2>&1; then
    echo "⚠️  NVIDIA GPU not detected (will run CPU-only)"
else
    echo "✅ GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
fi

echo ""
echo "Starting container..."
cd docker
docker compose up -d

echo ""
echo "Waiting for service to be ready..."
sleep 15

echo ""
echo "================================================="
echo "✅ Nemo Server is RUNNING"
echo "================================================="
echo ""
echo "Access the application:"
echo "  Dashboard: http://localhost:8000/ui/"
echo "  Login:     http://localhost:8000/ui/login.html"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "Default credentials:"
echo "  admin/admin123"
echo ""
echo "View logs:"
echo "  docker logs -f nemo_server"
echo ""
echo "Stop server:"
echo "  cd docker && docker compose down"
echo ""
