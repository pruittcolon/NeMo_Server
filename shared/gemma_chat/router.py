"""Chat intent classification and summary helpers for Gemma chat drawer."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

CHAT_SUMMARY_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"summaris(e|ze) (this|our|the) chat"),
    re.compile(r"summaris(e|ze) (entire|whole) conversation"),
    re.compile(r"recap (this|our) (chat|conversation)"),
    re.compile(r"entire chat so far"),
]

CHAT_META_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"what did i (just )?(ask|say)"),
    re.compile(r"what was (my|the) (last|previous) question"),
    re.compile(r"what did i ask before (that|this)"),
    re.compile(r"before (that|this) what did i"),
    re.compile(r"go beyond the excerpts"),
    re.compile(r"based on (our|this) chat"),
    re.compile(r"from the conversation"),
    re.compile(r"conversation (history|context)"),
    re.compile(r"\b(eight|8)[ -]*(word|words)\b"),
]

EIGHT_WORD_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"\b(eight|8)[ -]*(word|words)\b"),
    re.compile(r"\b8-word\b"),
]

CHAT_METHOD_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"how did you (arrive|decide)"),
    re.compile(r"explain (your )?method"),
    re.compile(r"what approach did you use"),
    re.compile(r"prompt you used"),
]

ARTIFACT_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"artifact"),
    re.compile(r"document"),
    re.compile(r"transcript"),
    re.compile(r"chunk"),
    re.compile(r"paragraph"),
    re.compile(r"section"),
    re.compile(r"cite"),
    re.compile(r"where did that (come from|originate|source)"),
]

CHAT_ACTION_PATTERNS = {
    "last_user": [
        re.compile(r"what did i (just )?(ask|say)"),
        re.compile(r"my last question"),
    ],
    "previous_user": [
        re.compile(r"what did i ask before"),
        re.compile(r"before (that|this) what did i"),
        re.compile(r"previous question before"),
    ],
    "last_assistant": [
        re.compile(r"what did you (just )?(say|tell me)"),
        re.compile(r"your last answer"),
    ],
    "summarize": list(CHAT_SUMMARY_PATTERNS),
    "eight_words": list(EIGHT_WORD_PATTERNS),
    "contextual": [re.compile(r"go beyond the excerpts"), re.compile(r"beyond the excerpts")],
}

STOPWORDS = {"the", "and", "you", "that", "this", "with", "from", "your", "have", "just", "what", "about", "here", "there", "into", "they", "them"}
FALLBACK_EIGHT_WORDS = [
    "conversation",
    "context",
    "insight",
    "pending",
    "further",
    "detail",
    "needed",
    "now",
]


def classify_chat_intent(message: str, history: Optional[Sequence[Dict[str, str]]] = None) -> str:
    """Heuristically classify whether a chat question needs artifact or history."""
    text = (message or "").strip().lower()
    if not text:
        return "clarify"

    meta_hit = any(pattern.search(text) for pattern in CHAT_META_PATTERNS)
    summary_hit = any(pattern.search(text) for pattern in CHAT_SUMMARY_PATTERNS)
    if meta_hit:
        return "chat_history"
    if summary_hit:
        return "chat_summary"
    if any(pattern.search(text) for pattern in CHAT_METHOD_PATTERNS):
        return "method"
    if "methodology" in text or "prompt" in text:
        return "method"
    if "chat" in text and "summar" in text:
        return "chat_summary"

    artifact_hits = sum(1 for pattern in ARTIFACT_PATTERNS if pattern.search(text))
    if artifact_hits:
        return "artifact"

    # If the conversation is short, default to artifact so the assistant provides context.
    if not history or len(history) < 2:
        return "artifact"

    # Fallback: assume artifact unless the user explicitly references conversation
    if "conversation" in text or "chat" in text:
        return "chat_history"
    return "artifact"


def infer_chat_action(message: str) -> str:
    text = (message or "").strip().lower()
    if not text:
        return "general"
    for action, patterns in CHAT_ACTION_PATTERNS.items():
        if any(pattern.search(text) for pattern in patterns):
            return action
    if "summarize" in text or "recap" in text:
        return "summarize"
    if "conversation" in text or "chat" in text:
        return "contextual"
    return "general"


def _normalize_role(role: Optional[str]) -> str:
    if not role:
        return "user"
    role_lower = role.lower()
    if role_lower.startswith("assist"):
        return "assistant"
    if role_lower.startswith("system"):
        return "system"
    return "user"


def _enumerate_chat_messages(messages: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {"user": 0, "assistant": 0, "system": 0}
    labeled: List[Dict[str, Any]] = []
    for msg in messages:
        role = _normalize_role(msg.get("role"))
        counts[role] = counts.get(role, 0) + 1
        prefix = "U" if role == "user" else ("A" if role == "assistant" else "S")
        label = f"{prefix}{counts[role]}"
        labeled.append({
            "role": role,
            "content": (msg.get("content") or "").strip(),
            "label": label,
        })
    return labeled


def _shorten(text: str, limit: int = 200) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "…"


def _get_nth_latest(entries: Sequence[Dict[str, Any]], role: str, n: int) -> Optional[Dict[str, Any]]:
    count = 0
    for entry in reversed(entries):
        if entry["role"] == role:
            count += 1
            if count == n:
                return entry
    return None


def _chat_citation(entry: Dict[str, Any], score: float = 1.0) -> Dict[str, Any]:
    return {
        "type": "chat",
        "role": entry["role"],
        "label": entry["label"],
        "index": entry["label"],
        "quote": _shorten(entry.get("content") or "", 160),
        "score": float(score),
    }


def _score_chat_entries(entries: Sequence[Dict[str, Any]], query: str, top_k: int = 3) -> List[Tuple[Dict[str, Any], float]]:
    text = (query or "").lower()
    tokens = [tok for tok in re.findall(r"[a-z0-9']+", text) if tok not in STOPWORDS]
    if not tokens:
        return []
    results: List[Tuple[Dict[str, Any], float]] = []
    for entry in entries:
        content = entry.get("content", "").lower()
        score = sum(1.0 for token in tokens if token in content)
        if score > 0:
            results.append((entry, score))
    results.sort(key=lambda item: (item[1], item[0]["label"]), reverse=True)
    return results[:top_k]


def _summarize_entries(entries: Sequence[Dict[str, Any]], max_items: int = 8) -> Tuple[str, List[Dict[str, Any]]]:
    slice_entries = list(entries[-max_items:])
    lines = []
    for entry in slice_entries:
        prefix = "You" if entry["role"] == "user" else "I"
        verb = "asked" if entry["role"] == "user" else "responded"
        lines.append(f"- [{entry['label']}] {prefix} {verb}: {_shorten(entry['content'], 160)}")
    summary = "Here is a quick recap of our chat so far:\n" + "\n".join(lines)
    return summary, slice_entries


def _build_eight_word_sentence(entries: Sequence[Dict[str, Any]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Compose a deterministic eight-word sentence from recent conversation."""
    recent_entries = list(entries[-4:]) or list(entries)
    source_entry = None
    if recent_entries:
        # Prefer the latest user entry; fallback to the latest entry of any role
        for entry in reversed(recent_entries):
            if entry["role"] == "user":
                source_entry = entry
                break
        if source_entry is None:
            source_entry = recent_entries[-1]
    corpus = " ".join(entry["content"] for entry in recent_entries if entry.get("content"))
    tokens = [tok.lower() for tok in re.findall(r"[a-z0-9']+", corpus)]
    keywords: List[str] = []
    for token in tokens:
        if token in STOPWORDS or len(token) <= 2:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) == 8:
            break
    if len(keywords) < 8:
        for token in tokens:
            if token not in keywords:
                keywords.append(token)
            if len(keywords) == 8:
                break
    if len(keywords) < 8:
        keywords.extend(FALLBACK_EIGHT_WORDS[: 8 - len(keywords)])
    if not keywords:
        keywords = FALLBACK_EIGHT_WORDS.copy()
    sentence = " ".join(keywords[:8])
    return sentence.strip(), source_entry


