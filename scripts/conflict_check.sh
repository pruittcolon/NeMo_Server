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
