# Gemma AI Service# Gemma AI Service# gemma-service



Large Language Model (LLM) inference service using Google's Gemma 3 model via llama.cpp with GPU acceleration.



## OverviewLarge Language Model (LLM) inference service using Google's Gemma 3 model via llama.cpp with GPU acceleration.## Phase Plan



The Gemma Service provides conversational AI capabilities with:



- **Long Context**: 64K token context window## Overview### 1. Requirements

- **GPU Acceleration**: CUDA-enabled inference via llama.cpp

- **RAG Integration**: Automatic retrieval of relevant memories- [ ] TODO: Define what this service must do

- **GPU Coordination**: Dynamic GPU sharing with transcription service

- **Streaming Support**: Token-by-token streaming responsesThe Gemma Service provides conversational AI capabilities with:

- **Chat History**: Maintains conversation context

### 2. Dependencies

## Architecture

- **Long Context**: 64K token context window- [ ] TODO: List required models, libraries, external services

### GPU Coordination Model

- **GPU Acceleration**: CUDA-enabled inference via llama.cpp

The service uses a **request-based GPU access** model:

- **RAG Integration**: Automatic retrieval of relevant memories### 3. API Contract

1. **Idle State**: Model loaded in CPU/RAM (n_gpu_layers=0)

2. **On Request**: - **GPU Coordination**: Dynamic GPU sharing with transcription service- [ ] TODO: Define endpoints with request/response schemas

   - Request GPU lock from coordinator

   - Wait for transcription service to pause (~1-2s)- **Streaming Support**: Token-by-token streaming responses

   - Reload model to GPU (n_gpu_layers=25)

   - Process inference- **Chat History**: Maintains conversation context### 4. Verification Steps

   - Offload model back to CPU

   - Release GPU lock- [ ] TODO: How to test this service works correctly

3. **Transcription Resumes**: Normal operation restored

## Architecture

This allows both services to coexist on a single GPU system.

### 5. Conflict Checks

### Request Flow

### GPU Coordination Model- [ ] TODO: Potential conflicts with other services

```

Client Request- [ ] TODO: Resource requirements (CPU, memory, GPU)

    ↓

Check RAG Context (semantic search)The service uses a **request-based GPU access** model:

    ↓

Build Prompt with Context## Implementation Status

    ↓

Request GPU from Coordinator1. **Idle State**: Model loaded in CPU/RAM (n_gpu_layers=0)

    ↓

Wait for GPU Lock2. **On Request**: - [ ] Dockerfile created

    ↓

Reload Model to GPU   - Request GPU lock from coordinator- [ ] Requirements defined

    ↓

LLM Inference (streaming)   - Wait for transcription service to pause (~1-2s)- [ ] Service code implemented

    ↓

Return Response   - Reload model to GPU (n_gpu_layers=25)- [ ] Tests written

    ↓

Offload Model to CPU   - Process inference- [ ] Health check endpoint working

    ↓

Release GPU Lock   - Offload model back to CPU- [ ] Integrated with docker-compose

```

   - Release GPU lock

## Key Features

3. **Transcription Resumes**: Normal operation restored## Notes

### 1. RAG-Enhanced Responses

- Automatically searches memories for relevant context

- Includes transcript segments and notes in prompt

- Configurable retrieval depth (top_k)This allows both services to coexist on a single GPU system.(Add implementation notes here)

- Bias towards recent conversations



### 2. Long Context Support### Request Flow

- 64K token context window (Gemma 3 capability)

- Maintains long conversation histories```

- Summarization strategies for ultra-long contextsClient Request

    ↓

### 3. GPU OptimizationCheck RAG Context (semantic search)

- On-demand GPU loading    ↓

- Fast CPU ↔ GPU model transferBuild Prompt with Context

- Minimal idle GPU usage    ↓

- Efficient batch processingRequest GPU from Coordinator

    ↓

### 4. Streaming ResponsesWait for GPU Lock

- Token-by-token streaming via Server-Sent Events (SSE)    ↓

- Low latency first tokenReload Model to GPU

- Interruptible generation    ↓

LLM Inference (streaming)

## API Endpoints    ↓

Return Response

### Chat Completion    ↓

```bashOffload Model to CPU