def build_chat_history_answer(
    history: Sequence[Dict[str, str]],
    question: str,
    summarize: bool = False,
) -> Dict[str, Any]:
    entries = _enumerate_chat_messages(history)
    if not entries:
        return {
            "text": "I don't have any prior messages to reference yet.",
            "citations": [],
            "strategy": "chat_history",
            "action": "none",
        }

    action = infer_chat_action(question)
    if summarize or action == "summarize":
        summary, used_entries = _summarize_entries(entries)
        return {
            "text": summary,
            "citations": [_chat_citation(entry) for entry in used_entries],
            "strategy": "chat_summary",
            "action": "summarize",
        }

    if action == "last_user":
        entry = _get_nth_latest(entries, "user", 1)
        if entry:
            text = f"Your most recent question ([{entry['label']}]) was:\n{entry['content']}"
            return {
                "text": text,
                "citations": [_chat_citation(entry)],
                "strategy": "chat_history",
                "action": action,
            }
    elif action == "previous_user":
        entry = _get_nth_latest(entries, "user", 2)
        if entry:
            text = f"The question before that ([{entry['label']}]) was:\n{entry['content']}"
            return {
                "text": text,
                "citations": [_chat_citation(entry)],
                "strategy": "chat_history",
                "action": action,
            }
        else:
            entry = _get_nth_latest(entries, "user", 1)
            if entry:
                text = (
                    "I only have one prior user question. Here it is:\n"
                    f"[{entry['label']}] {entry['content']}"
                )
                return {
                    "text": text,
                    "citations": [_chat_citation(entry)],
                    "strategy": "chat_history",
                    "action": action,
                }
    elif action == "last_assistant":
        entry = _get_nth_latest(entries, "assistant", 1)
        if entry:
            text = f"My last response ([{entry['label']}]) was:\n{entry['content']}"
            return {
                "text": text,
                "citations": [_chat_citation(entry)],
                "strategy": "chat_history",
                "action": action,
            }
    elif action == "eight_words":
        sentence, source_entry = _build_eight_word_sentence(entries)
        citations = [_chat_citation(source_entry)] if source_entry else []
        return {
            "text": sentence,
            "citations": citations,
            "strategy": "chat_eight_words",
            "action": action,
        }

    scored = _score_chat_entries(entries, question)
    if not scored:
        scored = [(entry, 0.0) for entry in entries[-3:]]
    lines = []
    for entry, _ in scored:
        prefix = "You asked" if entry["role"] == "user" else "I answered"
        lines.append(f"- [{entry['label']}] {prefix}: {_shorten(entry['content'], 200)}")
    header = "Here are the most relevant parts of our conversation:" if action != "contextual" else (
        "Per your request to rely on our chat history, here is what we've covered:" + ""
    )
    answer = header + "\n" + "\n".join(lines)
    return {
        "text": answer,
        "citations": [_chat_citation(entry, score) for entry, score in scored],
        "strategy": "chat_history",
        "action": action,
    }


def format_chat_history_for_prompt(messages: Sequence[Dict[str, str]], limit: int = 14) -> str:
    if not messages:
        return ""
    entries = _enumerate_chat_messages(messages[-limit:])
    lines = []
    for entry in entries:
        role = "USER" if entry["role"] == "user" else ("ASSISTANT" if entry["role"] == "assistant" else "SYSTEM")
        lines.append(f"[{entry['label']}] {role}: {entry['content']}")
    return "\n".join(lines)
