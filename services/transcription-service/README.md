# Transcription Service

Advanced speech-to-text service using NVIDIA NeMo toolkit with GPU coordination, speaker diarization, and emotion integration.

## Overview

The Transcription Service converts audio to text using NVIDIA's Parakeet RNNT models. It features:

- **Automatic Speech Recognition (ASR)**: State-of-the-art NeMo Parakeet models
- **Speaker Diarization**: Multi-speaker detection and labeling
- **Voice Activity Detection (VAD)**: Intelligent speech segment detection
- **Speaker Verification**: Match speakers against enrolled profiles
- **Emotion Analysis**: Integration with emotion service for sentiment
- **GPU Coordination**: Pause/resume capability for GPU sharing with Gemma service
- **RAG Integration**: Automatic indexing of transcripts for semantic search

## Architecture

### GPU Coordination
The service implements a sophisticated pause/resume system to share GPU with the Gemma AI service:

**Default State:**
- Service owns GPU and processes transcription requests
- Listens for pause/resume signals via Redis pub/sub channel

**When Gemma Requests GPU:**
1. Finish current transcription batch (~1-2 seconds)
2. Set paused flag and queue new requests
3. Acknowledge pause to GPU Coordinator
4. Gemma takes GPU ownership

**When Gemma Releases GPU:**
1. Receive resume signal from coordinator
2. Clear paused flag
3. Process all queued transcriptions
4. Resume normal operation

### Pipeline Flow

```
Audio Input
    ↓
VAD (Voice Activity Detection)
    ↓
Speech Segmentation
    ↓
ASR (Parakeet RNNT) → Transcription
    ↓
Speaker Diarization → Speaker Labels
    ↓
Speaker Verification → Match to Known Speakers
    ↓
Emotion Analysis → Sentiment per Segment
    ↓
RAG Indexing → Semantic Search Database
    ↓
Return Results + Store Metadata
```

## Key Features

### 1. Advanced ASR
- **Model**: NVIDIA Parakeet RNNT 0.6B or TDT 0.6B v2
- **Strategy**: RNNT or Parakeet-TDT (configurable)
- **Context Window**: Processes long-form audio with chunking
- **Batch Processing**: Efficient GPU utilization

### 2. Speaker Diarization
Two modes available:
- **NeMo Built-in**: Lightweight, VRAM efficient
- **Pyannote.audio**: More accurate, higher VRAM usage

Features:
- Automatic speaker count detection
- Configurable min/max speakers
- Silhouette scoring for optimal clustering
- Speaker embedding extraction (TitaNet Large model)

### 3. Voice Activity Detection (VAD)
- **Model**: MarbleNet multilingual VAD
- **Features**: 
  - Onset/offset thresholds for speech detection
  - Smoothing and padding for natural boundaries
  - Segment merging for continuous speech
  - Min/max segment length enforcement

### 4. Speaker Verification
- Match detected speakers against enrolled audio profiles
- Uses speaker embeddings for identification
- Configurable similarity thresholds
- Handles multi-speaker scenarios

### 5. Audio Quality Metrics
Extracts per-segment metrics:
- **Pitch**: F0 tracking for prosody analysis
- **Energy**: Volume/loudness measures
- **Speaking Rate**: Words per second
- **Zero Crossing Rate**: Voice quality indicator

## API Endpoints

### Transcribe Audio
```bash
POST /transcribe
Content-Type: multipart/form-data

audio: <audio file (WAV, MP3, etc.)>
enable_diarization: <true|false>
enable_emotion: <true|false>
enable_speaker_verification: <true|false>
```

Response:
```json
{
  "job_id": "uuid",
  "status": "completed",
  "text": "full transcription",
  "segments": [
    {
      "text": "segment text",
      "speaker": "SPEAKER_01",
      "verified_speaker": "john_doe",
      "start_time": 0.0,
      "end_time": 5.2,
      "emotion": "neutral",
      "emotion_confidence": 0.87,
      "audio_metrics": {
        "pitch_mean": 180.5,
        "energy_mean": 0.45,
        "speaking_rate": 2.8
      }
    }
  ],
  "audio_duration": 45.3,
  "processing_time": 2.1
}
```

### Pause Status
```bash
GET /pause/status
```

### Health Check
```bash
GET /health
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEMO_MODEL_NAME` | `nvidia/parakeet-rnnt-0.6b` | ASR model identifier |
| `TRANSCRIBE_STRATEGY` | `rnnt` | `rnnt` or `parakeet` |
| `TRANSCRIBE_USE_VAD` | `true` | Enable VAD preprocessing |
| `VAD_ONSET` | `0.6` | Speech start threshold |
| `VAD_OFFSET` | `0.4` | Speech end threshold |
| `ENABLE_PYANNOTE` | `true` | Use pyannote.audio for diarization |
| `DIARIZATION_SPK_MIN` | `1` | Minimum number of speakers |
| `DIARIZATION_SPK_MAX` | `3` | Maximum number of speakers |
| `ASR_BATCH_SIZE` | `2` | Batch size for ASR inference |
| `EMOTION_SERVICE_URL` | `http://emotion-service:8005` | Emotion analysis endpoint |
| `RAG_SERVICE_URL` | `http://rag-service:8004` | RAG indexing endpoint |
| `REDIS_URL` | `redis://redis:6379` | Redis for GPU coordination |

## Models Used

### ASR
- **nvidia/parakeet-rnnt-0.6b**: 600M parameter RNNT model
- **nvidia/parakeet-tdt-0.6b-v2**: 600M parameter TDT model

### Speaker Diarization
- **nvidia/speakerverification_en_titanet_large**: 23M parameter speaker embedding model
- **pyannote.audio 3.1.1**: Optional advanced diarization pipeline

### VAD
- **vad_multilingual_marblenet**: Lightweight multilingual VAD

## Performance

### GPU Memory Usage
- **RNNT Mode**: ~4-6GB VRAM
- **With Pyannote**: +2-3GB VRAM
- **Parakeet-TDT**: ~5-7GB VRAM

### Processing Speed
- Real-time factor: ~0.3-0.5x (processes 1 min audio in 20-30 seconds)
- Batch processing improves throughput significantly
- VAD preprocessing reduces compute on silence

## Dependencies

See `requirements.txt`. Key dependencies:
- **nemo_toolkit[all]** - NVIDIA NeMo for ASR
- **torch, torchaudio** - PyTorch framework
- **pyannote.audio** - Advanced diarization (optional)
- **librosa, soundfile** - Audio I/O
- **scikit-learn** - Clustering for diarization
- **redis** - GPU coordination
- **httpx** - Service communication

## Development

```bash
cd services/transcription-service
pip install -r requirements.txt
uvicorn src.main:app --reload --host 0.0.0.0 --port 8003
```

## Notes

- First run downloads models automatically (~2-3GB total)
- GPU recommended but CPU fallback available
- Supports various audio formats via ffmpeg
- Transcripts automatically indexed in RAG service
- Pause/resume adds <100ms latency to Gemma requests

Returns:
```json
{
  "paused": false,
  "current_processing": false,
  "queued_chunks": 0
}
```

## Environment Variables

- `REDIS_URL`: Redis connection URL (default: `redis://redis:6379`)
- `SERVICE_API_KEY`: Service authentication key

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Start service
uvicorn src.main:app --host 0.0.0.0 --port 8003
```

## Integration with GPU Coordinator

The service automatically:
1. Subscribes to `transcription_pause` and `transcription_resume` Redis channels
2. Acknowledges pause by publishing to `transcription_paused`
3. Queues chunks during pause
4. Processes queue on resume

No manual intervention required!