POST /chat    ↓

Content-Type: application/jsonRelease GPU Lock

```

{

  "messages": [## Key Features

    {"role": "user", "content": "What did John say about the project?"}

  ],### 1. RAG-Enhanced Responses

  "max_tokens": 512,- Automatically searches memories for relevant context

  "temperature": 0.7,- Includes transcript segments and notes in prompt

  "context": [],  // Optional: additional context documents- Configurable retrieval depth (top_k)

  "use_rag": true,  // Enable RAG retrieval- Bias towards recent conversations

  "rag_top_k": 5  // Number of relevant memories to retrieve

}### 2. Long Context Support

```- 64K token context window (Gemma 3 capability)

- Maintains long conversation histories

Response:- Summarization strategies for ultra-long contexts

```json

{### 3. GPU Optimization

  "response": "Based on the transcript from yesterday, John mentioned...",- On-demand GPU loading

  "model": "gemma-3-4b-it",- Fast CPU ↔ GPU model transfer

  "usage": {- Minimal idle GPU usage

    "prompt_tokens": 1024,- Efficient batch processing

    "completion_tokens": 156,

    "total_tokens": 1180### 4. Streaming Responses

  },- Token-by-token streaming via Server-Sent Events (SSE)

  "rag_context_used": 5,- Low latency first token

  "gpu_wait_time": 1.2,- Interruptible generation

  "inference_time": 3.4

}## API Endpoints

```

### Chat Completion

### Streaming Chat```bash

```bashPOST /chat

POST /chat/streamContent-Type: application/json

Content-Type: application/json

(Same body as /chat){

```  "messages": [

    {"role": "user", "content": "What did John say about the project?"}

Response: Server-Sent Events stream  ],

```  "max_tokens": 512,

data: {"token": "Based", "done": false}  "temperature": 0.7,

data: {"token": " on", "done": false}  "context": [],  // Optional: additional context documents

...  "use_rag": true,  // Enable RAG retrieval

data: {"token": ".", "done": true, "usage": {...}}  "rag_top_k": 5  // Number of relevant memories to retrieve

```}

```

### Health Check

```bashResponse:

GET /health```json

```{

  "response": "Based on the transcript from yesterday, John mentioned...",

## Configuration  "model": "gemma-3-4b-it",

  "usage": {

Environment variables:    "prompt_tokens": 1024,

    "completion_tokens": 156,

| Variable | Default | Description |    "total_tokens": 1180

|----------|---------|-------------|  },

| `GEMMA_MODEL_PATH` | `/app/models/gemma-3-4b-it-UD-Q4_K_XL.gguf` | Path to GGUF model file |  "rag_context_used": 5,

| `GEMMA_GPU_LAYERS` | `25` | Number of layers to offload to GPU |  "gpu_wait_time": 1.2,

| `GEMMA_CONTEXT_SIZE` | `65536` | Maximum context window (64K) |  "inference_time": 3.4

| `GEMMA_BATCH_SIZE` | `512` | Batch size for token processing |}

| `GPU_COORDINATOR_URL` | `http://gpu-coordinator:8002` | Coordinator service URL |```

| `RAG_SERVICE_URL` | `http://rag-service:8004` | RAG service for memory retrieval |

| `JWT_ONLY` | `false` | Enforce JWT-only authentication |### Streaming Chat

```bash

## Model InformationPOST /chat/stream

Content-Type: application/json

### Gemma 3 4B Instruct(Same body as /chat)

- **Architecture**: Decoder-only transformer```

- **Parameters**: 4 billion

- **Quantization**: Q4_K_XL (4-bit quantization)Response: Server-Sent Events stream

- **Context**: 64K tokens```

- **Size on Disk**: ~2.5GB (GGUF format)data: {"token": "Based", "done": false}

data: {"token": " on", "done": false}

### Performance Characteristics...

- **VRAM Usage**: ~4-5GB (with 25 GPU layers)data: {"token": ".", "done": true, "usage": {...}}

- **CPU RAM Usage**: ~6GB (when offloaded)```

- **Inference Speed**: ~20-30 tokens/second (on GPU)

- **First Token Latency**: ~200-500ms### Health Check

