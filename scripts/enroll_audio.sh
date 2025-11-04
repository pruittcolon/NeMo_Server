#!/bin/bash
# Script to enroll audio files from the command line

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <audio_file_path> <speaker_name>"
    echo "Example: $0 /path/to/audio.wav john_doe"
    exit 1
fi

AUDIO_FILE="$1"
SPEAKER_NAME="$2"
API_URL="http://localhost:8000/enroll/upload"

# Check if file exists
if [ ! -f "$AUDIO_FILE" ]; then
    echo "Error: Audio file not found: $AUDIO_FILE"
    exit 1
fi

echo "Enrolling speaker: $SPEAKER_NAME"
echo "Audio file: $AUDIO_FILE"
echo ""

# Get authentication token (if you have credentials)
# For now, we'll try without auth or you can add your token here
# TOKEN="your_token_here"

# Upload the audio file
curl -X POST "$API_URL" \
  -H "Content-Type: multipart/form-data" \
  -F "audio=@$AUDIO_FILE" \
  -F "speaker=$SPEAKER_NAME"

echo ""
echo "Done!"
