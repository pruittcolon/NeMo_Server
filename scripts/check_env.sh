#!/usr/bin/env bash
# Quick environment audit before running start.sh / tests
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Running environment checks...${NC}"
missing=()
warn=()

check_bin() {
  local name="$1"
  local display="${2:-$1}"
  if command -v "$name" >/dev/null 2>&1; then
    local version="$($name --version 2>/dev/null | head -n1)"
    echo -e "${GREEN}✓${NC} $display installed${version:+ — $version}"
    return 0
  fi
  return 1
}

if ! command -v docker >/dev/null 2>&1; then
  missing+=("docker")
else
  echo -e "${GREEN}✓${NC} Docker installed ($(docker --version | head -n1))"
fi

if command -v docker-compose >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} docker-compose installed ($(docker-compose --version | head -n1))"
elif docker compose version >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} docker compose plugin installed ($(docker compose version | head -n1))"
else
  missing+=("docker-compose")
fi

PY_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PY_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PY_BIN="python"
fi
if [ -z "$PY_BIN" ]; then
  missing+=("python3")
else
  echo -e "${GREEN}✓${NC} $PY_BIN available ($($PY_BIN --version))"
fi

if command -v npm >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} npm installed ($(npm --version))"
else
  warn+=("npm (needed for frontend builds)")
fi

if command -v node >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} node installed ($(node --version))"
else
  warn+=("node (needed for frontend builds)")
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} NVIDIA GPU detected ($(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1))"
else
  warn+=("nvidia-smi (GPU features will be disabled)")
fi

if [ ${#missing[@]} -gt 0 ]; then
  echo -e "${RED}Missing critical dependencies:${NC} ${missing[*]}"
  exit 1
fi

if [ ${#warn[@]} -gt 0 ]; then
  echo -e "${YELLOW}Warnings:${NC} ${warn[*]}"
fi

echo -e "${GREEN}Environment looks good.${NC}"