- **GPU Load Time**: ~500-800ms```bash

GET /health

## Prompt Engineering```



### System Prompt## Configuration

The service uses a carefully tuned system prompt that:

- Establishes assistant personaEnvironment variables:

- Provides RAG context integration instructions

- Sets response style and format guidelines| Variable | Default | Description |

- Handles multi-turn conversation context|----------|---------|-------------|

| `GEMMA_MODEL_PATH` | `/app/models/gemma-3-4b-it-UD-Q4_K_XL.gguf` | Path to GGUF model file |

### RAG Context Injection| `GEMMA_GPU_LAYERS` | `25` | Number of layers to offload to GPU |

When RAG is enabled:| `GEMMA_CONTEXT_SIZE` | `65536` | Maximum context window (64K) |

1. Query is embedded and searched against memory database| `GEMMA_BATCH_SIZE` | `512` | Batch size for token processing |

2. Top K relevant segments retrieved| `GPU_COORDINATOR_URL` | `http://gpu-coordinator:8002` | Coordinator service URL |

3. Context formatted with metadata (speaker, time, emotion)| `RAG_SERVICE_URL` | `http://rag-service:8004` | RAG service for memory retrieval |

4. Injected into prompt before user message| `JWT_ONLY` | `false` | Enforce JWT-only authentication |

5. Model instructed to cite sources when using context

## Model Information

## Dependencies

### Gemma 3 4B Instruct

See `requirements.txt`. Key dependencies:- **Architecture**: Decoder-only transformer

- **fastapi** - Web framework- **Parameters**: 4 billion

- **llama-cpp-python** - Installed via pre-built wheel (CUDA support)- **Quantization**: Q4_K_XL (4-bit quantization)

- **httpx** - Service communication- **Context**: 64K tokens

- **pydantic** - Data validation- **Size on Disk**: ~2.5GB (GGUF format)



**Note**: llama-cpp-python is installed from a pre-built wheel with CUDA support (see `docker/wheels/`) to avoid Docker build issues with libcuda.so.1 linking.### Performance Characteristics

- **VRAM Usage**: ~4-5GB (with 25 GPU layers)

## Development- **CPU RAM Usage**: ~6GB (when offloaded)

- **Inference Speed**: ~20-30 tokens/second (on GPU)

### Running Locally- **First Token Latency**: ~200-500ms

```bash- **GPU Load Time**: ~500-800ms

cd services/gemma-service

pip install -r requirements.txt## Prompt Engineering

# Install llama-cpp-python wheel separately

pip install ../../docker/wheels/llama_cpp_python-*.whl### System Prompt

The service uses a carefully tuned system prompt that:

uvicorn src.main:app --reload --host 0.0.0.0 --port 8001- Establishes assistant persona

```- Provides RAG context integration instructions

- Sets response style and format guidelines

### Running in Docker- Handles multi-turn conversation context

```bash

docker compose up gemma-service### RAG Context Injection

```When RAG is enabled:

1. Query is embedded and searched against memory database

## GPU Memory Management2. Top K relevant segments retrieved

3. Context formatted with metadata (speaker, time, emotion)

### Memory States4. Injected into prompt before user message

1. **Idle (CPU)**: ~6GB RAM, 0GB VRAM5. Model instructed to cite sources when using context

2. **Loading**: ~8GB RAM, 2GB VRAM (transition)

3. **Active (GPU)**: ~2GB RAM, 5GB VRAM## Dependencies

4. **Inference**: ~2GB RAM, 5-6GB VRAM (peak)

See `requirements.txt`. Key dependencies:

### Optimization Tips- **fastapi** - Web framework

- Reduce `GEMMA_GPU_LAYERS` for lower VRAM usage- **llama-cpp-python** - Installed via pre-built wheel (CUDA support)

- Reduce `GEMMA_CONTEXT_SIZE` if hitting memory limits- **httpx** - Service communication

- Use smaller quantization (Q3, Q2) for even lower memory- **pydantic** - Data validation

- Consider model sharding for multi-GPU setups

**Note**: llama-cpp-python is installed from a pre-built wheel with CUDA support (see `docker/wheels/`) to avoid Docker build issues with libcuda.so.1 linking.

