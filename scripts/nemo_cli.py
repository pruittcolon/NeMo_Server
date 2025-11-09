#!/usr/bin/env python3
"""Human-operable CLI for Nemo Server.

Replicates every major UI feature:
- Authentication/session helpers
- Transcription via WAV uploads or typed transcripts (with speaker/timestamp metadata)
- Transcript search/count/detail
- Semantic + RAG queries
- Analysis archive/list/search/meta/chat
- Memories create/search/stats/emotion stats
- Emotion analysis
- Gemma warmup/stats/chat/analyzer (batch + stream)
- Speaker enrollment + listing
- Patterns mock output (matches UI placeholder)

All commands share --base-url/--username/--password/--verbose options.
By default credentials fall back to admin/admin123 (demo users).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests
import shlex
import subprocess
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

try:  # Only needed for typed transcript direct indexing
    from shared.security.service_auth import get_service_auth  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    get_service_auth = None

DEFAULT_GEMMA_PROMPT = (
    "Identify logical fallacies, hyperbolic language, and emotional manipulation in the provided statements. "
    "List findings with concise explanations."
)


class CLIError(RuntimeError):
    """Raised when an expected CLI operation cannot be completed."""


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


DEFAULT_START_SCRIPT = Path(_env("NEMO_START_SCRIPT", str(REPO_ROOT / "start.sh")))
DEFAULT_START_ARGS = _env("NEMO_START_ARGS", "--no-browser --no-logs")


def _read_text_file(path: Path) -> str:
    if not path.is_file():
        raise CLIError(f"Text file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def _prompt_multiline(prompt: str = "Enter text (finish with EOF / Ctrl+D):\n") -> str:
    print(prompt, end="", flush=True)
    buf: List[str] = []
    try:
        while True:
            line = input()
            buf.append(line)
    except EOFError:
        pass
    return "\n".join(buf).strip()


def _split_segments(text: str) -> List[str]:
    blocks: List[str] = []
    for paragraph in text.replace("\r", "").split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        blocks.extend([line.strip() for line in paragraph.split("\n") if line.strip()])
    if not blocks:
        blocks = [line.strip() for line in text.split('.') if line.strip()]
    return [b for b in blocks if b]


def _build_segments(text: str, speaker: str, seconds_per_segment: float = 8.0) -> Dict[str, Any]:
    chunks = _split_segments(text)
    segments: List[Dict[str, Any]] = []
    start = 0.0
    dur = max(seconds_per_segment, 1.0)
    for chunk in chunks:
        end = start + dur
        segments.append({
            "speaker": speaker,
            "text": chunk,
            "start_time": round(start, 2),
            "end_time": round(end, 2),
            "emotion": None,
        })
        start = end
    audio_duration = segments[-1]["end_time"] if segments else 0.0
    return {"segments": segments, "audio_duration": audio_duration, "full_text": "\n".join(chunks)}


def _now_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _pretty(data: Any) -> str:
    if isinstance(data, str):
        try:
            return json.dumps(json.loads(data), indent=2, ensure_ascii=False)
        except Exception:
            return data
    return json.dumps(data, indent=2, ensure_ascii=False)


def _gateway_healthy(base_url: str, timeout: float = 3.0) -> bool:
    url = f"{base_url.rstrip('/')}/health"
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _wait_for_gateway(base_url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _gateway_healthy(base_url, timeout=3.0):
            return True
        time.sleep(2)
    return False


def _ensure_stack_running(base_url: str, *, start_script: Path, start_args: Sequence[str], timeout: float) -> None:
    if _gateway_healthy(base_url):
        return
    if not start_script.exists():
        raise CLIError(f"start script not found: {start_script}")
    cmd = [str(start_script), *start_args]
    env = os.environ.copy()
    env.setdefault("RUN_POST_START_TESTS", "0")
    env.setdefault("EXIT_AFTER_START", "1")
    if os.environ.get("START_SH_DRIVEN") == "1":
        env["START_SH_DRIVEN"] = "1"
    print(f"[stack] launching {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, cwd=start_script.parent, env=env)
    except subprocess.CalledProcessError as exc:
        raise CLIError(f"start.sh failed with exit code {exc.returncode}") from exc
    if not _wait_for_gateway(base_url, timeout):
        raise CLIError("Gateway failed to become healthy after start.sh")


class NemoClient:
    def __init__(self, base_url: str, username: str, password: str, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verbose = verbose
        self.session = requests.Session()
        self._logged_in = False
        self._service_auth = None
        self._service_secret_path = Path(_env("JWT_SECRET_PATH", REPO_ROOT / "docker/secrets/jwt_secret"))

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _csrf_headers(self) -> Dict[str, str]:
        token = self.session.cookies.get("ws_csrf")
        if not token:
            return {}
        return {"X-CSRF-Token": token}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = kwargs.pop("headers", {})
        headers.update(self._csrf_headers())
        kwargs["headers"] = headers
        url = self._url(path)
        if self.verbose:
            print(f"→ {method.upper()} {url}")
        resp = self.session.request(method, url, timeout=120, **kwargs)
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = json.dumps(resp.json())
            except Exception:
                pass
            raise CLIError(f"{method.upper()} {url} failed ({resp.status_code}): {detail}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return {"raw": resp.text}

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        payload = {"username": self.username, "password": self.password, "remember_me": False}
        data = self._request("POST", "/api/auth/login", json=payload)
        if not data.get("success"):
            raise CLIError("Login failed")
        if self.verbose:
            print("Logged in as", data.get("user", {}).get("user_id"))
        self._logged_in = True

    def ensure_login(self) -> None:
        if not self._logged_in:
            self.login()

    def logout(self) -> Dict[str, Any]:
        self.ensure_login()
        result = self._request("POST", "/api/auth/logout", json={})
        self._logged_in = False
        return result

    def session_info(self) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", "/api/auth/session")

    def auth_check(self) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", "/api/auth/check")

    # ------------------------------------------------------------------
    # Transcription + transcripts
    # ------------------------------------------------------------------

    def transcribe(self, wav_path: Path) -> Dict[str, Any]:
        self.ensure_login()
        if not wav_path.is_file():
            raise CLIError(f"WAV file not found: {wav_path}")
        with wav_path.open("rb") as fh:
            files = {"file": (wav_path.name, fh, "audio/wav")}
            return self._request("POST", "/api/transcription/transcribe", files=files)

    def compose_transcript(self, *, text: str, speaker: str = "Speaker 1", seconds_per_segment: float = 8.0,
                           segments_override: Optional[Sequence[Dict[str, Any]]] = None,
                           job_id: Optional[str] = None, session_id: Optional[str] = None,
                           allow_direct: bool = True) -> Dict[str, Any]:
        self.ensure_login()
        if not text and not segments_override:
            raise CLIError("No transcript text provided")
        if segments_override is not None:
            segments = list(segments_override)
            audio_duration = segments[-1]["end_time"] if segments else 0.0
            full_text = "\n".join(seg.get("text", "") for seg in segments)
        else:
            built = _build_segments(text, speaker, seconds_per_segment)
            segments = built["segments"]
            audio_duration = built["audio_duration"]
            full_text = built["full_text"]
        payload = {
            "job_id": job_id or _now_id("cli-job"),
            "session_id": session_id or _now_id("cli-session"),
            "full_text": full_text,
            "audio_duration": audio_duration,
            "segments": segments,
        }
        return self._index_transcript_payload(payload, allow_direct=allow_direct)

    def list_transcripts(self, limit: int = 10) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", f"/api/transcripts/recent?limit={limit}")

    def transcripts_query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("POST", "/api/transcripts/query", json=payload)

    def transcripts_count(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("POST", "/api/transcripts/count", json=payload)

    def transcript_detail(self, job_id: str) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", f"/api/transcript/{job_id}")

    # ------------------------------------------------------------------
    # Analysis + memories + emotions
    # ------------------------------------------------------------------

    def archive(self, title: str, body: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"title": title, "body": body, "metadata": metadata or {}, "index_body": False}
        return self._request("POST", "/api/analysis/archive", json=payload)

    def list_analysis(self, limit: int = 5, offset: int = 0) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", f"/api/analysis/list?limit={limit}&offset={offset}")

    def analysis_search(self, query: str) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("POST", "/api/analysis/search", json={"query": query})

    def analysis_meta(self, artifact_id: str) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("POST", "/api/analysis/meta", json={"artifact_id": artifact_id})

    def analysis_chat(self, artifact_id: str, message: str, mode: str = "rag") -> Dict[str, Any]:
        self.ensure_login()
        payload = {"artifact_id": artifact_id, "message": message, "mode": mode}
        return self._request("POST", "/api/gemma/chat-on-artifact/v2", json=payload)

    def memory_create(self, title: str, body: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"title": title, "body": body, "metadata": metadata or {}}
        return self._request("POST", "/api/memory/create", json=payload)

    def memory_search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"query": query, "limit": limit}
        return self._request("POST", "/api/memory/search", json=payload)

    def memory_stats(self) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", "/api/memory/stats")

    def memory_emotion_stats(self) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", "/api/memory/emotions/stats")

    def emotion_analyze(self, text: str) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("POST", "/api/emotion/analyze", json={"text": text})

    # ------------------------------------------------------------------
    # Gemma operations
    # ------------------------------------------------------------------

    def gemma_generate(self, prompt: str, max_tokens: int = 200, temperature: float = 0.3) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
        return self._request("POST", "/api/gemma/generate", json=payload)

    def gemma_chat(self, message: str) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"messages": [{"role": "user", "content": message}], "max_tokens": 256, "temperature": 0.4}
        return self._request("POST", "/api/gemma/chat", json=payload)

    def gemma_chat_rag(self, message: str, context: str, max_tokens: int = 128) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"messages": [{"role": "user", "content": message}], "context": context, "max_tokens": max_tokens}
        return self._request("POST", "/api/gemma/chat-rag", json=payload)

    def gemma_warmup(self) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("POST", "/api/gemma/warmup", json={})

    def gemma_stats(self) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", "/api/gemma/stats")

    def gemma_analyze(self, statements: Sequence[str], prompt: str = DEFAULT_GEMMA_PROMPT,
                      filters: Optional[Dict[str, Any]] = None, max_tokens: int = 512,
                      temperature: float = 0.3) -> Dict[str, Any]:
        self.ensure_login()
        payload = {
            "statements": list(statements),
            "custom_prompt": prompt,
            "filters": filters or {},
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        return self._request("POST", "/api/gemma/analyze", json=payload)

    def gemma_analyze_stream(self, payload: Dict[str, Any], duration: float = 6.0) -> Dict[str, Any]:
        self.ensure_login()
        job = self._request("POST", "/api/gemma/analyze/stream", json=payload)
        job_id = job.get("job_id")
        if not job_id:
            raise CLIError("Stream job missing job_id")
        url = self._url(f"/api/gemma/analyze/stream/{job_id}")
        headers = self._csrf_headers()
        start = time.time()
        events: List[str] = []
        with self.session.get(url, headers=headers, stream=True, timeout=duration + 5) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                events.append(line)
                if time.time() - start >= duration:
                    break
        return {"job_id": job_id, "events": events}

    # ------------------------------------------------------------------
    # Search utilities
    # ------------------------------------------------------------------

    def semantic_search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"query": query, "top_k": top_k}
        return self._request("POST", "/api/search/semantic", json=payload)

    def rag_query(self, question: str) -> Dict[str, Any]:
        self.ensure_login()
        payload = {"query": question}
        return self._request("POST", "/api/rag/query", json=payload)

    # ------------------------------------------------------------------
    # Speakers & patterns
    # ------------------------------------------------------------------

    def speakers_list(self) -> Dict[str, Any]:
        self.ensure_login()
        return self._request("GET", "/api/enroll/speakers")

    def enroll_speaker(self, wav_path: Path, speaker: str) -> Dict[str, Any]:
        self.ensure_login()
        if not wav_path.is_file():
            raise CLIError(f"WAV file not found: {wav_path}")
        with wav_path.open("rb") as fh:
            files = {"audio": (wav_path.name, fh, "audio/wav")}
            data = {"speaker": speaker}
            return self._request("POST", "/api/enroll/upload", files=files, data=data)

    def get_patterns(self, period: str = "today") -> Dict[str, Any]:
        self.ensure_login()
        path = f"/api/analyze/patterns?time_period={period}"
        try:
            return self._request("GET", path)
        except CLIError as exc:
            # Endpoint absent in current backend; return deterministic mock
            return {
                "success": False,
                "detail": str(exc),
                "mock": {
                    "period": period,
                    "total_patterns": 3,
                    "peak_hour": 10,
                    "avg_words": 42,
                    "patterns": [
                        {"type": "Topic", "description": "Compliance mentioned 12x more than average", "confidence": 0.92},
                        {"type": "Speech", "description": "Speaker 1 positive tone in mornings", "confidence": 0.87},
                        {"type": "Length", "description": "Friday calls last 3.5 minutes longer", "confidence": 0.78},
                    ],
                },
            }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def import_wavs(self, directory: Path, recursive: bool = False) -> Dict[str, Any]:
        self.ensure_login()
        if not directory.exists():
            raise CLIError(f"Directory not found: {directory}")
        wavs = []
        if directory.is_file() and directory.suffix.lower() == ".wav":
            wavs = [directory]
        else:
            iterator: Iterable[Path]
            iterator = directory.rglob("*.wav") if recursive else directory.glob("*.wav")
            wavs = sorted(p for p in iterator if p.is_file())
        results = []
        for wav in wavs:
            try:
                results.append({"file": str(wav), "result": self.transcribe(wav)})
            except Exception as exc:  # pragma: no cover - network failures
                results.append({"file": str(wav), "error": str(exc)})
        return {"count": len(results), "items": results}

    def full_run(self, wav_path: Path, title: str, question: str) -> Dict[str, Any]:
        tx = self.transcribe(wav_path)
        text = tx.get("text") or "\n".join(seg.get("text", "") for seg in tx.get("segments", []))
        if not text:
            text = f"[no text returned for {wav_path.name}]"
        artifact = self.archive(title=title, body=text, metadata={"source": "cli_full_run"})
        artifacts = self.list_analysis(limit=5)
        gemma = self.gemma_chat(question)
        return {
            "transcription": tx,
            "archive": artifact,
            "analysis_list": artifacts,
            "gemma_chat": gemma,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _index_transcript_payload(self, payload: Dict[str, Any], allow_direct: bool = True) -> Dict[str, Any]:
        if allow_direct:
            try:
                direct = self._post_rag_direct("/index/transcript", payload)
                return {"success": True, "mode": "rag", "response": direct}
            except CLIError as exc:
                if self.verbose:
                    print(f"[RAG] Direct indexing failed: {exc}. Falling back to artifact + memory.")
        title = f"Transcript {payload['job_id']}"
        body = payload.get("full_text", "")
        metadata = {"source": "cli_composed", "job_id": payload.get("job_id"), "session_id": payload.get("session_id")}
        artifact = self.archive(title=title, body=body, metadata=metadata)
        memory = self.memory_create(title=title, body=body, metadata=metadata)
        return {"success": False, "mode": "fallback", "artifact": artifact, "memory": memory}

    def _post_rag_direct(self, path: str, payload: Dict[str, Any]) -> Any:
        rag_url = _env("RAG_DIRECT_URL", "http://localhost:8004").rstrip("/")
        if os.environ.get("ALLOW_RAG_INDEX", "0") != "1":
            raise CLIError("Direct RAG indexing disabled (set ALLOW_RAG_INDEX=1)")
        if not get_service_auth:
            raise CLIError("shared.security.service_auth unavailable")
        if not self._service_secret_path.is_file():
            raise CLIError(f"JWT secret not found: {self._service_secret_path}")
        secret = self._service_secret_path.read_text(encoding="utf-8").strip()
        if not secret:
            raise CLIError("JWT secret file is empty")
        if self._service_auth is None:
            self._service_auth = get_service_auth("gateway-cli", secret)
        token = self._service_auth.create_token(expires_in=60, aud="internal")
        url = f"{rag_url}{path}"
        if self.verbose:
            print(f"→ POST {url} (direct RAG)")
        resp = requests.post(url, json=payload, headers={"X-Service-Token": token}, timeout=30)
        if resp.status_code >= 400:
            raise CLIError(f"Direct RAG {url} failed ({resp.status_code}): {resp.text}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text


# ----------------------------------------------------------------------
# CLI parsing
# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nemo Server CLI (UI parity)")
    parser.add_argument("--base-url", default=_env("NEMO_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--username", default=_env("NEMO_USERNAME", "admin"))
    parser.add_argument("--password", default=_env("NEMO_PASSWORD", "admin123"))
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--auto-start", dest="auto_start", action="store_true", default=True,
                        help="Automatically run start.sh if the gateway is unreachable (default: enabled)")
    parser.add_argument("--no-auto-start", dest="auto_start", action="store_false",
                        help="Disable automatic start.sh invocation")
    parser.add_argument("--start-script", default=str(DEFAULT_START_SCRIPT),
                        help="Path to start.sh (default: repo start.sh)")
    parser.add_argument("--start-arg", action="append", dest="start_args",
                        help="Extra argument to pass to start.sh (can be repeated)")
    parser.add_argument("--stack-timeout", type=int, default=int(_env("STACK_READY_TIMEOUT", "420")),
                        help="Seconds to wait for the gateway to become healthy after auto-start")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth-info", help="Show auth session + check")
    sub.add_parser("auth-logout", help="Logout current session")

    p_trans = sub.add_parser("transcribe", help="Upload WAV for transcription")
    p_trans.add_argument("--file", required=True, type=Path)

    p_comp = sub.add_parser("compose-transcript", help="Insert typed transcript with speaker/timestamps")
    p_comp.add_argument("--text")
    p_comp.add_argument("--text-file", type=Path)
    p_comp.add_argument("--speaker", default="Speaker 1")
    p_comp.add_argument("--segment-seconds", type=float, default=8.0)
    p_comp.add_argument("--segments-json", type=Path, help="JSON file with segments array")
    p_comp.add_argument("--job-id")
    p_comp.add_argument("--session-id")
    p_comp.add_argument("--interactive", action="store_true", help="Prompt for text via stdin")
    p_comp.add_argument("--force-fallback", action="store_true", help="Skip direct RAG indexing")

    p_list_tx = sub.add_parser("list-transcripts", help="List recent transcripts")
    p_list_tx.add_argument("--limit", type=int, default=5)

    p_tx_detail = sub.add_parser("transcript", help="Show transcript detail")
    p_tx_detail.add_argument("--job-id", required=True)

    p_tx_search = sub.add_parser("search-transcripts", help="Query transcript segments")
    p_tx_search.add_argument("--limit", type=int, default=5)
    p_tx_search.add_argument("--keywords", default="")
    p_tx_search.add_argument("--emotions")
    p_tx_search.add_argument("--speakers")
    p_tx_search.add_argument("--last-days", type=int)

    p_tx_count = sub.add_parser("transcripts-count", help="Count transcripts matching filters")
    p_tx_count.add_argument("--keywords", default="")
    p_tx_count.add_argument("--emotions")
    p_tx_count.add_argument("--speakers")
    p_tx_count.add_argument("--last-days", type=int)

    p_archive = sub.add_parser("archive", help="Archive analysis text")
    p_archive.add_argument("--title", required=True)
    p_archive.add_argument("--body", required=True)

    p_list_analysis = sub.add_parser("list-analysis", help="List analysis artifacts")
    p_list_analysis.add_argument("--limit", type=int, default=5)
    p_list_analysis.add_argument("--offset", type=int, default=0)

    p_analysis_search = sub.add_parser("analysis-search", help="Search analysis artifacts")
    p_analysis_search.add_argument("--query", required=True)

    p_analysis_meta = sub.add_parser("analysis-meta", help="Get artifact metadata")
    p_analysis_meta.add_argument("--artifact-id", required=True)

    p_analysis_chat = sub.add_parser("analysis-chat", help="Chat on artifact (Gemma)")
    p_analysis_chat.add_argument("--artifact-id", required=True)
    p_analysis_chat.add_argument("--message", required=True)
    p_analysis_chat.add_argument("--mode", default="rag")

    p_chat = sub.add_parser("chat", help="Gemma chat")
    p_chat.add_argument("--message", required=True)

    p_gen = sub.add_parser("gemma-generate", help="Gemma generate raw prompt")
    p_gen.add_argument("--prompt", required=True)
    p_gen.add_argument("--max-tokens", type=int, default=200)

    sub.add_parser("gemma-warmup", help="Warm up Gemma GPU")
    sub.add_parser("gemma-stats", help="Show Gemma stats")

    p_an = sub.add_parser("gemma-analyze", help="Run Gemma analyzer")
    p_an.add_argument("--statements", nargs="*", help="Statements to analyze")
    p_an.add_argument("--prompt", default=DEFAULT_GEMMA_PROMPT)
    p_an.add_argument("--days", type=int, help="Filter last N days")
    p_an.add_argument("--emotions")
    p_an.add_argument("--keywords")
    p_an.add_argument("--prev-lines", type=int)
    p_an.add_argument("--limit", type=int)

    p_an_stream = sub.add_parser("gemma-analyze-stream", help="Create stream job and tail events")
    p_an_stream.add_argument("--prompt", default="Stream analysis")
    p_an_stream.add_argument("--statements", nargs="*", default=["Provide an update.", "Highlight risks."])
    p_an_stream.add_argument("--duration", type=float, default=6.0)

    p_sem = sub.add_parser("semantic", help="Semantic search")
    p_sem.add_argument("--query", required=True)
    p_sem.add_argument("--top-k", type=int, default=5)

    p_rag = sub.add_parser("rag-query", help="Ask RAG service a question")
    p_rag.add_argument("--question", required=True)

    p_mem_c = sub.add_parser("memory-create", help="Create memory")
    p_mem_c.add_argument("--title", required=True)
    p_mem_c.add_argument("--body", required=True)

    p_mem_s = sub.add_parser("memory-search", help="Search memories")
    p_mem_s.add_argument("--query", required=True)
    p_mem_s.add_argument("--limit", type=int, default=5)

    sub.add_parser("memory-stats", help="Memory stats")
    sub.add_parser("memory-emotions", help="Memory emotion stats")

    p_emote = sub.add_parser("emotion-analyze", help="Analyze text for emotion")
    p_emote.add_argument("--text", required=True)

    p_speakers = sub.add_parser("speakers-list", help="List enrolled speakers")
    p_speakers.add_argument("--limit", type=int, default=50)

    p_enroll = sub.add_parser("enroll-upload", help="Enroll a speaker")
    p_enroll.add_argument("--file", required=True, type=Path)
    p_enroll.add_argument("--speaker", required=True)

    p_patterns = sub.add_parser("patterns", help="Show communication patterns (mock if endpoint absent)")
    p_patterns.add_argument("--period", default="today")

    p_import = sub.add_parser("import-wavs", help="Batch transcribe WAV files")
    p_import.add_argument("--path", required=True, type=Path)
    p_import.add_argument("--recursive", action="store_true")

    p_full = sub.add_parser("full-run", help="Transcribe → archive → list → chat")
    p_full.add_argument("--file", required=True, type=Path)
    p_full.add_argument("--title", required=True)
    p_full.add_argument("--question", default="Summarize the archived content.")

    return parser


def build_filters_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"limit": getattr(args, "limit", 5), "match": "any"}
    if getattr(args, "keywords", None):
        payload["keywords"] = args.keywords
    if getattr(args, "emotions", None):
        payload["emotions"] = [e.strip() for e in args.emotions.split(',') if e.strip()]
    if getattr(args, "speakers", None):
        payload["speakers"] = [s.strip() for s in args.speakers.split(',') if s.strip()]
    if getattr(args, "last_days", None) is not None:
        payload["last_days"] = int(args.last_days)
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    start_script = Path(args.start_script).resolve()
    default_start_args = shlex.split(DEFAULT_START_ARGS) if DEFAULT_START_ARGS else []
    start_args = args.start_args if args.start_args is not None else default_start_args
    if args.auto_start:
        _ensure_stack_running(args.base_url, start_script=start_script, start_args=start_args, timeout=float(args.stack_timeout))

    client = NemoClient(args.base_url, args.username, args.password, verbose=args.verbose)

    try:
        cmd = args.command
        if cmd == "auth-info":
            result = {"session": client.session_info(), "auth_check": client.auth_check()}
        elif cmd == "auth-logout":
            result = client.logout()
        elif cmd == "transcribe":
            result = client.transcribe(args.file)
        elif cmd == "compose-transcript":
            text = args.text or ""
            if args.text_file:
                text = "\n".join(filter(None, [text, _read_text_file(args.text_file)])).strip()
            if args.interactive:
                text = "\n".join(filter(None, [text, _prompt_multiline()])).strip()
            segments_override = None
            if args.segments_json:
                payload = json.loads(args.segments_json.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and "segments" in payload:
                    segments_override = payload["segments"]
                elif isinstance(payload, list):
                    segments_override = payload
                else:
                    raise CLIError("segments-json must contain a list or {segments: [...]}")
            allow_direct = not args.force_fallback
            result = client.compose_transcript(
                text=text,
                speaker=args.speaker,
                seconds_per_segment=args.segment_seconds,
                segments_override=segments_override,
                job_id=args.job_id,
                session_id=args.session_id,
                allow_direct=allow_direct,
            )
        elif cmd == "list-transcripts":
            result = client.list_transcripts(limit=args.limit)
        elif cmd == "transcript":
            result = client.transcript_detail(args.job_id)
        elif cmd == "search-transcripts":
            payload = build_filters_from_args(args)
            result = client.transcripts_query(payload)
        elif cmd == "transcripts-count":
            payload = build_filters_from_args(args)
            result = client.transcripts_count(payload)
        elif cmd == "archive":
            result = client.archive(args.title, args.body)
        elif cmd == "list-analysis":
            result = client.list_analysis(limit=args.limit, offset=args.offset)
        elif cmd == "analysis-search":
            result = client.analysis_search(args.query)
        elif cmd == "analysis-meta":
            result = client.analysis_meta(args.artifact_id)
        elif cmd == "analysis-chat":
            result = client.analysis_chat(args.artifact_id, args.message, mode=args.mode)
        elif cmd == "chat":
            result = client.gemma_chat(args.message)
        elif cmd == "gemma-generate":
            result = client.gemma_generate(args.prompt, max_tokens=args.max_tokens)
        elif cmd == "gemma-warmup":
            result = client.gemma_warmup()
        elif cmd == "gemma-stats":
            result = client.gemma_stats()
        elif cmd == "gemma-analyze":
            statements = args.statements or ["This is absolutely the greatest!", "Maybe this is not ideal."]
            filters: Dict[str, Any] = {}
            if args.days is not None:
                filters["last_days"] = args.days
            if args.emotions:
                filters["emotions"] = [e.strip() for e in args.emotions.split(',') if e.strip()]
            if args.keywords:
                filters["keywords"] = args.keywords
            if args.prev_lines is not None:
                filters["context_lines"] = args.prev_lines
            if args.limit is not None:
                filters["limit"] = args.limit
            result = client.gemma_analyze(statements, prompt=args.prompt, filters=filters)
        elif cmd == "gemma-analyze-stream":
            payload = {"analysis_id": _now_id("cli-anl"), "statements": args.statements, "custom_prompt": args.prompt, "filters": {}}
            result = client.gemma_analyze_stream(payload, duration=args.duration)
        elif cmd == "semantic":
            result = client.semantic_search(args.query, top_k=args.top_k)
        elif cmd == "rag-query":
            result = client.rag_query(args.question)
        elif cmd == "memory-create":
            result = client.memory_create(args.title, args.body)
        elif cmd == "memory-search":
            result = client.memory_search(args.query, limit=args.limit)
        elif cmd == "memory-stats":
            result = client.memory_stats()
        elif cmd == "memory-emotions":
            result = client.memory_emotion_stats()
        elif cmd == "emotion-analyze":
            result = client.emotion_analyze(args.text)
        elif cmd == "speakers-list":
            result = client.speakers_list()
        elif cmd == "enroll-upload":
            result = client.enroll_speaker(args.file, args.speaker)
        elif cmd == "patterns":
            result = client.get_patterns(args.period)
        elif cmd == "import-wavs":
            result = client.import_wavs(args.path, recursive=args.recursive)
        elif cmd == "full-run":
            result = client.full_run(args.file, args.title, args.question)
        else:  # pragma: no cover - argparse enforces
            parser.error(f"Unknown command {cmd}")
            return 1
    except CLIError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(_pretty(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
