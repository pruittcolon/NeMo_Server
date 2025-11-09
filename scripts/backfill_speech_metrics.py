#!/usr/bin/env python3
"""
Fill in extended speech metrics (pace, pitch, pauses, etc.) for historical
transcript segments. This mirrors the logic in services/rag-service/src/main.py
so older rows get the same analytics fields as new ingests.
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
import re

DB_PATH = Path("docker/rag_instance/rag.db")

WORD_REGEX = re.compile(r"[A-Za-z0-9']+")
FILLER_PATTERNS = [
    re.compile(rf"\b{phrase}\b", re.IGNORECASE)
    for phrase in [
        "um",
        "uh",
        "er",
        "ah",
        "like",
        "you know",
        "i mean",
        "sort of",
        "kind of",
        "basically",
        "actually",
    ]
]

EXTENDED_COLUMNS = [
    ("word_count", "INTEGER"),
    ("filler_count", "INTEGER"),
    ("pace_wpm", "REAL"),
    ("pause_ms", "REAL"),
    ("pitch_mean", "REAL"),
    ("pitch_std", "REAL"),
    ("volume_rms", "REAL"),
    ("volume_peak", "REAL"),
]


def ensure_columns(cursor: sqlite3.Cursor) -> None:
    cursor.execute("PRAGMA table_info(transcript_segments)")
    existing = {row["name"] for row in cursor.fetchall()}
    for name, decl in EXTENDED_COLUMNS:
        if name not in existing:
            cursor.execute(f"ALTER TABLE transcript_segments ADD COLUMN {name} {decl}")


def parse_audio_metrics(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) or {}
    except Exception:
        return {}


def estimate_volume(audio_metrics):
    volume_rms = audio_metrics.get("volume_rms")
    volume_peak = audio_metrics.get("volume_peak")
    amplitude_peak = audio_metrics.get("amplitude_peak")
    if volume_peak is None and amplitude_peak is not None:
        volume_peak = amplitude_peak
    if volume_rms is None:
        energy_mean = audio_metrics.get("energy_mean")
        if isinstance(energy_mean, (int, float)) and energy_mean >= 0:
            volume_rms = energy_mean ** 0.5
        elif isinstance(amplitude_peak, (int, float)):
            volume_rms = amplitude_peak / 2.0
    return volume_rms, volume_peak


def compute_metrics(row, last_end_by_speaker):
    text = row["text"] or ""
    tokens = WORD_REGEX.findall(text)
    word_count = len(tokens)
    filler_count = 0
    lowered = text.lower()
    for pattern in FILLER_PATTERNS:
        filler_count += len(pattern.findall(lowered))

    start_time = row["start_time"]
    end_time = row["end_time"]
    pace_wpm = None
    if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
        duration = max(0.0, end_time - start_time)
        if duration > 0:
            pace_wpm = (word_count / duration) * 60.0

    pause_ms = None
    speaker = row["speaker"]
    if speaker:
        prev_end = last_end_by_speaker.get(speaker)
        if prev_end is not None and isinstance(start_time, (int, float)):
            delta = (start_time - prev_end) * 1000.0
            if delta > 0:
                pause_ms = delta
        if isinstance(end_time, (int, float)):
            last_end_by_speaker[speaker] = end_time

    audio_metrics = parse_audio_metrics(row["audio_metrics"])
    pitch_mean = audio_metrics.get("pitch_mean")
    pitch_std = audio_metrics.get("pitch_std")
    volume_rms, volume_peak = estimate_volume(audio_metrics)

    return {
        "word_count": word_count or None,
        "filler_count": filler_count or None,
        "pace_wpm": pace_wpm,
        "pause_ms": pause_ms,
        "pitch_mean": pitch_mean,
        "pitch_std": pitch_std,
        "volume_rms": volume_rms,
        "volume_peak": volume_peak,
    }


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    schema_cur = conn.cursor()

    ensure_columns(schema_cur)
    conn.commit()

    select_cur = conn.cursor()
    update_cur = conn.cursor()

    select_cur.execute(
        """
        SELECT id, transcript_id, seq, text, speaker, start_time, end_time,
               audio_metrics, word_count, filler_count, pace_wpm, pause_ms,
               pitch_mean, pitch_std, volume_rms, volume_peak
        FROM transcript_segments
        ORDER BY transcript_id, seq
        """
    )

    updates = []
    last_transcript_id = None
    last_end_by_speaker = defaultdict(lambda: None)
    total_rows = 0
    updated_rows = 0

    for row in select_cur:
        total_rows += 1
        transcript_id = row["transcript_id"]
        if transcript_id != last_transcript_id:
            last_end_by_speaker.clear()
            last_transcript_id = transcript_id

        metrics = compute_metrics(row, last_end_by_speaker)

        existing = {
            "word_count": row["word_count"],
            "filler_count": row["filler_count"],
            "pace_wpm": row["pace_wpm"],
            "pause_ms": row["pause_ms"],
            "pitch_mean": row["pitch_mean"],
            "pitch_std": row["pitch_std"],
            "volume_rms": row["volume_rms"],
            "volume_peak": row["volume_peak"],
        }

        if all(existing[key] is not None for key in metrics):
            continue

        updated_rows += 1
        updates.append(
            (
                metrics["word_count"],
                metrics["filler_count"],
                metrics["pace_wpm"],
                metrics["pause_ms"],
                metrics["pitch_mean"],
                metrics["pitch_std"],
                metrics["volume_rms"],
                metrics["volume_peak"],
                row["id"],
            )
        )

        if len(updates) >= 500:
            update_cur.executemany(
                """
                UPDATE transcript_segments
                SET word_count=?, filler_count=?, pace_wpm=?, pause_ms=?,
                    pitch_mean=?, pitch_std=?, volume_rms=?, volume_peak=?
                WHERE id=?
                """,
                updates,
            )
            conn.commit()
            updates.clear()

    if updates:
        update_cur.executemany(
            """
            UPDATE transcript_segments
            SET word_count=?, filler_count=?, pace_wpm=?, pause_ms=?,
                pitch_mean=?, pitch_std=?, volume_rms=?, volume_peak=?
            WHERE id=?
            """,
            updates,
        )
        conn.commit()

    conn.close()
    print(f"Processed {total_rows} segments; updated {updated_rows} rows.")


if __name__ == "__main__":
    main()
