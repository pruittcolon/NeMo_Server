# Email Analyzer × Gemma Integration

Status: Implemented end-to-end (gateway + UI). This doc explains the plan, changes, and how to verify with curl and in-browser tests.

## Goals

- Ask a question about selected/filterable emails and have Gemma answer.
- Keep existing RAG email dataset, filters, and table UI intact.
- Stream progress to the UI via SSE with stable lifecycle (no false error logs).
- Do not break `gemma.html` working routes.
- Keep the demo email dataset synthetic. `docker/simulated_email_db.sql` only contains fabricated content for local testing, and no real PII ever enters the prompts.

## What Changed

- Gateway added Gemma-backed email endpoints:
  - POST `/api/email/analyze/gemma/quick`
    - Body: `{ question: string (>=3), filters: object, max_emails?: number }`
    - Flow: Queries RAG for emails, builds a prompt, calls Gemma `/generate`, returns `{ success, summary, model, emails_used }`.
  - GET `/api/email/analyze/gemma/stream?payload=<b64>`
    - Payload: `{ prompt: string, filters: object, max_emails?: number, max_chunks?: number }`
    - Flow: Queries RAG for emails, analyzes each email with Gemma (map), then combines them (reduce) and streams SSE events:
      - `progress` — high-level steps
      - `note` — per‑email progress/notes
      - `summary` — final answer
      - `done` — includes an `artifact_id`

- Frontend wiring (email page):
  - `frontend/assets/js/email_analyzer_ui.js`
    - Quick Summary now calls `api.emailAnalyzeGemmaQuick()`.
    - Streaming now connects to `/api/email/analyze/gemma/stream?payload=...`.
    - Enforces min question length (>=3) to avoid backend 422s.
    - Keeps the improved EventSource lifecycle (prevents false error logs on normal close).
  - `frontend/assets/js/api.js`
    - Added `emailAnalyzeGemmaQuick(payload)` method.
  - `frontend/email.html`
    - Bumped script query versions to bust cache.

## Files Touched

- `services/api-gateway/src/main.py`
  - Added `/api/email/analyze/gemma/quick` and `/api/email/analyze/gemma/stream`.
  - Reused `_service_jwt_headers`, `proxy_request`, `format_sse`, and `_gemma_generate_with_fallback`.
- `frontend/assets/js/email_analyzer_ui.js`
  - Calls Gemma quick endpoint; streams from Gemma email SSE.
  - Improved UX messages for too-short questions.
- `frontend/assets/js/api.js`
  - New `emailAnalyzeGemmaQuick` client method.
- `frontend/email.html`
  - Version bump for cache-busting.

## SSE Behavior (What you should see)

- Opening the stream logs events like:
  - `progress`: "Collecting email snippets"
  - `note`: "Applying filters: {...}"
  - `note`: "Analyzed email 1/N", ...
  - `summary`: Final, reduced answer
  - `done`: `{ "artifact_id": "email-artifact-..." }`

Firefox note: SSE payloads do not appear in the Network → Response tab; use the “Messages” sub‑tab.

## How to Verify End-to-End

1) Warmup Gemma (from the Email page)
   - The GPU chip should read “GPU ready – model pinned” after warmup. If not, the app falls back to CPU and continues.

2) Quick Summary (non-streaming)
   - Enter a question of at least 3 characters, e.g. “customer sentiment”.
   - Click “Quick Summary”.
   - Expect a concise Gemma answer in the summary area and a “Quick summary completed” log line.

3) Streaming Summary
   - In “Ask with streaming”, enter a prompt like “evaluate customer complaints this week”.
   - Click “Start Stream”.
   - Expect `progress`/`note` events, then a final `summary` and a `done` event. No red “stream error” if the stream completes.

4) RAG dataset is used
   - Filters (users, labels, participants, dates, keywords) affect the emails Gemma sees.

## Curl / Debug Aids

- Test Gemma service directly (sanity):
  ```bash
  curl -s -X POST http://localhost:8000/api/gemma/generate \
    -H 'Content-Type: application/json' \
    --cookie "$(python3 - <<'PY' 2>/dev/null || true
import re,sys
from http.cookies import SimpleCookie
import os
# If your browser session cookie is available, paste it here for local tests
print('')
PY
)" \
    -d '{"prompt":"Say hello from Gemma","max_tokens":50}' | jq .
  ```

- Stream via browser: the page is authenticated and will use your session automatically. Open DevTools → Network → select the SSE request → Messages tab.

## “No Messages on Stream” Diagnostic

If you still see no messages while the request shows 200 OK:

- Confirm you are on the updated assets: `email_analyzer_ui.js?v=2024111201` in the page source.
- Use the Network → Messages sub‑tab in Firefox (Response tab won’t show SSE frames).
- Look for early `note` events (filters applied) and `progress` events (collection started). If not present:
  - Check gateway logs for `[EMAIL][GEMMA] stream requested ...` and any errors.
  - Verify RAG `/email/query` returns items via the table refresh (top panel).
  - Test `POST /api/gemma/generate` (above) to ensure Gemma responds.

## Limits & Safety Rails

- `max_emails` is clamped to 1–25.
- Email bodies are clipped to ~800 characters per email for prompts.
- Temperatures are conservative for predictable summaries.
- Question length is enforced on the client and again on the server for quick mode.

## Non-Goals / Preserved Behavior

- `gemma.html` routes remain untouched.
- Existing RAG email endpoints remain available: `/api/email/analyze/quick` and `/api/email/analyze/stream` (stub stream).

## Next Steps (Optional Enhancements)

- Surface per-email intermediate answers in the UI (e.g., a collapsible list as SSE `note` items).
- Persist artifacts from the final `summary` to the archive API for later “chat on artifact”.
- Add server-side pagination for the email table if datasets are large.

## Appendix: Architecture Summary

- UI → Gateway:
  - Quick: `/api/email/analyze/gemma/quick`
  - Stream: `/api/email/analyze/gemma/stream?payload=...`
- Gateway → RAG: `/email/query` for the selected filters.
- Gateway → Gemma: `/generate` (map stage for each email, reduce stage for the final answer).

This path ensures Gemma is only ever exposed via the gateway and that filters are applied centrally.
