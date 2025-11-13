"""
Static guardrail to ensure real Hugging Face tokens never land in the repo.

We search source files for strings that look like `hf_<alnum>{20+}`, which
matches the shape of actual HF access tokens. Placeholders such as
`hf_YourTokenHere` (shorter than 20 chars) are allowed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"hf_[A-Za-z0-9]{20,}")
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".env",
    ".sh",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".dart",
}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "logs",
    "models",
    "gemma_instance",
    "__pycache__",
}


def _should_scan(path: Path) -> bool:
    if not path.is_file():
        return False
    rel_parts = path.relative_to(ROOT).parts
    if any(part in EXCLUDED_DIRS for part in rel_parts):
        return False
    if path.suffix in TEXT_SUFFIXES:
        return True
    return path.name.startswith("Dockerfile")


def test_repository_contains_no_real_hf_tokens():
    violations: list[str] = []
    for file_path in ROOT.rglob("*"):
        if not _should_scan(file_path):
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        match = PATTERN.search(text)
        if match:
            sample = match.group(0)[:24]
            violations.append(f"{file_path}: {sample}…")
    assert not violations, (
        "Potential Hugging Face tokens detected in repository:\n"
        + "\n".join(violations)
    )
