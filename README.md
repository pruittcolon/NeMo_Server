Nemo Server — Enterprise AI Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-24.0%2B-blue)](https://www.docker.com/)
[![CUDA](https://img.shields.io/badge/CUDA-12.x-green)](https://developer.nvidia.com/cuda-downloads)

Executive Summary
- Modern, production‑oriented AI platform delivering LLM chat (Gemma), retrieval‑augmented generation (RAG), real‑time speech‑to‑text with diarization, emotion analysis, and analytics — unified behind a secure API Gateway with a web UI and a Flutter mobile client.
- Built as a microservice architecture with GPU‑aware scheduling, sealed internal network, strong secrets hygiene, and repeatable Docker workflows for local and production deployments.
- Emphasis on operational excellence: health checks everywhere, explicit dependencies, immutable containers, observability hooks, and security verification tests.

Engineering Highlights
- System design: Distributed LLM + RAG + ASR behind a single public gateway and sealed internal network.
- GPU orchestration: Dedicated coordinator arbitrates Gemma and Parakeet workloads with back‑pressure via Redis/Postgres.
- Production hardening: Docker secrets, JWT‑only S2S, rate limiting, read‑only containers, health checks, CI.
- Observability & ops: health endpoints across services, deterministic startup, scripts and runbooks for recovery and audits.
- Multi‑modal integration: LLM, ASR+diarization, emotion analysis, vector search; web UI and Flutter client.

Core Capabilities
- LLM chat and analysis (Gemma) with optional RAG context injection.
- Real‑time transcription (Parakeet) with diarization; integrates with Emotion + RAG.
- Vector search (FAISS) and encrypted auxiliary datasets (e.g., email analyzer).
- Emotion/sentiment classification for text streams and transcripts.
- Gateway‑level authentication/authorization, rate limiting, and CORS hygiene.
- Frontend web and Flutter mobile app for end‑to‑end workflows.

High‑Level Architecture
- Public edge: API Gateway (8000). All other services run on an internal Docker network.
- Infrastructure: Redis (caching/pubsub) and Postgres (coordination/queue), loopback‑bound for dev; never exposed in prod.
- GPU Coordinator: arbitrates GPU access for Gemma and Transcription; provides gating and back‑pressure.
- Gemma Service: LLM inference; consults the RAG service for retrieval.
- Transcription Service: Parakeet TDT transcription with diarization and model/runtime tuning.
- RAG Service: embeddings, FAISS index, encrypted auxiliary DB for the email analyzer.
- Emotion Service: text emotion analysis.
- Insights Service: analytics/aggregation on application data.
- Shared Library: cross‑cutting auth, security, analytics, logging, utils (Python).

Repository Layout
- `services/` — api-gateway, gemma-service, rag-service, transcription-service, emotion-service, insights-service, api-service, queue-service
- `frontend/` — static web UI served via the gateway in dev
- `EvenDemoApp-main/` — Flutter mobile client
- `shared/` — reusable packages (auth, security, analytics, logging, utils)
- `docker/` — Dockerfiles, Compose, secrets, and service instances
- `scripts/` — orchestration, verification, and operational tooling
- `models/` — local model files and caches
- `tests/` — smoke, integration, and security tests
- `logs/` — local startup and compose logs for troubleshooting (dev only)

Service Overview
- API Gateway (`services/api-gateway`) — single public surface (8000). Routing, authn/z, rate limiting, static asset serving, health checks.
- GPU Coordinator (`services/queue-service`) — internal. GPU scheduling and gating for model services.
- Gemma Service (`services/gemma-service`) — internal. LLM inference; integrates with RAG.
- Transcription Service (`services/transcription-service`) — internal. Parakeet‑based transcription and diarization; integrates with Emotion + RAG.
- RAG Service (`services/rag-service`) — internal. Embeddings + FAISS; encrypted auxiliary DB for email analyzer.
- Emotion Service (`services/emotion-service`) — internal. Text emotion analysis for transcripts and chat.
- Insights Service (`services/insights-service`) — internal. Analytics across RAG and events.

Security Posture (High‑Level)
- Network isolation: only the gateway is exposed; other services remain internal.
- Identity: JWT‑only inter‑service communication (`JWT_ONLY=true`), session keys isolated, rate limiting by default.
- Secrets: managed through Docker secrets under `docker/secrets/`; never committed to source control.
- Data protection: encrypted auxiliary databases (RAG/email) with keys managed as secrets.
- Container hardening: read‑only filesystems, tmpfs scratch, `no-new-privileges`, dropped Linux capabilities on the gateway.
- Verification: security tests under `tests/security/` and scripts such as `scripts/verify_security.py` and `scripts/security_hardening.py`.

Getting Started (Docker Compose)
Prerequisites
- Docker + Docker Compose
- NVIDIA Container Toolkit for GPU services (Gemma, Transcription)
- Python 3.10+ for local scripts

1) Prepare secrets and environment
- `bash docker/secrets/generate_secrets.sh`
- `cp docker/.env.example docker/.env`

2) Build and start services
- `docker compose -f docker/docker-compose.yml up -d --build`

3) Validate runtime
- `curl http://localhost:8000/health` → expect a healthy status
- `docker compose -f docker/docker-compose.yml ps` → check all services healthy

