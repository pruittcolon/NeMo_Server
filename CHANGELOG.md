# Changelog

All notable changes to Nemo Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2025-11-03

### 🎉 Major Release - Microservices Architecture

Complete rewrite of Nemo Server as a microservices-based system with GPU coordination, enhanced security, and RAG-powered AI responses.

### Added

#### Architecture
- **Microservices Architecture**: Split monolithic application into 6 independent services
- **GPU Coordinator**: Intelligent GPU sharing between Transcription and Gemma services
- **Service Authentication**: JWT-based service-to-service authentication
- **Docker Compose Orchestration**: Full containerized deployment

#### Services
- **API Gateway** (Port 8000): Authentication, routing, frontend serving
- **Transcription Service** (Port 8003): NVIDIA NeMo ASR with speaker diarization
- **Emotion Service** (Port 8005): Sentiment analysis using DistilRoBERTa
- **RAG Service** (Port 8004): FAISS vector search for semantic memory
- **Gemma AI Service** (Port 8001): LLM inference with 64K context window
- **GPU Coordinator** (Port 8002): Task queue and GPU lock management

#### Features
- **Speaker Diarization**: Automatic multi-speaker detection and labeling
- **Speaker Verification**: Match speakers against enrolled voice profiles
- **Emotion Analysis**: Per-segment sentiment classification (6 emotions)
- **Semantic Search**: Natural language queries across all conversations
- **RAG-Enhanced AI**: Automatic context injection from memories
- **Voice Activity Detection**: Intelligent speech segmentation
- **Audio Quality Metrics**: Pitch, energy, speaking rate extraction
- **Streaming Responses**: Token-by-token AI response streaming
- **Long Context Support**: 64K token context window for Gemma

#### Security
- **Encrypted Storage**: SQLCipher for user data and transcripts
- **Docker Secrets**: Secure credential management
- **Session Management**: Encrypted cookie-based sessions
- **Replay Protection**: Request ID tracking for service calls
- **Rate Limiting**: Login attempt throttling
- **CORS Configuration**: Configurable allowed origins

#### Infrastructure
- **Redis**: Pub/sub for GPU coordination, caching, distributed locking
- **PostgreSQL**: Persistent task queue storage
- **FAISS**: Vector database for semantic search
- **NVIDIA CUDA**: GPU acceleration for ASR and LLM

#### Documentation
- Comprehensive README with architecture diagrams
- Service-specific documentation for all microservices
- API examples and configuration guides
- Docker secrets setup documentation
- Contributing guidelines and code of conduct

### Changed
- **GPU Usage**: Dynamic GPU sharing instead of exclusive ownership
- **Database**: Separate encrypted databases per service
- **Configuration**: Environment-based with Docker secrets
- **Deployment**: Docker Compose instead of standalone Python

### Technical Details

#### Models
- **ASR**: NVIDIA Parakeet RNNT 0.6B
- **Speaker Embeddings**: TitaNet Large
- **Diarization**: Pyannote.audio 3.1.1 (optional)
- **Emotion**: DistilRoBERTa-base
- **Embeddings**: all-MiniLM-L6-v2
- **LLM**: Gemma 3 4B Instruct (Q4_K_XL quantization)

#### Performance
- Real-time transcription factor: ~0.3-0.5x
- GPU memory: 8-12GB VRAM recommended
- LLM inference: ~20-30 tokens/second on GPU
- Semantic search: <50ms for 10K documents

### Migration Notes

This is a breaking change from v1.x. The architecture has been completely redesigned.

**Key differences from v1.x:**
- Microservices instead of monolithic Flask app
- GPU coordination for shared GPU usage
- Separate databases per service
- Docker-first deployment
- Enhanced security model
- New API endpoints

For migration assistance, see [MIGRATION.md](MIGRATION.md) (coming soon).

### Dependencies

- Docker 24.0+
- Docker Compose
- NVIDIA GPU with CUDA 12.6+
- Python 3.12 (in containers)
- 16GB+ RAM recommended
- 8GB+ VRAM recommended

---

## [1.x] - Legacy

Previous monolithic architecture. See `v1.x-legacy` branch for details.

### Note on Version History

This CHANGELOG starts with v2.0.0. For pre-v2.0 changes, refer to git history in the `v1.x-legacy` branch.

---

## Unreleased

### Planned Features
- Multi-language support for transcription
- Video processing capabilities
- Advanced analytics dashboard
- WebSocket support for real-time updates
- Mobile app integration improvements
- Custom model fine-tuning tools

---

## How to Read This Changelog

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security updates

---

[2.0.0]: https://github.com/pruittcolon/NeMo_Server/releases/tag/v2.0.0
[1.x]: https://github.com/pruittcolon/NeMo_Server/tree/v1.x-legacy
