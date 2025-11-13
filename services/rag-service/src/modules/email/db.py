"""Encrypted email database helper for the Gemma email analyzer."""
from __future__ import annotations

import os
import sqlite3
import logging
from pathlib import Path
from typing import Iterable, Dict, Any

from shared.crypto.db_encryption import create_encrypted_db
try:
    from pysqlcipher3 import dbapi2 as _sqlc_db
    _SQLCIPHER_ROW = getattr(_sqlc_db, "Row", None)
except Exception:  # noqa: BLE001
    _SQLCIPHER_ROW = None


LOGGER = logging.getLogger("gemma.email.db")

_DEFAULT_INSTANCE = Path(__file__).resolve().parents[2] / "instance"
EMAIL_DB_PATH = Path(os.getenv("EMAIL_DB_PATH", str(_DEFAULT_INSTANCE / "email.db")))

# Support secret via *_FILE, then env variable, else None
_key_file = os.getenv("EMAIL_DB_KEY_FILE")
_key_from_file = None
if _key_file:
    try:
        _key_from_file = Path(_key_file).read_text(encoding="utf-8").strip()
    except Exception:
        _key_from_file = None
EMAIL_DB_KEY = os.getenv("EMAIL_DB_KEY") or _key_from_file

EMAIL_DB_ENCRYPTION = os.getenv("EMAIL_DB_ENCRYPTION", "true").lower() in {"1", "true", "yes"}
TEST_MODE = os.getenv("TEST_MODE", "true").lower() in {"1", "true", "yes"}

if EMAIL_DB_ENCRYPTION and not EMAIL_DB_KEY:
    if TEST_MODE:
        EMAIL_DB_KEY = "dev-email-key"
        LOGGER.warning("[EMAIL][DB] EMAIL_DB_KEY missing – using dev key (TEST_MODE) – do not use in production")
    else:
        raise RuntimeError(
            "EMAIL_DB_KEY is required when EMAIL_DB_ENCRYPTION=true (set EMAIL_DB_KEY_FILE to a Docker secret path)"
        )

_database = create_encrypted_db(
    db_path=str(EMAIL_DB_PATH),
    encryption_key=EMAIL_DB_KEY,
    use_encryption=EMAIL_DB_ENCRYPTION,
    connect_kwargs={"check_same_thread": False},
)


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_connection() -> sqlite3.Connection:
    conn = _database.connect()
    # A neutral row factory that works for both sqlite3 and pysqlcipher3 cursors.
    conn.row_factory = _dict_factory
    return conn


def _exec(conn: sqlite3.Connection, sql: str, params: Dict[str, Any] | Iterable[Any] | None = None) -> None:
    conn.execute(sql, params or {})


def _init_schema(conn: sqlite3.Connection) -> None:
    _exec(
        conn,
        """
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            date TEXT NOT NULL,
            attachments TEXT,
            is_read INTEGER DEFAULT 0,
            labels TEXT
        );
        """,
    )
    _exec(conn, "CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date)")
    _exec(conn, "CREATE INDEX IF NOT EXISTS idx_emails_sender ON emails(LOWER(sender))")
    _exec(conn, "CREATE INDEX IF NOT EXISTS idx_emails_recipient ON emails(LOWER(recipient))")


SAMPLE_EMAILS = [
    {
        "id": "eml-1001",
        "sender": "ops@evenai.io",
        "recipient": "cto@customer.com",
        "subject": "GPU coordinator downtime notice",
        "body": "Heads up, GPU coordinator recycled at 02:00 UTC. Expect 2m pause per inference job.",
        "date": "2025-11-10T02:00:00Z",
        "attachments": "",
        "is_read": 0,
        "labels": "priority,ops",
    },
    {
        "id": "eml-1002",
        "sender": "insights@evenai.io",
        "recipient": "sales@evenai.io",
        "subject": "Customer sentiment weekly rollup",
        "body": "Top drivers: onboarding friction and dashboard latency. Attached csv highlights top accounts.",
        "date": "2025-11-09T15:30:00Z",
        "attachments": "sentiment.csv",
        "is_read": 1,
        "labels": "report,product",
    },
    {
        "id": "eml-1003",
        "sender": "sales@evenai.io",
        "recipient": "insights@evenai.io",
        "subject": "Re: Customer sentiment weekly rollup",
        "body": "Need a call-out on ACME Group – exec escalated. Can we highlight risk score > 80?",
        "date": "2025-11-10T08:10:00Z",
        "attachments": "",
        "is_read": 0,
        "labels": "followup,vip",
    },
    {
        "id": "eml-1004",
        "sender": "support@evenai.io",
        "recipient": "ops@evenai.io",
        "subject": "High latency for EU West tier",
        "body": "Ticket #8831 shows >4s response for EU West. Customers waiting on RCA.",
        "date": "2025-11-08T19:45:00Z",
        "attachments": "",
        "is_read": 0,
        "labels": "escalation,priority",
    },
    {
        "id": "eml-1005",
        "sender": "ceo@customer.com",
        "recipient": "ceo@evenai.io",
        "subject": "Executive briefing request",
        "body": "Need a consolidated readout on AI agent roadmap before board call.",
        "date": "2025-11-07T13:05:00Z",
        "attachments": "",
        "is_read": 0,
        "labels": "vip,exec",
    },
    {
        "id": "eml-1006",
        "sender": "finance@evenai.io",
        "recipient": "sales@evenai.io",
        "subject": "Renewal risk flagged – Northwind",
        "body": "ARR at risk due to delayed integrations. Need action plan by Friday.",
        "date": "2025-11-06T11:00:00Z",
        "attachments": "",
        "is_read": 1,
        "labels": "renewal,risk",
    },
]


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT COUNT(*) AS cnt FROM emails")
    row = cur.fetchone() or {}
    try:
        count = row[0] if isinstance(row, tuple) else int(row.get("cnt") or row.get("COUNT(*)") or 0)
    except Exception:
        count = 0
    if count:
        return
    LOGGER.info("[EMAIL][DB] Seeding %s sample emails", len(SAMPLE_EMAILS))
    conn.executemany(
        """
        INSERT INTO emails (id, sender, recipient, subject, body, date, attachments, is_read, labels)
        VALUES (:id, :sender, :recipient, :subject, :body, :date, :attachments, :is_read, :labels)
        """,
        SAMPLE_EMAILS,
    )
    conn.commit()


def initialize_database() -> None:
    conn = get_connection()
    _init_schema(conn)
    _seed_if_empty(conn)
    LOGGER.info(
        "[EMAIL][DB] Ready path=%s encrypted=%s rows=%s",
        EMAIL_DB_PATH,
        EMAIL_DB_ENCRYPTION,
        (lambda r: (r[0] if isinstance(r, tuple) else r.get("cnt") or r.get("COUNT(*)") or 0))(conn.execute("SELECT COUNT(*) AS cnt FROM emails").fetchone() or {}),
    )


# Initialization is performed by the service at startup.
