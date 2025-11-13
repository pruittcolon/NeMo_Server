"""Query helpers for the encrypted email database."""
from __future__ import annotations

import logging
import sqlite3
from typing import List, Dict, Any, Tuple

from .schemas import EmailQueryRequest, EmailQueryFilters
from .db import get_connection


LOGGER = logging.getLogger("gemma.email.repository")


def _split_csv(value: str | None) -> List[str]:
    if not value:
        return []
    return [chunk.strip() for chunk in value.split(',') if chunk.strip()]


def _row_value(row: sqlite3.Row | Dict[str, Any] | Tuple[Any, ...] | None, *keys: str) -> Any:
    if row is None:
        return None
    if isinstance(row, tuple):
        return row[0] if row else None
    if isinstance(row, sqlite3.Row):
        for key in keys:
            if key in row.keys():
                return row[key]
    if isinstance(row, dict):
        for key in keys:
            if key in row:
                return row[key]
    return None


def _build_where(filters: EmailQueryFilters) -> Tuple[str, Dict[str, Any]]:
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    if filters.users:
        placeholders = []
        for idx, email in enumerate(filters.users):
            key = f"user_{idx}"
            params[key] = email.lower()
            placeholders.append(f":{key}")
        clauses.append(f"LOWER(sender) IN ({', '.join(placeholders)})")

    if filters.participants:
        participant_clauses = []
        for idx, participant in enumerate(filters.participants):
            key = f"part_{idx}"
            params[key] = participant.lower()
            participant_clauses.append(
                f"LOWER(sender) = :{key} OR LOWER(recipient) LIKE '%' || :{key} || '%'"
            )
        if participant_clauses:
            clauses.append("(" + " OR ".join(participant_clauses) + ")")

    if filters.start_date:
        clauses.append("date >= :start_date")
        params["start_date"] = filters.start_date
    if filters.end_date:
        clauses.append("date <= :end_date")
        params["end_date"] = filters.end_date

    keywords = []
    if filters.keywords:
        keywords = [token.strip().lower() for token in filters.keywords.split(',') if token.strip()]

    if keywords:
        if (filters.match or "any") == "all":
            for idx, keyword in enumerate(keywords):
                key = f"kw_{idx}"
                params[key] = f"%{keyword}%"
                clauses.append(
                    f"(LOWER(subject) LIKE :{key} OR LOWER(body) LIKE :{key})"
                )
        else:
            sub = []
            for idx, keyword in enumerate(keywords):
                key = f"kw_{idx}"
                params[key] = f"%{keyword}%"
                sub.append(f"(LOWER(subject) LIKE :{key} OR LOWER(body) LIKE :{key})")
            clauses.append("(" + " OR ".join(sub) + ")")

    if filters.labels:
        for idx, label in enumerate(filters.labels):
            key = f"label_{idx}"
            params[key] = f"%,{label.lower()},%"
            clauses.append("(',' || LOWER(COALESCE(labels,'')) || ',') LIKE :" + key)

    where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where_clause, params


def _row_to_email(row: sqlite3.Row) -> Dict[str, Any]:
    labels = _split_csv(row["labels"])
    recipients = _split_csv(row["recipient"])
    participants = list({row["sender"].lower(), *(email.lower() for email in recipients)})
    return {
        "id": row["id"],
        "subject": row["subject"],
        "from_addr": row["sender"],
        "to_addrs": recipients,
        "labels": labels,
        "date": row["date"],
        "text": row["body"],
        "participants": participants,
    }


