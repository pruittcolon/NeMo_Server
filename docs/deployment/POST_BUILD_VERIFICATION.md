# Post-Build Verification Checklist

**Generated:** 2025-10-24 19:16:00  
**Build Started:** 19:11:30  
**Expected Completion:** 19:36:30 (~25 min)

## Overview

This document provides a comprehensive checklist for verifying the Docker build after completion. All tests must pass before the container is considered production-ready.

---

## Phase 1: Image Verification

### 1.1 Confirm Image Built Successfully

```bash
docker images | grep whisperserver-refactored
```

**Expected Output:**
```
whisperserver-refactored   latest    [IMAGE_ID]    [TIME]    [SIZE]GB
```

**Success Criteria:**
- ✅ Image exists with "latest" tag
- ✅ Size is approximately 15-20GB
- ✅ Timestamp matches today's date

### 1.2 Check Build Logs for Success Message

```bash
tail -100 /tmp/wheel_build_verified.log | grep -E "Successfully built|Successfully installed"
```

**Expected Output:**
```
Successfully built llama-cpp-python
Successfully installed llama-cpp-python-0.2.90 ...
```

**Success Criteria:**
- ✅ No error messages in final 100 lines
- ✅ "Successfully built" or "Successfully installed" present
- ✅ Version 0.2.90 is mentioned

---

## Phase 2: llama-cpp-python Verification

### 2.1 Test Import and Version

```bash
docker run --rm whisperserver-refactored:latest \
  python3.10 -c "import llama_cpp; print(f'Version: {llama_cpp.__version__}')"
```

**Expected Output:**
```
Version: 0.2.90
```

**Success Criteria:**
- ✅ No import errors
- ✅ Version is exactly 0.2.90
- ✅ Exit code is 0

### 2.2 Test CUDA Support

```bash
docker run --rm whisperserver-refactored:latest \
  python3.10 -c "import llama_cpp; print(f'CUDA Support: {llama_cpp.llama_supports_gpu_offload()}')"
```

**Expected Output:**
```
CUDA Support: True
```

**Success Criteria:**
- ✅ Returns `True` (not `False`)
- ✅ No exceptions or errors
- ✅ Exit code is 0

**If False:** llama-cpp-python was not built with CUDA - BUILD FAILED

### 2.3 Verify No Version Conflicts

```bash
docker run --rm whisperserver-refactored:latest pip list | grep llama-cpp-python
```

**Expected Output:**
```
llama-cpp-python    0.2.90
```

**Success Criteria:**
- ✅ Only ONE version listed
- ✅ Version is 0.2.90
- ✅ No warnings about conflicts

---

## Phase 3: GPU Visibility Test

### 3.1 Test nvidia-smi in Container

```bash
docker run --rm --gpus all whisperserver-refactored:latest nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
```

**Expected Output:**
```
NVIDIA [GPU MODEL], [MEMORY SIZE] MiB
```

**Success Criteria:**
- ✅ GPU is detected
- ✅ Memory size displayed correctly
- ✅ No "NVIDIA-SMI not found" errors

### 3.2 Test CUDA Environment Variables

```bash
docker run --rm --gpus all -e CUDA_VISIBLE_DEVICES=0 whisperserver-refactored:latest \
  bash -c 'echo $CUDA_VISIBLE_DEVICES'
```

**Expected Output:**
```
0
```

**Success Criteria:**
- ✅ Environment variable set correctly
- ✅ Value is "0" (GPU 0)

---

## Phase 4: Gemma Model Loading Test

### 4.1 Run GPU Verification Test Script

```bash
docker run --rm --gpus all \
  -v /home/pruittcolon/Downloads/WhisperServer/models:/app/models:ro \
  whisperserver-refactored:latest \
  python3.10 /app/tests/test_gemma_gpu.py
```

**Expected Output:**
```
============================================================
GEMMA GPU VERIFICATION TEST
============================================================

[ENV] CUDA_VISIBLE_DEVICES: 0
[ENV] NVIDIA_VISIBLE_DEVICES: 0

✅ llama-cpp-python version: 0.2.90
✅ CUDA GPU offload: SUPPORTED

[MODEL] Path: /app/models/gemma-3-4b-it-Q4_K_M.gguf
[MODEL] File found, attempting to load with GPU offloading...
✅ Gemma loaded successfully with GPU offloading

[INFERENCE] Running test generation...
✅ Inference test passed

============================================================
ALL GPU TESTS PASSED ✅
============================================================
```

**Success Criteria:**
- ✅ CUDA support confirmed
- ✅ Model loads without errors
- ✅ GPU memory allocated during loading
- ✅ Inference generates text successfully
- ✅ Exit code is 0

---

## Phase 5: Integration Test (Container Startup)

### 5.1 Start Container

```bash
cd /home/pruittcolon/Downloads/WhisperServer/REFACTORED
docker compose up -d
```

**Success Criteria:**
- ✅ Container starts without errors
- ✅ No "exit code 1" messages
- ✅ Container status is "Up"

### 5.2 Monitor Startup Logs

```bash
docker compose logs -f --tail=100
```

