import pytest

from shared.gemma_chat.conversation_utils import (
    analyze_tone,
    build_conversation_health,
    extract_questions,
    is_meta_question,
    tag_question,
)


def test_extract_questions_recognizes_multiple_sentences():
    prompt = "What are the risks? Should I escalate now? Provide options."
    questions = extract_questions(prompt)
    assert questions == ["What are the risks?", "Should I escalate now?"]


def test_is_meta_question_detects_variations():
    assert is_meta_question("What questions have I asked you so far?")
    assert is_meta_question("Can you list the questions I asked earlier?")
    assert not is_meta_question("What are the next steps?")


def test_tag_question_applies_domain_tags():
    tags = tag_question("Which metrics prove success for the program?")
    assert "metrics" in tags
    assert "general" not in tags


def test_analyze_tone_marks_failures():
    tone = analyze_tone("I'm sorry, but I cannot help you with that request.")
    assert tone["status"] == "fail"
    assert "apology" in tone["warnings"]


def test_conversation_health_reflects_tone():
    tone = {"status": "warn", "warnings": ["limitation"]}
    meta = {"turn_count": 4, "question_count": 2}
    health = build_conversation_health(meta, tone)
    assert health["status"] == "watch"
    assert health["turn_count"] == 4
    assert health["question_count"] == 2
