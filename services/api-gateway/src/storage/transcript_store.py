"""
Utility helpers for persisting transcripts directly to SQLite.

Provides a lightweight fallback when the full RAG service is unavailable.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _ensure_tables(cur: sqlite3.Cursor) -> None:
    """Create transcript tables if they do not exist."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transcript_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE,
            session_id TEXT,
            full_text TEXT,
            audio_duration REAL,
            timestamp TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transcript_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcript_id INTEGER,
            seq INTEGER,
            start_time REAL,
            end_time REAL,
            text TEXT,
            speaker TEXT,
            speaker_confidence REAL,
            emotion TEXT,
            emotion_confidence REAL,
            emotion_scores TEXT,
            created_at TEXT,
            FOREIGN KEY (transcript_id) REFERENCES transcript_records (id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT,
            speaker TEXT,
            start REAL,
            end REAL,
            text TEXT,
            created_at TEXT
        )
        """
    )


def store_transcript_fallback(
    db_path: Path,
    text: str,
    segments: List[Dict[str, Any]],
    job_id: str,
    session_id: str,
    audio_duration: float,
) -> int:
    """
    Persist transcript data directly to SQLite, mirroring AdvancedMemoryService.

    Returns the transcript_records primary key.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        _ensure_tables(cur)
        timestamp = datetime.utcnow().isoformat()

        cur.execute(
            """
            INSERT OR REPLACE INTO transcript_records
            (job_id, session_id, full_text, audio_duration, timestamp, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, session_id, text, audio_duration, timestamp, timestamp),
        )
        transcript_id = cur.lastrowid or cur.execute(
            "SELECT id FROM transcript_records WHERE job_id = ?", (job_id,)
        ).fetchone()[0]

        # Remove any previous segments for this transcript to avoid duplicates
        cur.execute("DELETE FROM transcript_segments WHERE transcript_id = ?", (transcript_id,))

        for idx, seg in enumerate(segments):
            emotion_scores_json = json.dumps(seg.get("emotions", {}))
            cur.execute(
                """
                INSERT INTO transcript_segments (
                    transcript_id, seq, start_time, end_time, text, speaker,
                    speaker_confidence, emotion, emotion_confidence, emotion_scores, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transcript_id,
                    idx,
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", 0.0) or 0.0),
                    seg.get("text", ""),
                    seg.get("speaker", "SPK"),
                    seg.get("speaker_confidence"),
                    seg.get("emotion", "neutral"),
                    seg.get("emotion_confidence", 0.0),
                    emotion_scores_json,
                    timestamp,
                ),
            )

        for seg in segments:
            cur.execute(
                """
                INSERT INTO transcripts (job_id, speaker, start, end, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    seg.get("speaker", "SPK"),
                    float(seg.get("start", 0.0) or 0.0),
                    float(seg.get("end", 0.0) or 0.0),
                    seg.get("text", ""),
                    timestamp,
                ),
            )

        conn.commit()
        return transcript_id

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
