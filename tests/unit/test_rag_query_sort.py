import threading
from typing import Any, Dict, List, Optional

from tests.unit.test_rag_filters import RAGService  # Reuse imported module stubs


class _DummyCursor:
    def __init__(self, service: "_QueryStub") -> None:
        self.service = service
        self.queries: List[Any] = []
        self._current_rows: List[Dict[str, Any]] = []
        self._last_query: str = ""

    def execute(self, query: str, params: List[Any] = None) -> None:
        if params is None:
            params = []
        self.queries.append((query, tuple(params)))
        self._last_query = query

        # COUNT(*) query returns a single row with the configured total
        if "COUNT(" in query:
            self._current_rows = [(self.service.count_total,)]
            return

        # Primary SELECT query uses limit/offset slicing of the stub rows
        if "FROM transcript_segments ts" in query:
            limit = params[-2] if params else len(self.service.rows_data)
            offset = params[-1] if params else 0
            start = int(offset)
            stop = start + int(limit)
            self._current_rows = self.service.rows_data[start:stop]
            return

        # Fallback for any other query (e.g., context fetch)
        self._current_rows = []

    def fetchall(self):
        return self._current_rows


class _DummyConn:
    def __init__(self, service: "_QueryStub") -> None:
        self.service = service
        self.cursor_instance = _DummyCursor(service)

    def cursor(self):
        return self.cursor_instance

    def close(self) -> None:  # pragma: no cover - nothing to clean up
        pass


class _QueryStub(RAGService):
    def __init__(self, rows: List[Dict[str, Any]], total: int = None) -> None:
        # Avoid base __init__ (heavy); set required attributes directly
        self.rows_data = list(rows)
        self.count_total = len(rows) if total is None else total
        self.emotion_column = "emotion"
        self.lock = threading.RLock()
        self._last_cursor: Optional[_DummyCursor] = None

    def _connect(self):  # pragma: no cover - simple stub
        conn = _DummyConn(self)
        self._last_cursor = conn.cursor_instance
        return conn

    def count_transcripts_filtered(self, filters: Dict[str, Any]) -> int:  # noqa: D401
        return self.count_total


def _make_row(idx: int, speaker: str, created_at: str) -> Dict[str, Any]:
    return {
        "id": idx,
        "text": f"Utterance {idx}",
        "speaker": speaker,
        "emotion": "neutral",
        "transcript_id": 900 + idx,
        "seq": idx,
        "start_time": float(idx),
        "end_time": float(idx) + 0.5,
        "job_id": f"job-{idx}",
        "created_at": created_at,
    }


def test_query_transcripts_orders_by_created_at_desc():
    rows = [_make_row(1, "Agent", "2024-02-10T10:00:00"), _make_row(2, "User", "2023-12-31T23:00:00")]
    svc = _QueryStub(rows)

    result = svc.query_transcripts_filtered({
        "limit": 2,
        "offset": 0,
        "context_lines": 0,
        "sort_by": "created_at",
        "order": "desc",
    })

    assert result["sort_by"] == "created_at"
    assert result["order"] == "desc"
    assert svc._last_cursor is not None
    sql = svc._last_cursor.queries[-1][0]
    assert "ORDER BY tr.created_at DESC, ts.seq ASC" in sql
    assert "LOWER(ts.speaker)" not in sql


def test_query_transcripts_orders_by_speaker_asc_and_reports_paging():
    rows = [
        _make_row(1, "Bravo", "2024-02-10T10:00:00"),
        _make_row(2, "Alpha", "2024-02-11T09:00:00"),
        _make_row(3, "Charlie", "2024-02-12T08:00:00"),
    ]
    svc = _QueryStub(rows, total=5)

    result = svc.query_transcripts_filtered({
        "limit": 2,
        "offset": 0,
        "context_lines": 0,
        "sort_by": "speaker",
        "order": "asc",
    })

    assert svc._last_cursor is not None
    sql = svc._last_cursor.queries[-1][0]
    assert "ORDER BY LOWER(ts.speaker) ASC, tr.created_at DESC, ts.seq ASC" in sql
    assert result["has_more"] is True  # total (5) greater than loaded (2)
    assert result["next_offset"] == 2


def test_query_transcripts_has_more_false_when_consumed():
    rows = [_make_row(1, "Agent", "2024-02-10T10:00:00"), _make_row(2, "User", "2024-02-11T12:00:00")]
    svc = _QueryStub(rows, total=2)

    result = svc.query_transcripts_filtered({
        "limit": 5,
        "offset": 0,
        "context_lines": 0,
    })

    assert result["has_more"] is False
    assert result["next_offset"] == len(rows)
