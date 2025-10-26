# Gemma Analysis Service Summary

**Service**: LLM-Powered Analysis & Summarization  
**Location**: `REFACTORED/src/services/gemma/`  
**Status**: PENDING  
**Last Updated**: October 24, 2025

---

## 📦 **Files in This Service**

### ⏳ `service.py`
**Status**: NOT STARTED  
**Purpose**: Wrapper around existing GemmaContextAnalyzer

**Planned Classes**:
- `GemmaService` - Wrapper with GPU-ONLY enforcement
- `JobManager` - Background job processing
- `WebSocketBroadcaster` - Real-time updates

**Models Used**:
- `Gemma-3-4B-IT-Q4_K_M.gguf` (4B parameter LLM, **GPU EXCLUSIVE**)

**Key Features**:
- Comprehensive personality analysis
- "Snippy meter" (sarcasm detection)
- "Hyperbolic meter" (exaggeration detection)
- Background job processing
- WebSocket streaming
- **CRITICAL**: Exclusive GPU access

**Imports (UNCHANGED)**:
```python
from src.gemma_context_analyzer import GemmaContextAnalyzer
```

**GPU Requirements** (CRITICAL):
- **CUDA_VISIBLE_DEVICES=0** (GPU exclusive)
- Must load maximum GPU layers
- No CPU fallback allowed
- No other service can see GPU

**Conflicts Checked**:
- [ ] Exclusive GPU access verified
- [ ] llama-cpp-python CUDA build correct
- [ ] GGUF model path: models/gemma-3-4b-it-Q4_K_M.gguf
- [ ] No GPU interference from other services
- [ ] Max GPU layers loaded
- [ ] VRAM sufficient (~2-3GB)

**Dependencies**:
- GemmaContextAnalyzer (existing, 586 lines - UNTOUCHED)
- llama-cpp-python (CUDA build)
- torch
- asyncio (for jobs)
- websockets

---

### ⏳ `routes.py`
**Status**: NOT STARTED  
**Purpose**: Analysis and summary endpoints

**Endpoints**:
- `POST /analyze/personality` - Start comprehensive analysis job
- `GET /analyze/personality/{job_id}` - Get job status/results
- `POST /analyze/prepare` - Prepare analysis prompts
- `POST /analyze/gemma_summary` - Single text summary
- `POST /analyze/gemma_summary_batch` - Batch summaries
- `POST /analyze/deep_memory` - Deep memory analysis
- `WS /ws/jobs/{job_id}` - WebSocket real-time job updates

**Extracted From**:
- main3.py lines 967-1099 (personality analysis)
- main3.py lines 440-462 (WebSocket broadcasting)

**Conflicts Checked**:
- [ ] Job ID format matches
- [ ] WebSocket protocol compatible
- [ ] Log paths: logs/jobs/{job_id}/job.log
- [ ] Progress tracking format same

**Dependencies**:
- FastAPI
- WebSocket
- GemmaService
- threading (for background jobs)

---

## ✅ **Completed Tasks**

None yet

---

## 🚨 **Known Issues**

- **GPU Contention**: Original system had GPU memory conflicts - MUST ensure Gemma gets exclusive access
- **llama-cpp-python**: Must be built with CUDA support

---

## 📝 **Notes**

**CRITICAL SERVICE**: This is the ONLY service that gets GPU access. All other services (ASR, embeddings, emotion) MUST run on CPU.

**GPU Isolation Strategy**:
1. Gemma service: `CUDA_VISIBLE_DEVICES=0`
2. All other services: `CUDA_VISIBLE_DEVICES=""` or `NVIDIA_VISIBLE_DEVICES=void`
3. Docker compose: GPU reservation only for gemma-service
4. Verify no GPU leakage to other containers

**Performance**:
- Gemma inference: 2-10 seconds per response
- Comprehensive analysis: 10-30 minutes
- Must not be blocked by other services

---

**Next Steps**:
1. Create `GemmaService` wrapper with GPU-only enforcement
2. Test exclusive GPU access
3. Verify llama-cpp-python loads on GPU
4. Create job management system
5. Implement WebSocket broadcasting
6. Create FastAPI routes
7. Test comprehensive analysis job


