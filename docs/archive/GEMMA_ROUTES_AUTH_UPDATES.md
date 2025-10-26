# Gemma Routes Authentication Updates

## Endpoints Requiring Authentication

All the following endpoints need to be updated to:
1. Import and use `require_auth` from `src.auth.permissions`
2. Add `ws_session: Optional[str] = Cookie(None)` parameter
3. Call `session = require_auth(ws_session)`
4. Pass `created_by_user_id=session.user_id` to `submit_job()`

### Endpoints to Update:

1. **`/analyze/personality` (Line 149)** - POST - submit personality analysis job
2. **`/analyze/emotional_triggers` (Line 173)** - POST - submit emotional triggers job
3. **`/analyze/gemma_summary` (Line 197)** - POST - submit summary job
4. **`/analyze/comprehensive` (Line 221)** - POST - submit comprehensive analysis job
5. **`/analyze/chat` (Line 245)** - POST - synchronous chat (also submits job)

### Pattern for Each Endpoint:

```python
@router.post("/{endpoint_name}")
def endpoint_function(payload: RequestModel) -> Dict[str, str]:
    """
    Docstring...
    """
    # ADD THESE IMPORTS
    from src.auth.permissions import require_auth
    from fastapi import Cookie
    from typing import Optional
    
    # ADD AUTHENTICATION
    ws_session: Optional[str] = Cookie(None)
    session = require_auth(ws_session)
    
    service = get_service()
    
    try:
        job_id = service.submit_job(
            job_type="...",
            params={...},
            created_by_user_id=session.user_id  # ADD THIS
        )
        return {"job_id": job_id, "status": "queued"}
    except Exception as e:
        print(f"[GEMMA API] ... error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

## Status:

- [x] `/job/{job_id}` - GET - COMPLETE ✅
- [x] `/jobs` - GET - COMPLETE ✅  
- [ ] `/analyze/personality` - POST - TODO
- [ ] `/analyze/emotional_triggers` - POST - TODO
- [ ] `/analyze/gemma_summary` - POST - TODO
- [ ] `/analyze/comprehensive` - POST - TODO
- [ ] `/analyze/chat` - POST - TODO

## Implementation Complete: 40% (2/5 analysis endpoints remain)