class EmailRepository:
    def __init__(self) -> None:
        self.conn = get_connection()

    def list_users(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT sender AS email, COUNT(*) AS mailbox_count FROM emails GROUP BY sender ORDER BY mailbox_count DESC"
        ).fetchall()
        items = []
        for row in rows:
            email = row["email"]
            display = email.split("@")[0].title()
            items.append({
                "id": email,
                "email": email,
                "display_name": display,
                "mailbox_count": row["mailbox_count"],
            })
        return items

    def list_labels(self) -> List[Dict[str, Any]]:
        cur = self.conn.execute("SELECT labels FROM emails WHERE labels IS NOT NULL AND labels != ''")
        agg: Dict[str, int] = {}
        for (labels,) in cur.fetchall():
            for label in _split_csv(labels.lower()):
                agg[label] = agg.get(label, 0) + 1
        return [
            {"label": label, "count": count}
            for label, count in sorted(agg.items(), key=lambda item: item[1], reverse=True)
        ]

    def stats(self, filters: EmailQueryFilters) -> Dict[str, Any]:
        where_clause, params = _build_where(filters)
        by_day = self.conn.execute(
            f"SELECT substr(date,1,10) AS day, COUNT(*) AS cnt FROM emails{where_clause} GROUP BY day ORDER BY day DESC LIMIT 14",
            params,
        ).fetchall()
        totals_row = self.conn.execute(
            f"SELECT COUNT(*) AS total, COUNT(DISTINCT subject) AS threads FROM emails{where_clause}",
            params,
        ).fetchone()
        vip_row = self.conn.execute(
            f"SELECT COUNT(*) AS cnt FROM emails{where_clause + (' AND ' if where_clause else ' WHERE ')}(',' || LOWER(COALESCE(labels,'')) || ',') LIKE '%,vip,%'"
            if where_clause
            else "SELECT COUNT(*) AS cnt FROM emails WHERE (',' || LOWER(COALESCE(labels,'')) || ',') LIKE '%,vip,%'",
            params,
        ).fetchone()
        vip_count = _row_value(vip_row, "cnt", "count", "COUNT(*)") or 0
        top_senders = self.conn.execute(
            f"SELECT sender, COUNT(*) AS cnt FROM emails{where_clause} GROUP BY sender ORDER BY cnt DESC LIMIT 5",
            params,
        ).fetchall()
        top_threads = self.conn.execute(
            f"SELECT subject, COUNT(*) AS cnt FROM emails{where_clause} GROUP BY subject ORDER BY cnt DESC LIMIT 5",
            params,
        ).fetchall()
        return {
            "totals": {
                "messages": totals_row["total"],
                "threads": totals_row["threads"],
                "vip_flags": vip_count,
            },
            "by_day": [
                {"date": row["day"], "count": row["cnt"]}
                for row in by_day
            ],
            "top_senders": [
                {"sender": row["sender"], "count": row["cnt"]}
                for row in top_senders
            ],
            "top_threads": [
                {"thread_id": row["subject"], "subject": row["subject"], "count": row["cnt"]}
                for row in top_threads
            ],
        }

    def query_emails(self, request: EmailQueryRequest) -> Dict[str, Any]:
        where_clause, params = _build_where(request.filters)
        sort_column = {
            "date": "date",
            "sender": "sender",
            "thread": "subject",
        }.get(request.sort_by, "date")
        order = "DESC" if request.order == "desc" else "ASC"
        params.update({"limit": request.limit, "offset": request.offset})
        rows = self.conn.execute(
            f"SELECT * FROM emails{where_clause} ORDER BY {sort_column} {order} LIMIT :limit OFFSET :offset",
            params,
        ).fetchall()
        count_row = self.conn.execute(
            f"SELECT COUNT(*) AS total FROM emails{where_clause}",
            params,
        ).fetchone()
        items = [_row_to_email(row) for row in rows]
        return {
            "items": items,
            "count": count_row["total"],
            "offset": request.offset,
            "has_more": request.offset + request.limit < count_row["total"],
        }

    def quick_summary(self, filters: EmailQueryFilters, question: str) -> Dict[str, Any]:
        payload = self.query_emails(EmailQueryRequest(filters=filters, limit=50, offset=0, sort_by="date", order="desc"))
        total = payload["count"]
        highlight = payload["items"][0]["subject"] if payload["items"] else "n/a"
        summary = (
            f"Analyzed {total} matching emails for '{question[:60]}'. "
            f"Representative thread: {highlight}."
        )
        return {
            "summary": summary,
            "tokens_used": max(64, min(512, total * 8)),
            "gpu_seconds": 0.0,
            "artifact_id": f"email-artifact-{total:03d}",
        }


repository = EmailRepository()
