import importlib.util
import pathlib
import sys
import types
import tempfile
from pathlib import Path


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
assert spec.loader is not None
spec.loader.exec_module(rag_main)


def _make_rag(tmpdir: Path):
    db_path = tmpdir / "rag_artifacts.db"
    faiss_path = tmpdir / "index.bin"
    return rag_main.RAGService(db_path=db_path, faiss_index_path=faiss_path, embedding_model_name="dummy", db_encryption_key=None)


def test_archive_and_get_artifact(tmp_path: Path):
    rag = _make_rag(tmp_path)
    aid = rag.archive_analysis_artifact(
        artifact_id=None,
        analysis_id="a123",
        title="Test Artifact",
        body="This is a test body. Hello world.",
        metadata={"user_id": "u1"},
        index_body=False,
    )
    assert isinstance(aid, str) and len(aid) > 0
    art = rag.get_analysis_artifact(aid)
    assert art and art["title"] == "Test Artifact"
    assert "Hello" in art["body"]


def test_list_artifacts_pagination(tmp_path: Path):
    rag = _make_rag(tmp_path)
    # create several artifacts
    for i in range(7):
        rag.archive_analysis_artifact(
            artifact_id=None,
            analysis_id=f"run{i}",
            title=f"Run {i}",
            body=f"Body {i}",
            metadata={"user_id": "u1"},
            index_body=False,
        )
    page1 = rag.list_analysis_artifacts(limit=5, offset=0, user_id="u1")
    assert page1["count"] == 5 and page1["has_more"] is True
    page2 = rag.list_analysis_artifacts(limit=5, offset=5, user_id="u1")
    assert page2["count"] == 2 and page2["has_more"] is False


def test_search_artifacts_keyword(tmp_path: Path):
    rag = _make_rag(tmp_path)
    rag.archive_analysis_artifact(
        artifact_id=None,
        analysis_id="a1",
        title="Interesting summary",
        body="The system discovered hyperbolic language and fallacies.",
        metadata={},
        index_body=False,
    )
    rag.archive_analysis_artifact(
        artifact_id=None,
        analysis_id="a2",
        title="Boring",
        body="Nothing to see here.",
        metadata={},
        index_body=False,
    )
    items = rag.search_analysis_artifacts("hyperbolic", limit=10)
    assert any("hyperbolic" in (it.get("preview") or "").lower() for it in items)

