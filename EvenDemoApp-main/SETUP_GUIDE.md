# EvenDemoApp Setup Guide

Complete guide to configure the Flutter app to connect to your Nemo Server backend.

---

## 📋 Quick Setup (5 Minutes)

### Step 1: Create `.env` File

```bash
cd EvenDemoApp-main
cp .env.example .env
```

### Step 2: Configure Your Server IP

Open `.env` and replace `YOUR_SERVER_IP` with your actual server IP address:

```bash
# Find your server IP address
hostname -I | awk '{print $1}'
# Or check your network settings
ip addr show | grep 'inet '
```

### Step 3: Edit `.env`

```env
# Example for local network
MEMORY_SERVER_BASE=http://192.168.1.100:8000
WHISPER_SERVER_BASE=http://192.168.1.100:8000
ASR_SERVER_BASE=http://192.168.1.100:8000
WHISPER_CHUNK_SECS=30
```

### Step 4: Whitelist Your Device on Server

Add your Flutter device IP to the server's whitelist:

```bash
# In Nemo_Server directory, edit .env
FLUTTER_WHITELIST=192.168.1.50,127.0.0.1,::1
```

Replace `192.168.1.50` with your phone's IP address.

### Step 5: Restart Server

```bash
cd ~/Desktop/Nemo_Server
docker compose restart
```

### Step 6: Build & Run Flutter App

```bash
cd EvenDemoApp-main
flutter clean
flutter pub get
flutter run
```

---

## 🔧 Detailed Configuration

### Required Variables

#### `MEMORY_SERVER_BASE`
**Purpose**: Backend server URL for memory/RAG operations  
**Format**: `http://IP_ADDRESS:PORT`  
**Example**: `http://192.168.1.100:8000`  
**Used For**:
- Storing transcriptions in database
- Searching memories with RAG
- Speaker enrollment data
- Emotion analysis results

#### `WHISPER_SERVER_BASE`
**Purpose**: Transcription endpoint URL  
**Format**: `http://IP_ADDRESS:PORT`  
**Example**: `http://192.168.1.100:8000`  
**Used For**:
- Real-time audio transcription
- Streaming audio chunks
- Getting transcription results

#### `ASR_SERVER_BASE`
**Purpose**: ASR (Automatic Speech Recognition) service URL  
**Format**: `http://IP_ADDRESS:PORT`  
**Example**: `http://192.168.1.100:8000`  
**Used For**:
- Primary ASR endpoint
- Speaker diarization
- Audio processing

#### `WHISPER_CHUNK_SECS`
**Purpose**: Audio chunk size in seconds  
**Format**: Integer (seconds)  
**Default**: `30`  
**Range**: `5-60` seconds  
**Recommendation**: 
- `30` seconds = balanced (default)
- `15` seconds = faster response, more API calls
- `60` seconds = fewer API calls, slower response

---

## 🌐 Network Configuration Scenarios

### Scenario 1: Same Machine (Development)

**Server and Flutter running on same computer**

```env
MEMORY_SERVER_BASE=http://localhost:8000
WHISPER_SERVER_BASE=http://localhost:8000
ASR_SERVER_BASE=http://localhost:8000
WHISPER_CHUNK_SECS=30
```

Server `.env`:
```env
FLUTTER_WHITELIST=127.0.0.1,::1
```

### Scenario 2: Local Network (Most Common)

**Server on desktop, Flutter on phone (same Wi-Fi)**

1. **Find your server IP**:
   ```bash
   hostname -I | awk '{print $1}'
   # Example output: 192.168.1.100
   ```

2. **Flutter `.env`**:
   ```env
   MEMORY_SERVER_BASE=http://192.168.1.100:8000
   WHISPER_SERVER_BASE=http://192.168.1.100:8000
   ASR_SERVER_BASE=http://192.168.1.100:8000
   WHISPER_CHUNK_SECS=30
   ```

3. **Find your phone's IP** (on phone):
   - Android: Settings → About Phone → Status → IP Address
   - iOS: Settings → Wi-Fi → (tap your network) → IP Address

4. **Server `.env` whitelist**:
   ```env
   FLUTTER_WHITELIST=192.168.1.50,127.0.0.1,::1
   # Replace 192.168.1.50 with your phone's IP
   ```

### Scenario 3: Remote Server (VPN/Cloud)

**Server on remote machine, Flutter on phone**

1. **Server must have public IP or VPN**
2. **Flutter `.env`**:
   ```env
   MEMORY_SERVER_BASE=http://YOUR_SERVER_PUBLIC_IP:8000
   WHISPER_SERVER_BASE=http://YOUR_SERVER_PUBLIC_IP:8000
   ASR_SERVER_BASE=http://YOUR_SERVER_PUBLIC_IP:8000
   WHISPER_CHUNK_SECS=30
   ```

3. **Server `.env` whitelist**:
   ```env
   FLUTTER_WHITELIST=YOUR_PHONE_PUBLIC_IP,127.0.0.1
   ```

⚠️ **Security Warning**: Exposing server on public internet requires HTTPS! See SECURITY.md.

---

## 🔍 Troubleshooting

### Problem: "Connection refused" or "Network error"

**Check 1: Server is running**
```bash
docker ps | grep nemo_server
# Should show: nemo_server ... Up X minutes (healthy)
```

**Check 2: Port is accessible**
```bash
curl http://YOUR_SERVER_IP:8000/health
# Should return: {"status":"healthy"}
```

