# Gemma Insights: Architecture, Failure Analysis, and Fixes

This document explains how the Gemma Insights feature is wired end‑to‑end, why “Run Streaming Analysis” failed to produce results, why “Quick Summary” could feel untethered from selected transcripts, and the targeted fixes implemented in this repo to address both.

## High‑Level Architecture

- Frontend (served by gateway at `/ui`)
  - Page: `frontend/gemma.html`
  - UI logic: `frontend/assets/js/gemma_analyzer_ui.js`
  - API client: `frontend/assets/js/api.js` (adds `/api` prefix, handles CSRF cookies)

- API Gateway: `services/api-gateway/src/main.py`
  - Proxies browser requests to services with short‑lived JWTs in `X-Service-Token`.
  - Auth & CSRF: validates session cookies; POST/PUT/DELETE require `X-CSRF-Token` matching cookie `ws_csrf`.
  - Security headers: strict CSP, HSTS (if enabled).
  - Frontend hosting: static site mounted at `/ui` with no‑cache headers.

- Gemma Service: `services/gemma-service/src/main.py`
  - Model lifecycle, warmup, generation.
  - Analyzer: `services/gemma-service/src/gemma_analyzer.py` builds prompts from transcript context.

- RAG Service: `services/rag-service/src/main.py`
  - Transcript storage + segment search.
  - Endpoints: `/transcripts/query` (segment‑level query + context), `/transcripts/recent` (fallback), `/analysis/*` (archive), etc.

## Data Flows

1) Streaming Analysis (before)
- UI POST: `/api/gemma/analyze/stream` → gateway returns `{ job_id }`.
- UI SSE: `/api/gemma/analyze/stream/{job_id}` → gateway fetches segments (RAG), prompts Gemma per segment, emits SSE events (`meta`, `step`, `result`, `done`).

2) Quick Summary (before)
- UI POST: `/api/gemma/analyze` → gateway → Gemma Analyzer → RAG `/transcripts/recent` (basic filtering) → build a single prompt → Gemma `/generate` → response.

## Observed Issues

- Streaming analysis “does not respond”
  - Symptom: Clicking “Run Streaming Analysis” produced `error`/disconnected state before any `meta/result` events.
  - Likely causes observed in code:
    - The gateway used an in‑memory `analysis_jobs` dict. If the POST and the SSE GET landed on different worker processes, the job wasn’t found (404), and the SSE immediately aborted. Even in single‑worker dev, brief restarts or hot‑reloads can exhibit this race.
    - The UI was tightly coupled to the job‑creation flow, making it fragile compared to a stateless SSE approach.

- Quick summary hallucination / not aligned with the selected filters
  - Symptom: “Quick Summary” felt generic and unmoored from the specific segments intended.
  - Root cause in `GemmaAnalyzer.fetch_transcripts`: it pulled `/transcripts/recent` and only applied coarse filtering (speaker/emotion/date). It ignored keyword/search‑type/context filters and did not leverage segment‑level context returned by `/transcripts/query`.

## Fixes Implemented

1) Robust Streaming: stateless SSE endpoint + UI switch

- New GET endpoint (API Gateway): `/api/gemma/analyze/stream/inline/start?payload=<base64>`
  - File: `services/api-gateway/src/main.py: gemma_analyze_stream_inline`
  - Accepts a base64‑encoded JSON payload identical to what the POST used:
    - `{ filters, custom_prompt, max_tokens, temperature, max_statements, analysis_id }`
  - Runs the same pipeline as the original SSE handler (GPU warmup → RAG `/transcripts/query` with fallback → per‑segment prompting → `done` summary).
  - No in‑memory job handoff, so it’s resilient to multi‑worker or hot‑reload scenarios.

