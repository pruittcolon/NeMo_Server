import logging
import os
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from shared.analytics import AnalyticsEngine
from shared.security.secrets import get_secret

logger = logging.getLogger("insights-service")

APP_ENV = os.getenv("APP_ENV", "local")
DB_PATH = os.getenv("INSIGHTS_DB_PATH", "/app/instance/rag.db")
try:
    DB_KEY = get_secret("rag_db_key")
    if DB_KEY:
        logger.info("[Insights] Loaded rag_db_key secret for analytics access")
    else:
        logger.warning("[Insights] rag_db_key secret not found; falling back to plaintext analytics DB")
except Exception as exc:
    DB_KEY = None
    logger.error("[Insights] Failed to load rag_db_key secret: %s", exc)

engine = AnalyticsEngine(DB_PATH, encryption_key=DB_KEY)
logger.info("[Insights] Starting in %s mode using DB %s", APP_ENV, DB_PATH)
if not engine.db_path.exists():
    logger.warning("[Insights] DB path %s does not exist", engine.db_path)

app = FastAPI(title="Insights Service", version="1.0.0")

# Allow internal calls; gateway enforces auth.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def healthcheck():
    return {
        "status": "ok",
        "env": APP_ENV,
        "db_path": str(engine.db_path),
        "db_exists": engine.db_path.exists(),
    }


@app.get("/analytics/signals", tags=["analytics"])
def analytics_signals(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    speakers: Optional[str] = Query(None, description="Comma-separated speaker list"),
    emotions: Optional[str] = Query(None, description="Comma-separated emotion list"),
    metrics: Optional[str] = Query(None, description="Comma-separated speech metrics"),
):
    speaker_list: Optional[List[str]] = (
        [s.strip() for s in speakers.split(",") if s.strip()] if speakers else None
    )
    emotion_list: Optional[List[str]] = (
        [e.strip() for e in emotions.split(",") if e.strip()] if emotions else None
    )
    metric_list: Optional[List[str]] = (
        [m.strip() for m in metrics.split(",") if m.strip()] if metrics else None
    )

    try:
        payload = engine.query_signals(
            start_date=start_date,
            end_date=end_date,
            speakers=speaker_list,
            emotions=emotion_list,
            metrics=metric_list,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("[Insights] analytics_signals failed")
        payload = engine.empty_payload(
            metrics=metric_list,
            fallback_reason="insights_error",
            error=str(exc),
        )
    if not payload.get("summary"):
        # Ensure frontend always receives a complete structure.
        payload = engine.empty_payload(
            metrics=metric_list,
            fallback_reason=payload.get("fallback_reason") or "insights_empty",
            error=str(payload.get("error")) if payload.get("error") else None,
        )
    return payload


@app.get("/analytics/segments", tags=["analytics"])
def analytics_segments(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    speakers: Optional[str] = Query(None, description="Comma-separated speaker list"),
    emotions: Optional[str] = Query(None, description="Comma-separated emotion list"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order: str = Query("desc"),
):
    speaker_list: Optional[List[str]] = (
        [s.strip() for s in speakers.split(",") if s.strip()] if speakers else None
    )
    emotion_list: Optional[List[str]] = (
        [e.strip() for e in emotions.split(",") if e.strip()] if emotions else None
    )

    try:
        payload = engine.query_segments(
            start_date=start_date,
            end_date=end_date,
            speakers=speaker_list,
            emotions=emotion_list,
            limit=limit,
            offset=offset,
            order=order,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("[Insights] analytics_segments failed")
        payload = {"items": [], "count": 0, "grouped_by_speaker": [], "error": str(exc)}
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8010")),
        reload=False,
    )