4) Run checks and tests
- Smoke tests: `./scripts/smoke_test.sh`
- Full test suite: `./scripts/run_tests.sh`
- Security checks: `pytest tests/security -q`

Configuration & Secrets Overview
- Secrets provided by Compose under `secrets:` (see `docker/docker-compose.yml`):
  - `jwt_secret`, `jwt_secret_primary`, `jwt_secret_previous`, `session_key`, `users_db_key`, `rag_db_key`, `email_db_key`, `postgres_user`, `postgres_password`, `huggingface_token`
- Do not commit `.env` or secret values. For dev, environment toggles are documented in each service’s README; common ones include:
  - `JWT_ONLY`, `ALLOWED_ORIGINS`, rate‑limit settings, model paths, FAISS index paths, `HF_HOME`

Local Development Notes
- Python services
  - Create a venv, install the service’s `requirements.txt`, run via `uvicorn` or `python src/main.py` as appropriate.
  - GPU‑backed services should prefer Docker to ensure consistent CUDA/cuDNN runtime.
- Frontend
  - The gateway serves `frontend/` for dev; open `http://localhost:8000/`.
- Flutter mobile
  - See `EvenDemoApp-main/README.md` and `EvenDemoApp-main/SETUP_GUIDE.md` for platform setup and environment wiring.

Operations & Observability
- Health endpoints: all services expose `/health`; the gateway exposes it publicly.
- Logs: `docker compose -f docker/docker-compose.yml logs -f` for runtime logs; dev startup bundles in `logs/`.
- Tools: `tools/log_viewer.py` for focused inspection; `scripts/restart_all_core_services.sh` for rolling restarts; `scripts/rebuild_rag_with_cache.sh` to refresh indices.
- Metrics/Tracing: hooks are present for standard Python logging and can be extended with Prometheus/OpenTelemetry in deployment environments.

Data & Model Governance
- Models reside under `models/`; large assets are mounted read‑only or pre‑fetched during Docker builds.
- RAG uses FAISS with embeddings (`sentence-transformers/all-MiniLM-L6-v2` by default); email analyzer DB is encrypted and keyed via Docker secrets.
- Document provenance and licensing for any model or dataset additions.
- Redaction and retention policies should be enforced at the gateway and storage layers for production deployments.

Performance & Scalability (Design Notes)
- GPU utilization is coordinated by an internal scheduler to avoid contention between Gemma and Transcription.
- Stateless services enable horizontal scaling behind the gateway; Redis/Postgres back service coordination.
- Batch sizes, context lengths, and caching strategies are configurable per service and environment.

Quality & Testing Strategy
- Unit, integration, and smoke tests are available under `tests/` with scripts for common flows.
- Security tests verify secrets hygiene and public surface boundaries.
- CI integrates linting, tests, and container builds (`.github/workflows/ci.yml`).

Release & Change Management
- Semantic versioning with release notes tracked in `CHANGELOG.md`.
- Backwards‑compatible API changes are preferred; breaking changes are versioned and documented with migration steps.
- Rollouts favor canary and staged deployments; health checks gate promotion.

Deployment Guidance (Production Baseline)
- Keep only the gateway public; remove dev host port mappings for infra services.
- Terminate TLS and enforce HSTS at the edge (reverse proxy or gateway).
- Rotate JWT and DB keys regularly; prefer a managed secret store in production.
- Enforce strict CORS, rate limits, and IP filtering for administrative endpoints.
- Use read‑only containers with tmpfs scratch and drop Linux capabilities; enable `no-new-privileges`.
- Centralize logs/metrics and configure alerts for health endpoints and error rates.

Troubleshooting
- Check service health and container state: `docker compose -f docker/docker-compose.yml ps`
- Inspect logs: `docker compose -f docker/docker-compose.yml logs <service>`
- Verify GPU availability with `nvidia-smi` inside a CUDA base image if model services fail to start.
- Rebuild RAG indices with `scripts/rebuild_rag_with_cache.sh` if retrieval looks empty.

Directory Structure (At a Glance)
```
Nemo_Server/
├─ services/
│  ├─ api-gateway/
│  ├─ transcription-service/
│  ├─ emotion-service/
│  ├─ gemma-service/
│  ├─ rag-service/
│  ├─ insights-service/
│  ├─ api-service/
│  └─ queue-service/
├─ shared/
├─ frontend/
├─ EvenDemoApp-main/
├─ docker/
├─ scripts/
├─ models/
├─ tests/
└─ logs/
```

Related Documentation
- Service READMEs under `services/*/README.md`
- Security overview: `SECURITY.md`
- CI pipeline: `.github/workflows/ci.yml`
- Selected deep dives:
  - `docs/GEMMA_ARCHITECTURE_AND_FIX.md`
  - `docs/EMAIL_GEMMA_INTEGRATION.md`
  - `docs/NEURAL_DIARIZER_RUNBOOK.md`
  - `docs/CLI_FULL_SYSTEM_TEST_PLAN.md`

License
- MIT — see `LICENSE` for the full text.

Contributing
- Please include tests for new features and a brief note on security implications (auth, data handling, network exposure) in PR descriptions.
- See `CONTRIBUTING.md` for the review process and coding standards.
