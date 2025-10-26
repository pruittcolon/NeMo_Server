# Changelog

All notable changes to Nemo Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2025-10-26

### 🎉 Initial Release

First public release of Nemo Server - Enterprise AI Voice Intelligence Platform.

### Added

#### Core Features
- **Real-time transcription** using NVIDIA NeMo Parakeet-TDT-0.6B ASR model
- **Speaker diarization** with TitaNet embeddings and K-means clustering
- **Emotion analysis** using DistilRoBERTa (j-hartman/emotion-english-distilroberta-base)
- **Gemma 3 LLM integration** (4B parameter model, Q4_K_M quantization)
- **RAG system** with FAISS vector search and MiniLM embeddings
- **Speaker enrollment** for voice profile matching
- **TV detection** using acoustic feature analysis

#### Authentication & Security
- Session-based authentication with HTTP-only cookies
- Bcrypt password hashing for secure credential storage
- Role-based access control (Admin, User roles)
- **100% speaker-based data isolation** at SQL level
- Job ownership tracking for AI analysis tasks
- Rate limiting (100 requests/minute per IP)
- Security headers (X-Frame-Options, CSP, etc.)
- Configurable IP whitelist for Flutter app access

#### Frontend
- **7 HTML pages**: Login, Dashboard, Memories, Analysis, Gemma Chat, Emotions, Transcripts
- Glassmorphism design with gradient backgrounds
- Responsive layout for desktop and tablet
- Real-time updates via WebSocket
- Authentication integration with auto-redirect

#### Mobile Integration
- Flutter app support (EvenDemoApp)
- Real-time audio transcription from mobile device
- Voice enrollment from phone
- Gemma chat functionality
- Cross-platform (Android/iOS)

#### API Endpoints
- **24 protected API endpoints**:
  - 9 RAG/Memory endpoints (search, list, stats, analyze)
  - 7 Gemma AI endpoints (personality, triggers, chat, jobs)
  - 5 Transcription endpoints (list, search, analytics)
  - 3 Speaker enrollment endpoints (upload, list, stats)
  - 3 Authentication endpoints (login, logout, check)

#### Docker & Deployment
- Docker containerization with NVIDIA GPU support
- docker-compose configuration for easy deployment
- GPU optimization (ASR + Gemma on GPU, others on CPU)
- Volume mounts for persistent data
- Health check endpoint

#### Documentation
- Comprehensive README with quick start guide
- Speaker isolation documentation
- API documentation (OpenAPI/Swagger)
- Security policy
- Contributing guidelines
- Installation and configuration guides

#### Testing
- Security test suite (10 comprehensive tests)
- Speaker isolation verification tests
- Health check tests
- Smoke tests

### Technical Details

#### Models
- **ASR**: NVIDIA NeMo Parakeet-TDT-0.6B (~2GB VRAM)
- **LLM**: Gemma 3 4B Q4_K_M GGUF (~4GB VRAM)
- **Embeddings**: sentence-transformers/all-MiniLM-L6-v2
- **Emotion**: j-hartman/emotion-english-distilroberta-base
- **Speaker**: NVIDIA TitaNet

#### Dependencies
- FastAPI 0.110.3
- PyTorch 2.3.1
- NeMo Toolkit 2.5.1
- llama-cpp-python 0.2.90 (Note: 0.3.9 wheel required for Gemma 3)
- Transformers 4.53.0
- FAISS 1.8.0

#### Hardware Requirements
- **GPU**: NVIDIA GTX 1660 Ti (6GB VRAM) or equivalent
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 80GB+ for models and data
- **CPU**: 8+ cores recommended

### Security

- Default passwords included (⚠️ MUST CHANGE IN PRODUCTION)
- HTTP only (no HTTPS by default - configure reverse proxy for production)
- Database stored in plaintext (restrict file permissions)
- Designed for local network deployment

### Known Limitations

- No built-in HTTPS (requires reverse proxy)
- Database not encrypted at rest
- Limited to local network by default
- Default passwords must be changed for production
- Session tokens stored in memory (lost on restart)

### Breaking Changes

None (initial release)

---

## [Unreleased]

### Planned Features
- HTTPS support with Let's Encrypt integration
- Database encryption at rest
- Persistent session storage
- Multi-language support
- Improved diarization accuracy
- Real-time streaming transcription
- WebSocket for live updates
- Custom model support
- Backup and restore functionality
- Advanced analytics dashboard

---

## Version History

- **1.0.0** (2025-10-26) - Initial public release

---

## Links

- [GitHub Repository](https://github.com/YOUR_USERNAME/Nemo_Server)
- [Issue Tracker](https://github.com/YOUR_USERNAME/Nemo_Server/issues)
- [Documentation](./docs/)
- [Security Policy](./SECURITY.md)
- [Contributing](./CONTRIBUTING.md)

---

**Note**: This changelog is maintained manually. For a complete list of commits, see the [Git commit history](https://github.com/YOUR_USERNAME/Nemo_Server/commits/).

