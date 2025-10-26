"""
Shared pytest configuration and fixtures for WhisperServer REFACTORED tests

Provides:
- Mock model loaders (avoids VRAM usage)
- Test database setup
- Audio fixtures
- Test client configuration
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Generator
import pytest
import numpy as np

# Add source directories to path
REFACTORED_SRC = Path(__file__).parent.parent / "src"
ORIGINAL_SRC = Path(__file__).parent.parent.parent / "src"

if str(REFACTORED_SRC) not in sys.path:
    sys.path.insert(0, str(REFACTORED_SRC))
if str(ORIGINAL_SRC) not in sys.path:
    sys.path.insert(0, str(ORIGINAL_SRC))


# ============================================================================
# Test Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")
    config.addinivalue_line("markers", "gpu: marks tests that require GPU")
    config.addinivalue_line("markers", "live: marks tests that need live services")


# ============================================================================
# Mock Model Fixtures (Avoid VRAM Usage)
# ============================================================================

@pytest.fixture(scope="session")
def mock_nemo_asr_model(monkeypatch_session):
    """Mock NeMo ASR model to avoid loading real model"""
    class MockASRModel:
        def eval(self):
            pass
        
        def transcribe(self, paths, batch_size=1, timestamps=True):
            """Return mock transcription"""
            class MockHypothesis:
                text = "This is a test transcription."
                timestep = {
                    "segment": [
                        {"start": 0.0, "end": 2.0, "segment": "This is a test"},
                        {"start": 2.0, "end": 4.0, "segment": "transcription."}
                    ]
                }
            return [MockHypothesis()]
    
    return MockASRModel()


@pytest.fixture(scope="session")
def mock_speaker_model():
    """Mock TitaNet speaker model"""
    class MockSpeakerModel:
        def eval(self):
            pass
        
        def get_embedding(self, audio_path):
            """Return mock 192-dim embedding"""
            class MockTensor:
                def detach(self):
                    return self
                def cpu(self):
                    return self
                def numpy(self):
                    return np.random.randn(192).astype(np.float32)
                def reshape(self, *args):
                    return np.random.randn(192).astype(np.float32)
            return MockTensor()
    
    return MockSpeakerModel()


@pytest.fixture(scope="session")
def mock_embedding_model():
    """Mock SentenceTransformer embedding model"""
    class MockEmbeddingModel:
        def encode(self, texts, **kwargs):
            """Return mock embeddings"""
            if isinstance(texts, str):
                return np.random.randn(384).astype(np.float32)
            return np.random.randn(len(texts), 384).astype(np.float32)
    
    return MockEmbeddingModel()


@pytest.fixture(scope="session")
def mock_emotion_classifier():
    """Mock DistilRoBERTa emotion classifier"""
    def mock_analyze_emotion(text):
        return {
            "dominant_emotion": "neutral",
            "confidence": 0.85,
            "emotions": {
                "anger": 0.05,
                "disgust": 0.02,
                "fear": 0.03,
                "joy": 0.10,
                "neutral": 0.70,
                "sadness": 0.05,
                "surprise": 0.05
            }
        }
    return mock_analyze_emotion


@pytest.fixture(scope="session")
def mock_gemma_llm():
    """Mock Gemma LLM"""
    class MockGemma:
        def __call__(self, prompt, **kwargs):
            return {
                "choices": [{
                    "text": "This is a mock Gemma response.",
                    "finish_reason": "stop"
                }]
            }
    return MockGemma()


# ============================================================================
# Test Audio Fixtures
# ============================================================================

@pytest.fixture
def test_audio_array():
    """Generate test audio array (1 second, 16kHz, mono)"""
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0  # A4 note
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = np.sin(2 * np.pi * frequency * t).astype(np.float32)
    return audio


@pytest.fixture
def test_audio_file(test_audio_array, tmp_path):
    """Create temporary WAV file"""
    import soundfile as sf
    
    wav_path = tmp_path / "test_audio.wav"
    sf.write(str(wav_path), test_audio_array, 16000)
    return str(wav_path)


@pytest.fixture
def test_audio_bytes(test_audio_file):
    """Read audio file as bytes"""
    with open(test_audio_file, "rb") as f:
        return f.read()


# ============================================================================
# Test Database Fixtures
# ============================================================================

@pytest.fixture
def test_db_path(tmp_path):
    """Create temporary SQLite database"""
    db_path = tmp_path / "test_memory.db"
    return str(db_path)


@pytest.fixture
def test_faiss_index_path(tmp_path):
    """Create temporary FAISS index path"""
    index_path = tmp_path / "test_faiss_index.bin"
    return str(index_path)


# ============================================================================
# Test Client Fixtures
# ============================================================================

@pytest.fixture
def test_upload_dir(tmp_path):
    """Create temporary upload directory"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    return str(upload_dir)


@pytest.fixture
def test_enrollment_dir(tmp_path):
    """Create temporary enrollment directory"""
    enroll_dir = tmp_path / "enrollment"
    enroll_dir.mkdir()
    return str(enroll_dir)


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_transcript_segments():
    """Sample transcription segments"""
    return [
        {
            "start": 0.0,
            "end": 2.5,
            "text": "Hello, how are you doing today?",
            "speaker": "Pruitt",
            "emotion": "neutral",
            "emotion_confidence": 0.85
        },
        {
            "start": 2.5,
            "end": 4.8,
            "text": "I'm doing great, thanks for asking!",
            "speaker": "Ericah",
            "emotion": "joy",
            "emotion_confidence": 0.92
        }
    ]


@pytest.fixture
def sample_speaker_embeddings():
    """Sample 192-dim speaker embeddings"""
    return {
        "pruitt": np.random.randn(192).astype(np.float32),
        "ericah": np.random.randn(192).astype(np.float32)
    }


# ============================================================================
# Session-scoped Fixtures (Expensive Setup)
# ============================================================================

@pytest.fixture(scope="session")
def docker_compose_file():
    """Path to test docker-compose file"""
    return str(Path(__file__).parent.parent / "docker-compose.test.yml")


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped monkeypatch"""
    from _pytest.monkeypatch import MonkeyPatch
    m = MonkeyPatch()
    yield m
    m.undo()


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_temp_files():
    """Clean up temporary files after each test"""
    yield
    # Cleanup happens automatically with tmp_path fixtures


# ============================================================================
# GPU Test Helpers
# ============================================================================

@pytest.fixture
def check_gpu_available():
    """Check if GPU is available"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


@pytest.fixture
def skip_if_no_gpu(check_gpu_available):
    """Skip test if GPU not available"""
    if not check_gpu_available:
        pytest.skip("GPU not available")


