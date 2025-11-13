from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from shared.analysis.fallback_store import AnalysisFallbackStore


def _artifact(artifact_id: str, user_id: str, created_at: datetime) -> dict:
    return {
        "artifact_id": artifact_id,
        "title": f"title-{artifact_id}",
        "body": "body",
        "metadata": {"user_id": user_id},
        "created_at": created_at.isoformat() + "Z",
    }


def test_per_user_isolation(tmp_path):
    store = AnalysisFallbackStore(base_dir=tmp_path / "store", max_per_user=10)
    now = datetime.now(UTC)
    store.upsert_user_artifact("user1", _artifact("a1", "user1", now))
    store.upsert_user_artifact("user2", _artifact("b1", "user2", now + timedelta(seconds=1)))

    user1_items = store.list_user_artifacts("user1")
    user2_items = store.list_user_artifacts("user2")
    assert [item["artifact_id"] for item in user1_items] == ["a1"]
    assert [item["artifact_id"] for item in user2_items] == ["b1"]

    all_items = store.list_all_artifacts()
    assert [item["artifact_id"] for item in all_items] == ["b1", "a1"]


def test_max_per_user_enforced(tmp_path):
    store = AnalysisFallbackStore(base_dir=tmp_path / "store", max_per_user=2)
    now = datetime.now(UTC)
    store.upsert_user_artifact("user1", _artifact("a1", "user1", now))
    store.upsert_user_artifact("user1", _artifact("a2", "user1", now + timedelta(seconds=1)))
    store.upsert_user_artifact("user1", _artifact("a3", "user1", now + timedelta(seconds=2)))

    user_items = store.list_user_artifacts("user1")
    assert [item["artifact_id"] for item in user_items] == ["a3", "a2"]
    assert "a1" not in [item["artifact_id"] for item in user_items]


def test_legacy_file_migrated(tmp_path):
    legacy_file = tmp_path / "legacy.json"
    legacy_items = [
        _artifact("old1", "legacy-user", datetime.now(UTC)),
        _artifact("old2", "", datetime.now(UTC)),
    ]
    legacy_file.write_text(json.dumps(legacy_items))

    store = AnalysisFallbackStore(
        base_dir=tmp_path / "store",
        legacy_file=legacy_file,
        max_per_user=10,
    )

    migrated_user_items = store.list_user_artifacts("legacy-user")
    assert migrated_user_items and migrated_user_items[0]["artifact_id"] == "old1"

    admin_items = store.list_all_artifacts()
    assert {item["artifact_id"] for item in admin_items} == {"old1", "old2"}

    assert legacy_file.with_suffix(".migrated").exists()
