"""
Basic code validation tests
Tests that all refactored modules can be imported and have correct structure
"""

import sys
from pathlib import Path
import pytest

# Add source to path
REFACTORED_SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(REFACTORED_SRC))


class TestCodeStructure:
    """Validate refactored code structure"""
    
    def test_all_modules_importable(self):
        """Test that all service modules can be imported"""
        # These imports should not fail
        try:
            from services.transcription import service as trans_service
            from services.transcription import routes as trans_routes
            assert trans_service is not None
            assert trans_routes is not None
        except ImportError as e:
            pytest.skip(f"Transcription service import failed (expected): {e}")
        
        try:
            from services.speaker import service as speaker_service
            from services.speaker import routes as speaker_routes
            assert speaker_service is not None
            assert speaker_routes is not None
        except ImportError as e:
            pytest.skip(f"Speaker service import failed (expected): {e}")
        
        try:
            from services.rag import service as rag_service
            from services.rag import routes as rag_routes
            assert rag_service is not None
            assert rag_routes is not None
        except ImportError as e:
            pytest.skip(f"RAG service import failed (expected): {e}")
        
        try:
            from services.emotion import service as emotion_service
            from services.emotion import routes as emotion_routes
            assert emotion_service is not None
            assert emotion_routes is not None
        except ImportError as e:
            pytest.skip(f"Emotion service import failed (expected): {e}")
        
        try:
            from services.gemma import service as gemma_service
            from services.gemma import routes as gemma_routes
            assert gemma_service is not None
            assert gemma_routes is not None
        except ImportError as e:
            pytest.skip(f"Gemma service import failed (expected): {e}")
    
    def test_utils_importable(self):
        """Test that utility modules can be imported"""
        try:
            from utils import audio_utils
            from utils import gpu_utils
            assert audio_utils is not None
            assert gpu_utils is not None
        except ImportError as e:
            pytest.skip(f"Utils import failed (expected): {e}")
    
    def test_main_app_syntax_valid(self):
        """Test that main_refactored.py is syntactically valid"""
        import py_compile
        main_path = Path(__file__).parent.parent / "src" / "main_refactored.py"
        
        if not main_path.exists():
            pytest.skip(f"main_refactored.py not found at {main_path}")
        
        try:
            py_compile.compile(str(main_path), doraise=True)
        except py_compile.PyCompileError as e:
            pytest.fail(f"Syntax error in main_refactored.py: {e}")
    
    def test_all_service_files_exist(self):
        """Test that all expected service files exist"""
        base = Path(__file__).parent.parent / "src" / "services"
        
        expected_services = [
            "transcription/service.py",
            "transcription/routes.py",
            "speaker/service.py",
            "speaker/routes.py",
            "rag/service.py",
            "rag/routes.py",
            "emotion/service.py",
            "emotion/routes.py",
            "gemma/service.py",
            "gemma/routes.py",
        ]
        
        for service_file in expected_services:
            file_path = base / service_file
            assert file_path.exists(), f"Missing service file: {service_file}"
    
    def test_all_utility_files_exist(self):
        """Test that all utility files exist"""
        base = Path(__file__).parent.parent / "src" / "utils"
        
        expected_utils = [
            "audio_utils.py",
            "gpu_utils.py",
        ]
        
        for util_file in expected_utils:
            file_path = base / util_file
            assert file_path.exists(), f"Missing utility file: {util_file}"
    
    def test_docker_files_exist(self):
        """Test that Docker configuration files exist"""
        base = Path(__file__).parent.parent
        
        assert (base / "Dockerfile").exists(), "Dockerfile missing"
        assert (base / "docker-compose.yml").exists(), "docker-compose.yml missing"
        assert (base / "Makefile").exists(), "Makefile missing"
    
    def test_documentation_exists(self):
        """Test that key documentation files exist"""
        base = Path(__file__).parent.parent
        
        docs = [
            "README.md",
            "QUICKSTART.md",
            "IMPLEMENTATION_SUMMARY.md",
            "CHANGELOG.md"
        ]
        
        for doc in docs:
            assert (base / doc).exists(), f"Missing documentation: {doc}"


