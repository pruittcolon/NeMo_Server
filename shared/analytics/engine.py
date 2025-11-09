import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


class AnalyticsEngine:
    """Read-only analytics engine that aggregates transcript insights."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.lock = Lock()
        self.logger = logging.getLogger("analytics")
        self._emotion_column = None
        self._segment_columns: Optional[Set[str]] = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _detect_emotion_column(self) -> str:
        if self._emotion_column:
            return self._emotion_column
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(transcript_segments)")
        columns = {row["name"] for row in cur.fetchall()}
        conn.close()
        if "emotion" in columns:
            self._emotion_column = "emotion"
        elif "dominant_emotion" in columns:
            self._emotion_column = "dominant_emotion"
        else:
            self._emotion_column = "emotion"
        return self._emotion_column

    def _get_segment_columns(self) -> Set[str]:
        if self._segment_columns is not None:
            return self._segment_columns
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(transcript_segments)")
        self._segment_columns = {row["name"] for row in cur.fetchall()}
        conn.close()
        return self._segment_columns

    @staticmethod
    def _build_date_range(start: Optional[str], end: Optional[str], max_days: int = 120) -> List[str]:
        if not start or not end:
            return []
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            return []
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt
        delta = (end_dt - start_dt).days
        if delta > max_days:
            end_dt = start_dt + timedelta(days=max_days)
        dates = []
        cursor = start_dt
        while cursor <= end_dt:
            dates.append(cursor.strftime("%Y-%m-%d"))
            cursor += timedelta(days=1)
        return dates

    @staticmethod
    def _normalize_list(values: Sequence[Optional[float]]) -> List[Optional[float]]:
        return [None if v is None else float(v) for v in values]

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def query_signals(
        self,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        speakers: Optional[List[str]] = None,
        emotions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, any]:
        """Aggregate multi-dimensional analytics for the dashboard."""
        emotion_column = self._detect_emotion_column()
        default_metric_order = [
            "pace_wpm",
            "pitch_mean",
            "volume_rms",
            "volume_peak",
            "pause_ms",
            "word_count",
        ]
        allowed_metrics = set(default_metric_order)
        requested_metrics = metrics or default_metric_order
        normalized_metrics: List[str] = []
        seen: Set[str] = set()
        for metric in requested_metrics:
            if not metric:
                continue
            name = str(metric).strip().lower()
            if name in allowed_metrics and name not in seen:
                normalized_metrics.append(name)
                seen.add(name)
        if not normalized_metrics:
            normalized_metrics = default_metric_order.copy()
        segment_columns = self._get_segment_columns()
        metrics_with_columns = [m for m in normalized_metrics if m in segment_columns]
        speaker_filter = {s.lower() for s in speakers} if speakers else set()
        emotion_filter = {e.lower() for e in emotions} if emotions else set()

        with self.lock:
            conn = self._connect()
            cur = conn.cursor()

            conditions = []
            params: List[Any] = []
            if start_date:
                conditions.append("tr.created_at >= ?")
                params.append(f"{start_date}T00:00:00")
            if end_date:
                conditions.append("tr.created_at <= ?")
                params.append(f"{end_date}T23:59:59")
            if speaker_filter:
                placeholders = ",".join("?" for _ in speaker_filter)
                conditions.append(f"LOWER(ts.speaker) IN ({placeholders})")
                params.extend(sorted(speaker_filter))
            if emotion_filter:
                placeholders = ",".join("?" for _ in emotion_filter)
                conditions.append(f"LOWER(ts.{emotion_column}) IN ({placeholders})")
                params.extend(sorted(emotion_filter))

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params_tuple = tuple(params)

            # Emotion totals + timeline
            cur.execute(
                f"""
                SELECT date(tr.created_at) AS day,
                       LOWER(ts.{emotion_column}) AS emotion,
                       COUNT(*) AS count
                FROM transcript_segments ts
                JOIN transcript_records tr ON ts.transcript_id = tr.id
                WHERE {where_clause}
                GROUP BY day, emotion
                ORDER BY day ASC
                """,
                params_tuple,
            )
            emotion_rows = cur.fetchall()

            emotion_totals: Dict[str, int] = defaultdict(int)
            date_set = set()
            for row in emotion_rows:
                if not row["emotion"]:
                    continue
                emotion_totals[row["emotion"]] += row["count"]
                if row["day"]:
                    date_set.add(row["day"])

            # Speech timeline
            speech_fields = ["date(tr.created_at) AS day"]
            for metric in metrics_with_columns:
                speech_fields.append(f"AVG(ts.{metric}) AS {metric}")
            speech_select = ",\n                       ".join(speech_fields)
            cur.execute(
                f"""
                SELECT {speech_select}
                FROM transcript_segments ts
                JOIN transcript_records tr ON ts.transcript_id = tr.id
                WHERE {where_clause}
                GROUP BY day
                ORDER BY day ASC
                """,
                params_tuple,
            )
            speech_rows = cur.fetchall()
            for row in speech_rows:
                if row["day"]:
                    date_set.add(row["day"])

            # Speaker profiles
            speaker_fields = [
                "ts.speaker",
                "COUNT(*) AS segments",
            ]
            for metric in metrics_with_columns:
                speaker_fields.append(f"AVG(ts.{metric}) AS {metric}")
            speaker_select = ",\n                       ".join(speaker_fields)
            cur.execute(
                f"""
                SELECT {speaker_select}
                FROM transcript_segments ts
                JOIN transcript_records tr ON ts.transcript_id = tr.id
                WHERE {where_clause}
                GROUP BY ts.speaker
                ORDER BY segments DESC
                LIMIT 24
                """,
                params_tuple,
            )
            speaker_rows = cur.fetchall()

            # Speaker emotion mix
            cur.execute(
                f"""
                SELECT ts.speaker,
                       LOWER(ts.{emotion_column}) AS emotion,
                       COUNT(*) AS count
                FROM transcript_segments ts
                JOIN transcript_records tr ON ts.transcript_id = tr.id
                WHERE {where_clause} AND ts.speaker IS NOT NULL
                GROUP BY ts.speaker, LOWER(ts.{emotion_column})
                """,
                params_tuple,
            )
            speaker_emotion_rows = cur.fetchall()
            speaker_emotions: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for row in speaker_emotion_rows:
                if not row["speaker"] or not row["emotion"]:
                    continue
                speaker_emotions[row["speaker"]][row["emotion"]] += row["count"]

            conn.close()

        # Build timeline axis
        if start_date and end_date:
            dates = self._build_date_range(start_date, end_date)
        else:
            dates = sorted(date_set)
        date_index = {date: idx for idx, date in enumerate(dates)}

        emotion_series: Dict[str, List[int]] = {}
        for row in emotion_rows:
            day = row["day"]
            emotion = row["emotion"] or "unknown"
            if not day or day not in date_index:
                continue
            series = emotion_series.setdefault(emotion, [0] * len(dates))
            series[date_index[day]] = row["count"]

        speech_series: Dict[str, List[Optional[float]]] = {
            metric: [None] * len(dates) for metric in normalized_metrics
        }
        for row in speech_rows:
            day = row["day"]
            if not day or day not in date_index:
                continue
            idx = date_index[day]
            for metric in metrics_with_columns:
                value = row[metric]
                speech_series[metric][idx] = float(value) if value is not None else None

        # Speaker profiles with emotion mix
        speaker_profiles: List[Dict[str, Any]] = []
        for row in speaker_rows:
            speaker_name = row["speaker"]
            if not speaker_name:
                continue
            profile = {
                "speaker": speaker_name,
                "segments": row["segments"],
                "emotion_mix": dict(speaker_emotions.get(speaker_name, {})),
            }
            for metric in normalized_metrics:
                if metric in metrics_with_columns:
                    value = row[metric]
                    profile[metric] = float(value) if value is not None else None
                else:
                    profile[metric] = None
            speaker_profiles.append(profile)

        total_segments = sum(row["segments"] for row in speaker_rows if row["segments"])
        speaker_field_names = set(speaker_rows[0].keys()) if speaker_rows else set()

        def _weighted_avg(key: str) -> Optional[float]:
            if not total_segments:
                return None
            if key not in speaker_field_names:
                return None
            numerator = 0.0
            weight = 0
            for row in speaker_rows:
                segment_count = row["segments"] or 0
                value = row[key]
                if segment_count and value is not None:
                    numerator += float(value) * segment_count
                    weight += segment_count
            if not weight:
                return None
            return numerator / weight

        joy_count = emotion_totals.get("joy", 0)
        negative_count = sum(
            emotion_totals.get(label, 0) for label in ("anger", "sadness", "fear")
        )
        total_analyzed = sum(emotion_totals.values())
        summary = {
            "emotion_totals": dict(emotion_totals),
            "joy_count": joy_count,
            "negative_count": negative_count,
            "total_analyzed": total_analyzed,
            "avg_pace_wpm": _weighted_avg("pace_wpm"),
            "avg_pitch_mean": _weighted_avg("pitch_mean"),
            "avg_pause_ms": _weighted_avg("pause_ms"),
        }

        return {
            "summary": summary,
            "timeline": {
                "dates": dates,
                "emotions": emotion_series,
                "speech": speech_series,
            },
            "speakers": speaker_profiles,
            "metrics": normalized_metrics,
        }
