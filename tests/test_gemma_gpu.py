#!/usr/bin/env python3
"""
GPU Verification Test for Gemma Model Loading
Tests llama-cpp-python CUDA support and Gemma model GPU offloading
"""
import os
import sys
from llama_cpp import Llama

print("=" * 60)
print("GEMMA GPU VERIFICATION TEST")
print("=" * 60)

# Check environment
print(f"\n[ENV] CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES', 'not set')}")
print(f"[ENV] NVIDIA_VISIBLE_DEVICES: {os.environ.get('NVIDIA_VISIBLE_DEVICES', 'not set')}")

# Test llama-cpp-python
try:
    from llama_cpp import __version__
    print(f"\n✅ llama-cpp-python version: {__version__}")
except Exception as e:
    print(f"\n❌ Failed to get llama-cpp-python version: {e}")
    sys.exit(1)

# Check CUDA support
try:
    from llama_cpp import llama_supports_gpu_offload
    cuda_supported = llama_supports_gpu_offload()
    if cuda_supported:
        print("✅ CUDA GPU offload: SUPPORTED")
    else:
        print("❌ CUDA GPU offload: NOT SUPPORTED")
        print("   This means llama-cpp-python was not built with CUDA!")
        sys.exit(1)
except Exception as e:
    print(f"❌ Error checking CUDA support: {e}")
    sys.exit(1)

# Try to load Gemma model
model_path = "/app/models/gemma-3-4b-it-Q4_K_M.gguf"
print(f"\n[MODEL] Path: {model_path}")

if not os.path.exists(model_path):
    print(f"⚠️  Model file not found (this is OK for Docker build test)")
    print("   Model loading will be tested during integration phase")
    sys.exit(0)

print("[MODEL] File found, attempting to load with GPU offloading...")

try:
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,  # Offload all layers to GPU
        n_ctx=2048,
        n_batch=512,
        verbose=True
    )
    print("✅ Gemma loaded successfully with GPU offloading")
    
    # Test inference
    print("\n[INFERENCE] Running test generation...")
    response = llm("Test: ", max_tokens=10, temperature=0.7)
    print(f"✅ Inference test passed")
    print(f"   Response: {response['choices'][0]['text'][:50]}...")
    
except Exception as e:
    print(f"❌ Failed to load Gemma or run inference: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL GPU TESTS PASSED ✅")
print("=" * 60)

