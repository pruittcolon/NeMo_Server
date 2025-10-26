"""
Audio Processing Utilities

Handles:
- FFmpeg audio conversion
- Audio overlap caching for streaming
- WAV file creation and validation
- Sample rate conversion

Extracted from: main3.py lines 638-660, TAIL_CACHE logic
"""

import os
import subprocess
import tempfile
from typing import Optional, Dict
import numpy as np
import soundfile as sf


class AudioConverter:
    """FFmpeg-based audio conversion utility"""
    
    def __init__(self, target_sample_rate: int = 16000, target_channels: int = 1):
        """
        Initialize audio converter
        
        Args:
            target_sample_rate: Target sample rate (default: 16000 Hz)
            target_channels: Target number of channels (default: 1 for mono)
        """
        self.target_sample_rate = target_sample_rate
        self.target_channels = target_channels
        
        # Check FFmpeg availability
        if not self._is_ffmpeg_available():
            raise RuntimeError("FFmpeg is not installed or not in PATH")
    
    @staticmethod
    def _is_ffmpeg_available() -> bool:
        """Check if FFmpeg is available"""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def convert_to_wav(
        self,
        input_path: str,
        output_path: str,
        remove_input: bool = True
    ) -> None:
        """
        Convert audio file to WAV format (16kHz mono PCM)
        
        Args:
            input_path: Path to input audio file
            output_path: Path to output WAV file
            remove_input: Whether to remove input file after conversion
        
        Raises:
            RuntimeError: If FFmpeg conversion fails
        """
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", input_path,
            "-ar", str(self.target_sample_rate),
            "-ac", str(self.target_channels),
            "-c:a", "pcm_s16le",
            output_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=60
            )
            
            # Remove input file if requested
            if remove_input and os.path.exists(input_path):
                try:
                    os.remove(input_path)
                except Exception as e:
                    print(f"[AUDIO] Warning: Could not remove input file: {e}")
                    
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg conversion failed: {e.stderr}"
            print(f"[AUDIO] {error_msg}")
            raise RuntimeError(error_msg)
        except subprocess.TimeoutExpired:
            error_msg = "FFmpeg conversion timed out (>60s)"
            print(f"[AUDIO] {error_msg}")
            raise RuntimeError(error_msg)
    
    def convert_segment(
        self,
        input_path: str,
        start_time: float,
        end_time: float,
        output_path: Optional[str] = None
    ) -> str:
        """
        Extract audio segment and convert to WAV
        
        Args:
            input_path: Path to input audio file
            start_time: Start time in seconds
            end_time: End time in seconds
            output_path: Optional output path (temp file if None)
        
        Returns:
            Path to output WAV file
        
        Raises:
            RuntimeError: If FFmpeg conversion fails
        """
        if output_path is None:
            # Create temp file
            temp_fd, output_path = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)
        
        start_time = max(0.0, start_time)
        end_time = max(start_time, end_time)
        
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-y",
            "-i", input_path,
            "-ar", str(self.target_sample_rate),
            "-ac", str(self.target_channels),
            "-c:a", "pcm_s16le",
            "-ss", str(start_time),
            "-to", str(end_time),
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            return output_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # Clean up temp file on error
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            raise RuntimeError(f"Segment conversion failed: {e}")
    
    def validate_wav(self, wav_path: str) -> bool:
        """
        Validate WAV file format
        
        Args:
            wav_path: Path to WAV file
        
        Returns:
            True if valid, False otherwise
        """
        try:
            audio_array, sr = sf.read(wav_path, dtype="float32")
            
            # Check sample rate
            if sr != self.target_sample_rate:
                print(f"[AUDIO] Warning: Sample rate {sr} != {self.target_sample_rate}")
                return False
            
            # Check channels
            if audio_array.ndim > 1:
                if audio_array.shape[1] != self.target_channels:
                    print(f"[AUDIO] Warning: Channels {audio_array.shape[1]} != {self.target_channels}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"[AUDIO] WAV validation failed: {e}")
            return False


class AudioOverlapManager:
    """
    Manages audio overlap caching for streaming transcription
    
    Stores tail samples from previous audio chunks to handle word boundaries
    that span chunk boundaries.
    
    Replaces: TAIL_CACHE global dictionary from main3.py
    """
    
    def __init__(self, overlap_seconds: float = 0.7, sample_rate: int = 16000):
        """
        Initialize overlap manager
        
        Args:
            overlap_seconds: Duration of overlap in seconds
            sample_rate: Audio sample rate
        """
        self.overlap_seconds = overlap_seconds
        self.sample_rate = sample_rate
        self.tail_samples = int(sample_rate * overlap_seconds)
        self._cache: Dict[str, np.ndarray] = {}
        
        print(f"[AUDIO] Overlap manager initialized: {overlap_seconds}s ({self.tail_samples} samples)")
    
    def add_overlap(
        self,
        stream_id: str,
        audio_array: np.ndarray,
        prepend_cached: bool = True
    ) -> tuple[np.ndarray, int]:
        """
        Add overlap from cache and update cache with new tail
        
        Args:
            stream_id: Unique stream identifier
            audio_array: New audio chunk
            prepend_cached: Whether to prepend cached overlap
        
        Returns:
            (final_audio, overlap_used): Combined audio and overlap sample count
        """
        overlap_used = 0
        final_audio = audio_array
        
        # Prepend cached overlap if requested
        if prepend_cached and stream_id in self._cache:
            prev = self._cache[stream_id]
            if prev is not None and len(prev) > 0:
                overlap_used = len(prev)
                final_audio = np.concatenate((prev, audio_array))
                print(f"[AUDIO] Stream {stream_id}: Added {overlap_used} overlap samples")
        
        # Store tail for next chunk
        if self.tail_samples > 0:
            if len(final_audio) >= self.tail_samples:
                self._cache[stream_id] = final_audio[-self.tail_samples:]
            else:
                self._cache[stream_id] = final_audio
        
        return final_audio, overlap_used
    
    def clear_stream(self, stream_id: str) -> None:
        """Clear cached overlap for a stream"""
        if stream_id in self._cache:
            del self._cache[stream_id]
            print(f"[AUDIO] Cleared overlap cache for stream {stream_id}")
    
    def clear_all(self) -> None:
        """Clear all cached overlaps"""
        self._cache.clear()
        print("[AUDIO] Cleared all overlap caches")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            "active_streams": len(self._cache),
            "overlap_seconds": self.overlap_seconds,
            "tail_samples": self.tail_samples,
            "sample_rate": self.sample_rate
        }


