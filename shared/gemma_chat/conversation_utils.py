"""Shared helpers for Gemma conversational memory, tone analysis, and meta queries."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

META_QUESTION_PATTERNS = (
    "what questions have i asked",
    "what questions did i ask",
    "which questions have i asked",
    "can you list the questions i asked",
    "remind me what i asked",
    "what did i just ask",
    "what have i asked you",
)

QUESTION_HINT_WORDS = (
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "which",
    "can",
    "could",
    "would",
    "should",
)

QUESTION_SPLIT_REGEX = re.compile(r"([^?]+\?)")

QUESTION_TAG_RULES: Dict[str, tuple[str, ...]] = {
    "compliance": ("compliance", "policy", "governance", "regulation"),
    "leadership": ("leadership", "exec", "executive", "brief"),
    "dependencies": ("depend", "dependency", "team", "stakeholder", "partner"),
    "risk": ("risk", "threat", "issue", "concern", "blocker"),
    "metrics": ("metric", "kpi", "measure", "success"),
    "timeline": ("timeline", "schedule", "deadline", "milestone"),
    "action": ("should we", "next step", "plan", "action"),
}

TONE_WARNING_PATTERNS: Dict[str, tuple[str, ...]] = {
    "limitation": (
        "i cannot",
        "i can't",
        "i am unable",
        "i'm unable",
        "not able to",
    ),
    "apology": ("i'm sorry", "i am sorry", "sorry, but", "apolog"),
    "hedging": (
        "maybe",
        "perhaps",
        "might be able",
        "i'm just an ai",
        "as an ai",
    ),
    "refusal": ("cannot help", "won't be able", "i do not have that information"),
}

POSITIVE_TONE_CUES = (
    "let's focus",
    "here's what we can do",
    "we can",
    "recommended next",
    "consider starting with",
    "here are the steps",
)


def is_meta_question(text: Optional[str]) -> bool:
    """Detect if a prompt is a meta question about prior user questions."""
    if not text:
        return False
    normalized = text.strip().lower()
    if not normalized:
        return False
    return any(pattern in normalized for pattern in META_QUESTION_PATTERNS)


def extract_questions(content: str) -> List[str]:
    """Extract up to three question sentences from user input."""
    if not content:
        return []
    normalized = content.strip()
    if not normalized:
        return []
    questions: List[str] = []
    for match in QUESTION_SPLIT_REGEX.findall(normalized):
        question = match.strip()
        if not question:
            continue
        if not question.endswith("?"):
            question += "?"
        questions.append(question)
    if not questions:
        lower_text = normalized.lower()
        if any(lower_text.startswith(word + " ") for word in QUESTION_HINT_WORDS):
            questions.append(normalized if normalized.endswith("?") else normalized + "?")
    return questions[:3]


def tag_question(question: str) -> List[str]:
    """Assign heuristic tags to a question for downstream analytics."""
    tags: List[str] = []
    normalized = (question or "").lower()
    for tag, keywords in QUESTION_TAG_RULES.items():
        if any(keyword in normalized for keyword in keywords):
            tags.append(tag)
    if not tags:
        tags.append("general")
    return sorted(set(tags))


def analyze_tone(response_text: str) -> Dict[str, Any]:
    """
    Perform lightweight tone heuristics.

    Returns:
        {
            "status": "pass" | "warn" | "fail",
            "warnings": [...],
            "positive_cues": [...],
            "summary": str,
        }
    """
    text = (response_text or "").strip()
    if not text:
        return {
            "status": "fail",
            "warnings": ["empty_response"],
            "positive_cues": [],
            "summary": "No response text provided.",
        }
    lowered = text.lower()
    warnings: List[str] = []
    for label, patterns in TONE_WARNING_PATTERNS.items():
        if any(pattern in lowered for pattern in patterns):
            warnings.append(label)
    positives = [cue for cue in POSITIVE_TONE_CUES if cue in lowered]
    if warnings and positives:
        # Remove positives that overlap with warnings to focus on true signals
        positives = [cue for cue in positives if cue not in warnings]
    if len(warnings) >= 2:
        status = "fail"
    elif warnings:
        status = "warn"
    else:
        status = "pass"
    summary = "Tone balanced."
    if status == "warn":
        summary = f"Tone warning: {', '.join(warnings)}."
    elif status == "fail":
        summary = f"Tone failure: {', '.join(warnings)}."
    elif positives:
        summary = "Positive, action-oriented tone."
    return {
        "status": status,
        "warnings": warnings,
        "positive_cues": positives,
        "summary": summary,
    }


def build_reasoning_trace(
    user_prompt: str,
    history_turns: int,
    *,
    used_citations: Optional[int] = None,
) -> str:
    """Provide a short narrative describing how the assistant formed its reply."""
    parts = [
        f"Last user prompt length: {len((user_prompt or '').split())} words.",
        f"History turns available: {history_turns}.",
    ]
    if used_citations is not None:
        parts.append(f"Citations referenced: {used_citations}.")
    return " ".join(parts)


def build_conversation_health(meta: Dict[str, Any], tone: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize conversation health for diagnostics."""
    turn_count = meta.get("turn_count", 0)
    question_count = meta.get("question_count", 0)
    tone_status = tone.get("status", "pass")
    tone_warnings = tone.get("warnings", [])
    status = "ok"
    if tone_status == "fail":
        status = "action_needed"
    elif tone_status == "warn" or tone_warnings:
        status = "watch"
    return {
        "status": status,
        "turn_count": turn_count,
        "question_count": question_count,
        "tone_warnings": tone_warnings,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }
