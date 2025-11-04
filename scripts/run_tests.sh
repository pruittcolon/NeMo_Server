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

echo "============================================================================"
echo "REFACTORED - Comprehensive Test Suite"
echo "============================================================================"
echo ""

# Determine which markers to run
RUN_INTEGRATION=${RUN_INTEGRATION:-0}
RUN_PERFORMANCE=${RUN_PERFORMANCE:-0}

MARKERS="-m 'unit or smoke or security'"
if [[ "$RUN_INTEGRATION" == "1" || "$RUN_INTEGRATION" == "true" ]]; then
    MARKERS="-m 'unit or smoke or security or integration'"
fi
if [[ "$RUN_PERFORMANCE" == "1" || "$RUN_PERFORMANCE" == "true" ]]; then
    MARKERS="-m 'unit or smoke or security or integration or performance'"
fi

echo -e "${YELLOW}Installing test dependencies...${NC}"
python -m pip install -q --upgrade pip
python -m pip install -q -r tests/requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

echo "============================================================================"
echo "Running Tests: $MARKERS"
echo "============================================================================"
pytest $MARKERS -v -s --maxfail=1 || {
    echo -e "${RED}✗ Tests failed${NC}"
    exit 1
}

# Generate coverage report
echo "============================================================================"
echo "Generating Coverage Report"
echo "============================================================================"
pytest -q --cov=services --cov=shared --cov-report=html --cov-report=term-missing
echo ""

echo "============================================================================"
echo -e "${GREEN}✓ Test Suite Complete!${NC}"
echo "============================================================================"
echo ""
echo "Coverage report: htmlcov/index.html"
echo ""





