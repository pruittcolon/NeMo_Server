# Vision Mode - Implementation Guide

## Overview
Vision Mode is a new feature that allows the Even smart glasses to capture images using the phone's rear camera and send them to ChatGPT (GPT-4o) for visual analysis. Responses are shortened to fit on the glasses display.

## How to Use

### Activating Vision Mode
1. Say **"Vision"** to activate Vision Mode
2. The glasses will display: "Vision Mode: Camera active. Ask me about what I see. Say 'Terminate' to exit."
3. The rear camera will start capturing images every 3 seconds

### Using Vision Mode
- Ask questions about what the camera sees:
  - "What's in front of me?"
  - "Read the text on this sign"
  - "What color is this object?"
  - "Describe what you see"
  
### Exiting Vision Mode
- Say **"Terminate"** or **"End"** to exit
- Vision mode automatically exits after 10 minutes

## Technical Details

### Features Implemented

#### 1. Camera Integration
- **Package**: `camera: ^0.10.5+5`
- **Image Processing**: `image: ^4.1.3`
- **Rear Camera**: Automatically selects back-facing camera
- **Resolution**: Medium quality (balance between quality and processing speed)
- **Capture Frequency**: Every 3 seconds

#### 2. Image Processing
- **Compression**: Images resized to 800px width max
- **Quality**: JPEG at 70% quality
- **Format**: Base64 encoded for API transmission
- **Size Optimization**: Reduces data transfer and API costs

#### 3. GPT-4o Vision API
- **Model**: `gpt-4o` (supports vision)
- **Max Tokens**: 150 (ensures responses fit on glasses)
- **Response Limit**: 50 words (configured in system prompt)
- **Context**: Maintains conversation history

#### 4. Permissions
- **Android**: Camera permission automatically requested
- **Manifest**: Updated with camera permissions
- **Runtime**: Permission requested before camera initialization

### File Changes

#### Modified Files:
1. **`pubspec.yaml`**
   - Added `camera: ^0.10.5+5`
   - Added `image: ^4.1.3`

2. **`AndroidManifest.xml`**
   - Added camera permissions
   - Added camera hardware feature declarations

3. **`lib/services/evenai.dart`**
   - Added vision mode state variables
   - Added `_matchesVisionMode()` method
   - Added `_startVisionMode()` method
   - Added `_initCamera()` method
   - Added `_captureImage()` method
   - Added `_stopCamera()` method
   - Added `_exitVisionMode()` method
   - Updated `clear()` to dispose camera resources
   - Updated conversation flow to include images

4. **`lib/services/api_services_deepseek.dart`**
   - Updated `sendChatRequest()` to accept optional parameters:
     - `conversationHistory`: For maintaining context
     - `imageBase64`: For vision requests
   - Added support for multi-part messages (text + image)
   - Automatically selects `gpt-4o` for vision requests

#### New Files:
1. **`lib/services/camera_permission_helper.dart`**
   - Helper class for managing camera permissions
   - Methods: `requestCameraPermission()`, `hasPermission()`

### Architecture

```
User says "Vision"
    ↓
Vision mode activated
    ↓
Request camera permission
    ↓
Initialize rear camera
    ↓
Start periodic capture (3s interval)
    ↓
User asks question
    ↓
Send: text + latest image → GPT-4o
    ↓
Response shortened to 50 words
    ↓
Display on glasses
    ↓
Continue conversation...
    ↓
User says "Terminate" → Exit and cleanup
```

## Performance Considerations

### Battery Usage
Vision mode is battery-intensive due to:
- Continuous camera operation
- Periodic image capture
- Image processing (compression)
- Network requests with images
- BLE communication

**Recommendation**: Use sparingly, auto-exits after 10 minutes

### Latency
- **Text-only requests**: ~1-2 seconds
- **Vision requests**: ~3-5 seconds (image upload + processing)

### Cost
GPT-4o vision requests are more expensive than text-only:
- **Text**: ~$0.005 per request
- **Vision**: ~$0.01-0.02 per request (depending on image size)

## Testing

### Before Testing:
1. Run `flutter pub get` to install new dependencies
2. Ensure `.env` has valid `OPENAI_API_KEY`
3. Build and install app on physical device (camera needed)

### Test Scenarios:
1. **Basic Activation**
   - Say "Vision"
   - Verify camera permission prompt
   - Verify glasses show activation message

2. **Simple Questions**
   - "What do you see?"
   - "What color is this?"
   - Verify responses are under 50 words

3. **Text Recognition**
   - Point at text/sign
   - "Read this text"
   - Verify accurate OCR

4. **Object Identification**
   - Point at objects
   - "What is this?"
   - Verify object recognition

5. **Exit**
   - Say "Terminate"
   - Verify camera stops
   - Verify mode exits cleanly

## Troubleshooting

### Camera Won't Initialize
- Check permissions granted
- Ensure device has rear camera
- Check logs for initialization errors

### No Image Captured
- Verify periodic timer is running
- Check `_latestImageBase64` is not null
- Review capture error logs

### Poor Quality Responses
- Increase image resolution in `_initCamera()`
- Adjust JPEG quality in `_captureImage()`
- Increase `max_tokens` in API request

### Permission Denied
- App Settings → Permissions → Camera → Enable
- Or use `CameraPermissionHelper.requestCameraPermission()`

## Future Enhancements

### Potential Improvements:
1. **On-Demand Capture**: Capture only when question asked (save battery)
2. **Multiple Cameras**: Support front camera for selfie mode
3. **Video Mode**: Continuous video feed analysis
4. **Local Processing**: Use on-device ML models to reduce API costs
5. **Image History**: Keep last N images for context
6. **Voice Feedback**: Audio cues when image captured
7. **Quality Settings**: User-configurable image quality/resolution

## API Reference

### Vision Mode Methods

#### `_startVisionMode()`
Initializes vision mode, requests permissions, starts camera

#### `_initCamera()`
Sets up camera controller with rear camera at medium resolution

#### `_captureImage()`
Captures, compresses, and encodes image to base64

#### `_stopCamera()`
Disposes camera controller and cleans up resources

#### `_exitVisionMode()`
Complete cleanup and exit from vision mode

### API Service Methods

#### `sendChatRequest(String question, {List<Map<String, String>>? conversationHistory, String? imageBase64})`
Sends request to OpenAI with optional conversation context and image

## Notes

- Vision mode uses the same conversation framework as Interview and Chat modes
- Camera permission is required - app will request on first use
- Images are not stored locally - only latest capture kept in memory
- All vision requests use GPT-4o for optimal performance
- Responses automatically limited to 50 words for glasses compatibility

## Support

For issues or questions:
1. Check logs for error messages
2. Verify all dependencies installed
3. Ensure API key is valid
4. Test on physical device (emulator camera limited)
