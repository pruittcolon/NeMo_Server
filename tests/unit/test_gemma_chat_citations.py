import pytest

from shared.gemma_chat.router import build_chat_history_answer


@pytest.mark.unit
def test_chat_citations_include_labels():
    history = [
        {"role": "user", "content": "First question about compliance"},
        {"role": "assistant", "content": "Answer"},
        {"role": "user", "content": "Second question about risk controls"},
    ]
    result = build_chat_history_answer(history, "go beyond the excerpts and list what I asked")
    labels = {cite["label"] for cite in result["citations"]}
    assert any(label.startswith("U") for label in labels)
    assert all(len(cite.get("quote", "")) <= 160 for cite in result["citations"])
