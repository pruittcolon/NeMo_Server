"""
Audio Metrics Extraction

Extracts audio features for voice fine-tuning and analysis:
- Pitch (mean, std)
- Energy/amplitude
- Speaking rate
- Spectral features

These metrics enable future voice cloning and TTS personalization.
"""

import logging
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Try to import librosa (optional for advanced features)
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logger.warning("librosa not available - using basic metrics only")


def extract_audio_metrics(
    audio_data: np.ndarray,
    sample_rate: int,
    text: Optional[str] = None
) -> Dict[str, float]:
    """
    Extract audio metrics for voice fine-tuning
    
    Args:
        audio_data: Audio waveform as numpy array
        sample_rate: Sample rate in Hz
        text: Transcript text (for speaking rate calculation)
    
    Returns:
        Dictionary of audio metrics
    """
    try:
        metrics = {}
        
        # Duration
        duration_ms = len(audio_data) / sample_rate * 1000
        metrics['duration_ms'] = float(duration_ms)
        
        # Energy (RMS amplitude)
        energy_mean = float(np.sqrt(np.mean(audio_data ** 2)))
        metrics['energy_mean'] = energy_mean
        metrics['energy_std'] = float(np.std(audio_data ** 2))
        
        # Peak amplitude
        metrics['amplitude_peak'] = float(np.max(np.abs(audio_data)))
        
        # Zero-crossing rate (proxy for noisiness/breathiness)
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio_data)))) / 2
        metrics['zero_crossing_rate'] = float(zero_crossings / len(audio_data))
        
        # Speaking rate (if text provided)
        if text:
            word_count = len(text.split())
            duration_sec = duration_ms / 1000
            if duration_sec > 0:
                metrics['speaking_rate'] = float(word_count / duration_sec)  # words/sec
        
        # Advanced features (if librosa available)
        if LIBROSA_AVAILABLE:
            try:
                # Pitch (F0) estimation using librosa
                pitches, magnitudes = librosa.piptrack(
                    y=audio_data.astype(np.float32),
                    sr=sample_rate,
                    fmin=50,  # Min frequency (Hz)
                    fmax=400  # Max frequency (Hz)
                )
                
                # Extract pitch values where magnitude is highest
                pitch_values = []
                for t in range(pitches.shape[1]):
                    index = magnitudes[:, t].argmax()
                    pitch = pitches[index, t]
                    if pitch > 0:
                        pitch_values.append(pitch)
                
                if pitch_values:
                    metrics['pitch_mean'] = float(np.mean(pitch_values))
                    metrics['pitch_std'] = float(np.std(pitch_values))
                    metrics['pitch_min'] = float(np.min(pitch_values))
                    metrics['pitch_max'] = float(np.max(pitch_values))
                
                # Spectral centroid (brightness of sound)
                spectral_centroids = librosa.feature.spectral_centroid(
                    y=audio_data.astype(np.float32),
                    sr=sample_rate
                )[0]
                metrics['spectral_centroid_mean'] = float(np.mean(spectral_centroids))
                metrics['spectral_centroid_std'] = float(np.std(spectral_centroids))
                
                # Spectral rolloff (frequency below which 85% of energy is contained)
                spectral_rolloff = librosa.feature.spectral_rolloff(
                    y=audio_data.astype(np.float32),
                    sr=sample_rate
                )[0]
                metrics['spectral_rolloff_mean'] = float(np.mean(spectral_rolloff))
                
                # MFCC (Mel-frequency cepstral coefficients) - voice timbre
                mfccs = librosa.feature.mfcc(
                    y=audio_data.astype(np.float32),
                    sr=sample_rate,
                    n_mfcc=13
                )
                for i in range(min(5, mfccs.shape[0])):  # Store first 5 MFCCs
                    metrics[f'mfcc_{i}_mean'] = float(np.mean(mfccs[i]))
                
            except Exception as e:
                logger.warning(f"Failed to extract advanced metrics: {e}")
        
        logger.debug(f"Extracted {len(metrics)} audio metrics")
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to extract audio metrics: {e}")
        # Return basic metrics
        return {
            'duration_ms': float(len(audio_data) / sample_rate * 1000),
            'energy_mean': float(np.mean(np.abs(audio_data))),
            'error': str(e)
        }


def calculate_segment_metrics(
    audio_data: np.ndarray,
    sample_rate: int,
    start_time: float,
    end_time: float,
    text: str
) -> Dict[str, float]:
    """
    Extract metrics for a specific segment
    
    Args:
        audio_data: Full audio waveform
        sample_rate: Sample rate in Hz
        start_time: Segment start time (seconds)
        end_time: Segment end time (seconds)
        text: Segment transcript
    
    Returns:
        Dictionary of audio metrics
    """
    try:
        # Extract segment
        start_sample = int(start_time * sample_rate)
        end_sample = int(end_time * sample_rate)
        segment_audio = audio_data[start_sample:end_sample]
        
        if len(segment_audio) == 0:
            logger.warning(f"Empty audio segment at {start_time}-{end_time}")
            return {}
        
        # Extract metrics
        return extract_audio_metrics(segment_audio, sample_rate, text)
        
    except Exception as e:
        logger.error(f"Failed to calculate segment metrics: {e}")
        return {}





