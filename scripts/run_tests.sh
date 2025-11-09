#!/bin/bash
#!/usr/bin/env bash
# Comprehensive Test Runner for Nemo Server
# Executes unit + smoke by default; opt-in integration/performance via env

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PY_BIN=${PY_BIN:-$(command -v python3 || command -v python || true)}
if [[ -z "$PY_BIN" ]]; then
    echo -e "${RED}python3/python not found in PATH. Install Python before running tests.${NC}"
    exit 127
fi

PIP_FLAGS=()
EXTERNALLY_MANAGED=false
if ls /usr/lib/python*/EXTERNALLY-MANAGED >/dev/null 2>&1 || \
   ls /usr/lib/python*/dist-packages/EXTERNALLY-MANAGED >/dev/null 2>&1; then
    EXTERNALLY_MANAGED=true
fi
if [[ "$EXTERNALLY_MANAGED" == "true" ]]; then
    PIP_FLAGS+=(--break-system-packages)
    echo -e "${YELLOW}PEP 668 environment detected — piping installs with --break-system-packages${NC}"
fi
if [[ -n "${PIP_EXTRA_INSTALL_FLAGS:-}" ]]; then
    # shellcheck disable=SC2206
    EXTRA_FLAGS=($PIP_EXTRA_INSTALL_FLAGS)
    PIP_FLAGS+=("${EXTRA_FLAGS[@]}")
fi

echo "============================================================================"
echo "REFACTORED - Comprehensive Test Suite"
echo "============================================================================"
echo ""

# Determine which markers to run
RUN_INTEGRATION=${RUN_INTEGRATION:-0}
RUN_PERFORMANCE=${RUN_PERFORMANCE:-0}
RUN_COVERAGE=${RUN_COVERAGE:-0}

MARKER_EXPR="unit or smoke or security"
if [[ "$RUN_INTEGRATION" == "1" || "$RUN_INTEGRATION" == "true" ]]; then
    MARKER_EXPR="${MARKER_EXPR} or integration"
fi
if [[ "$RUN_PERFORMANCE" == "1" || "$RUN_PERFORMANCE" == "true" ]]; then
    MARKER_EXPR="${MARKER_EXPR} or performance"
fi

echo -e "${YELLOW}Installing test dependencies...${NC}"
"$PY_BIN" -m pip install "${PIP_FLAGS[@]}" -q --upgrade pip
"$PY_BIN" -m pip install "${PIP_FLAGS[@]}" -q -r tests/requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

echo "============================================================================"
echo "Running Tests: -m '$MARKER_EXPR'"
echo "============================================================================"
"$PY_BIN" -m pytest -m "$MARKER_EXPR" -v -s --maxfail=1 || {
    echo -e "${RED}✗ Tests failed${NC}"
    exit 1
}

if [[ "$RUN_COVERAGE" == "1" ]]; then
    echo "============================================================================"
    echo "Generating Coverage Report"
    echo "============================================================================"
    "$PY_BIN" -m pytest -m "$MARKER_EXPR" -q --cov=services --cov=shared --cov-report=html --cov-report=term-missing
    echo ""
else
    echo "============================================================================"
    echo "Skipping coverage run (set RUN_COVERAGE=1 to enable)"
    echo "============================================================================"
fi

echo "============================================================================"
echo -e "${GREEN}✓ Test Suite Complete!${NC}"
echo "============================================================================"
echo ""
echo "Coverage report: htmlcov/index.html"
echo ""
