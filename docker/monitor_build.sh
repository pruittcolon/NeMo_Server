#!/bin/bash
# Monitor Docker build progress

LOG_FILE="/tmp/nemo_ubuntu22_full.log"

echo "=== Docker Build Monitor ===" 
echo "Log file: $LOG_FILE"
echo ""

# Wait for build to start
sleep 5

echo "Monitoring build progress..."
echo "Key milestones:"
echo "  1. System packages installation"
echo "  2. Pip upgrade"
echo "  3. NeMo dependencies installation (~5-7 minutes)"
echo "  4. llama-cpp-python wheel installation"
echo "  5. Verification"
echo ""

# Monitor for key events
tail -f $LOG_FILE 2>/dev/null | while read line; do
    # Show key progress indicators
    if [[ "$line" =~ "Successfully installed" ]]; then
        echo "✅ $(echo $line | grep -o 'Successfully installed.*')"
    elif [[ "$line" =~ "Building wheel" ]]; then
        echo "🔨 $(echo $line | grep -o 'Building wheel for.*')"
    elif [[ "$line" =~ "llama-cpp-python wheel installed" ]]; then
        echo "✅ llama-cpp-python wheel installed!"
    elif [[ "$line" =~ "All packages installed" ]]; then
        echo "✅ All packages verified!"
    elif [[ "$line" =~ "ERROR" ]]; then
        echo "❌ ERROR: $line"
    elif [[ "$line" =~ "DONE" ]]; then
        step=$(echo $line | grep -o '#[0-9]*')
        echo "✓ Step $step completed"
    fi
done