- UI switched to stateless SSE
  - File: `frontend/assets/js/gemma_analyzer_ui.js`
  - `runStreamingAnalysis()` now encodes the payload and connects directly to:
    - `GET /api/gemma/analyze/stream/inline/start?payload=<encoded>&analysis_id=<id>`
  - Adds `encodePayload()` helper, mirroring the working email analyzer flow.

2) Accurate Quick Summary: RAG `/transcripts/query` + context aware formatting

- Gemma Analyzer now prefers segment‑level query:
  - File: `services/gemma-service/src/gemma_analyzer.py`
  - `fetch_transcripts()` calls RAG `/transcripts/query` with filters: `speakers, emotions, start_date, end_date, keywords, match, search_type, context_lines` and returns segment records.
  - Falls back to `/transcripts/recent` if `/query` is unavailable, applying basic client‑side filtering.
  - `format_transcripts_for_analysis()` includes context_before lines and preserves speaker/emotion metadata for clarity.
  - Uses model context size from `GEMMA_CONTEXT_SIZE` env (defaults to 2048) when trimming prompts.

## How It Works Now

- Streaming flow
  - UI builds payload from current filters + prompt.
  - Connects SSE to `/api/gemma/analyze/stream/inline/start?payload=...`.
  - Gateway fetches matching segments, prompts Gemma per segment, emits `meta/step/result` updates, and returns a `done` payload with a summary. Archive creation continues to work when available; a local artifact is created in the UI if remote archiving is down.

- Quick summary flow
  - UI POST `/api/gemma/analyze` unchanged.
  - Gemma service queries segment‑level data (same filters the UI shows), includes short context windows, assembles a compact transcript block, and generates a single, focused analysis with conservative prompt trimming.

## Relevant File References

- Frontend
  - `frontend/gemma.html`
  - `frontend/assets/js/gemma_analyzer_ui.js:1710` (streaming handler reworked)
  - `frontend/assets/js/api.js` (base URL + CSRF)

- Gateway
  - `services/api-gateway/src/main.py:869` (original SSE endpoint with job_id)
  - `services/api-gateway/src/main.py:...` (new `/api/gemma/analyze/stream` inline SSE)

- Gemma Service
  - `services/gemma-service/src/gemma_analyzer.py: __init__` (context window)
  - `services/gemma-service/src/gemma_analyzer.py: fetch_transcripts` (now uses `/transcripts/query`)
  - `services/gemma-service/src/gemma_analyzer.py: format_transcripts_for_analysis` (adds context_before)

- RAG Service
  - `services/rag-service/src/main.py:586` (`query_transcripts_filtered`)

## Validation Checklist

- Login and open `/ui/gemma.html`.
- Confirm GPU stats load (header).
- Set filters (speaker/emotions/keywords/dates) and run:
  - Streaming analysis → log shows `meta`, then `step` and `result` events, then `done` with summary.
  - Quick Summary → output references the selected filters and recent statements, not generic content.
- Optional: stop/start services; streaming should still connect because it no longer depends on a separate in‑memory job handoff.

## Notes and Additional Hardening

- CSP and hosting
  - Pages should be served from the gateway (`/ui`) so `connect-src 'self'` allows `fetch`/`EventSource` back to the same origin. Avoid opening `gemma.html` directly with `file://`, which would block connections by CSP.

- Multi‑worker deployments
  - The new inline SSE design removes the job handoff race across workers. If you prefer to keep the job pattern, back it with Redis (or another shared store) instead of a per‑process dict.

- CSRF
  - POSTs originate from `api.js` which includes the `X-CSRF-Token` header taken from the cookie (`ws_csrf`). SSE GET requests do not require CSRF and include the session cookie for auth.

## Summary

- Streaming failures were due to a brittle in‑memory job handoff. Switching to a stateless SSE endpoint fixes reliability without sacrificing features.
- Quick Summary now respects the same filters as the UI, pulling focused, segment‑level context from RAG. This anchors Gemma’s output to the actual selected transcripts and reduces the odds of generic or untethered analysis.