def create_wav_from_pcm(
    pcm_data: np.ndarray,
    output_path: str,
    sample_rate: int = 16000,
    channels: int = 1,
    bits_per_sample: int = 16
) -> None:
    """
    Create WAV file from raw PCM data
    
    Args:
        pcm_data: PCM audio data (numpy array)
        output_path: Path to output WAV file
        sample_rate: Sample rate (default: 16000)
        channels: Number of channels (default: 1)
        bits_per_sample: Bits per sample (default: 16)
    """
    # Simple WAV header for PCM data
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_data)
    file_size = 36 + data_size
    
    import struct
    
    header = bytearray()
    
    # RIFF header
    header.extend(b'RIFF')
    header.extend(struct.pack('<I', file_size))
    header.extend(b'WAVE')
    
    # fmt chunk
    header.extend(b'fmt ')
    header.extend(struct.pack('<I', 16))  # fmt chunk size
    header.extend(struct.pack('<H', 1))   # PCM format
    header.extend(struct.pack('<H', channels))
    header.extend(struct.pack('<I', sample_rate))
    header.extend(struct.pack('<I', byte_rate))
    header.extend(struct.pack('<H', block_align))
    header.extend(struct.pack('<H', bits_per_sample))
    
    # data chunk
    header.extend(b'data')
    header.extend(struct.pack('<I', data_size))
    
    # Write file
    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(pcm_data.tobytes())
    
    print(f"[AUDIO] Created WAV file: {output_path} ({data_size} bytes)")


# Convenience function for quick conversions
def quick_convert(input_path: str, output_path: str) -> None:
    """Quick conversion using default settings"""
    converter = AudioConverter()
    converter.convert_to_wav(input_path, output_path)


