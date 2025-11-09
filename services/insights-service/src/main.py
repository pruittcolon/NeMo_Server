import os
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from shared.analytics import AnalyticsEngine

APP_ENV = os.getenv("APP_ENV", "local")
DB_PATH = os.getenv("INSIGHTS_DB_PATH", "/app/instance/rag.db")

engine = AnalyticsEngine(DB_PATH)

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
    return {"status": "ok", "env": APP_ENV}


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

    payload = engine.query_signals(
        start_date=start_date,
        end_date=end_date,
        speakers=speaker_list,
        emotions=emotion_list,
        metrics=metric_list,
    )
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8010")),
        reload=False,
    )
