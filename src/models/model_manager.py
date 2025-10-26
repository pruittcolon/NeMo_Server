"""
Model Management Layer

Provides centralized model loading with strict GPU/CPU device control
Ensures:
- Gemma LLM gets exclusive GPU access
- ASR, embeddings, emotion models run on CPU only
- No model loaded more than once
- Environment variables respected for device assignment

Base classes for all AI models in the system
"""

import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TypeVar, Generic
from pathlib import Path
import threading

# Import GPU utilities
from ..utils.gpu_utils import (
    is_gpu_available,
    get_device_info,
    initialize_gpu_environment,
    log_vram_usage,
    clear_gpu_cache
)


T = TypeVar('T')  # Generic type for model


class ModelManager(ABC, Generic[T]):
    """
    Base class for all model managers
    
    Handles:
    - Device assignment (GPU/CPU)
    - Model caching (singleton pattern)
    - Lifecycle management
    - Thread safety
    """
    
    # Class-level model cache (singleton pattern)
    _instances: Dict[str, 'ModelManager'] = {}
    _lock = threading.RLock()
    
    def __init__(
        self,
        model_name: str,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        force_cpu: bool = False,
        force_gpu: bool = False,
        gpu_id: int = 0
    ):
        """
        Initialize model manager
        
        Args:
            model_name: Model identifier
            model_path: Path to model files (if local)
            device: Specific device to use (overrides force_* flags)
            force_cpu: Force CPU-only operation
            force_gpu: Force GPU-only operation
            gpu_id: GPU device ID if using GPU
        """
        self.model_name = model_name
        self.model_path = model_path
        self.force_cpu = force_cpu
        self.force_gpu = force_gpu
        self.gpu_id = gpu_id
        
        # Determine device
        if device is not None:
            self.device = device
        elif force_cpu:
            self.device = "cpu"
        elif force_gpu:
            if is_gpu_available():
                self.device = f"cuda:{gpu_id}"
            else:
                raise RuntimeError(f"GPU requested for {model_name} but none available")
        else:
            # Auto-detect
            self.device = f"cuda:{gpu_id}" if is_gpu_available() else "cpu"
        
        self._model: Optional[T] = None
        self._is_loaded = False
        self._load_lock = threading.RLock()
        
        print(f"[MODEL] {model_name} manager initialized (device: {self.device})")
    
    @abstractmethod
    def _load_model(self) -> T:
        """
        Load the actual model (implemented by subclasses)
        
        Returns:
            Loaded model instance
        """
        pass
    
    @abstractmethod
    def _unload_model(self) -> None:
        """
        Unload the model and free resources (implemented by subclasses)
        """
        pass
    
    def load(self) -> T:
        """
        Load model with thread safety and caching
        
        Returns:
            Loaded model instance
        """
        with self._load_lock:
            if self._is_loaded and self._model is not None:
                print(f"[MODEL] {self.model_name} already loaded, using cache")
                return self._model
            
            print(f"[MODEL] Loading {self.model_name} on {self.device}...")
            
            # Clear cache before loading (if GPU)
            if "cuda" in self.device:
                clear_gpu_cache()
                log_vram_usage(f"[MODEL-{self.model_name}] Before load")
            
            try:
                self._model = self._load_model()
                self._is_loaded = True
                
                # Log VRAM after loading (if GPU)
                if "cuda" in self.device:
                    log_vram_usage(f"[MODEL-{self.model_name}] After load")
                
                print(f"[MODEL] {self.model_name} loaded successfully")
                return self._model
                
            except Exception as e:
                print(f"[MODEL] Failed to load {self.model_name}: {e}")
                raise
    
    def unload(self) -> None:
        """Unload model and free resources"""
        with self._load_lock:
            if not self._is_loaded:
                return
            
            print(f"[MODEL] Unloading {self.model_name}...")
            
            try:
                self._unload_model()
                self._model = None
                self._is_loaded = False
                
                # Clear GPU cache after unload (if GPU)
                if "cuda" in self.device:
                    clear_gpu_cache()
                    log_vram_usage(f"[MODEL-{self.model_name}] After unload")
                
                print(f"[MODEL] {self.model_name} unloaded")
                
            except Exception as e:
                print(f"[MODEL] Error unloading {self.model_name}: {e}")
    
    def reload(self) -> T:
        """Reload model (unload then load)"""
        self.unload()
        return self.load()
    
    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded"""
        return self._is_loaded
    
    @property
    def model(self) -> Optional[T]:
        """Get loaded model instance"""
        if not self._is_loaded:
            raise RuntimeError(f"{self.model_name} not loaded. Call load() first.")
        return self._model
    
    def get_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "name": self.model_name,
            "path": self.model_path,
            "device": self.device,
            "loaded": self._is_loaded,
            "force_cpu": self.force_cpu,
            "force_gpu": self.force_gpu,
        }
    
    @classmethod
    def get_instance(cls, model_name: str) -> Optional['ModelManager']:
        """Get cached model manager instance"""
        with cls._lock:
            return cls._instances.get(model_name)
    
    @classmethod
    def register_instance(cls, model_name: str, instance: 'ModelManager') -> None:
        """Register model manager instance in cache"""
        with cls._lock:
            cls._instances[model_name] = instance
            print(f"[MODEL] Registered {model_name} in global cache")
    
    @classmethod
    def clear_all_instances(cls) -> None:
        """Unload and clear all cached model instances"""
        with cls._lock:
            for name, instance in list(cls._instances.items()):
                try:
                    instance.unload()
                except Exception as e:
                    print(f"[MODEL] Error unloading {name}: {e}")
            
            cls._instances.clear()
            clear_gpu_cache()
            print("[MODEL] All instances cleared")


class ASRModelManager(ModelManager):
    """
    Manager for ASR (Automatic Speech Recognition) models
    
    NOW ALLOWS GPU: Uses GPU for maximum accuracy (~2GB), leaves remainder for Gemma
    """
    
    def __init__(
        self,
        model_name: str = "nvidia/parakeet-tdt-0.6b-v2",  # Parakeet TDT (6% WER)
        model_path: Optional[str] = None,  # Support local .nemo files
        batch_size: int = 1,
        use_gpu: bool = True  # GPU enabled for maximum accuracy
    ):
        # Allow GPU for ASR to maximize accuracy (user requirement)
        super().__init__(
            model_name=model_name,
            model_path=model_path,
            force_cpu=not use_gpu,  # CPU only if use_gpu=False
            force_gpu=False  # Don't FORCE GPU, allow fallback to CPU if needed
        )
        self.batch_size = batch_size
        self.use_gpu = use_gpu
        self.local_nemo_file = None
        
        # Check for local .nemo file
        if model_path and Path(model_path).exists():
            self.local_nemo_file = str(model_path)
            print(f"[ASR] Found local .nemo file: {self.local_nemo_file}")
        
        device_str = "GPU" if use_gpu and is_gpu_available() else "CPU"
        print(f"[ASR] Initialized ASR manager: {model_name}")
        print(f"[ASR] Device: {device_str}, batch_size={batch_size}")
        print(f"[ASR] Expected VRAM: ~2.0GB (Parakeet TDT), WER: ~6%")
    
    def _load_model(self):
        """Load NeMo ASR model (GPU preferred for accuracy)"""
        import nemo.collections.asr as nemo_asr
        from ..utils.gpu_utils import log_vram_usage
        
        # PRIORITY 1: Try local .nemo file first (Parakeet TDT 0.6B V2)
        if self.local_nemo_file:
            try:
                print(f"[ASR] Loading local .nemo file: {self.local_nemo_file}")
                print(f"[ASR] Target device: {self.device}")
                log_vram_usage("[ASR] VRAM before model load")
                
                model = nemo_asr.models.ASRModel.restore_from(
                    restore_path=self.local_nemo_file,
                    map_location=self.device
                )
                model.eval()
                
                # Move to GPU if requested and available
                if self.use_gpu and "cuda" in self.device:
                    model = model.cuda()
                    log_vram_usage("[ASR] VRAM after model load (GPU)")
                    print(f"[ASR] ✅ Local Parakeet TDT loaded on GPU")
                    print(f"[ASR] Model type: {type(model).__name__}")
                else:
                    print(f"[ASR] Local Parakeet TDT loaded on CPU")
                
                return model
                
            except Exception as e_local:
                print(f"[ASR] ⚠️  Failed to load local .nemo file: {e_local}")
                print(f"[ASR] Falling back to cloud models...")
        
        # PRIORITY 2: Try cloud Parakeet-CTC-1.1B
        try:
            print(f"[ASR] Loading {self.model_name} on {self.device}...")
            model = nemo_asr.models.ASRModel.from_pretrained(
                model_name=self.model_name,
                map_location=self.device
            )
            model.eval()
            
            # Move to GPU if requested and available
            if self.use_gpu and "cuda" in self.device:
                model = model.cuda()
                log_vram_usage(f"[ASR] VRAM after {self.model_name} load")
                print(f"[ASR] ✅ {self.model_name} loaded on GPU")
            else:
                print(f"[ASR] {self.model_name} loaded on CPU")
            
            return model
            
        except Exception as e1:
            print(f"[ASR] Failed to load {self.model_name}: {e1}")
            print(f"[ASR] Trying fallback: nvidia/stt_en_fastconformer_hybrid_large_pc")
            
            # Fallback 1: FastConformer
            try:
                model = nemo_asr.models.ASRModel.from_pretrained(
                    model_name="nvidia/stt_en_fastconformer_hybrid_large_pc",
                    map_location=self.device
                )
                model.eval()
                if self.use_gpu and "cuda" in self.device:
                    model = model.cuda()
                print(f"[ASR] ✅ FastConformer loaded on {self.device}")
                return model
                
            except Exception as e2:
                print(f"[ASR] FastConformer also failed: {e2}")
                print(f"[ASR] Final fallback: nvidia/stt_en_conformer_ctc_large on CPU")
                
                # Fallback 2: Basic Conformer on CPU
                try:
                    model = nemo_asr.models.ASRModel.from_pretrained(
                        model_name="nvidia/stt_en_conformer_ctc_large",
                        map_location="cpu"
                    )
                    model.eval()
                    print(f"[ASR] ✅ Basic Conformer loaded on CPU (fallback)")
                    return model
                    
                except Exception as e3:
                    raise RuntimeError(f"All ASR models failed to load: {e3}")
    
    def _unload_model(self) -> None:
        """Unload ASR model"""
        if self._model is not None:
            del self._model


class SpeakerModelManager(ModelManager):
    """
    Manager for speaker verification models (TitaNet)
    
    Enforces CPU-only operation
    """
    
    def __init__(
        self,
        model_name: str = "nvidia/speakerverification_en_titanet_large",
        model_path: Optional[str] = None
    ):
        # FORCE CPU for speaker models
        super().__init__(
            model_name=model_name,
            model_path=model_path,
            force_cpu=True,  # CRITICAL: Speaker verification must be on CPU
            force_gpu=False
        )
        print("[SPEAKER] Initialized speaker model manager (CPU-only)")
    
    def _load_model(self):
        """Load TitaNet speaker model on CPU"""
        from nemo.collections.asr.models import EncDecSpeakerLabelModel
        
        try:
            model = EncDecSpeakerLabelModel.from_pretrained(
                self.model_name,
                map_location="cpu"  # FORCE CPU
            )
            model.eval()
            return model
        except Exception as e:
            raise RuntimeError(f"Failed to load speaker model: {e}")
    
    def _unload_model(self) -> None:
        """Unload speaker model"""
        if self._model is not None:
            del self._model


class EmbeddingModelManager(ModelManager):
    """
    Manager for text embedding models (Sentence Transformers)
    
    Enforces CPU-only operation
    """
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        model_path: Optional[str] = None
    ):
        # FORCE CPU for embedding models
        super().__init__(
            model_name=model_name,
            model_path=model_path,
            force_cpu=True,  # CRITICAL: Embeddings must be on CPU
            force_gpu=False
        )
        print("[EMBEDDING] Initialized embedding model manager (CPU-only)")
    
    def _load_model(self):
        """Load Sentence Transformer model on CPU"""
        from sentence_transformers import SentenceTransformer
        
        try:
            # Try local path first
            if self.model_path and Path(self.model_path).exists():
                print(f"[EMBEDDING] Loading from local path: {self.model_path}")
                model = SentenceTransformer(self.model_path, device="cpu")
            else:
                print(f"[EMBEDDING] Loading {self.model_name} from Hugging Face")
                model = SentenceTransformer(self.model_name, device="cpu")
            
            return model
        except Exception as e:
            raise RuntimeError(f"Failed to load embedding model: {e}")
    
    def _unload_model(self) -> None:
        """Unload embedding model"""
        if self._model is not None:
            del self._model


class EmotionModelManager(ModelManager):
    """
    Manager for emotion analysis models (DistilRoBERTa)
    
    Enforces CPU-only operation
    """
    
    def __init__(
        self,
        model_name: str = "j-hartmann/emotion-english-distilroberta-base",
        model_path: Optional[str] = None
    ):
        # FORCE CPU for emotion models
        super().__init__(
            model_name=model_name,
            model_path=model_path,
            force_cpu=True,  # CRITICAL: Emotion analysis must be on CPU
            force_gpu=False
        )
        print("[EMOTION] Initialized emotion model manager (CPU-only)")
    
    def _load_model(self):
        """Load emotion classifier on CPU"""
        from transformers import pipeline
        
        try:
            model = pipeline(
                "text-classification",
                model=self.model_name,
                device=-1,  # -1 = CPU
                top_k=None  # Return all emotion scores
            )
            return model
        except Exception as e:
            raise RuntimeError(f"Failed to load emotion model: {e}")
    
    def _unload_model(self) -> None:
        """Unload emotion model"""
        if self._model is not None:
            del self._model


class GemmaModelManager(ModelManager):
    """
    Manager for Gemma LLM model
    
    ENFORCES GPU-ONLY operation (exclusive GPU access)
    """
    
    def __init__(
        self,
        model_path: str,
        n_threads: int = 4,
        max_tokens: int = 512,
        temperature: float = 0.7,
        n_gpu_layers: int = -1  # -1 = all layers on GPU
    ):
        # FORCE GPU for Gemma
        if not is_gpu_available():
            raise RuntimeError("Gemma requires GPU but none available")
        
        super().__init__(
            model_name="Gemma-3-4B-IT",
            model_path=model_path,
            force_cpu=False,
            force_gpu=True,  # CRITICAL: Gemma MUST be on GPU
            gpu_id=0
        )
        
        self.n_threads = n_threads
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.n_gpu_layers = n_gpu_layers
        
        print(f"[GEMMA] Initialized Gemma manager (GPU-ONLY, {n_gpu_layers} GPU layers)")
    
    def _load_model(self):
        """Load Gemma GGUF model with llama-cpp-python (GPU)"""
        from llama_cpp import Llama
        
        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"Gemma model not found: {self.model_path}")
        
        try:
            # Check GPU memory before loading
            log_vram_usage("[GEMMA] Before load")
            
            model = Llama(
                model_path=self.model_path,
                n_ctx=2048,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,  # Maximum GPU layers
                verbose=False,
                use_mmap=True,
                use_mlock=False,
            )
            
            # Verify GPU usage
            log_vram_usage("[GEMMA] After load")
            
            return model
            
        except Exception as e:
            raise RuntimeError(f"Failed to load Gemma model: {e}")
    
    def _unload_model(self) -> None:
        """Unload Gemma model"""
        if self._model is not None:
            del self._model
            clear_gpu_cache()
    
    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop: Optional[list] = None
    ) -> str:
        """
        Generate text with Gemma
        
        Args:
            prompt: Input prompt
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            stop: Stop sequences
        
        Returns:
            Generated text
        """
        if not self.is_loaded:
            raise RuntimeError("Gemma model not loaded")
        
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature or self.temperature
        
        try:
            response = self._model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=stop or [],
                echo=False
            )
            
            return response["choices"][0]["text"].strip()
            
        except Exception as e:
            raise RuntimeError(f"Gemma generation failed: {e}")


# Convenience functions for quick model loading

def load_asr_model(batch_size: int = 1) -> ASRModelManager:
    """Load ASR model (CPU-only)"""
    manager = ASRModelManager(batch_size=batch_size)
    manager.load()
    return manager


def load_speaker_model() -> SpeakerModelManager:
    """Load speaker verification model (CPU-only)"""
    manager = SpeakerModelManager()
    manager.load()
    return manager


def load_embedding_model(model_path: Optional[str] = None) -> EmbeddingModelManager:
    """Load embedding model (CPU-only)"""
    manager = EmbeddingModelManager(model_path=model_path)
    manager.load()
    return manager


def load_emotion_model() -> EmotionModelManager:
    """Load emotion analysis model (CPU-only)"""
    manager = EmotionModelManager()
    manager.load()
    return manager


def load_gemma_model(
    model_path: str,
    max_tokens: int = 512,
    n_gpu_layers: int = -1
) -> GemmaModelManager:
    """Load Gemma LLM (GPU-only)"""
    manager = GemmaModelManager(
        model_path=model_path,
        max_tokens=max_tokens,
        n_gpu_layers=n_gpu_layers
    )
    manager.load()
    return manager

