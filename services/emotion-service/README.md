# Emotion Analysis Service

CPU-based emotion classification service using DistilRoBERTa transformer model for sentiment analysis of text.

## Overview

Provides emotion detection for transcribed text segments with:

- **6 Emotion Classes**: joy, sadness, anger, fear, surprise, neutral
- **Confidence Scores**: Per-class probability distribution
- **CPU-Only**: No GPU required, efficient inference
- **Batch Processing**: Handles multiple texts simultaneously
- **Fast Response**: <100ms per text segment

## Architecture

The service wraps a pre-trained emotion classification model in a FastAPI microservice.

```
Text Input
    ↓
Tokenization (RoBERTa tokenizer)
    ↓
Model Inference (DistilRoBERTa)
    ↓
Softmax → Emotion Probabilities
    ↓
Return Label + Scores
```

## API Endpoints

### Analyze Single Text
```bash
POST /analyze
Content-Type: application/json

{
  "text": "I'm so excited about this project!"
}
```

Response:
```json
{
  "emotion": "joy",
  "confidence": 0.94,
  "scores": {
    "joy": 0.94,
    "neutral": 0.03,
    "surprise": 0.02,
    "anger": 0.01,
    "fear": 0.00,
    "sadness": 0.00
  }
}
```

### Batch Analysis
```bash
POST /analyze/batch
Content-Type: application/json

{
  "texts": [
    "This is amazing!",
    "I'm feeling worried.",
    "The meeting went well."
  ]
}
```

### Health Check
```bash
GET /health
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_ONLY` | `false` | Enforce JWT service authentication |

## Model

- **Model**: `emotion-english-distilroberta-base`
- **Architecture**: DistilRoBERTa (distilled RoBERTa)
- **Parameters**: ~82M
- **Size**: ~330MB
- **Language**: English
- **Classes**: 6 emotions

## Dependencies

- **transformers**: Hugging Face transformers library
- **torch**: PyTorch for model inference
- **fastapi**: Web framework

## Usage

The emotion service is primarily called by the transcription service to enrich transcript segments with sentiment data.

Example integration:
```python
import httpx

result = httpx.post("http://emotion-service:8005/analyze", json={
    "text": "That was a great presentation!"
})
emotion_data = result.json()
# {"emotion": "joy", "confidence": 0.91, ...}
```
