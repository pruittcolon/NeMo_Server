# Speaker-Based Data Isolation

## Overview

Nemo Server implements **100% speaker-based data isolation** to ensure that users can only access transcripts, memories, and analysis results for their assigned speaker identity.

This document explains how speaker isolation works, how it's enforced, and how to use it.

---

## Architecture

### Authentication System

**File**: `src/auth/auth_manager.py`

The authentication system manages users, sessions, and role-based access:

```python
class User:
    user_id: str
    username: str
    password_hash: str
    role: UserRole  # ADMIN or USER
    speaker_id: Optional[str]  # Key field for isolation
    email: Optional[str]
    created_at: Optional[float]
    modified_at: Optional[float]

class Session:
    session_token: str
    user_id: str
    role: UserRole
    speaker_id: Optional[str]  # Copied from User for fast lookups
    created_at: float
    expires_at: float
    ip_address: Optional[str]
    last_refresh: Optional[float]
```

### Key Concepts

1. **speaker_id** links a User to a speaker identity (e.g., "user1", "television")
2. **Admin users** have `speaker_id = None` and can see ALL speakers
3. **Regular users** have a specific `speaker_id` and can ONLY see that speaker's data
4. **Sessions** store the `speaker_id` for fast access control checks

---

## Default Users

### Admin User
- **Username**: `admin`
- **Password**: `admin123` ⚠️ CHANGE IN PRODUCTION
- **Role**: `admin`
- **Speaker ID**: `None` (sees all speakers)
- **Access**: Full system access, can view all transcripts, all analysis, all memories

### User1
- **Username**: `user1`
- **Password**: `user1pass`
- **Role**: `user`
- **Speaker ID**: `"user1"`
- **Access**: Only sees data where `speaker = "user1"`

### Television
- **Username**: `television`
- **Password**: `tvpass123`
- **Role**: `user`
- **Speaker ID**: `"television"`
- **Access**: Only sees data where `speaker = "television"`

---

## Enforcement Mechanisms

### 1. Backend SQL Filtering

All database queries are automatically filtered based on the authenticated user's `speaker_id`.

**Example**: `src/services/rag/routes.py`

```python
@memory_router.get("/list")
def list_memories(
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(require_auth)
) -> List[Dict[str, Any]]:
    """
    List transcript segments WITH SPEAKER ISOLATION
    """
    
    if session.role == UserRole.ADMIN:
        # Admin sees everything
        query = """
            SELECT * FROM transcript_segments
            WHERE text IS NOT NULL
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params = (limit, offset)
    else:
        # Non-admin ONLY sees their speaker
        query = """
            SELECT * FROM transcript_segments
            WHERE text IS NOT NULL AND speaker = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params = (session.speaker_id, limit, offset)
    
    cur.execute(query, params)
    return cur.fetchall()
```

### 2. Frontend UI Hiding

**File**: `frontend/assets/js/auth.js`

The frontend hides speaker selection dropdowns and filters for non-admin users:

```javascript
updateUIForRole() {
  if (!this.currentUser) return;
  
  // SPEAKER ISOLATION: Hide speaker selectors for non-admin users
  if (this.currentUser.role !== 'admin') {
    document.querySelectorAll('.speaker-filter, .speaker-dropdown, [data-admin-only]').forEach(el => {
      el.style.display = 'none';
    });
    console.log('[AUTH] Non-admin user - speaker filters hidden');
  }
  
  // Update user display
  const currentUserEl = document.getElementById('current-user');
  if (currentUserEl) {
    currentUserEl.textContent = `${this.currentUser.username} (${this.currentUser.role})`;
  }
}
```

### 3. Job Ownership Tracking

**File**: `src/services/gemma/service.py`

Analysis jobs (personality analysis, emotional triggers, etc.) track the `created_by_user_id`:

```python
class GemmaJob:
    job_id: str
    job_type: str
    params: Dict[str, Any]
    created_by_user_id: Optional[str]  # Track owner
    status: JobStatus
    progress: float
    result: Optional[Dict[str, Any]]
    # ...

def submit_job(
    self,
    job_type: str,
    params: Dict[str, Any],
    created_by_user_id: Optional[str] = None
) -> str:
    """Submit analysis job with user tracking"""
    job_id = str(uuid.uuid4())
    job = GemmaJob(
        job_id=job_id,
        job_type=job_type,
        params=params,
        created_by_user_id=created_by_user_id  # Store owner
    )
    # ...
```

**Access Control**: Non-admin users can only view/retrieve their own jobs:

