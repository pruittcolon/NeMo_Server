import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence, Set

from shared.crypto.db_encryption import create_encrypted_db, EncryptedDatabase


class AnalyticsEngine:
    """Read-only analytics engine that aggregates transcript insights."""

    def __init__(
        self,
        db_path: str,
        *,
        encryption_key: Optional[str] = None,
        use_encryption: Optional[bool] = None,
    ):
        self.db_path = Path(db_path)
        self.lock = Lock()
        self.logger = logging.getLogger("analytics")
        self._encrypted_db: Optional[EncryptedDatabase] = None
        desired_encryption = use_encryption if use_encryption is not None else bool(encryption_key)
        if desired_encryption:
            try:
                self._encrypted_db = create_encrypted_db(
                    db_path=str(self.db_path),
                    encryption_key=encryption_key,
                    use_encryption=True,
                    connect_kwargs={"check_same_thread": False},
                )
                self.logger.info("AnalyticsEngine connected to encrypted database at %s", self.db_path)
            except Exception as exc:
                self.logger.error("AnalyticsEngine failed to initialize encrypted DB: %s", exc)
                raise
        else:
            if encryption_key:
                self.logger.warning(
                    "AnalyticsEngine received encryption key but encryption disabled; using plaintext connection"
                )
        self._default_metrics = [
            "pace_wpm",
            "pitch_mean",
            "volume_rms",
            "volume_peak",
            "pause_ms",
            "word_count",
        ]
        self._emotion_column: Optional[str] = None
        self._table_columns: Dict[str, Set[str]] = {}
        self._metric_meta: Dict[str, Dict[str, Optional[str]]] = {
            "pace_wpm": {"unit": "wpm"},
            "pitch_mean": {"unit": "Hz"},
            "volume_rms": {"unit": "rms"},
            "volume_peak": {"unit": "peak"},
            "pause_ms": {"unit": "ms"},
            "word_count": {"unit": "words"},
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        if self._encrypted_db:
            conn = self._encrypted_db.connect()
        else:
            conn = sqlite3.connect(self.db_path)
        self._apply_row_factory(conn)
        try:
            conn.execute("PRAGMA query_only=ON")
        except sqlite3.Error:
            self.logger.warning("[Analytics] Failed to enable query_only mode", exc_info=True)
        return conn

    def _apply_row_factory(self, conn: sqlite3.Connection) -> None:
        module_name = getattr(conn.__class__, "__module__", "")
        if module_name.startswith(("pysqlcipher3", "sqlcipher3")):
            try:
                import sys as _sys

                mod = _sys.modules.get(module_name)
                row_cls = getattr(mod, "Row", None)
                if row_cls is not None:
                    conn.row_factory = row_cls
                    return
            except Exception:
                pass
            def _dict_factory(cursor, row):
                out = {}
                description = getattr(cursor, "description", None) or []
                for idx, column in enumerate(description):
                    name = column[0] if isinstance(column, (tuple, list)) else str(column)
                    out[name] = row[idx]
                return out

            conn.row_factory = _dict_factory
            return
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            conn.row_factory = None

    def _get_table_columns(self, table: str, conn: Optional[sqlite3.Connection] = None) -> Set[str]:
        cached = self._table_columns.get(table)
        if cached is not None:
            return cached
        close_conn = False
        if conn is None:
            conn = self._connect()
            close_conn = True
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            raw_columns = cur.fetchall()
        except sqlite3.Error as exc:
            self.logger.warning("[Analytics] Failed to read schema for %s: %s", table, exc)
            raw_columns = []
        finally:
            if close_conn:
                conn.close()
        columns = set()
        for row in raw_columns:
            try:
                columns.add(row["name"])
            except (KeyError, TypeError):
                columns.add(row[1])
        if columns:
            self._table_columns[table] = columns
        return columns

    def _get_segment_columns(self, conn: Optional[sqlite3.Connection] = None) -> Set[str]:
        return self._get_table_columns("transcript_segments", conn)

    def _get_record_columns(self, conn: Optional[sqlite3.Connection] = None) -> Set[str]:
        return self._get_table_columns("transcript_records", conn)

    def _missing_tables(self, conn: sqlite3.Connection) -> Set[str]:
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            names = {row["name"] for row in cur.fetchall()}
        except sqlite3.Error as exc:
            self.logger.error("[Analytics] Unable to enumerate tables: %s", exc)
            return {"transcript_records", "transcript_segments"}
        required = {"transcript_records", "transcript_segments"}
        return required - names

    def _detect_emotion_column(self, segment_columns: Optional[Set[str]] = None) -> Optional[str]:
        columns = segment_columns or self._get_segment_columns()
        if not columns:
            return None
        if self._emotion_column and self._emotion_column in columns:
            return self._emotion_column
        if "emotion" in columns:
            self._emotion_column = "emotion"
            return self._emotion_column
        if "dominant_emotion" in columns:
            self._emotion_column = "dominant_emotion"
            return self._emotion_column
        return None

    @staticmethod
    def _detect_record_date_column(record_columns: Set[str]) -> Optional[str]:
        if "created_at" in record_columns:
            return "created_at"
        if "timestamp" in record_columns:
            return "timestamp"
        return None

    def _base_metric_ranges(self, metrics: Sequence[str]) -> Dict[str, Dict[str, Optional[float]]]:
        ranges: Dict[str, Dict[str, Optional[float]]] = {}
        for metric in metrics:
            meta = self._metric_meta.get(metric, {})
            ranges[metric] = {
                "min": None,
                "max": None,
                "unit": meta.get("unit"),
            }
        return ranges

    def _compute_metric_ranges(
        self,
        cursor: sqlite3.Cursor,
        metrics: Sequence[str],
        segment_columns: Set[str],
    ) -> Dict[str, Dict[str, Optional[float]]]:
        ranges = self._base_metric_ranges(metrics)
        for metric in metrics:
            if metric not in segment_columns:
                continue
            try:
                cursor.execute(
                    f"""
                    SELECT MIN(ts.{metric}) AS min_value,
                           MAX(ts.{metric}) AS max_value
                    FROM transcript_segments ts
                    WHERE ts.{metric} IS NOT NULL
                    """
                )
                row = cursor.fetchone()
            except sqlite3.Error as exc:
                self.logger.warning("[Analytics] Failed to compute %s range: %s", metric, exc)
                continue
            if not row:
                continue
            min_value = row["min_value"] if isinstance(row, sqlite3.Row) else row[0]
            max_value = row["max_value"] if isinstance(row, sqlite3.Row) else row[1]
            ranges[metric]["min"] = float(min_value) if min_value is not None else None
            ranges[metric]["max"] = float(max_value) if max_value is not None else None
        return ranges

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

    def empty_payload(
        self,
        metrics: Optional[Sequence[str]] = None,
        *,
        fallback_reason: Optional[str] = None,
        error: Optional[str] = None,
        metric_ranges: Optional[Dict[str, Dict[str, Optional[float]]]] = None,
    ) -> Dict[str, Any]:
        metric_list = list(metrics) if metrics else self._default_metrics
        return self._build_empty_payload(
            metric_list,
            fallback_reason=fallback_reason,
            error=error,
            metric_ranges=metric_ranges,
        )

    def _build_empty_payload(
        self,
        metrics: Sequence[str],
        *,
        fallback_reason: Optional[str] = None,
        error: Optional[str] = None,
        metric_ranges: Optional[Dict[str, Dict[str, Optional[float]]]] = None,
    ) -> Dict[str, Any]:
        metric_list = list(metrics) or self._default_metrics
        speech_series = {metric: [] for metric in metric_list}
        ranges = metric_ranges or self._base_metric_ranges(metric_list)
        payload: Dict[str, Any] = {
            "summary": {
                "emotion_totals": {},
                "joy_count": 0,
                "negative_count": 0,
                "total_analyzed": 0,
                "avg_pace_wpm": None,
                "avg_pitch_mean": None,
                "avg_pause_ms": None,
            },
            "timeline": {
                "dates": [],
                "emotions": {},
                "speech": speech_series,
            },
            "speakers": [],
            "metrics": metric_list,
            "metric_ranges": ranges,
        }
        if fallback_reason:
            payload["fallback_reason"] = fallback_reason
        if error:
            payload["error"] = error
        return payload

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
        allowed_metrics = set(self._default_metrics)
        range_metrics = list(self._default_metrics)
        requested_metrics = metrics or self._default_metrics
        metric_ranges: Dict[str, Dict[str, Optional[float]]] = self._base_metric_ranges(range_metrics)
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
            normalized_metrics = list(self._default_metrics)
        speaker_filter = {s.lower() for s in speakers} if speakers else set()
        emotion_filter = {e.lower() for e in emotions} if emotions else set()

        metrics_with_columns: List[str] = []
        emotion_rows: Sequence[sqlite3.Row] = []
        speech_rows: Sequence[sqlite3.Row] = []
        speaker_rows: Sequence[sqlite3.Row] = []
        speaker_emotion_rows: Sequence[sqlite3.Row] = []
        segment_columns: Set[str] = set()

        with self.lock:
            conn = self._connect()
            try:
                missing_tables = self._missing_tables(conn)
                if missing_tables:
                    reason = "missing_tables:" + ",".join(sorted(missing_tables))
                    return self._build_empty_payload(
                        normalized_metrics,
                        fallback_reason=reason,
                        metric_ranges=self._base_metric_ranges(range_metrics),
                    )

                cur = conn.cursor()
                record_columns = self._get_record_columns(conn)
                segment_columns = self._get_segment_columns(conn)
                metric_ranges = self._compute_metric_ranges(cur, range_metrics, segment_columns)
                metrics_with_columns = [m for m in normalized_metrics if m in segment_columns]
                date_column = self._detect_record_date_column(record_columns)
                if not date_column:
                    return self._build_empty_payload(
                        normalized_metrics,
                        fallback_reason="missing_date_column",
                        metric_ranges=metric_ranges,
                    )

                emotion_column = self._detect_emotion_column(segment_columns)
                if emotion_filter and not (emotion_column and emotion_column in segment_columns):
                    return self._build_empty_payload(
                        normalized_metrics,
                        fallback_reason="missing_emotion_column",
                        metric_ranges=metric_ranges,
                    )

                conditions = []
                params: List[Any] = []
                if start_date:
                    conditions.append(f"tr.{date_column} >= ?")
                    params.append(f"{start_date}T00:00:00")
                if end_date:
                    conditions.append(f"tr.{date_column} <= ?")
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
                day_expr = f"date(tr.{date_column})"

                if emotion_column and emotion_column in segment_columns:
                    cur.execute(
                        f"""
                        SELECT {day_expr} AS day,
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

                speech_fields = [f"{day_expr} AS day"]
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

                if emotion_column and emotion_column in segment_columns:
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
            except sqlite3.Error as exc:
                self.logger.error("[Analytics] Query failed: %s", exc, exc_info=True)
                return self._build_empty_payload(
                    normalized_metrics,
                    fallback_reason="operational_error",
                    error=str(exc),
                    metric_ranges=self._base_metric_ranges(range_metrics),
                )
            finally:
                conn.close()

        speaker_emotions: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in speaker_emotion_rows:
            speaker_name = row["speaker"]
            emotion_name = row["emotion"]
            if not speaker_name or not emotion_name:
                continue
            speaker_emotions[speaker_name][emotion_name] += row["count"]

        emotion_totals: Dict[str, int] = defaultdict(int)
        date_set = set()
        for row in emotion_rows:
            if not row["emotion"]:
                continue
            emotion_totals[row["emotion"]] += row["count"]
            if row["day"]:
                date_set.add(row["day"])
        for row in speech_rows:
            if row["day"]:
                date_set.add(row["day"])

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
            "metric_ranges": metric_ranges,
        }

    # ------------------------------------------------------------------ #
    # Segments drill-down
    # ------------------------------------------------------------------ #
    def query_segments(
        self,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        speakers: Optional[List[str]] = None,
        emotions: Optional[List[str]] = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
    ) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 50), 500))
        offset = max(0, int(offset or 0))
        order = "ASC" if str(order).lower() == "asc" else "DESC"

        normalized_speakers = {s.lower() for s in speakers} if speakers else set()
        normalized_emotions = {e.lower() for e in emotions} if emotions else set()

        with self.lock:
            conn = self._connect()
            try:
                missing_tables = self._missing_tables(conn)
                if missing_tables:
                    return {"items": [], "count": 0, "grouped_by_speaker": []}

                cur = conn.cursor()
                record_columns = self._get_record_columns(conn)
                segment_columns = self._get_segment_columns(conn)
                date_column = self._detect_record_date_column(record_columns)
                if not date_column:
                    return {"items": [], "count": 0, "grouped_by_speaker": []}

                emotion_column = self._detect_emotion_column(segment_columns)
                conditions = []
                params: List[Any] = []
                if start_date:
                    conditions.append(f"tr.{date_column} >= ?")
                    params.append(f"{start_date}T00:00:00")
                if end_date:
                    conditions.append(f"tr.{date_column} <= ?")
                    params.append(f"{end_date}T23:59:59")
                if normalized_speakers:
                    placeholders = ",".join("?" for _ in normalized_speakers)
                    conditions.append(f"LOWER(ts.speaker) IN ({placeholders})")
                    params.extend(sorted(normalized_speakers))
                if normalized_emotions and emotion_column:
                    placeholders = ",".join("?" for _ in normalized_emotions)
                    conditions.append(f"LOWER(ts.{emotion_column}) IN ({placeholders})")
                    params.extend(sorted(normalized_emotions))
                where_clause = " AND ".join(conditions) if conditions else "1=1"

                metric_selects = []
                for metric in self._default_metrics:
                    if metric in segment_columns:
                        metric_selects.append(f"ts.{metric} AS {metric}")
                    else:
                        metric_selects.append(f"NULL AS {metric}")
                metric_projection = ",\n                       ".join(metric_selects)
                emotion_projection = (
                    f"LOWER(ts.{emotion_column}) AS emotion" if emotion_column else "NULL AS emotion"
                )
                created_output_column = "created_at" if "created_at" in record_columns else date_column

                base_query = (
                    "FROM transcript_segments ts\n"
                    "JOIN transcript_records tr ON ts.transcript_id = tr.id\n"
                    f"WHERE {where_clause}"
                )

                cur.execute(f"SELECT COUNT(*) {base_query}", tuple(params))
                total_row = cur.fetchone()
                total_count = int(total_row[0]) if total_row and total_row[0] is not None else 0

                cur.execute(
                    f"""
                    SELECT ts.id,
                           ts.transcript_id,
                           ts.seq,
                           ts.start_time,
                           ts.end_time,
                           ts.text,
                           ts.speaker,
                           ts.speaker_confidence,
                           {emotion_projection},
                           ts.emotion_confidence,
                           tr.job_id,
                           tr.{created_output_column} AS created_at,
                           {metric_projection}
                    {base_query}
                    ORDER BY tr.{date_column} {order}, ts.id {order}
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params) + (limit, offset),
                )
                rows = cur.fetchall()

                metric_names = list(self._default_metrics)
                items: List[Dict[str, Any]] = []
                for row in rows:
                    metrics = {}
                    for metric in metric_names:
                        try:
                            value = row[metric]
                        except (KeyError, IndexError, TypeError):
                            value = None
                        metrics[metric] = float(value) if value is not None else None
                    items.append(
                        {
                            "id": row["id"],
                            "transcript_id": row["transcript_id"],
                            "seq": row["seq"],
                            "start_time": row["start_time"],
                            "end_time": row["end_time"],
                            "text": row["text"],
                            "speaker": row["speaker"],
                            "speaker_confidence": row["speaker_confidence"],
                            "emotion": row["emotion"],
                            "emotion_confidence": row["emotion_confidence"],
                            "job_id": row["job_id"],
                            "created_at": row["created_at"],
                            "metrics": metrics,
                        }
                    )

                cur.execute(
                    f"""
                    SELECT ts.speaker AS speaker,
                           COUNT(*) AS count
                    {base_query}
                    GROUP BY ts.speaker
                    ORDER BY count DESC
                    LIMIT 50
                    """,
                    tuple(params),
                )
                grouped_rows = cur.fetchall()
                grouped = [
                    {
                        "speaker": row["speaker"] or "Unknown",
                        "count": row["count"],
                    }
                    for row in grouped_rows
                ]
            finally:
                conn.close()

        return {"items": items, "count": total_count, "grouped_by_speaker": grouped}