## Troubleshooting

## Development

### Model Not Loading

- Check model file exists at `GEMMA_MODEL_PATH`### Running Locally

- Verify CUDA drivers installed```bash

- Check VRAM availability with `nvidia-smi`cd services/gemma-service

pip install -r requirements.txt

### Slow Response Times# Install llama-cpp-python wheel separately

- Check GPU coordinator logs for contentionpip install ../../docker/wheels/llama_cpp_python-*.whl

- Verify GPU is actually being used (nvidia-smi during inference)

- Consider increasing `GEMMA_GPU_LAYERS`uvicorn src.main:app --reload --host 0.0.0.0 --port 8001

```

### Out of Memory

- Reduce `GEMMA_CONTEXT_SIZE`### Running in Docker

- Reduce `GEMMA_GPU_LAYERS````bash

- Check for memory leaks in long-running processesdocker compose up gemma-service

- Restart service to clear GPU memory```



## Examples## GPU Memory Management



### Simple Chat### Memory States

```python1. **Idle (CPU)**: ~6GB RAM, 0GB VRAM

import httpx2. **Loading**: ~8GB RAM, 2GB VRAM (transition)

3. **Active (GPU)**: ~2GB RAM, 5GB VRAM

response = httpx.post("http://localhost:8001/chat", json={4. **Inference**: ~2GB RAM, 5-6GB VRAM (peak)

    "messages": [

        {"role": "user", "content": "Explain quantum computing"}### Optimization Tips

    ],- Reduce `GEMMA_GPU_LAYERS` for lower VRAM usage

    "max_tokens": 200- Reduce `GEMMA_CONTEXT_SIZE` if hitting memory limits

})- Use smaller quantization (Q3, Q2) for even lower memory

print(response.json()["response"])- Consider model sharding for multi-GPU setups

```

## Troubleshooting

### RAG-Enhanced Query

```python### Model Not Loading

response = httpx.post("http://localhost:8001/chat", json={- Check model file exists at `GEMMA_MODEL_PATH`

    "messages": [- Verify CUDA drivers installed

        {"role": "user", "content": "What did Sarah say about the deadline?"}- Check VRAM availability with `nvidia-smi`

    ],

    "use_rag": True,### Slow Response Times

    "rag_top_k": 5,- Check GPU coordinator logs for contention

    "max_tokens": 300- Verify GPU is actually being used (nvidia-smi during inference)

})- Consider increasing `GEMMA_GPU_LAYERS`

print(response.json()["response"])

# Will include context from transcripts mentioning Sarah and deadlines### Out of Memory

```- Reduce `GEMMA_CONTEXT_SIZE`

- Reduce `GEMMA_GPU_LAYERS`

### Streaming Response- Check for memory leaks in long-running processes

```python- Restart service to clear GPU memory

import httpx

import json## Examples



with httpx.stream("POST", "http://localhost:8001/chat/stream", json={### Simple Chat

    "messages": [{"role": "user", "content": "Tell me a story"}],```python

    "max_tokens": 500import httpx

}) as stream:

    for line in stream.iter_lines():response = httpx.post("http://localhost:8001/chat", json={

        if line.startswith("data: "):    "messages": [

            token_data = json.loads(line[6:])        {"role": "user", "content": "Explain quantum computing"}

            print(token_data["token"], end="", flush=True)    ],

```    "max_tokens": 200

})
print(response.json()["response"])
```

### RAG-Enhanced Query
```python
response = httpx.post("http://localhost:8001/chat", json={
    "messages": [
        {"role": "user", "content": "What did Sarah say about the deadline?"}
    ],
    "use_rag": True,
    "rag_top_k": 5,
    "max_tokens": 300
})
print(response.json()["response"])
# Will include context from transcripts mentioning Sarah and deadlines
```

### Streaming Response
```python
import httpx
import json

with httpx.stream("POST", "http://localhost:8001/chat/stream", json={
    "messages": [{"role": "user", "content": "Tell me a story"}],
    "max_tokens": 500
}) as stream:
    for line in stream.iter_lines():
        if line.startswith("data: "):
            token_data = json.loads(line[6:])
            print(token_data["token"], end="", flush=True)
```
