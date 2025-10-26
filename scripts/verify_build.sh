#!/bin/bash
# Automated Post-Build Verification Script
# Runs all verification checks and generates a report

REPORT_FILE="/tmp/build_verification_report_$(date +%Y%m%d_%H%M%S).txt"
PASS_COUNT=0
FAIL_COUNT=0
TOTAL_CHECKS=0

echo "=========================================="
echo "BUILD VERIFICATION SCRIPT"
echo "Started: $(date)"
echo "Report: $REPORT_FILE"
echo "=========================================="

# Helper function to run a check
run_check() {
    local check_name="$1"
    local command="$2"
    local expected_pattern="$3"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo ""
    echo "[$TOTAL_CHECKS] $check_name"
    echo "Command: $command"
    
    OUTPUT=$(eval "$command" 2>&1)
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ] && echo "$OUTPUT" | grep -q "$expected_pattern"; then
        echo "✅ PASS"
        PASS_COUNT=$((PASS_COUNT + 1))
        echo "[$TOTAL_CHECKS] ✅ $check_name" >> "$REPORT_FILE"
    else
        echo "❌ FAIL"
        echo "Expected pattern: $expected_pattern"
        echo "Actual output: $OUTPUT"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "[$TOTAL_CHECKS] ❌ $check_name" >> "$REPORT_FILE"
        echo "   Output: $OUTPUT" >> "$REPORT_FILE"
    fi
}

# Start report
cat > "$REPORT_FILE" << EOF
========================================
BUILD VERIFICATION REPORT
Date: $(date)
========================================

EOF

echo ""
echo "=========================================="
echo "PHASE 1: IMAGE VERIFICATION"
echo "=========================================="

run_check \
    "Docker image exists" \
    "docker images whisperserver-refactored:latest --format '{{.Repository}}:{{.Tag}}'" \
    "whisperserver-refactored:latest"

run_check \
    "Build log shows success" \
    "tail -100 /tmp/wheel_build_verified.log | grep -E 'Successfully|successfully'" \
    "Successfully"

echo ""
echo "=========================================="
echo "PHASE 2: llama-cpp-python VERIFICATION"
echo "=========================================="

run_check \
    "llama-cpp-python version 0.2.90" \
    "docker run --rm whisperserver-refactored:latest python3.10 -c 'import llama_cpp; print(llama_cpp.__version__)'" \
    "0.2.90"

run_check \
    "CUDA support enabled" \
    "docker run --rm whisperserver-refactored:latest python3.10 -c 'import llama_cpp; print(llama_cpp.llama_supports_gpu_offload())'" \
    "True"

run_check \
    "No version conflicts" \
    "docker run --rm whisperserver-refactored:latest pip list | grep llama-cpp-python | wc -l" \
    "1"

echo ""
echo "=========================================="
echo "PHASE 3: GPU VISIBILITY"
echo "=========================================="

run_check \
    "nvidia-smi accessible" \
    "docker run --rm --gpus all whisperserver-refactored:latest nvidia-smi --query-gpu=name --format=csv,noheader" \
    "NVIDIA"

run_check \
    "CUDA environment variable" \
    "docker run --rm --gpus all -e CUDA_VISIBLE_DEVICES=0 whisperserver-refactored:latest bash -c 'echo \$CUDA_VISIBLE_DEVICES'" \
    "0"

echo ""
echo "=========================================="
echo "PHASE 4: DISK SPACE CHECK"
echo "=========================================="

DISK_FREE=$(df -h / | tail -1 | awk '{print $4}' | sed 's/G//')
echo "Disk space free: ${DISK_FREE}GB"
if (( $(echo "$DISK_FREE > 10" | bc -l) )); then
    echo "✅ Sufficient disk space (>10GB)"
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "[$TOTAL_CHECKS] ✅ Disk space >10GB" >> "$REPORT_FILE"
else
    echo "⚠️  Low disk space (<10GB)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    echo "[$TOTAL_CHECKS] ⚠️  Low disk space: ${DISK_FREE}GB" >> "$REPORT_FILE"
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
echo "=========================================="
echo "VERIFICATION SUMMARY"
echo "=========================================="
echo "Total Checks: $TOTAL_CHECKS"
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"
echo ""

cat >> "$REPORT_FILE" << EOF

========================================
SUMMARY
========================================
Total Checks: $TOTAL_CHECKS
Passed: $PASS_COUNT
Failed: $FAIL_COUNT

EOF

if [ $FAIL_COUNT -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED!"
    echo "✅ ALL CHECKS PASSED!" >> "$REPORT_FILE"
    echo ""
    echo "Container is ready for integration testing."
    exit 0
else
    echo "❌ $FAIL_COUNT CHECKS FAILED"
    echo "❌ $FAIL_COUNT CHECKS FAILED" >> "$REPORT_FILE"
    echo ""
    echo "Review the report: $REPORT_FILE"
    exit 1
fi

