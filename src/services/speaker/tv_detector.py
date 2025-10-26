"""
TV Audio Detection Module

Detects television audio using acoustic features and speaker clustering,
rather than voice matching (which fails due to TV having multiple speakers).

TV Characteristics:
- Multiple speakers changing frequently (2-5+ per 30s)
- Consistent distance from microphone (TV doesn't move)
- Background music and sound effects
- Broadcast audio compression
- Indirect sound (room reflections)
- Scripted/acted speech patterns
"""

import numpy as np
import librosa
from typing import List, Dict, Any, Optional
from pathlib import Path


class TVDetector:
    """
    Detects television audio using acoustic features
    """
    
    def __init__(
        self,
        speaker_change_threshold: int = 1,  # >1 speaker in segment = likely TV (lowered from 2)
        distance_consistency_threshold: float = 0.20,  # RMS variation < 20% = consistent distance (relaxed from 15%)
        min_segment_duration: float = 5.0  # Minimum duration to analyze (lowered from 10s)
    ):
        """
        Initialize TV detector
        
        Args:
            speaker_change_threshold: Number of speaker changes to flag as TV
            distance_consistency_threshold: Max RMS variation for "same distance"
            min_segment_duration: Minimum audio duration for analysis
        """
        self.speaker_change_threshold = speaker_change_threshold
        self.distance_consistency_threshold = distance_consistency_threshold
        self.min_segment_duration = min_segment_duration
    
    def analyze_speaker_changes(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze speaker change patterns in segments
        
        Args:
            segments: List of segments with 'speaker' field
        
        Returns:
            Analysis dict with speaker change metrics
        """
        if not segments:
            return {"speaker_count": 0, "change_rate": 0.0, "is_tv_pattern": False}
        
        # Count unique speakers
        speakers = set(seg.get("speaker", "SPK_00") for seg in segments)
        speaker_count = len(speakers)
        
        # Calculate change rate (changes per 30 seconds)
        total_duration = segments[-1].get("end", 0) - segments[0].get("start", 0)
        if total_duration < self.min_segment_duration:
            return {"speaker_count": speaker_count, "change_rate": 0.0, "is_tv_pattern": False}
        
        # Count speaker transitions
        changes = 0
        for i in range(1, len(segments)):
            if segments[i].get("speaker") != segments[i-1].get("speaker"):
                changes += 1
        
        # Normalize to per-30-seconds
        change_rate = (changes / total_duration) * 30.0 if total_duration > 0 else 0.0
        
        # TV pattern: multiple speakers changing frequently
        # Lowered threshold: even 2 speakers with ANY changes suggests TV
        is_tv_pattern = speaker_count > self.speaker_change_threshold and change_rate > 0.5
        
        return {
            "speaker_count": speaker_count,
            "speaker_changes": changes,
            "change_rate": change_rate,
            "total_duration": total_duration,
            "is_tv_pattern": is_tv_pattern
        }
    
    def analyze_audio_distance(self, audio_path: str, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze audio distance/power consistency
        
        TV audio comes from consistent distance (TV doesn't move).
        Human speech varies more as person moves/turns.
        
        Args:
            audio_path: Path to audio file
            segments: List of segments with start/end times
        
        Returns:
            Analysis dict with distance metrics
        """
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=16000)
            
            # Extract RMS energy for each segment
            segment_rms = []
            for seg in segments:
                start_sample = int(seg.get("start", 0) * sr)
                end_sample = int(seg.get("end", 0) * sr)
                
                if end_sample > start_sample and end_sample <= len(y):
                    segment_audio = y[start_sample:end_sample]
                    rms = np.sqrt(np.mean(segment_audio**2))
                    segment_rms.append(rms)
            
            if not segment_rms:
                return {"is_consistent_distance": False, "rms_variation": 1.0}
            
            # Calculate variation (coefficient of variation)
            mean_rms = np.mean(segment_rms)
            std_rms = np.std(segment_rms)
            variation = std_rms / mean_rms if mean_rms > 0 else 1.0
            
            # TV = consistent distance = low variation
            is_consistent = variation < self.distance_consistency_threshold
            
            return {
                "mean_rms": float(mean_rms),
                "rms_variation": float(variation),
                "is_consistent_distance": is_consistent,
                "segment_count": len(segment_rms)
            }
            
        except Exception as e:
            print(f"[TV_DETECTOR] Audio analysis error: {e}")
            return {"is_consistent_distance": False, "rms_variation": 1.0}
    
    def detect_background_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Detect background music/sound effects (common in TV)
        
        Uses spectral analysis to detect non-speech audio components.
        
        Args:
            audio_path: Path to audio file
        
        Returns:
            Analysis dict with background audio metrics
        """
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=16000)
            
            # Compute mel spectrogram
            mel_spec = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128)
            mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)
            
            # Detect background components
            # TV often has continuous low-frequency background (music, ambient)
            low_freq_energy = np.mean(mel_spec_db[:20, :])  # Lower mel bands
            mid_freq_energy = np.mean(mel_spec_db[20:80, :])  # Voice range
            
            # TV = higher low-freq relative to mid (music/ambience)
            background_ratio = low_freq_energy / mid_freq_energy if mid_freq_energy != 0 else 0
            
            has_background = background_ratio > 0.7  # Threshold for "significant background"
            
            return {
                "low_freq_energy": float(low_freq_energy),
                "mid_freq_energy": float(mid_freq_energy),
                "background_ratio": float(background_ratio),
                "has_background_audio": has_background
            }
            
        except Exception as e:
            print(f"[TV_DETECTOR] Background detection error: {e}")
            return {"has_background_audio": False, "background_ratio": 0.0}
    
    def is_television(
        self,
        audio_path: str,
        segments: List[Dict[str, Any]],
        pruitt_match_count: int = 0
    ) -> Dict[str, Any]:
        """
        Determine if audio is from television
        
        Combines multiple detection methods:
        1. Speaker change patterns
        2. Audio distance consistency
        3. Background audio presence
        
        Args:
            audio_path: Path to audio file
            segments: List of segments with speaker/timing info
            pruitt_match_count: Number of segments matched to 'pruitt'
        
        Returns:
            Detection result with confidence and reasoning
        """
        # If pruitt speaks, definitely not pure TV
        if pruitt_match_count > 0:
            return {
                "is_tv": False,
                "confidence": 0.95,
                "reason": "Pruitt detected in audio",
                "details": {}
            }
        
        # Analyze speaker changes
        speaker_analysis = self.analyze_speaker_changes(segments)
        
        # Analyze audio distance
        distance_analysis = self.analyze_audio_distance(audio_path, segments)
        
        # Analyze background audio
        background_analysis = self.detect_background_audio(audio_path)
        
        # Scoring system
        score = 0.0
        reasons = []
        
        # Multiple speakers changing = strong TV indicator
        if speaker_analysis["is_tv_pattern"]:
            score += 0.5
            reasons.append(f"{speaker_analysis['speaker_count']} speakers, {speaker_analysis['change_rate']:.1f} changes/30s")
        
        # Consistent distance = TV stays in place
        if distance_analysis["is_consistent_distance"]:
            score += 0.3
            reasons.append(f"Consistent audio distance (var={distance_analysis['rms_variation']:.2f})")
        
        # Background audio = TV often has music/SFX
        if background_analysis["has_background_audio"]:
            score += 0.2
            reasons.append(f"Background audio detected (ratio={background_analysis['background_ratio']:.2f})")
        
        is_tv = score >= 0.25  # Threshold for TV classification (lowered from 0.5)
        confidence = min(score, 1.0)
        
        return {
            "is_tv": is_tv,
            "confidence": confidence,
            "score": score,
            "reason": " + ".join(reasons) if reasons else "Insufficient evidence",
            "details": {
                "speaker_analysis": speaker_analysis,
                "distance_analysis": distance_analysis,
                "background_analysis": background_analysis
            }
        }


# Global detector instance
_tv_detector: Optional[TVDetector] = None


def get_tv_detector() -> TVDetector:
    """Get or create global TV detector instance"""
    global _tv_detector
    if _tv_detector is None:
        _tv_detector = TVDetector()
    return _tv_detector

