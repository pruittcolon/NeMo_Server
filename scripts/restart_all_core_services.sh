#!/bin/bash
# Safe restart for all core services to reload secrets and avoid JWT mismatch
set -e
cd "$(dirname "$0")/.."

SERVICES=(api-gateway rag-service gemma-service emotion-service transcription-service queue-service)

echo "[nemo] Stopping all core services..."
docker compose -f docker/docker-compose.yml stop "${SERVICES[@]}"

echo "[nemo] Starting all core services (secrets will be reloaded)..."
docker compose -f docker/docker-compose.yml up -d "${SERVICES[@]}"

echo "[nemo] All core services restarted."
