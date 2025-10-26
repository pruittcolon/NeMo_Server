# RAG Service Summary

**Service**: Memory & Vector Search  
**Location**: `REFACTORED/src/services/rag/`  
**Status**: PENDING  
**Last Updated**: October 24, 2025

---

## 📦 **Files in This Service**

### ⏳ `service.py`
**Status**: NOT STARTED  
**Purpose**: Wrapper around existing AdvancedMemoryService

**Planned Classes**:
- `RagService` - Wrapper with CPU enforcement

**Models Used**:
- `sentence-transformers/all-MiniLM-L6-v2` (CPU, 384-dim embeddings)

**Key Features**:
- FAISS vector search
- Semantic similarity search
- Memory storage and retrieval
- Session management
- Force CPU for embeddings

**Imports (UNCHANGED)**:
```python
from src.advanced_memory_service import AdvancedMemoryService
```

**Conflicts Checked**:
- [ ] Import path works from REFACTORED/
- [ ] config.EMBEDDING_MODEL_PATH matches
- [ ] FAISS index path consistent
- [ ] Database path: instance/memories.db
- [ ] 1,240+ documents preserved
- [ ] SQLite schema unchanged

**Dependencies**:
- AdvancedMemoryService (existing, 1,607 lines - UNTOUCHED)
- torch
- FAISS
- sentence-transformers

---

### ⏳ `routes.py`
**Status**: NOT STARTED  
**Purpose**: Memory and transcript search endpoints

**Endpoints**:
- `GET /memory/search?query={q}` - Semantic memory search
- `GET /memory/list` - List all memories
- `POST /memory/create` - Create new memory
- `POST /memory/clear_session` - Clear conversation session
- `GET /transcript/search?query={q}` - Full-text transcript search
- `POST /query` - RAG-powered question answering

**Extracted From**:
- main3.py lines 879-965 (`/query` endpoint)
- main3.py lines 1143-1158 (search functions)

**Conflicts Checked**:
- [ ] JSON response schemas match
- [ ] Score calculations identical
- [ ] Session management preserved
- [ ] Query context format same

**Dependencies**:
- FastAPI
- RagService

---

## ✅ **Completed Tasks**

None yet

---

## 🚨 **Known Issues**

None - AdvancedMemoryService is already well-structured (1,607 lines of quality code)

---

## 📝 **Notes**

**IMPORTANT**: We are NOT refactoring `advanced_memory_service.py` - it's already clean and well-organized. We're just wrapping it in a service class that enforces CPU-only operation for the embedding model.

**Database Preservation**:
- SQLite database at `instance/memories.db` contains 1,240+ documents
- MUST NOT be modified or corrupted
- FAISS index must remain compatible
- Embeddings must be identical format

---

**Next Steps**:
1. Create `RagService` wrapper class
2. Test import of AdvancedMemoryService
3. Verify CPU-only embeddings
4. Create FastAPI routes
5. Test semantic search returns same results


