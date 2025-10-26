# WhisperServer REFACTORED - Quick Start Guide

**Total Time**: 5-10 minutes  
**Prerequisites**: Docker, Docker Compose, NVIDIA GPU with Container Toolkit

---

## 🚀 **Start in 3 Commands**

```bash
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
make init
make up
```

That's it! Services will start in ~2 minutes.

---

## ✅ **Verify It's Working**

### **1. Check Health**

Visit: **http://localhost:8000/health**

Expected output:
```json
{
  "status": "ok",
  "version": "3.2-refactored",
  "services": {
    "transcription": { "status": "ready", "device": "cpu" },
    "speaker": { "status": "ready", "device": "cpu" },
    "rag": { "status": "ready" },
    "emotion": { "status": "ready", "device": "cpu" },
    "gemma": { "status": "ready", "gpu_available": true }
  },
  "architecture": {
    "gpu_exclusive_to": "gemma"
  }
}
```

### **2. Check GPU Isolation**

```bash
# Gemma should see GPU
docker exec whisperserver-gemma nvidia-smi

# Others should NOT see GPU
docker exec whisperserver-refactored nvidia-smi
# Expected: "No devices were found"
```

### **3. Open UI**

Visit: **http://localhost:8000/**

You'll see a nice landing page with links to:
- Memory Intelligence UI (port 8001)
- API Documentation (/docs)
- Health status

---

## 📱 **Connect Your Flutter App**

### **No Changes Needed!**

Your `EvenDemoApp` will work with zero modifications.

Just ensure `.env` points to refactored server:

```
# EvenDemoApp-main/.env
WHISPER_SERVER_BASE=http://localhost:8000
```

(Or use your server's IP if running remotely)

### **Test Connection**

1. Open Flutter app
2. Record audio
3. Check `/transcribe` endpoint works
4. Verify speaker enrollment works

All 30 endpoints are identical to original!

---

## 🧪 **Quick Test**

### **Test Transcription**

```bash
curl -X POST http://localhost:8000/transcribe \
  -F "audio=@/path/to/test.wav" \
  -F "seq=1"
```

Expected: JSON with segments and text

### **Test Health**

```bash
curl http://localhost:8000/health
```

Expected: JSON with all services "ready"

### **Test Gemma GPU**

```bash
# Check Gemma service
curl http://localhost:8001/analyze/stats
```

Expected: `"gpu_available": true`

---

## 🛑 **Stop Services**

```bash
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
make down
```

---

## 🔧 **Troubleshooting**

### **Issue: Port 8000 already in use**

```bash
# Stop original server first
cd /home/pruittcolon/Downloads/WhisperServer
docker-compose down
```

### **Issue: GPU not accessible**

```bash
# Check NVIDIA Container Toolkit
nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### **Issue: Services won't start**

```bash
# Check logs
docker-compose logs whisperserver-refactored
docker-compose logs gemma-service

# Rebuild
make rebuild
```

### **Issue: Models not found**

```bash
# Ensure models directory exists and has Gemma model
ls -lh /home/pruittcolon/Downloads/WhisperServer/models/

# Required:
# - gemma-3-4b-it-Q4_K_M.gguf
```

---

## 📊 **Port Map**

| Service | Port | URL |
|---------|------|-----|
| **API Gateway** | 8000 | http://localhost:8000 |
| **Gemma Service** | 8001 | http://localhost:8001 |
| **RAG Service** | 8002 | http://localhost:8002 |
| **Emotion Service** | 8003 | http://localhost:8003 |

---

## 🔄 **Rollback to Original**

If you need to go back:

```bash
# Stop refactored
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
make down

# Start original
cd /home/pruittcolon/Downloads/WhisperServer
bash START_SERVER.sh
```

Original code is **completely preserved** and untouched!

---

## 📚 **More Info**

- **Full Documentation**: See `README.md`
- **Implementation Details**: See `IMPLEMENTATION_SUMMARY.md`
- **API Reference**: Visit http://localhost:8000/docs
- **Change Log**: See `CHANGELOG.md`

---

## ✅ **Success Checklist**

After running `make up`, verify:

- [ ] http://localhost:8000/health returns "ok"
- [ ] http://localhost:8000/ shows landing page
- [ ] http://localhost:8000/docs shows API documentation
- [ ] `docker ps` shows 4 containers running
- [ ] `docker exec whisperserver-gemma nvidia-smi` shows GPU
- [ ] Flutter app can connect (optional - test when ready)

---

## 🎉 **You're Done!**

Your refactored WhisperServer is now running with:

✅ Gemma on GPU (exclusive access)  
✅ All other services on CPU  
✅ All 30 endpoints working  
✅ 100% backward compatible  
✅ Faster startup, cleaner code  

**Enjoy your GPU-optimized AI server! 🚀**


