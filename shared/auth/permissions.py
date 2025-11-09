"""
Authorization Middleware and Permission Helpers
Provides role-based access control and speaker-based data isolation
"""

from fastapi import HTTPException, Cookie, Depends, Request
from typing import Optional, List, Dict, Any
from .auth_manager import get_auth_manager, UserRole, Session, User
from src.config import SecurityConfig as SecConf

def require_auth(request: Request) -> Session:
    """
    Dependency: Require valid authentication
    Works with AuthenticationMiddleware - retrieves pre-validated session from request.state
    Returns session object that was validated by middleware
    """
    # Session is already validated by AuthenticationMiddleware and stored in request.state
    if hasattr(request.state, 'session'):
        return request.state.session
    
    # Fallback: If middleware didn't run (shouldn't happen), do validation here
    ws_session = request.cookies.get(SecConf.SESSION_COOKIE_NAME)
    
    if not ws_session:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated. Please log in."
        )
    
    auth_manager = get_auth_manager()
    session = auth_manager.validate_session(ws_session)
    
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please log in again."
        )
    
    return session

def require_admin(session: Session = Depends(require_auth)) -> Session:
    """
    Dependency: Require ADMIN role
    Returns session if admin, raises 403 if insufficient permissions
    """
    if session.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required. Insufficient permissions."
        )
    
    return session

def get_current_user(session: Session = Depends(require_auth)) -> User:
    """
    Dependency: Get current authenticated user object
    """
    auth_manager = get_auth_manager()
    user = auth_manager.get_user_by_id(session.user_id)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found. Session may be invalid."
        )
    
    return user

def filter_by_speaker(user: User, base_filter: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add speaker filtering for non-admin users
    
    Args:
        user: Current user object
        base_filter: Base query filters
        
    Returns:
        Updated filters with speaker restriction if user is not admin
    """
    if user.role == UserRole.ADMIN:
        # Admin sees everything
        return base_filter
    
    # Non-admin users only see their speaker's data
    filtered = base_filter.copy()
    filtered["speaker_id"] = user.speaker_id
    
    return filtered

def can_access_transcript(user: User, transcript: Dict[str, Any]) -> bool:
    """
    Check if user can access a specific transcript
    
    Args:
        user: Current user object
        transcript: Transcript data with 'speaker' field
        
    Returns:
        True if user can access, False otherwise
    """
    if user.role == UserRole.ADMIN:
        return True
    
    # Check if transcript's speaker matches user's speaker_id
    transcript_speaker = transcript.get("speaker", "").lower()
    user_speaker = (user.speaker_id or "").lower()
    
    return transcript_speaker == user_speaker

def can_access_segment(user: User, segment: Dict[str, Any]) -> bool:
    """
    Check if user can access a specific transcript segment
    
    Args:
        user: Current user object
        segment: Segment data with 'speaker' field
        
    Returns:
        True if user can access, False otherwise
    """
    if user.role == UserRole.ADMIN:
        return True
    
    # Check if segment's speaker matches user's speaker_id
    segment_speaker = segment.get("speaker", "").lower()
    user_speaker = (user.speaker_id or "").lower()
    
    return segment_speaker == user_speaker

def filter_segments_by_speaker(user: User, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter list of segments based on user's speaker access
    
    Args:
        user: Current user object
        segments: List of segment dictionaries
        
    Returns:
        Filtered list (all segments for admin, speaker-filtered for users)
    """
    if user.role == UserRole.ADMIN:
        return segments
    
    # Filter to only user's speaker
    return [seg for seg in segments if can_access_segment(user, seg)]

def filter_transcripts_by_speaker(user: User, transcripts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter list of transcripts based on user's speaker access
    
    Args:
        user: Current user object
        transcripts: List of transcript dictionaries
        
    Returns:
        Filtered list (all transcripts for admin, speaker-filtered for users)
    """
    if user.role == UserRole.ADMIN:
        return transcripts
    
    # Filter to only user's speaker
    return [t for t in transcripts if can_access_transcript(user, t)]

def get_speaker_filter_sql(user: User) -> tuple[str, List[Any]]:
    """
    Get SQL WHERE clause and parameters for speaker filtering
    
    Args:
        user: Current user object
        
    Returns:
        Tuple of (where_clause, params) - empty for admin, filtered for users
    """
    if user.role == UserRole.ADMIN:
        return ("", [])
    
    return ("AND speaker = ?", [user.speaker_id])

def validate_speaker_access(user: User, speaker_id: str) -> None:
    """
    Validate that user can access data for the given speaker
    Raises HTTPException if access denied
    
    Args:
        user: Current user object
        speaker_id: Speaker ID being accessed
    """
    if user.role == UserRole.ADMIN:
        return  # Admin can access any speaker
    
    if user.speaker_id != speaker_id:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. You can only access data for speaker '{user.speaker_id}'."
        )

def get_allowed_speakers(user: User) -> Optional[List[str]]:
    """
    Get list of speakers user is allowed to access
    
    Args:
        user: Current user object
        
    Returns:
        None for admin (all speakers), list with single speaker_id for users
    """
    if user.role == UserRole.ADMIN:
        return None  # All speakers allowed
    
    return [user.speaker_id] if user.speaker_id else []

# Security audit log helper
def log_access_attempt(user: User, resource: str, action: str, success: bool, details: str = ""):
    """
    Log security-relevant access attempts
    
    Args:
        user: User attempting access
        resource: Resource being accessed (e.g., 'transcripts', 'analysis')
        action: Action being performed (e.g., 'read', 'write', 'delete')
        success: Whether access was granted
        details: Additional details about the attempt
    """
    # Import here to avoid circular dependency
    try:
        from src.audit.audit_logger import log_security_event
        log_security_event(
            event_type="access_attempt",
            user_id=user.user_id,
            resource=resource,
            action=action,
            success=success,
            details=details
        )
    except ImportError:
        # Audit logger not yet implemented, skip
        pass
