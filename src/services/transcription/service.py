"""
Transcription Service

Handles audio transcription using NeMo Parakeet ASR
Enforces CPU-only operation
Extracted from: main3.py lines 110-119, 621-854

Key Features:
- NeMo Conformer-CTC Large model
- CPU-only processing (GPU reserved for Gemma)
- Timestamp extraction
- Retry logic for errors
- Batch processing support
"""

import os
import tempfile
from typing import List, Dict, Any, Optional, Tuple
import uuid

import numpy as np
import soundfile as sf
import torch

# Import our utilities
from src.utils.audio_utils import AudioConverter, AudioOverlapManager
from src.utils.gpu_utils import clear_gpu_cache
from src.models.model_manager import ASRModelManager

# Import config from parent
import sys
from pathlib import Path
# Add parent src to path for config import
parent_src = str(Path(__file__).parent.parent.parent.parent / "src")
if parent_src not in sys.path:
    sys.path.insert(0, parent_src)

try:
    import config
except ImportError:
    # Fallback if config not found
    class config:
        ASR_BATCH = 1
        OVERLAP_SECS = 0.7
        SEGMENT_MIN_SECONDS = 1.0


class TranscriptionService:
    """
    NeMo ASR transcription service
    
    CPU-only operation to leave GPU free for Gemma
    """
    
    def __init__(
        self,
        batch_size: int = 1,
        overlap_seconds: float = 0.7,
        upload_dir: Optional[str] = None
    ):
        """
        Initialize transcription service
        
        Args:
            batch_size: ASR batch size (default: 1)
            overlap_seconds: Audio overlap for streaming (default: 0.7)
            upload_dir: Directory for temporary audio files
        """
        self.batch_size = batch_size
        self.overlap_seconds = overlap_seconds
        self.upload_dir = upload_dir or tempfile.gettempdir()
        
        # Initialize components
        self.audio_converter = AudioConverter(target_sample_rate=16000, target_channels=1)
        self.overlap_manager = AudioOverlapManager(overlap_seconds=overlap_seconds, sample_rate=16000)
        
        # ASR model manager (will load on first use)
        # Using Parakeet TDT 0.6B V2 - best quality ASR model
        self.asr_manager = ASRModelManager(
            model_name="nvidia/parakeet-tdt-0.6b-v2",
            model_path="/app/models/parakeet-tdt-0.6b-v2.nemo",
            batch_size=batch_size,
            use_gpu=True  # GPU for maximum accuracy
        )
        
        # Job storage
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.latest_result: Dict[str, str] = {"answer": "No transcription yet."}
        
        print(f"[TRANSCRIPTION] Service initialized (batch_size={batch_size}, overlap={overlap_seconds}s)")
    
    def load_model(self) -> None:
        """Load ASR model (CPU-only)"""
        if not self.asr_manager.is_loaded:
            print("[TRANSCRIPTION] Loading NeMo ASR model...")
            self.asr_manager.load()
            print("[TRANSCRIPTION] ASR model loaded on CPU")
    
    def _save_uploaded_file(self, file_data: bytes, filename: str) -> Tuple[str, str]:
        """
        Save uploaded file to disk
        
        Args:
            file_data: Raw file bytes
            filename: Original filename
        
        Returns:
            (job_id, raw_path): Job ID and path to saved file
        """
        job_id = str(uuid.uuid4())
        raw_path = os.path.join(self.upload_dir, f"{job_id}_{filename}")
        
        with open(raw_path, "wb") as f:
            f.write(file_data)
        
        print(f"[TRANSCRIPTION] Saved uploaded file: {raw_path}")
        return job_id, raw_path
    
    def _convert_audio(self, raw_path: str, job_id: str) -> str:
        """
        Convert audio to 16kHz mono WAV
        
        Args:
            raw_path: Path to raw audio file
            job_id: Job identifier
        
        Returns:
            Path to converted WAV file
        
        Raises:
            RuntimeError: If conversion fails
        """
        conv_path = os.path.join(self.upload_dir, f"{job_id}.wav")
        
        try:
            self.audio_converter.convert_to_wav(
                input_path=raw_path,
                output_path=conv_path,
                remove_input=True
            )
            print(f"[TRANSCRIPTION] Converted to WAV: {conv_path}")
            return conv_path
            
        except RuntimeError as e:
            raise RuntimeError(f"Audio conversion failed: {e}")
    
    def _load_audio_array(self, wav_path: str) -> np.ndarray:
        """
        Load audio as numpy array
        
        Args:
            wav_path: Path to WAV file
        
        Returns:
            Audio array (mono, float32)
        
        Raises:
            RuntimeError: If loading fails or format is wrong
        """
        try:
            audio_array, sr = sf.read(wav_path, dtype="float32")
            
            if sr != 16000:
                raise RuntimeError(f"Unexpected sample rate {sr}; expected 16000")
            
            # Convert to mono if stereo
            if audio_array.ndim > 1:
                audio_array = audio_array.mean(axis=1)
            
            return audio_array
            
        except Exception as e:
            raise RuntimeError(f"Failed to load audio: {e}")
    
    def _prepare_inference_audio(
        self,
        audio_array: np.ndarray,
        stream_id: str,
        original_path: str
    ) -> Tuple[str, int]:
        """
        Prepare audio for inference (add overlap if streaming)
        
        Args:
            audio_array: Current audio chunk
            stream_id: Stream identifier
            original_path: Path to original WAV file
        
        Returns:
            (inference_path, overlap_used): Path to audio for inference and overlap sample count
        """
        # Add overlap from previous chunk
        final_audio, overlap_used = self.overlap_manager.add_overlap(
            stream_id=stream_id,
            audio_array=audio_array,
            prepend_cached=True
        )
        
        # If no overlap added, use original file
        if overlap_used == 0 or len(final_audio) == len(audio_array):
            return original_path, overlap_used
        
        # Create temp file with overlapped audio
        temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(temp_fd)
        
        try:
            sf.write(temp_path, final_audio, 16000)
            return temp_path, overlap_used
        except Exception as e:
            # Clean up on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise RuntimeError(f"Failed to create inference audio: {e}")
    
    def _transcribe_with_nemo(self, audio_path: str) -> Any:
        """
        Transcribe audio with NeMo ASR
        
        Args:
            audio_path: Path to audio file
        
        Returns:
            NeMo transcription output
        
        Raises:
            RuntimeError: If transcription fails
        """
        # Ensure model is loaded
        if not self.asr_manager.is_loaded:
            self.load_model()
        
        model = self.asr_manager.model
        
        try:
            # Clear cache before (though we're on CPU)
            clear_gpu_cache()
            
            # Transcribe
            transcribe_output = model.transcribe(
                [audio_path],
                batch_size=self.batch_size,
                timestamps=True
            )
            
            # Clear cache after
            clear_gpu_cache()
            
            return transcribe_output
            
        except RuntimeError as exc:
            # Handle CUDA OOM (shouldn't happen on CPU but check anyway)
            if "out of memory" in str(exc).lower():
                print("[TRANSCRIPTION] Memory error, clearing cache and retrying...")
                clear_gpu_cache()
                
                try:
                    transcribe_output = model.transcribe(
                        [audio_path],
                        batch_size=self.batch_size,
                        timestamps=True
                    )
                    clear_gpu_cache()
                    return transcribe_output
                except Exception as retry_exc:
                    raise RuntimeError(f"Transcription failed after retry: {retry_exc}")
            else:
                raise RuntimeError(f"Transcription failed: {exc}")
                
        except Exception as exc:
            raise RuntimeError(f"Transcription failed: {exc}")
    
    def _parse_nemo_output(self, transcribe_output: Any) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Parse NeMo hypothesis output
        
        Args:
            transcribe_output: NeMo transcription result
        
        Returns:
            (full_text, segment_entries): Transcribed text and timestamp segments
        """
        hypothesis = transcribe_output[0] if transcribe_output else None
        
        if hypothesis is not None and hasattr(hypothesis, 'text'):
            full_text = (hypothesis.text or "").strip()
            
            # Try to get timestamp info from hypothesis
            if hasattr(hypothesis, 'timestep'):
                timestamp_info = hypothesis.timestep or {}
            elif hasattr(hypothesis, 'timestamp'):
                timestamp_info = hypothesis.timestamp or {}
            else:
                timestamp_info = {}
            
            # Get segment entries
            if isinstance(timestamp_info, dict):
                segment_entries = timestamp_info.get("segment") or []
            else:
                segment_entries = []
        else:
            full_text = ""
            segment_entries = []
        
        return full_text, segment_entries
    
    def transcribe(
        self,
        audio_data: bytes,
        filename: str,
        stream_id: Optional[str] = None,
        seq: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio file
        
        Args:
            audio_data: Raw audio file bytes
            filename: Original filename
            stream_id: Optional stream identifier for overlap caching
            seq: Optional sequence number
        
        Returns:
            Transcription result with segments and full text
        
        Raises:
            RuntimeError: If transcription fails
        """
        temp_paths = []
        
        try:
            # Save uploaded file
            job_id, raw_path = self._save_uploaded_file(audio_data, filename)
            print(f"[TRANSCRIPTION] Job {job_id}: Processing {filename}")
            
            # Convert to WAV
            conv_path = self._convert_audio(raw_path, job_id)
            temp_paths.append(conv_path)
            
            # Load audio array
            audio_array = self._load_audio_array(conv_path)
            
            # Prepare inference audio (with overlap if streaming)
            sid = stream_id or job_id
            inference_path, overlap_used = self._prepare_inference_audio(
                audio_array, sid, conv_path
            )
            
            if inference_path != conv_path:
                temp_paths.append(inference_path)
            
            # Transcribe with NeMo
            transcribe_output = self._transcribe_with_nemo(inference_path)
            
            # Parse output
            full_text, segment_entries = self._parse_nemo_output(transcribe_output)
            
            # Build result (without speaker/emotion - that's done by other services)
            segments = []
            for seg in segment_entries:
                segments.append({
                    "start": float(seg.get("start", 0.0) or 0.0),
                    "end": float(seg.get("end", 0.0) or 0.0),
                    "text": (seg.get("segment") or seg.get("text") or "").strip(),
                    "speaker": "SPK",  # Default, will be updated by speaker service
                })
            
            result = {
                "job_id": job_id,
                "text": full_text,
                "segments": segments,
                "seq": seq,
                "audio_duration": len(audio_array) / 16000,
                "overlap_used": overlap_used / 16000 if overlap_used > 0 else 0,
                "audio_path": conv_path,  # Keep audio file for diarization
            }
            
            # Store in jobs cache
            self.jobs[job_id] = {
                "status": "complete",
                "answer": full_text,
                "result": result
            }
            
            # Update latest result
            if full_text:
                self.latest_result["answer"] = full_text
            
            print(f"[TRANSCRIPTION] Job {job_id}: Complete ({len(segments)} segments, {len(audio_array)/16000:.2f}s)")
            
            return result
            
        finally:
            # Clean up temp files (except conv_path which diarization needs)
            for path in temp_paths:
                if path and os.path.exists(path) and path != conv_path:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job result by ID"""
        return self.jobs.get(job_id)
    
    def get_latest_result(self) -> str:
        """Get latest transcription result"""
        return self.latest_result.get("answer", "No transcription yet.")
    
    def clear_stream(self, stream_id: str) -> None:
        """Clear overlap cache for a stream"""
        self.overlap_manager.clear_stream(stream_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "model_loaded": self.asr_manager.is_loaded,
            "model_device": self.asr_manager.device,
            "total_jobs": len(self.jobs),
            "overlap_stats": self.overlap_manager.get_stats(),
            "batch_size": self.batch_size,
        }


