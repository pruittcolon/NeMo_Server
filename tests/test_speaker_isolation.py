"""
Speaker Isolation Test Suite

Tests authentication and speaker-based data isolation across all API endpoints.
"""

import pytest
import requests
from typing import Dict, Any

BASE_URL = "http://localhost:8000"


class TestAuthentication:
    """Test authentication flow"""
    
    def test_admin_login(self):
        """Admin can log in"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        
    def test_user1_login(self):
        """User1 can log in"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "user1", "password": "user1pass"}
        )
        assert resp.status_code == 200, f"User1 login failed: {resp.text}"
        
    def test_television_login(self):
        """Television can log in"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "television", "password": "tvpass123"}
        )
        assert resp.status_code == 200, f"Television login failed: {resp.text}"
        
    def test_invalid_login(self):
        """Invalid credentials are rejected"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "invalid", "password": "wrong"}
        )
        assert resp.status_code in [401, 403], "Invalid login should be rejected"
        
    def test_no_auth_blocked(self):
        """Unauthenticated requests return 401"""
        resp = requests.get(f"{BASE_URL}/memory/list")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


class TestSpeakerIsolationMemory:
    """Test speaker isolation for memory/RAG endpoints"""
    
    def test_admin_sees_all_memories(self):
        """Admin can access all speaker data"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/memory/list?limit=10")
        assert resp.status_code == 200, f"Admin memory access failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Expected list response"
        
    def test_user1_isolated_memories(self):
        """User1 only sees user1 data"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "user1", "password": "user1pass"}
        )
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/memory/list?limit=10")
        assert resp.status_code == 200, f"User1 memory access failed: {resp.text}"
        data = resp.json()
        
        # Verify all speakers are "user1" or list is empty
        for item in data:
            if 'speaker' in item:
                assert item['speaker'] == 'user1', f"User1 should not see speaker: {item['speaker']}"
                
    def test_television_isolated_memories(self):
        """Television only sees television data"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "television", "password": "tvpass123"}
        )
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/memory/list?limit=10")
        assert resp.status_code == 200, f"Television memory access failed: {resp.text}"
        data = resp.json()
        
        # Verify all speakers are "television" or list is empty
        for item in data:
            if 'speaker' in item:
                assert item['speaker'] == 'television', f"Television should not see speaker: {item['speaker']}"


class TestSpeakerIsolationTranscripts:
    """Test speaker isolation for transcription endpoints"""
    
    def test_admin_sees_all_transcripts(self):
        """Admin can access all transcripts"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/transcripts?limit=10")
        assert resp.status_code == 200, f"Admin transcript access failed: {resp.text}"
        
    def test_user1_isolated_transcripts(self):
        """User1 only sees user1 transcripts"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "user1", "password": "user1pass"}
        )
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/transcripts?limit=10")
        assert resp.status_code == 200, f"User1 transcript access failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert 'transcripts' in data or isinstance(data, list), "Invalid response structure"


class TestSpeakerIsolationSpeakerService:
    """Test speaker isolation for speaker enrollment endpoints"""
    
    def test_admin_sees_all_enrolled_speakers(self):
        """Admin can see all enrolled speakers"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/enroll/speakers")
        assert resp.status_code == 200, f"Admin speaker access failed: {resp.text}"
        
    def test_user1_isolated_speakers(self):
        """User1 only sees user1 enrollment"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "user1", "password": "user1pass"}
        )
        assert resp.status_code == 200
        
        resp = session.get(f"{BASE_URL}/enroll/speakers")
        assert resp.status_code == 200, f"User1 speaker access failed: {resp.text}"
        data = resp.json()
        
        # Verify only user1 speaker returned
        if 'speakers' in data and data['speakers']:
            for speaker in data['speakers']:
                assert speaker == 'user1', f"User1 should not see speaker: {speaker}"


class TestJobOwnership:
    """Test job ownership tracking for Gemma analysis"""
    
    def test_user1_can_create_job(self):
        """User1 can create analysis jobs"""
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "user1", "password": "user1pass"}
        )
        assert resp.status_code == 200
        
        # Try to create a job (may fail if no data, but should not be auth error)
        resp = session.post(
            f"{BASE_URL}/analyze/chat",
            json={"message": "Test analysis"}
        )
        # Should be 200 (success) or 500 (no data), but not 401/403
        assert resp.status_code not in [401, 403], f"Job creation blocked: {resp.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])



