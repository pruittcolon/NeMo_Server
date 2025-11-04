"""Audio conversion and chunking utilities for the Parakeet pipeline."""

from __future__ import annotations

import logging
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import soundfile as sf

logger = logging.getLogger(__name__)


@dataclass
class ConvertedAudio:
    """Represents a normalised WAV file that may need cleanup."""

    path: str
    created: bool = False

    def cleanup(self) -> None:
        """Remove the file if it was created by the converter."""
        if self.created and os.path.exists(self.path):
            try:
                os.unlink(self.path)
            except OSError:
                logger.debug("Failed to remove temporary audio file %s", self.path)


def convert_audio_to_wav(input_path: str, sample_rate: int = 16000) -> ConvertedAudio:
    """
    Convert any audio format to mono 16 kHz WAV using ffmpeg.

    Returns an object that tracks whether a new temporary file was created.
    """
    target_suffix = ".wav"
    input_suffix = Path(input_path).suffix.lower()

    # If already WAV at 16 kHz/mono we still normalise via ffmpeg
    temp_file = tempfile.NamedTemporaryFile(suffix=target_suffix, delete=False)
    temp_file.close()
    output_path = temp_file.name

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "1",
        output_path,
    ]

    logger.debug("Converting audio with ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg conversion failed: %s", result.stderr.strip())
        # Clean up the temp file since conversion failed
        try:
            os.unlink(output_path)
        except OSError:
            pass
        raise RuntimeError(f"ffmpeg failed to convert audio: {result.stderr.strip()}")

    created = True
    return ConvertedAudio(path=output_path, created=created)


def _get_wav_duration(path: str) -> float:
    try:
        info = sf.info(path)
        return float(info.duration)
    except Exception as exc:
        logger.warning("Failed to read audio duration for %s: %s", path, exc)
        return 0.0


def split_audio_into_chunks(wav_path: str, chunk_duration: int = 300) -> Tuple[List[str], float]:
    """
    Split a WAV file into fixed-length chunks using ffmpeg.

    Returns a tuple of (chunk_paths, total_duration_seconds).
    """
    duration = _get_wav_duration(wav_path)
    if duration <= 0:
        logger.warning("Audio duration unavailable or invalid for %s; skipping split", wav_path)
        return [wav_path], duration

    if duration <= chunk_duration:
        logger.info("Audio shorter than chunk duration (%.2fs <= %ds); no split performed", duration, chunk_duration)
        return [wav_path], duration

    num_chunks = math.ceil(duration / chunk_duration)
    logger.info("Splitting audio (%.2fs) into %d chunk(s) of %ds", duration, num_chunks, chunk_duration)

    chunk_paths: List[str] = []
    temp_dir = tempfile.mkdtemp(prefix="parakeet_chunks_")

    for idx in range(num_chunks):
        start_time = idx * chunk_duration
        output_path = os.path.join(temp_dir, f"chunk_{idx:04d}.wav")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_time),
            "-i",
            wav_path,
            "-t",
            str(chunk_duration),
            "-c:a",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            output_path,
        ]

        logger.debug("Creating chunk with ffmpeg: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Failed to create chunk %d: %s", idx, result.stderr.strip())
            # Clean up previously created chunks
            for chunk in chunk_paths:
                try:
                    os.unlink(chunk)
                except OSError:
                    pass
            raise RuntimeError(f"ffmpeg failed during chunking: {result.stderr.strip()}")

        chunk_paths.append(output_path)

    return chunk_paths, duration
