import pytest

from shared.gemma_chat.router import (
    classify_chat_intent,
    build_chat_history_answer,
    format_chat_history_for_prompt,
)


@pytest.mark.integration
def test_chat_history_workflow_general():
    history = [
        {"role": "user", "content": "Let's discuss compliance gaps"},
        {"role": "assistant", "content": "Sure, what gaps?"},
        {"role": "user", "content": "Specifically the audit trail and missing approvals"},
        {"role": "assistant", "content": "We noted missing approvals yesterday."},
    ]
    intent = classify_chat_intent("go beyond the excerpts and recap our chat", history)
    assert intent == "chat_history"
    answer = build_chat_history_answer(history, "go beyond the excerpts and recap our chat")
    assert "chat" in answer["text"].lower()
    assert answer["citations"]
    prompt = format_chat_history_for_prompt(history, limit=4)
    assert "[U1]" in prompt and "[A2]" in prompt
