#!/usr/bin/env bash
set -euo pipefail
# Commits the running rag container as a cache image, then builds rag-service using it
# Usage: ./scripts/rebuild_rag_with_cache.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOCKERFILE="$ROOT_DIR/docker/Dockerfile.rag"
CACHE_IMAGE="refactored-rag-cache:latest"
TARGET_IMAGE="refactored-rag-service:latest"

echo "[rebuild] locating running rag container..."
CONTAINER=$(docker ps --format '{{.Names}}' | grep -i rag || true)
if [ -z "$CONTAINER" ]; then
  echo "[rebuild] no running rag container found. Aborting." >&2
  exit 1
fi
echo "[rebuild] found container: $CONTAINER"

echo "[rebuild] committing container to image: $CACHE_IMAGE"
docker commit "$CONTAINER" "$CACHE_IMAGE"

echo "[rebuild] building $TARGET_IMAGE with cache-from $CACHE_IMAGE"
docker build --cache-from "$CACHE_IMAGE" -t "$TARGET_IMAGE" -f "$DOCKERFILE" "$ROOT_DIR" || {
  echo "[rebuild] docker build failed" >&2
  exit 2
}

echo "[rebuild] bringing up rag-service via docker compose"
docker compose -f "$ROOT_DIR/docker/docker-compose.yml" up -d rag-service

echo "[rebuild] waiting 3s for container to initialize..."
sleep 3

NEW_CONT=$(docker ps --format '{{.Names}}' | grep -i rag || true)
echo "[rebuild] running container: ${NEW_CONT:-<none>}"

echo "[rebuild] last 120 lines of rag logs:"
docker logs --tail 120 "${NEW_CONT}" || true

echo "[rebuild] done"
