"""FastAPI router that exposes temporary email analyzer stubs.
The goal is to provide end-to-end wiring for the new email.html UI while
backend ingestion/query work is still underway."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from .schemas import (
    EmailQueryRequest,
    EmailQuickAnalyzeRequest,
    EmailStreamRequest,
    EmailCancelRequest,
    EmailListResponse,
    EmailStatsResponse,
    EmailUsersResponse,
    EmailLabelsResponse,
    EmailSummary,
    EmailQueryFilters,
)
from .repository import repository

logger = logging.getLogger("gemma.email")

router = APIRouter(tags=["Email Analyzer"])


@router.get("/users", response_model=EmailUsersResponse)
async def list_email_users() -> EmailUsersResponse:
    items = repository.list_users()
    logger.info("[EMAIL] /users count=%s", len(items))
    return EmailUsersResponse(items=items, count=len(items))


@router.get("/labels", response_model=EmailLabelsResponse)
async def list_email_labels() -> EmailLabelsResponse:
    items = repository.list_labels()
    logger.info("[EMAIL] /labels count=%s", len(items))
    return EmailLabelsResponse(items=items, count=len(items))


@router.get("/stats", response_model=EmailStatsResponse)
async def get_email_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: Optional[str] = None,
    label: Optional[str] = None,
) -> EmailStatsResponse:
    filters = EmailQueryFilters(
        start_date=start_date,
        end_date=end_date,
        users=[user] if user else None,
        labels=[label] if label else None,
    )
    logger.info(
        "[EMAIL] /stats start=%s end=%s user=%s label=%s",
        start_date,
        end_date,
        user,
        label,
    )
    stats = repository.stats(filters)
    return EmailStatsResponse(
        totals={
            **stats["totals"],
            "window": {"start": start_date, "end": end_date},
            "selected_user": user,
            "selected_label": label,
        },
        by_day=stats["by_day"],
        top_senders=stats["top_senders"],
        top_threads=stats["top_threads"],
    )


@router.post("/query", response_model=EmailListResponse)
async def query_emails(request: EmailQueryRequest) -> EmailListResponse:
    logger.info(
        "[EMAIL] /query limit=%s offset=%s filters=%s",
        request.limit,
        request.offset,
        request.filters.dict(),
    )
    payload = repository.query_emails(request)
    return EmailListResponse(**payload)


@router.post("/analyze/quick", response_model=EmailSummary)
async def analyze_emails_quick(request: EmailQuickAnalyzeRequest) -> EmailSummary:
    logger.info(
        "[EMAIL] /analyze/quick question_len=%s",
        len(request.question),
    )
    summary = repository.quick_summary(request.filters, request.question)
    return EmailSummary(**summary)


def _decode_stream_payload(raw: Optional[str]) -> EmailStreamRequest:
    if not raw:
        raise HTTPException(status_code=400, detail="Missing payload parameter")
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        data = json.loads(decoded)
        return EmailStreamRequest(**data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid payload encoding: {exc}") from exc


@router.get("/analyze/stream")
async def analyze_emails_stream(payload: Optional[str] = Query(default=None)) -> StreamingResponse:
    request = _decode_stream_payload(payload)
    logger.info(
        "[EMAIL] /analyze/stream prompt_len=%s max_chunks=%s",
        len(request.prompt),
        request.max_chunks,
    )
    query_request = EmailQueryRequest(
        filters=request.filters,
        limit=request.max_chunks,
        offset=0,
        sort_by="date",
        order="desc",
    )
    query_payload = repository.query_emails(query_request)

    async def event_stream():
        top_subject = query_payload["items"][0]["subject"] if query_payload["items"] else "n/a"
        events = [
            ("progress", {"message": "Collecting email snippets"}),
            ("note", {"message": f"Applying filters: {request.filters.dict()}"}),
            (
                "summary",
                {
                    "message": (
                        f"Analyzed {query_payload['count']} emails for '{request.prompt[:40]}...'. "
                        f"Representative thread: {top_subject}."
                    )
                },
            ),
            ("done", {"artifact_id": f"email-artifact-{uuid.uuid4().hex[:8]}"}),
        ]
        for event, data in events:
            logger.info("[EMAIL] stream event=%s data_keys=%s", event, list(data.keys()))
            yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
            await asyncio.sleep(0.3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/analyze/cancel")
async def cancel_email_analysis(request: EmailCancelRequest) -> Dict[str, Any]:
    logger.info("[EMAIL] /analyze/cancel analysis_id=%s", request.analysis_id)
    return {
        "success": True,
        "analysis_id": request.analysis_id,
        "message": "Analysis cancellation acknowledged (no-op stub).",
    }
