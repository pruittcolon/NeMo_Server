import pytest

from shared.gemma_chat.router import (
    classify_chat_intent,
    build_chat_history_answer,
)


@pytest.mark.unit
def test_classify_chat_intent_meta_question():
    assert classify_chat_intent("What did I just ask you?", history=[{"role": "user", "content": "hello"}]) == "chat_history"


@pytest.mark.unit
def test_classify_chat_intent_artifact_question():
    assert classify_chat_intent("Where did that come from?", history=[{"role": "user", "content": "hello"}]) == "artifact"


@pytest.mark.unit
def test_build_chat_history_answer_last_question():
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "How are sales?"},
    ]
    result = build_chat_history_answer(history, "what did I just ask?")
    assert "How are sales" in result["text"]
    assert result["strategy"] == "chat_history"
    assert result["citations"]
    assert result["citations"][0]["type"] == "chat"


@pytest.mark.unit
def test_build_chat_history_answer_summary():
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "Need recap"},
        {"role": "assistant", "content": "Sure"},
    ]
    result = build_chat_history_answer(history, "summarize this chat", summarize=True)
    assert result["strategy"] == "chat_summary"
    assert result["citations"]
    assert result["citations"][0]["type"] == "chat"


@pytest.mark.unit
def test_build_chat_history_answer_eight_words():
    history = [
        {"role": "user", "content": "We should review compliance gaps in detail"},
        {"role": "assistant", "content": "Sure let's review them now"},
    ]
    result = build_chat_history_answer(history, "give me an eight word sentence summarizing this")
    words = result["text"].split()
    assert len(words) == 8
    assert result["strategy"] == "chat_eight_words"
    assert result["citations"]
