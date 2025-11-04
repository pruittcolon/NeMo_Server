"""
Parakeet transcription pipeline.

Provides a high-level wrapper around the NeMo Parakeet-TDT ASR model
combined with optional Pyannote diarization. This implementation mirrors
the behaviour of https://github.com/jfgonsalves/parakeet-diarized but
returns segments in the format expected by the Nemo Server transcription
service.
"""

from .transcriber import ParakeetPipeline, ParakeetSegment, ParakeetTranscription

__all__ = [
    "ParakeetPipeline",
    "ParakeetSegment",
    "ParakeetTranscription",
]
