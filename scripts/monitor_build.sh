#!/bin/bash
# Autonomous Build Monitoring Script
# Checks build progress every 3 minutes and reports status

LOG_FILE="/tmp/wheel_build_verified.log"
START_TIME=$(date +%s)
CHECK_INTERVAL=180  # 3 minutes

echo "=========================================="
echo "Build Monitor Started: $(date)"
echo "Log file: $LOG_FILE"
echo "Check interval: ${CHECK_INTERVAL}s (3 minutes)"
echo "=========================================="

while true; do
    sleep $CHECK_INTERVAL
    
    # Check if build is still running
    if ! pgrep -f "docker compose build" > /dev/null; then
        echo ""
        echo "=========================================="
        echo "Build process stopped at: $(date)"
        
        # Check if it was successful
        if tail -20 "$LOG_FILE" 2>/dev/null | grep -q "Successfully built\|Successfully installed"; then
            echo "✅ BUILD COMPLETED SUCCESSFULLY"
        else
            echo "❌ BUILD FAILED OR INTERRUPTED"
        fi
        echo "=========================================="
        break
    fi
    
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    MINUTES=$((ELAPSED/60))
    
    echo ""
    echo "=========================================="
    echo "⏱️  BUILD STATUS - Minute $MINUTES ($(date +%H:%M:%S))"
    echo "=========================================="
    
    # Show wheel build progress
    WHEEL_LINE=$(tail -5 "$LOG_FILE" 2>/dev/null | grep "Building wheel" | tail -1)
    if [ -n "$WHEEL_LINE" ]; then
        echo "📦 $WHEEL_LINE"
    fi
    
    # Check for verification steps
    if tail -20 "$LOG_FILE" 2>/dev/null | grep -q "llama-cpp-python imported"; then
        echo "✅ llama-cpp-python verification passed"
    fi
    
    # Check for errors (exclude benign ones)
    ERROR_COUNT=$(tail -50 "$LOG_FILE" 2>/dev/null | grep -iE "error|failed" | grep -v "error_handler\|errorlevel" | wc -l)
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "⚠️  ERRORS DETECTED: $ERROR_COUNT"
        tail -50 "$LOG_FILE" 2>/dev/null | grep -iE "error|failed" | grep -v "error_handler\|errorlevel" | tail -3
    else
        echo "✓ No errors detected"
    fi
    
    # System resources
    DISK_AVAIL=$(df -h / | tail -1 | awk '{print $4}')
    MEM_AVAIL=$(free -h | grep Mem | awk '{print $7}')
    echo ""
    echo "💾 Disk available: $DISK_AVAIL"
    echo "🧠 Memory available: $MEM_AVAIL"
    
    # Estimate remaining time (rough estimate: 20-25 min total)
    if [ $MINUTES -lt 25 ]; then
        REMAINING=$((25 - MINUTES))
        echo "⏳ Estimated time remaining: ~$REMAINING minutes"
    fi
    
    echo "=========================================="
done

