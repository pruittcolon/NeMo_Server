# PRODUCTION BUILD & TESTING GUIDE

## Quick Testing Strategy

This build has **3 levels of verification** to catch issues early:

### 1. PREFLIGHT TEST (5 seconds) - Test linking BEFORE 20-min build
```bash
# Build ONLY the preflight stage to verify CUDA linking works
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
docker build --target preflight -f Dockerfile.production ..

# If this succeeds, the full build will NOT fail at link stage
# If this fails, fix it before wasting 20 minutes
```

**What it tests:** Can the linker find CUDA symbols with our CMAKE_ARGS?

---

### 2. WHEEL-BUILDER TEST (20 minutes) - Build the wheel
```bash
# Build up to wheel-builder stage (includes preflight)
docker build --target wheel-builder -t whisperserver:wheel-test -f Dockerfile.production ..

# Extract and inspect the wheel
docker create --name temp whisperserver:wheel-test
docker cp temp:/wheels/. ./test_wheels/
docker rm temp

ls -lh ./test_wheels/
# Should show: llama_cpp_python-0.2.90-*.whl
```

**What it tests:** Can llama-cpp-python build successfully with our CMAKE_ARGS?

---

### 3. RUNTIME VERIFICATION (build-time, 2 minutes) - GPU check
The full build automatically runs this Python check:
```python
import llama_cpp
assert llama_cpp.llama_supports_gpu_offload() == True
```

**What it tests:** Does the installed wheel actually have GPU support?

---

### 4. FINAL SMOKE TEST (runtime, 10 seconds) - Test in running container
```bash
# After full build, test GPU in running container
docker compose -f docker-compose.production.yml up -d

# Wait 5 seconds for startup
sleep 5

# Test GPU detection
docker exec whisperserver_prod python3.10 << 'EOF'
import torch
import llama_cpp

print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
print(f"PyTorch CUDA device count: {torch.cuda.device_count()}")
if torch.cuda.is_available():
    print(f"GPU name: {torch.cuda.get_device_name(0)}")

print(f"\nllama-cpp-python version: {llama_cpp.__version__}")
print(f"GPU offload support: {llama_cpp.llama_supports_gpu_offload()}")
EOF

# Test API health
curl http://localhost:8000/health
```

---

## FULL BUILD SEQUENCE

### Option A: Build Everything (fastest if it works)
```bash
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED

# Full build (preflight + wheel + runtime)
docker compose -f docker-compose.production.yml build

# Run it
docker compose -f docker-compose.production.yml up -d

# Check logs
docker compose -f docker-compose.production.yml logs -f
```

### Option B: Step-by-step (safer, catch issues early)
```bash
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED

# Step 1: Test preflight ONLY (5 seconds)
echo "=== STEP 1: Preflight test ==="
docker build --target preflight -f Dockerfile.production .. && \
  echo "✓ Preflight PASSED - linking will work" || \
  (echo "✗ Preflight FAILED - fix CMAKE_ARGS before continuing" && exit 1)

# Step 2: Build wheel (20 minutes)
echo "=== STEP 2: Build wheel ==="
docker build --target wheel-builder -t whisperserver:wheel-test -f Dockerfile.production .. && \
  echo "✓ Wheel built successfully" || \
  (echo "✗ Wheel build FAILED" && exit 1)

# Step 3: Build full runtime (2 minutes)
echo "=== STEP 3: Build runtime ==="
docker compose -f docker-compose.production.yml build && \
  echo "✓ Runtime built successfully" || \
  (echo "✗ Runtime build FAILED" && exit 1)

# Step 4: Run and test
echo "=== STEP 4: Run and smoke test ==="
docker compose -f docker-compose.production.yml up -d
sleep 10
curl -f http://localhost:8000/health && \
  echo "✓ Service is healthy" || \
  echo "✗ Service health check failed"
```

---

## WHAT EACH STAGE CATCHES

| Stage | Time | What It Catches | Fix Before Wasting |
|-------|------|-----------------|-------------------|
| **preflight** | 5 sec | CUDA linker errors | 20 min wheel build |
| **wheel-builder** | 20 min | Build configuration issues | 2 min runtime build |
| **runtime verify** | 30 sec | CPU-only wheel (no GPU) | Runtime failures |
| **smoke test** | 10 sec | Runtime GPU access issues | Production deploy |

---

## TROUBLESHOOTING

### If preflight fails:
```bash
# Check CUDA paths in container
docker run --rm nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04 \
  ls -la /usr/local/cuda-12.1/targets/x86_64-linux/lib/stubs/
```

### If wheel build fails:
```bash
# Check build logs
docker build --target wheel-builder -f Dockerfile.production .. 2>&1 | tee /tmp/wheel_build.log

# Look for linker errors
grep -i "undefined reference" /tmp/wheel_build.log
```

### If GPU verification fails:
```bash
# Check if wheel has CUDA
docker run --rm whisperserver:production-cuda python3.10 -c \
  "import llama_cpp; print(llama_cpp.llama_supports_gpu_offload())"

# Should print: True
```

### If runtime GPU access fails:
```bash
# Check NVIDIA runtime
docker run --rm --gpus all nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 nvidia-smi

# Check container GPU access
docker exec whisperserver_prod nvidia-smi
```

---

## QUICK REBUILD (after code changes)

If you only changed application code (not dependencies):
```bash
# Rebuild just the runtime stage (reuses cached wheel)
docker compose -f docker-compose.production.yml build --no-cache runtime

# Restart
docker compose -f docker-compose.production.yml up -d --force-recreate
```

---

## EXPECTED BUILD TIMES

| Stage | First Build | Cached Build |
|-------|-------------|--------------|
| preflight | 5 sec | 2 sec |
| wheel-builder | 20 min | 2 min (if wheel cached) |
| runtime | 5 min | 1 min |
| **TOTAL** | **~25 min** | **~3 min** |

---

## SUCCESS INDICATORS

✅ **Preflight:** `✓ PREFLIGHT PASSED: Linker can find CUDA symbols`

✅ **Wheel build:** `✓ Wheel built successfully` + file exists in `/wheels/`

✅ **Runtime verify:** `✓ GPU VERIFICATION PASSED: llama_supports_gpu_offload() == True`

✅ **Smoke test:** 
```
PyTorch CUDA available: True
GPU name: NVIDIA GeForce GTX 1660 Ti
GPU offload support: True
{"status":"healthy"}
```

---

## FILES REQUIRED

Before building, ensure these exist:

```
/home/pruittcolon/Downloads/WhisperServer/
├── requirements.txt                     # Python dependencies
├── models/                              # Pre-downloaded models (optional)
└── REFACTORED/
    ├── Dockerfile.production            # This multi-stage Dockerfile
    ├── docker-compose.production.yml    # Compose file with GPU config
    ├── src/
    │   ├── main_refactored.py          # FastAPI app
    │   └── ...
    ├── frontend_html/                   # HTML UI
    ├── _original_src/
    │   ├── config.py
    │   └── __init__.py
    ├── data/                            # Created on first run
    └── logs/                            # Created on first run
```

