"""
Static checks to ensure sensitive headers/tokens are not logged directly.

We scan function calls to `print` and common logger methods for string literals
containing credential-bearing headers (Authorization, Set-Cookie ws_session, etc.).
"""

from __future__ import annotations

import ast
from pathlib import Path

BANNED_SUBSTRINGS = (
    "Authorization",  # headers containing bearer tokens
    "Set-Cookie: ws_session",
    "ws_session=",
)

LOG_METHODS = {"debug", "info", "warning", "error", "critical", "exception"}
REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIRS = ["services", "shared", "scripts"]


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for rel in TARGET_DIRS:
        base = REPO_ROOT / rel
        if not base.exists():
            continue
        files.extend(base.rglob("*.py"))
    return files


def _is_logging_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "print":
        return True
    if isinstance(func, ast.Attribute) and func.attr in LOG_METHODS:
        return True
    return False


def _literal_chunks(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        chunks: list[str] = []
        for value in node.values:
            chunks.extend(_literal_chunks(value))
        return chunks
    return []


def test_logging_calls_do_not_reference_sensitive_headers():
    violations: list[str] = []
    for path in _iter_python_files():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_logging_call(node):
                for arg in node.args:
                    for chunk in _literal_chunks(arg):
                        if any(banned in chunk for banned in BANNED_SUBSTRINGS):
                            violations.append(f"{path}:{node.lineno} -> {chunk.strip()}")
    assert not violations, (
        "Sensitive header names found in logging statements. "
        f"Update logging to use safe indicators.\n{chr(10).join(violations)}"
    )