```python
@jobs_router.get("/job/{job_id}")
def get_job_status(job_id: str, session: Session = Depends(require_auth)):
    """Get job status WITH OWNERSHIP CHECK"""
    
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Enforce job ownership - users can only view their own jobs
    if session.role != UserRole.ADMIN:
        if job.get("created_by_user_id") != session.user_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied. You can only view your own analysis jobs."
            )
    
    return job
```

---

## API Endpoints with Speaker Isolation

All 24 protected API endpoints enforce speaker isolation:

### RAG/Memory Endpoints (9 endpoints)
- `GET /memory/search` - Search memories (filtered by speaker)
- `GET /memory/count` - Count segments (filtered by speaker)
- `GET /memory/list` - List memories (filtered by speaker)
- `GET /memory/stats` - Memory statistics (filtered by speaker)
- `GET /memory/speakers/list` - List speakers (filtered)
- `GET /memory/by_speaker/{speaker_id}` - Get speaker memories (access check)
- `GET /memory/by_emotion/{emotion}` - Get emotion memories (filtered)
- `GET /memory/emotions/stats` - Emotion statistics (filtered)
- `POST /memory/analyze` - Comprehensive analysis (filtered, job tracked)

### Gemma AI Endpoints (7 endpoints)
- `POST /analyze/personality` - Personality analysis (job tracked)
- `POST /analyze/emotional_triggers` - Emotional triggers (job tracked)
- `POST /analyze/gemma_summary` - Gemma summary (job tracked)
- `POST /analyze/comprehensive` - Comprehensive analysis (job tracked)
- `POST /analyze/chat` - Chat with Gemma (job tracked)
- `GET /job/{job_id}` - Get job status (ownership checked)
- `GET /jobs` - List jobs (filtered by owner)

### Transcription Endpoints (5 endpoints)
- `GET /transcripts` - List transcripts (filtered by speaker)
- `GET /transcripts/{transcript_id}` - Get transcript (access checked)
- `GET /transcripts/search/speakers` - Search speakers (filtered)
- `GET /transcripts/search/sessions` - Search sessions (filtered)
- `GET /transcripts/analytics/summary` - Analytics summary (filtered)

### Speaker Enrollment Endpoints (3 endpoints)
- `POST /enroll/upload` - Upload enrollment audio (access checked)
- `GET /enroll/speakers` - List enrolled speakers (filtered)
- `GET /enroll/stats` - Speaker statistics (filtered)

---

## Testing Speaker Isolation

### Manual Testing

```bash
# 1. Login as admin
curl -s -c admin_cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 2. Admin sees all memories
curl -s -b admin_cookies.txt http://localhost:8000/memory/list?limit=5
# Should return memories from ALL speakers

# 3. Login as user1
curl -s -c user1_cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"user1pass"}'

# 4. User1 sees only user1 memories
curl -s -b user1_cookies.txt http://localhost:8000/memory/list?limit=5
# Should return ONLY memories where speaker = "user1"

# 5. Login as television
curl -s -c tv_cookies.txt -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"television","password":"tvpass123"}'

# 6. Television sees only television memories
curl -s -b tv_cookies.txt http://localhost:8000/memory/list?limit=5
# Should return ONLY memories where speaker = "television"
```

### Automated Testing

**Run the comprehensive test suite:**

```bash
cd /home/pruittcolon/Desktop/Nemo_Server
bash tests/test_security_comprehensive.sh
```

**Expected output:**
```
=========================================
  Nemo Server Security Test Suite
=========================================

[TEST 1] Admin login... ✅ PASS
[TEST 2] Admin data access... ✅ PASS
[TEST 3] User1 login... ✅ PASS
[TEST 4] User1 speaker isolation... ✅ PASS
[TEST 5] No auth = 401... ✅ PASS
[TEST 6] Television login... ✅ PASS
[TEST 7] Television speaker isolation... ✅ PASS
[TEST 8] Admin transcript access... ✅ PASS
[TEST 9] User1 transcript isolation... ✅ PASS
[TEST 10] Admin speaker enrollment access... ✅ PASS

PASSED: 10
FAILED: 0
TOTAL:  10

✅ ALL TESTS PASSED!
```

---

## Frontend Integration

### Login Flow

1. User visits `http://localhost:8000/ui/login.html`
2. Enters username and password
3. Backend validates credentials and creates session
4. Session token stored as HTTP-only cookie (`ws_session`)
5. User redirected to dashboard

### Auto-Redirect on 401

All protected HTML pages check authentication on load:

