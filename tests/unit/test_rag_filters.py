import importlib.util
import pathlib
import sys
import types


# Provide lightweight stubs for optional heavy dependencies so we can import the module.
if "faiss" not in sys.modules:
    class _FakeIndex:
        def __init__(self, dim: int = 0):
            self.dim = dim
            self.ntotal = 0

        def add(self, embeddings):
            self.ntotal += len(embeddings)

    fake_faiss = types.ModuleType("faiss")
    fake_faiss.IndexFlatIP = lambda dim: _FakeIndex(dim)
    fake_faiss.read_index = lambda path: _FakeIndex()
    sys.modules["faiss"] = fake_faiss

if "sentence_transformers" not in sys.modules:
    class _DummySentenceTransformer:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("SentenceTransformer should not be instantiated in unit tests")

    fake_st = types.ModuleType("sentence_transformers")
    fake_st.SentenceTransformer = _DummySentenceTransformer
    sys.modules["sentence_transformers"] = fake_st


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
RAG_MAIN_PATH = PROJECT_ROOT / "services" / "rag-service" / "src" / "main.py"

spec = importlib.util.spec_from_file_location("rag_main", RAG_MAIN_PATH)
rag_main = importlib.util.module_from_spec(spec)
assert spec.loader is not None  # narrow type checker
spec.loader.exec_module(rag_main)


RAGService = rag_main.RAGService


def test_normalize_filter_list_handles_mixed_inputs():
    normalize = RAGService._normalize_filter_list

    assert normalize(None) == []
    assert normalize("anger") == ["anger"]
    assert normalize(["joy", "fear"]) == ["joy", "fear"]

    mixed = [{"value": "sadness"}, {"speaker": "Agent"}, "surprise", {"unknown": "keep"}]
    assert normalize(mixed) == ["sadness", "Agent", "surprise", "{'unknown': 'keep'}"]


class _StubRAG(RAGService):
    def __init__(self, emotion_column: str = "emotion"):
        self.emotion_column = emotion_column

    # Reuse statics as instance methods for the builder under test
    def _normalize_filter_list(self, value):
        return RAGService._normalize_filter_list(value)

    def _escape_like(self, value: str) -> str:
        return RAGService._escape_like(value)


def test_build_segment_filters_uses_detected_emotion_column():
    stub = _StubRAG(emotion_column="dominant_emotion")

    filters = {"emotions": ["Joy"], "speakers": "Agent"}
    conditions, params = RAGService._build_segment_filters(stub, filters)

    joined = " AND ".join(conditions)
    assert "LOWER(COALESCE(ts.dominant_emotion" in joined
    assert any("LOWER(ts.speaker)" in clause for clause in conditions)
    assert params == ["agent", "joy"]


def test_keyword_filters_escape_wildcards():
    stub = _StubRAG()
    filters = {
        "keywords": "100% guarantee, _hidden",
        "match": "all",
        "search_type": "keyword",
    }
    conditions, params = RAGService._build_segment_filters(stub, filters)

    assert len(params) == 2
    assert params[0] == "%100\\% guarantee%"
    assert params[1] == "%\\_hidden%"
    assert all("LIKE ?" in clause for clause in conditions if "LIKE" in clause)
