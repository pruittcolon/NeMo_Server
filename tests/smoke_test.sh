#!/bin/bash
# WhisperServer REFACTORED - Smoke Test
# Quick validation of all services
# Target: <2 minutes execution

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 WhisperServer REFACTORED - Smoke Test"
echo "========================================"
echo ""

# Helper functions
check_url() {
    local url=$1
    local name=$2
    echo -n "  Testing $name... "
    if curl -s -f "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗${NC}"
        return 1
    fi
}

check_json() {
    local url=$1
    local name=$2
    local key=$3
    echo -n "  Testing $name... "
    response=$(curl -s "$url")
    if echo "$response" | grep -q "\"$key\""; then
        echo -e "${GREEN}✓${NC}"
        return 0
    else
        echo -e "${RED}✗ (key '$key' not found)${NC}"
        return 1
    fi
}

# Test 1: Service Health Checks
echo "1️⃣  Service Health Checks"
echo "------------------------"
check_url "http://localhost:8000/health" "API Gateway (port 8000)"
check_url "http://localhost:8001/analyze/stats" "Gemma Service (port 8001)"
check_url "http://localhost:8002/memory/health" "RAG Service (port 8002)"
check_url "http://localhost:8003/analyze/emotion/health" "Emotion Service (port 8003)"
echo ""

# Test 2: API Gateway Endpoints
echo "2️⃣  API Gateway Endpoints"
echo "------------------------"
check_json "http://localhost:8000/health" "Health status" "status"
check_url "http://localhost:8000/" "Root page"
check_url "http://localhost:8000/latest_result" "Latest result endpoint"
echo ""

# Test 3: GPU Isolation
echo "3️⃣  GPU Isolation"
echo "------------------------"
echo -n "  Checking Gemma has GPU... "
if docker exec whisperserver-gemma nvidia-smi > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ (GPU not visible to Gemma!)${NC}"
fi

echo -n "  Checking API Gateway NO GPU... "
if docker exec whisperserver-refactored nvidia-smi 2>&1 | grep -q "No devices"; then
    echo -e "${GREEN}✓${NC}"
elif docker exec whisperserver-refactored nvidia-smi 2>&1 | grep -q "command not found"; then
    echo -e "${GREEN}✓ (nvidia-smi not installed - CPU only)${NC}"
else
    echo -e "${YELLOW}⚠ (GPU might be visible - check CUDA_VISIBLE_DEVICES)${NC}"
fi
echo ""

# Test 4: Docker Containers
echo "4️⃣  Docker Containers"
echo "------------------------"
echo -n "  Checking containers running... "
running=$(docker ps --filter "name=whisperserver" --format "{{.Names}}" | wc -l)
if [ "$running" -ge 4 ]; then
    echo -e "${GREEN}✓ ($running containers)${NC}"
else
    echo -e "${YELLOW}⚠ (Expected 4, found $running)${NC}"
fi

echo -n "  Checking container health... "
healthy=$(docker ps --filter "name=whisperserver" --filter "health=healthy" --format "{{.Names}}" | wc -l)
if [ "$healthy" -ge 3 ]; then
    echo -e "${GREEN}✓ ($healthy healthy)${NC}"
else
    echo -e "${YELLOW}⚠ ($healthy healthy, waiting for others...)${NC}"
fi
echo ""

# Test 5: Service Communication
echo "5️⃣  Service Communication"
echo "------------------------"
echo -n "  Testing memory search... "
response=$(curl -s "http://localhost:8002/memory/search?q=test&top_k=1")
if [ -n "$response" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
fi

echo -n "  Testing emotion analysis... "
response=$(curl -s -X POST "http://localhost:8003/analyze/emotion" \
    -H "Content-Type: application/json" \
    -d '{"text":"I am happy"}')
if echo "$response" | grep -q "dominant_emotion"; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
fi
echo ""

# Test 6: API Documentation
echo "6️⃣  API Documentation"
echo "------------------------"
check_url "http://localhost:8000/docs" "OpenAPI docs"
check_url "http://localhost:8000/redoc" "ReDoc"
echo ""

# Summary
echo "========================================"
echo "✅ Smoke Test Complete!"
echo ""
echo "📊 Next Steps:"
echo "  1. Open UI: http://localhost:8000/"
echo "  2. Test Flutter app connection"
echo "  3. Run integration tests: make test-integration"
echo "  4. Check logs: make logs"
echo ""
echo "📚 Documentation:"
echo "  - README.md - Full guide"
echo "  - QUICKSTART.md - Quick start"
echo "  - IMPLEMENTATION_SUMMARY.md - What was built"
echo ""


