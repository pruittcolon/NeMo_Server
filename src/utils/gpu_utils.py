"""
GPU Management Utilities

Centralizes GPU memory management and device assignment
Replaces 20+ scattered torch.cuda calls from main3.py

Key Functions:
- Smart GPU cache clearing
- VRAM monitoring and logging
- Device enforcement (CPU-only or GPU-only)
- cuDNN optimizations
"""

import os
from typing import Optional, Dict, Any
import torch


def is_gpu_available() -> bool:
    """Check if GPU is available"""
    return torch.cuda.is_available()


def get_device_info() -> Dict[str, Any]:
    """
    Get comprehensive GPU information
    
    Returns:
        Dictionary with GPU details or empty dict if no GPU
    """
    if not is_gpu_available():
        return {"available": False}
    
    device = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(device)
    
    return {
        "available": True,
        "device_id": device,
        "name": torch.cuda.get_device_name(device),
        "total_memory_gb": props.total_memory / (1024 ** 3),
        "major": props.major,
        "minor": props.minor,
        "multi_processor_count": props.multi_processor_count,
    }


def log_vram_usage(prefix: str = "[VRAM]") -> None:
    """
    Log current VRAM usage
    
    Args:
        prefix: Log message prefix
    """
    if not is_gpu_available():
        print(f"{prefix} No GPU available")
        return
    
    try:
        device = torch.cuda.current_device()
        allocated = torch.cuda.memory_allocated(device) / (1024 ** 3)
        cached = torch.cuda.memory_reserved(device) / (1024 ** 3)
        total = torch.cuda.get_device_properties(device).total_memory / (1024 ** 3)
        free = total - allocated
        
        print(f"{prefix} Allocated: {allocated:.2f}GB | "
              f"Cached: {cached:.2f}GB | "
              f"Free: {free:.2f}GB | "
              f"Total: {total:.2f}GB")
    except Exception as e:
        print(f"{prefix} Error logging VRAM: {e}")


def clear_gpu_cache(force: bool = False) -> None:
    """
    Clear GPU cache intelligently
    
    Consolidates multiple torch.cuda.empty_cache() calls from main3.py
    
    Args:
        force: If True, clear twice for thorough cleanup
    """
    if not is_gpu_available():
        return
    
    try:
        torch.cuda.empty_cache()
        
        if force:
            # Double clear for thorough cleanup (from main3.py pattern)
            torch.cuda.empty_cache()
            print("[GPU] Cache cleared (forced)")
        else:
            print("[GPU] Cache cleared")
            
    except Exception as e:
        print(f"[GPU] Error clearing cache: {e}")


def collect_and_clear() -> None:
    """
    Full cleanup: garbage collection + GPU cache clearing
    
    Replaces pattern from main3.py lines 134-138
    """
    import gc
    
    # Python garbage collection
    gc.collect()
    
    # GPU cache clearing
    if is_gpu_available():
        clear_gpu_cache(force=True)
        print("[GPU] Full cleanup complete (gc + cache)")


def apply_cudnn_optimizations() -> bool:
    """
    Apply cuDNN optimizations for better performance
    
    Extracted from main3.py lines 80-88
    
    Returns:
        True if optimizations applied, False if no GPU
    """
    if not is_gpu_available():
        return False
    
    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
        print("[GPU] cuDNN optimizations applied (TF32 + benchmark)")
        return True
    except Exception as e:
        print(f"[GPU] Warning: Could not apply cuDNN optimizations: {e}")
        return False


def force_tf32_enable() -> None:
    """
    Force TF32 re-enable
    
    Some libraries (like pyannote) disable TF32
    From main3.py lines 90-95
    """
    if not is_gpu_available():
        return
    
    try:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        print("[GPU] TF32 re-enabled (overriding library changes)")
    except Exception as e:
        print(f"[GPU] Warning: Could not force TF32: {e}")


