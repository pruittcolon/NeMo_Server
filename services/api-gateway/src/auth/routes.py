"""
Enhanced Authentication API Routes
With audit logging, rate limiting, and encrypted sessions
"""

import secrets
from fastapi import APIRouter, HTTPException, Response, Request, Depends, Cookie
from pydantic import BaseModel
from typing import Optional, List
from .auth_manager import get_auth_manager, UserRole
from .permissions import require_auth, require_admin, get_current_user
from src.audit.audit_logger import get_audit_logger
from src import config

router = APIRouter(prefix="/api/auth", tags=["authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False

class LoginResponse(BaseModel):
    success: bool
    session_token: Optional[str] = None
    user: Optional[dict] = None
    message: Optional[str] = None
    csrf_token: Optional[str] = None

class SessionResponse(BaseModel):
    valid: bool
    user: Optional[dict] = None

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

class UserListResponse(BaseModel):
    users: List[dict]

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, req: Request, response: Response):
    """
    Authenticate user and create encrypted session
    Sets httpOnly cookie with session token
    """
    auth_manager = get_auth_manager()
    audit_logger = get_audit_logger()
    
    ip_address = req.client.host if req.client else "unknown"
    
    # Authenticate
    session_token = auth_manager.authenticate(
        username=request.username,
        password=request.password,
        ip_address=ip_address
    )
    
    if not session_token:
        # Log failed login
        audit_logger.log_login(
            username=request.username,
            ip_address=ip_address,
            success=False,
            details="Invalid credentials"
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_info = auth_manager.get_user_info(session_token)
    session = auth_manager.validate_session(session_token)
    csrf_token = session.csrf_token if session and session.csrf_token else secrets.token_hex(32)
    
    # Log successful login
    audit_logger.log_login(
        username=request.username,
        ip_address=ip_address,
        success=True,
        details=f"Role: {user_info.get('role')}, Speaker: {user_info.get('speaker_id')}"
    )
    
    # Set httpOnly cookie
    max_age = 2592000 if request.remember_me else 86400  # 30 days vs 24 hours
    response.set_cookie(
        key="ws_session",
        value=session_token,
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=max_age
    )
    response.set_cookie(
        key=config.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=config.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=max_age
    )
    
    return LoginResponse(
        success=True,
        session_token=session_token,
        user=user_info,
        message="Login successful",
        csrf_token=csrf_token
    )

@router.get("/check", response_model=SessionResponse)
async def check_session(ws_session: Optional[str] = Cookie(None)):
    """
    Validate current session
    Called by frontend on page load
    """
    if not ws_session:
        return SessionResponse(valid=False, user=None)
    
    auth_manager = get_auth_manager()
    session = auth_manager.validate_session(ws_session)
    
    if not session:
        return SessionResponse(valid=False, user=None)
    
    user_info = auth_manager.get_user_info(ws_session)
    return SessionResponse(valid=True, user=user_info)

@router.post("/logout")
async def logout(req: Request, response: Response, ws_session: Optional[str] = Cookie(None)):
    """
    End session and clear cookie
    """
    auth_manager = get_auth_manager()
    audit_logger = get_audit_logger()
    
    if ws_session:
        session = auth_manager.validate_session(ws_session)
        if session:
            ip_address = req.client.host if req.client else "unknown"
            audit_logger.log_logout(
                user_id=session.user_id,
                ip_address=ip_address
            )
        auth_manager.logout(ws_session)
    
    response.delete_cookie(key="ws_session")
    response.delete_cookie(key=config.CSRF_COOKIE_NAME)
    return {"success": True, "message": "Logged out"}

@router.get("/user")
async def get_current_user_info(user = Depends(get_current_user)):
    """
    Get current user information
    """
    return {
        "user_id": user.user_id,
        "username": user.username,
        "role": user.role.value,
        "speaker_id": user.speaker_id,
        "email": user.email
    }

@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    req: Request,
    user = Depends(get_current_user)
):
    """
    Change user password
    Requires current password verification
    """
    auth_manager = get_auth_manager()
    audit_logger = get_audit_logger()
    
    success = auth_manager.change_password(
        username=user.username,
        old_password=request.old_password,
        new_password=request.new_password
    )
    
    ip_address = req.client.host if req.client else "unknown"
    
    if success:
        audit_logger.log_password_change(
            user_id=user.user_id,
            ip_address=ip_address,
            success=True
        )
        return {"success": True, "message": "Password changed successfully"}
    else:
        audit_logger.log_password_change(
            user_id=user.user_id,
            ip_address=ip_address,
            success=False
        )
        raise HTTPException(status_code=401, detail="Current password is incorrect")

@router.get("/users", response_model=UserListResponse)
async def list_users(admin_session = Depends(require_admin)):
    """
    List all users (admin only)
    """
    auth_manager = get_auth_manager()
    users = auth_manager.list_users()
    return UserListResponse(users=users)

@router.get("/rate-limit/status")
async def get_rate_limit_status(req: Request, user = Depends(get_current_user)):
    """
    Get current rate limit status for user
    """
    from src.middleware.rate_limiter import get_rate_limiter
    
    rate_limiter = get_rate_limiter()
    ip_address = req.client.host if req.client else "unknown"
    
    status = rate_limiter.get_status(ip_address)
    
    return {
        "ip_address": ip_address,
        "user_id": user.user_id,
        "limits": status
    }

# Helper dependency for role checking
def require_role(role: UserRole):
    """Dependency factory that requires specific role"""
    def role_checker(ws_session: Optional[str] = Cookie(None)):
        if not ws_session:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        auth_manager = get_auth_manager()
        if not auth_manager.check_permission(ws_session, role):
            session = auth_manager.validate_session(ws_session)
            user_role = session.role.value if session else "unknown"
            raise HTTPException(
                status_code=403, 
                detail=f"Insufficient permissions. Required: {role.value}, Your role: {user_role}"
            )
        
        return ws_session
    return role_checker

@router.get("/admin/test")
async def admin_only_route(session = Depends(require_admin)):
    """Example: Admin-only endpoint"""
    return {"message": "Welcome, admin!", "user_id": session.user_id}