```javascript
// In every protected page
async function initPage() {
  // Require authentication
  const authenticated = await Auth.init({ requireAuth: true });
  if (!authenticated) return;  // Auto-redirects to /ui/login.html
  
  // Load page data...
}

document.addEventListener('DOMContentLoaded', initPage);
```

If an API call returns HTTP 401, the user is automatically redirected to login:

```javascript
// In api.js
if (response.status === 401) {
  console.warn('[API] Authentication required - redirecting to login');
  window.location.href = '/ui/login.html';
  throw new Error('Not authenticated');
}
```

### Speaker Filter UI

For admin users, speaker filter dropdowns are visible:

```html
<div class="speaker-filter" style="display: none;">
  <label for="speaker-select">Filter by Speaker:</label>
  <select id="speaker-select">
    <option value="">All Speakers</option>
    <option value="user1">User1</option>
    <option value="television">Television</option>
  </select>
</div>
```

For non-admin users, these elements are automatically hidden by `auth.js`.

---

## Creating New Users

To create additional users with speaker isolation:

```python
# In src/auth/auth_manager.py

# Add to default_users list in _create_default_users():
User(
    user_id="john_doe",
    username="john_doe",
    password_hash=self._hash_password("secure_password"),
    role=UserRole.USER,
    speaker_id="john_doe",  # Link to speaker identity
    email="john@example.com",
    created_at=now,
    modified_at=now
)
```

Then restart the server to create the user.

---

## Security Best Practices

### 1. Change Default Passwords
```python
# In production, change these in auth_manager.py:
password_hash=self._hash_password("STRONG_RANDOM_PASSWORD_HERE")
```

### 2. Set Environment Variables
```bash
# In docker-compose.yml or .env:
SECRET_KEY=your-256-bit-secret-key-here
DB_ENCRYPTION_KEY=your-encryption-key-here
```

### 3. Enable HTTPS
```yaml
# In production, use a reverse proxy like Nginx:
server {
    listen 443 ssl;
    server_name nemo.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 4. Regular Security Audits
- Review user sessions: `GET /api/auth/sessions` (admin only)
- Check failed login attempts in logs
- Monitor rate limiting triggers
- Audit database access patterns

---

## Troubleshooting

### Issue: User sees all speakers

**Symptoms**: Non-admin user can see transcripts from other speakers

**Solution**:
1. Check user's `speaker_id` in database:
   ```sql
   SELECT user_id, username, role, speaker_id FROM users;
   ```
2. Verify session has correct `speaker_id`:
   ```bash
   curl -b cookies.txt http://localhost:8000/api/auth/check
   ```
3. Check backend logs for SQL queries

### Issue: Admin sees no data

**Symptoms**: Admin user gets empty results

**Solution**:
1. Admin `speaker_id` should be `None` or `null`
2. Check SQL query logic for admin role handling
3. Verify `role = "admin"` (not "ADMIN" or "administrator")

### Issue: 403 Forbidden on job access

**Symptoms**: User gets 403 when accessing their own analysis job

**Solution**:
1. Verify job's `created_by_user_id` matches user's `user_id`
2. Check session token is valid and not expired
3. Review job ownership logic in `src/services/gemma/routes.py`

---

## Implementation Checklist

- [x] Authentication system with bcrypt password hashing
- [x] Session management with encrypted tokens
- [x] User model with `speaker_id` field
- [x] Session model with `speaker_id` field
- [x] Authentication middleware enforcing 401
- [x] SQL filtering by `speaker_id` in all endpoints
- [x] Frontend UI hiding for non-admin users
- [x] Job ownership tracking for analysis jobs
- [x] Comprehensive test suite (10/10 tests passing)
- [x] Documentation (this file)

---

## Summary

Speaker-based data isolation in Nemo Server is enforced at multiple levels:

1. **Database Level**: SQL queries filter by `speaker_id`
2. **API Level**: Endpoint logic checks user role and speaker access
3. **Session Level**: Session tokens carry `speaker_id` for fast checks
4. **UI Level**: Frontend hides controls non-admin users shouldn't see
5. **Job Level**: Analysis jobs track creator and enforce ownership

This multi-layered approach ensures **100% data separation** between speakers while maintaining a seamless user experience.

For more information, see:
- `README.md` - Quick start guide
- `AUTHENTICATION_COMPLETE.md` - Implementation details
- `tests/test_security_comprehensive.sh` - Test suite
- `src/auth/` - Authentication source code

---

**Last Updated**: October 26, 2025