**Check 3: Same network**
```bash
# On phone, can you ping server?
ping YOUR_SERVER_IP
```

**Check 4: Firewall**
```bash
# On server, allow port 8000
sudo ufw allow 8000/tcp
```

### Problem: "401 Unauthorized" for transcription

**Check**: Phone IP is whitelisted in server `.env`

```bash
# Server .env must include your phone's IP
FLUTTER_WHITELIST=192.168.1.50,127.0.0.1
```

Then restart server:
```bash
docker compose restart
```

### Problem: App builds but doesn't connect

**Check 1: `.env` file exists**
```bash
cd EvenDemoApp-main
ls -la .env
# Should show the file
```

**Check 2: `.env` is loaded**
```bash
# Rebuild app after changing .env
flutter clean
flutter pub get
flutter run
```

**Check 3: Server logs**
```bash
docker logs -f nemo_server
# Should show connection attempts from your phone
```

### Problem: Transcription is slow

**Solution 1**: Reduce chunk size
```env
WHISPER_CHUNK_SECS=15  # Faster response
```

**Solution 2**: Check server GPU usage
```bash
nvidia-smi
# GPU should show load when transcribing
```

**Solution 3**: Check network latency
```bash
ping YOUR_SERVER_IP
# Latency should be <50ms for local network
```

---

## 📱 Flutter App Architecture

### How It Connects to Nemo Server

```
Flutter App (Phone)
    ↓
[Record Audio]
    ↓
[Chunk into 30-sec segments]
    ↓
[Send to ASR_SERVER_BASE/transcribe]
    ↓
Nemo Server receives audio
    ↓
[Parakeet ASR: Speech → Text]
    ↓
[Speaker Diarization: Who spoke?]
    ↓
[Emotion Analysis: How do they feel?]
    ↓
[Store in Database]
    ↓
[Return transcript to Flutter]
    ↓
Flutter displays transcript
```

### Key Services Used

| Service | Endpoint | Purpose |
|---------|----------|---------|
| **Transcription** | `POST /transcribe` | Upload audio for ASR |
| **Memory Search** | `POST /memory/search` | RAG-based search |
| **Speaker Enrollment** | `POST /enroll/upload` | Create voice profile |
| **Gemma Chat** | `POST /analyze/chat` | AI conversation |
| **Emotion Stats** | `GET /memory/emotions/stats` | Emotion analytics |

---

## 🔐 Security Considerations

### For Development
✅ Use local network (192.168.x.x)  
✅ No HTTPS required  
✅ IP whitelist is sufficient  

### For Production
❌ **Never** expose HTTP server to internet  
✅ **Must** use HTTPS (TLS/SSL)  
✅ **Must** use authentication tokens (not IP whitelist)  
✅ **Must** implement rate limiting per user  
✅ **Must** encrypt database  

---

## 📚 Additional Resources

- **Backend API Documentation**: `http://YOUR_SERVER_IP:8000/docs`
- **Server Configuration**: See `Nemo_Server/.env.example`
- **Flutter Logs**: `flutter logs` while app is running
- **Server Logs**: `docker logs -f nemo_server`

---

## ✅ Verification Checklist

Before using the app, verify:

- [ ] `.env` file created in `EvenDemoApp-main/`
- [ ] All three URLs point to your server IP
- [ ] Server is running (`docker ps`)
- [ ] Server health check works (`curl http://IP:8000/health`)
- [ ] Phone IP is whitelisted in server `.env`
- [ ] Phone and server on same network
- [ ] Port 8000 is accessible
- [ ] Flutter dependencies installed (`flutter pub get`)
- [ ] App builds successfully (`flutter run`)

---

## 🆘 Getting Help

If you're still stuck:

1. **Check server logs**:
   ```bash
   docker logs -f nemo_server | grep transcribe
   ```

2. **Check network connectivity**:
   ```bash
   # From phone (using Termux or similar)
   curl http://YOUR_SERVER_IP:8000/health
   ```

3. **Verify whitelist**:
   ```bash
   # On server
   cat .env | grep FLUTTER_WHITELIST
   docker compose restart
   ```

4. **Try localhost first**:
   If running Flutter on same machine as server, use `localhost:8000` to rule out network issues.

---

## 📝 Example Working Configuration

### Server (Desktop at 192.168.1.100)

**Nemo_Server/.env**:
```env
HOST=0.0.0.0
PORT=8000
FLUTTER_WHITELIST=192.168.1.50,127.0.0.1,::1
# ... other settings ...
```

### Flutter App (Phone at 192.168.1.50)

**EvenDemoApp-main/.env**:
```env
MEMORY_SERVER_BASE=http://192.168.1.100:8000
WHISPER_SERVER_BASE=http://192.168.1.100:8000
ASR_SERVER_BASE=http://192.168.1.100:8000
WHISPER_CHUNK_SECS=30
```

### Test:
```bash
# From phone, test connection:
curl http://192.168.1.100:8000/health
# Expected: {"status":"healthy"}

# From server, check whitelist:
docker logs nemo_server | grep "192.168.1.50"
# Should show: [AUTH] Allowing whitelisted device 192.168.1.50
```

---

**Ready to connect!** 🚀

If everything is configured correctly, your Flutter app should now be able to:
- Record audio from your phone
- Stream it to the Nemo Server
- Get real-time transcriptions
- See speaker diarization
- View emotion analysis
- Chat with Gemma AI
- Enroll your voice profile

All from your mobile device! 📱