**Watch For:**
- ✅ "Backend is healthy"
- ✅ "WhisperServer Refactored - READY"
- ✅ "GPU check..." showing GPU details
- ❌ NO CUDA errors
- ❌ NO model loading failures
- ❌ NO import errors

**Startup should complete within 2-3 minutes**

### 5.3 Test Health Endpoint

```bash
curl -s http://localhost:8001/health | python3 -m json.tool
```

**Expected Output:**
```json
{
  "status": "healthy",
  "timestamp": "...",
  ...
}
```

**Success Criteria:**
- ✅ Returns HTTP 200
- ✅ Status is "healthy"
- ✅ Response is valid JSON

### 5.4 Test Gemma Endpoint

```bash
curl -X POST http://localhost:8001/gemma/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, this is a test", "context_type": "conversation"}' \
  -s | python3 -m json.tool
```

**Expected Output:**
```json
{
  "analysis": "...",
  "confidence": ...,
  ...
}
```

**Success Criteria:**
- ✅ Returns HTTP 200
- ✅ Response contains analysis
- ✅ No CUDA errors in logs
- ✅ GPU memory increases during request (check nvidia-smi)

### 5.5 Monitor GPU Usage

In another terminal:

```bash
watch -n 1 nvidia-smi
```

**During Gemma API call, verify:**
- ✅ GPU memory usage INCREASES (by 2-4GB)
- ✅ GPU utilization shows activity
- ✅ Process name includes "python" or "uvicorn"

---

## Phase 6: Side-by-Side Test

### 6.1 Verify Original Container Still Running

```bash
curl -s http://localhost:8000/health
```

**Success Criteria:**
- ✅ Original container responds on port 8000
- ✅ Refactored container responds on port 8001
- ✅ No port conflicts
- ✅ Both can run simultaneously

### 6.2 Compare Functionality

Test the same endpoint on both:

```bash
# Original (port 8000)
curl -X POST http://localhost:8000/gemma/analyze -H "Content-Type: application/json" -d '{"text": "Test", "context_type": "conversation"}'

# Refactored (port 8001)
curl -X POST http://localhost:8001/gemma/analyze -H "Content-Type: application/json" -d '{"text": "Test", "context_type": "conversation"}'
```

**Success Criteria:**
- ✅ Both return valid responses
- ✅ Refactored version uses GPU efficiently
- ✅ Response quality is comparable

---

## Phase 7: Resource Verification

### 7.1 Check Disk Usage

```bash
df -h /
docker system df
```

**Success Criteria:**
- ✅ At least 10GB free disk space remaining
- ✅ Build cache is reasonable size
- ✅ No disk space warnings

### 7.2 Check Container Resource Usage

```bash
docker stats whisperserver_refactored --no-stream
```

**Success Criteria:**
- ✅ Memory usage is reasonable (<8GB at idle)
- ✅ CPU usage is low at idle (<5%)
- ✅ No memory leaks over time

---

## Failure Scenarios & Troubleshooting

### Scenario 1: CUDA Support = False

**Diagnosis:** llama-cpp-python not built with CUDA

**Solutions:**
1. Check CMAKE_ARGS in Dockerfile
2. Verify CUDA toolkit is available during build
3. Rebuild with `--no-cache` flag

### Scenario 2: Model Fails to Load

**Diagnosis:** GPU memory insufficient or model file corrupt

**Solutions:**
1. Check available GPU VRAM (should have 4-5GB free)
2. Verify model file integrity
3. Try loading with fewer GPU layers

### Scenario 3: API Returns Errors

**Diagnosis:** Integration issue with refactored code

**Solutions:**
1. Check container logs: `docker compose logs`
2. Verify all services initialized
3. Test individual endpoints

### Scenario 4: Build Completed But Image Missing

**Diagnosis:** Build failed silently

**Solutions:**
1. Check build logs for errors: `grep -i error /tmp/wheel_build_verified.log`
2. Verify disk space wasn't exhausted
3. Retry build with verbose logging

---

## Final Checklist

Before marking verification as complete, ALL must be ✅:

- [ ] Docker image exists with correct tag
- [ ] llama-cpp-python version is 0.2.90
- [ ] llama-cpp-python reports CUDA support = True
- [ ] No version conflicts in pip list
- [ ] nvidia-smi works in container
- [ ] Gemma model loads with GPU offloading
- [ ] Gemma inference generates text successfully
- [ ] Container starts and reaches "READY" state
- [ ] Health endpoint responds
- [ ] Gemma API endpoint responds
- [ ] GPU memory increases during Gemma requests
- [ ] Original container still works on port 8000
- [ ] At least 10GB disk space remaining
- [ ] No memory leaks or resource issues

---

## Success Report Template

After all tests pass, document results:

```
VERIFICATION COMPLETE ✅
Date: [DATE]
Build Time: [DURATION]
Final Image Size: [SIZE]GB
GPU: [MODEL]
VRAM: [AMOUNT]GB

All 14 verification checks passed.
Container is production-ready.

Next Steps:
1. Document any warnings or notes
2. Update CHANGELOG.md
3. Create backup of working image
4. Deploy to production (if applicable)
```

---

**END OF VERIFICATION CHECKLIST**