def enforce_cpu_only() -> str:
    """
    Enforce CPU-only operation by hiding GPU
    
    Sets environment variables to make GPU invisible
    This should be called BEFORE loading any models
    
    Returns:
        Device string ("cpu")
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["NVIDIA_VISIBLE_DEVICES"] = "void"
    print("[GPU] CPU-only mode enforced (GPU hidden)")
    return "cpu"


def enforce_gpu_only(device_id: int = 0) -> str:
    """
    Enforce GPU-only operation
    
    Sets environment variables to expose specific GPU
    This should be called BEFORE loading any models
    
    Args:
        device_id: GPU device ID to use
    
    Returns:
        Device string ("cuda:0", etc.)
    """
    os.environ["CUDA_VISIBLE_DEVICES"] = str(device_id)
    
    if is_gpu_available():
        print(f"[GPU] GPU-only mode enforced (device {device_id})")
        return f"cuda:{device_id}"
    else:
        print("[GPU] Warning: GPU requested but not available, falling back to CPU")
        return "cpu"


def get_optimal_device(prefer_gpu: bool = True, gpu_id: int = 0) -> str:
    """
    Get optimal device based on availability and preference
    
    Args:
        prefer_gpu: Whether to prefer GPU if available
        gpu_id: GPU device ID if using GPU
    
    Returns:
        Device string ("cuda:0", "cpu", etc.)
    """
    if prefer_gpu and is_gpu_available():
        return f"cuda:{gpu_id}"
    else:
        return "cpu"


class DeviceManager:
    """
    Context manager for temporary device enforcement
    
    Example:
        with DeviceManager(cpu_only=True):
            # Load model on CPU
            model = load_model()
    """
    
    def __init__(self, cpu_only: bool = False, gpu_only: bool = False, gpu_id: int = 0):
        """
        Initialize device manager
        
        Args:
            cpu_only: Force CPU-only mode
            gpu_only: Force GPU-only mode
            gpu_id: GPU device ID if gpu_only
        """
        self.cpu_only = cpu_only
        self.gpu_only = gpu_only
        self.gpu_id = gpu_id
        self.original_cuda_visible = None
        self.original_nvidia_visible = None
    
    def __enter__(self):
        """Save current environment and enforce device"""
        # Save original environment
        self.original_cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
        self.original_nvidia_visible = os.environ.get("NVIDIA_VISIBLE_DEVICES")
        
        # Enforce device
        if self.cpu_only:
            enforce_cpu_only()
        elif self.gpu_only:
            enforce_gpu_only(self.gpu_id)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original environment"""
        if self.original_cuda_visible is not None:
            os.environ["CUDA_VISIBLE_DEVICES"] = self.original_cuda_visible
        elif "CUDA_VISIBLE_DEVICES" in os.environ:
            del os.environ["CUDA_VISIBLE_DEVICES"]
        
        if self.original_nvidia_visible is not None:
            os.environ["NVIDIA_VISIBLE_DEVICES"] = self.original_nvidia_visible
        elif "NVIDIA_VISIBLE_DEVICES" in os.environ:
            del os.environ["NVIDIA_VISIBLE_DEVICES"]
        
        print("[GPU] Device environment restored")


def initialize_gpu_environment(
    service_name: str,
    cpu_only: bool = False,
    gpu_only: bool = False,
    gpu_id: int = 0,
    apply_optimizations: bool = True
) -> str:
    """
    Initialize GPU environment for a service
    
    This is the main entry point for services to set up their GPU/CPU usage
    
    Args:
        service_name: Name of the service (for logging)
        cpu_only: Force CPU-only mode
        gpu_only: Force GPU-only mode
        gpu_id: GPU device ID if gpu_only
        apply_optimizations: Whether to apply cuDNN optimizations
    
    Returns:
        Device string to use
    """
    print(f"[GPU] Initializing GPU environment for {service_name}...")
    
    # Get device info
    info = get_device_info()
    if info["available"]:
        print(f"[GPU] GPU detected: {info['name']} ({info['total_memory_gb']:.1f}GB)")
    else:
        print("[GPU] No GPU detected, using CPU")
    
    # Enforce device mode
    if cpu_only:
        device = enforce_cpu_only()
    elif gpu_only:
        device = enforce_gpu_only(gpu_id)
    else:
        device = get_optimal_device(prefer_gpu=info["available"], gpu_id=gpu_id)
    
    # Apply optimizations if GPU and requested
    if "cuda" in device and apply_optimizations:
        apply_cudnn_optimizations()
    
    # Log final VRAM state
    if "cuda" in device:
        log_vram_usage(f"[GPU-{service_name}]")
    
    print(f"[GPU] {service_name} initialized with device: {device}")
    return device


# Convenience function for clearing cache before/after model operations
def with_cache_clear(func):
    """
    Decorator to clear GPU cache before and after function
    
    Example:
        @with_cache_clear
        def transcribe(audio):
            return model.transcribe(audio)
    """
    def wrapper(*args, **kwargs):
        clear_gpu_cache()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            clear_gpu_cache()
    
    return wrapper


