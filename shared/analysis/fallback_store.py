"""Multi-tenant fallback storage for analysis artifacts."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SAFE_USER_PATTERN = re.compile(r"[^a-zA-Z0-9_.-]")


class AnalysisFallbackStore:
    """Stores analysis artifacts per user in simple JSON files."""

    def __init__(
        self,
        base_dir: Path,
        legacy_file: Optional[Path] = None,
        max_per_user: int = 200,
        unknown_bucket: str = "unknown",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.legacy_file = Path(legacy_file) if legacy_file else None
        self.max_per_user = max(1, max_per_user)
        self.unknown_bucket = unknown_bucket
        self._lock = Lock()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_file()

    # ------------------------------------------------------------------ public
    def upsert_user_artifact(self, user_id: str, artifact: Dict[str, object]) -> Dict[str, object]:
        """Insert/update artifact for the given user."""
        user_key = self._user_key(user_id)
        with self._lock:
            items = self._load_user_items(user_key)
            items = [item for item in items if item.get("artifact_id") != artifact.get("artifact_id")]
            items.insert(0, artifact)
            if len(items) > self.max_per_user:
                items = items[: self.max_per_user]
            self._write_user_items(user_key, items)
        return artifact

    def list_user_artifacts(self, user_id: str) -> List[Dict[str, object]]:
        """Return all artifacts for a specific user (newest first)."""
        user_key = self._user_key(user_id)
        with self._lock:
            return list(self._load_user_items(user_key))

    def list_all_artifacts(self) -> List[Dict[str, object]]:
        """Return aggregated artifacts across all users."""
        with self._lock:
            items: List[Dict[str, object]] = []
            for path in sorted(self.base_dir.glob("*.json")):
                items.extend(self._load_path_items(path))
            # Files are already newest-first, but concatenation by user may not be sorted.
            items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
            return items

    def get_user_artifact(self, user_id: str, artifact_id: str) -> Optional[Dict[str, object]]:
        """Return artifact for the given user if present."""
        user_key = self._user_key(user_id)
        with self._lock:
            items = self._load_user_items(user_key)
            for item in items:
                if item.get("artifact_id") == artifact_id:
                    return item
        return None

    def get_any_artifact(self, artifact_id: str) -> Optional[Dict[str, object]]:
        """Return artifact regardless of owner (admin use)."""
        with self._lock:
            for path in self.base_dir.glob("*.json"):
                for item in self._load_path_items(path):
                    if item.get("artifact_id") == artifact_id:
                        return item
        return None

    # -------------------------------------------------------------- utilities
    def _user_key(self, user_id: Optional[str]) -> str:
        raw = (user_id or "").strip()
        if not raw:
            return self.unknown_bucket
        sanitized = _SAFE_USER_PATTERN.sub("_", raw)
        sanitized = sanitized[:128] or self.unknown_bucket
        return sanitized

    def _user_path(self, user_key: str) -> Path:
        return self.base_dir / f"{user_key}.json"

    def _load_user_items(self, user_key: str) -> List[Dict[str, object]]:
        path = self._user_path(user_key)
        return self._load_path_items(path)

    def _load_path_items(self, path: Path) -> List[Dict[str, object]]:
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())  # type: ignore[no-any-return]
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ANALYSIS-FALLBACK] Failed to read %s: %s", path, exc)
            return []

    def _write_user_items(self, user_key: str, items: List[Dict[str, object]]) -> None:
        path = self._user_path(user_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, indent=2))

    def _migrate_legacy_file(self) -> None:
        """Partition legacy single-file fallback store into per-user files."""
        if not self.legacy_file or not self.legacy_file.exists():
            return
        try:
            legacy_items = json.loads(self.legacy_file.read_text())
            logger.info(
                "[ANALYSIS-FALLBACK] Migrating %s items from legacy file %s",
                len(legacy_items),
                self.legacy_file,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ANALYSIS-FALLBACK] Failed to read legacy file %s: %s", self.legacy_file, exc)
            legacy_items = []

        with self._lock:
            for item in legacy_items:
                metadata = item.get("metadata") or {}
                user_key = self._user_key(metadata.get("user_id"))
                existing = self._load_user_items(user_key)
                existing.insert(0, item)
                if len(existing) > self.max_per_user:
                    existing = existing[: self.max_per_user]
                self._write_user_items(user_key, existing)

        backup_path = self.legacy_file.with_suffix(".migrated")
        try:
            self.legacy_file.rename(backup_path)
            logger.info("[ANALYSIS-FALLBACK] Legacy file migrated to %s", backup_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ANALYSIS-FALLBACK] Failed to rename legacy file %s: %s", self.legacy_file, exc)
