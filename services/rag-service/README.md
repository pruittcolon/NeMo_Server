# RAG Service (Retrieval-Augmented Generation)

Semantic search service using FAISS vector database for indexing and querying transcripts and memories.

## Overview

Enables natural language queries across all stored conversations and notes:

- **Vector Search**: FAISS IndexFlatL2 for fast similarity search
- **Embeddings**: Sentence transformers (all-MiniLM-L6-v2)
- **Encrypted Storage**: SQLite with SQLCipher for metadata
- **Rich Metadata**: Speaker, emotion, audio metrics per segment
- **Multiple Doc Types**: Transcripts and user-created memories
- **Temporal Filtering**: Search by date range or last N transcripts

## Architecture

```
Text Query
    ↓
Embed Query (sentence-transformers)
    ↓
FAISS Vector Search → Top K Results
    ↓
Fetch Metadata from SQLite
    ↓
Apply Filters (date, speaker, emotion)
    ↓
Return Ranked Results
```

## Key Features

### 1. Semantic Search
- Query in natural language: "what did they say about deadlines?"
- Returns contextually relevant segments, not just keyword matches
- Cosine similarity scoring

### 2. Automatic Indexing
- Transcription service auto-indexes completed transcripts
- Each segment indexed separately with metadata
- Incremental updates (no full reindex needed)

### 3. Memory Management
- Store custom notes/memories
- Tag with metadata (tags, categories)
- Search across transcripts and memories together

### 4. Advanced Filtering
- **Temporal**: Last N transcripts, date ranges
- **Speaker**: Filter by specific speakers
- **Emotion**: Bias towards specific emotions
- **Doc Type**: Transcripts vs memories

## API Endpoints

### Semantic Search
```bash
POST /search
Content-Type: application/json

{
  "query": "what did sarah say about the wireless signal?",
  "top_k": 5,
  "speakers": ["sarah"],
  "start_date": "2025-01-01",
  "last_n_transcripts": 10
}
```

Response:
```json
{
  "results": [
    {
      "doc_id": "uuid",
      "doc_type": "transcript_segment",
      "text": "The wireless signal keeps dropping in the conference room",
      "speaker": "sarah",
      "score": 0.89,
      "metadata": {
        "timestamp": "2025-11-03T10:30:00",
        "emotion": "frustrated",
        "emotion_confidence": 0.82
      }
    }
  ],
  "total_results": 5,
  "query_embedding_time": 0.05,
  "search_time": 0.12
}
```

### Index Transcript
```bash
POST /index/transcript
Content-Type: application/json

{
  "job_id": "uuid",
  "session_id": "uuid",
  "full_text": "Complete transcript...",
  "audio_duration": 120.5,
  "segments": [
    {
      "text": "segment text",
      "speaker": "john",
      "start_time": 0.0,
      "end_time": 5.2,
      "emotion": "neutral",
      "audio_metrics": {...}
    }
  ]
}
```

### Add Memory
```bash
POST /memory/add
Content-Type: application/json

{
  "title": "Project Deadline",
  "body": "Final delivery is Nov 15th",
  "metadata": {"tags": ["deadline", "important"]}
}
```

### List Memories
```bash
GET /memory/list?limit=10&offset=0
```

### Health Check
```bash
GET /health
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `/app/instance/rag.db` | SQLite database path |
| `FAISS_INDEX_PATH` | `/app/faiss_index/index.bin` | FAISS index file |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `JWT_ONLY` | `false` | Enforce JWT authentication |

Secrets:
- `rag_db_key`: 32-byte encryption key for SQLite database

## Database Schema

### Documents Table
```sql
CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,  -- 'transcript_segment' or 'memory'
    text_content TEXT NOT NULL,
    embedding_id INTEGER NOT NULL,  -- Index into FAISS
    speaker TEXT,
    timestamp REAL,
    metadata TEXT,  -- JSON blob
    created_at REAL NOT NULL
);
```

### Sessions Table
```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    job_id TEXT,
    full_text TEXT,
    audio_duration REAL,
    created_at REAL NOT NULL
);
```

## Performance

- **Index Size**: ~384 bytes per document (embedding dimension)
- **Search Latency**: <50ms for 10K documents
- **Embedding Speed**: ~0.05s per query
- **Memory Usage**: ~400MB baseline + (384 bytes × num_docs)

## Dependencies

- **sentence-transformers**: Embedding generation
- **faiss-cpu**: Fast vector search
- **pysqlcipher3**: Encrypted SQLite
- **torch**: PyTorch for transformers
- **numpy**: Array operations

## Examples

### Search Recent Conversations
```python
import httpx

response = httpx.post("http://localhost:8004/search", json={
    "query": "budget discussions",
    "last_n_transcripts": 5,
    "top_k": 10
})

for result in response.json()["results"]:
    print(f"[{result['speaker']}]: {result['text']}")
    print(f"  Score: {result['score']:.2f}")
```

### Add Custom Memory
```python
response = httpx.post("http://localhost:8004/memory/add", json={
    "title": "Important Contact",
    "body": "John's email: john@example.com",
    "metadata": {"category": "contacts"}
})
memory_id = response.json()["memory_id"]
```
