#!/usr/bin/env bash
set -euo pipefail

# Watch API Gateway logs periodically, focusing on auth/login/CSRF events.
# Usage: scripts/watch_gateway.sh [interval_seconds]
# Env:
#   FILTER=1          Show filtered view (default 1). Set to 0 for full logs.
#   STOP_ON=REGEX     Stop when a matching line appears (default matches common auth failures).
#   OUT=path          Write accumulated logs to this file (default logs/system-tests/gateway_watch.log)

INTERVAL="${1:-30}"
FILTER="${FILTER:-1}"
STOP_ON="${STOP_ON:-ERROR|CSRF|401|403|Invalid|Not authenticated|Too many login attempts|Redirect}"
OUT="${OUT:-logs/system-tests/gateway_watch.log}"

mkdir -p "$(dirname "$OUT")"

# Resolve gateway container id via compose; fall back to known name
CID=""
if command -v docker compose >/dev/null 2>&1; then
  CID=$(cd docker && docker compose ps -q api-gateway 2>/dev/null || true)
elif command -v docker-compose >/dev/null 2>&1; then
  CID=$(cd docker && docker-compose ps -q api-gateway 2>/dev/null || true)
fi
CID=${CID:-refactored_gateway}

if ! docker inspect "${CID##*/}" >/dev/null 2>&1; then
  if ! docker inspect "$CID" >/dev/null 2>&1; then
    echo "[watch_gateway] Gateway container not found (got '$CID'). Start the stack first." >&2
    exit 1
  fi
fi

SINCE_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[watch_gateway] Watching container '$CID' every ${INTERVAL}s (since $SINCE_TS)" | tee -a "$OUT"
echo "[watch_gateway] Stop condition regex: $STOP_ON" | tee -a "$OUT"

while true; do
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo -e "\n===== $(date '+%F %T %Z') (since $SINCE_TS) =====" | tee -a "$OUT"
  raw=$(docker logs "$CID" --since "$SINCE_TS" 2>&1 || true)
  # Always append full raw logs to file for forensics
  if [ -n "$raw" ]; then
    echo "$raw" >> "$OUT"
  else
    echo "[watch_gateway] No new log lines" | tee -a "$OUT"
  fi

  view="$raw"
  if [ "$FILTER" = "1" ]; then
    view=$(echo "$raw" | grep -E "POST \/api\/auth\/login|GET \/ui\/|CSRF|cookie|session|Unauthorized|Invalid|ERROR|WARNING|\" 401 |\" 403 |Redirect" || true)
  fi

  if [ -n "$view" ]; then
    echo "$view"
  fi

  if [ -n "$STOP_ON" ] && echo "$raw" | grep -Eq "$STOP_ON"; then
    echo "[watch_gateway] Stop condition matched. Exiting." | tee -a "$OUT"
    exit 0
  fi

  SINCE_TS="$now"
  sleep "$INTERVAL"
done
