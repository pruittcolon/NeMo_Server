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
