# Speaker Diarization Service Summary

**Service**: Speaker Identification & Enrollment  
**Location**: `REFACTORED/src/services/speaker/`  
**Status**: PENDING  
**Last Updated**: October 24, 2025

---

## 📦 **Files in This Service**

### ⏳ `service.py`
**Status**: NOT STARTED  
**Purpose**: Unified speaker identification (consolidates 3x duplicate logic)

**Planned Classes**:
- `SpeakerService` - Main speaker ID wrapper
- `SpeakerMapper` - Label mapping (Pruitt, Ericah, SPK_XX)

**Models Used**:
- `nvidia/speakerverification_en_titanet_large` (TitaNet, CPU)

**Key Features**:
- K-means clustering (2 speakers)
- Voice enrollment matching
- Cosine similarity comparison
- Single source of truth for speaker ID

**Extracted From** (CONSOLIDATING 3x IMPLEMENTATIONS):
1. main3.py lines 238-348 (`apply_diarization()`)
2. main3.py lines 743-793 (enrollment matching in `/transcribe`)
3. main3.py lines 300-348 (K-means clustering logic)

**Conflicts Checked**:
- [ ] Speaker labels match: Pruitt, Ericah, SPK_00, SPK_01
- [ ] Enrollment path: instance/enrollment/
- [ ] Cosine similarity calculations identical
- [ ] Threshold 0.60 preserved
- [ ] numpy/scipy versions match

**Dependencies**:
- nemo.collections.asr.models (EncDecSpeakerLabelModel)
- sklearn.cluster (KMeans)
- sklearn.preprocessing (normalize)
- scipy.spatial.distance (cosine)
- numpy

---

### ⏳ `routes.py`
**Status**: NOT STARTED  
**Purpose**: Speaker enrollment endpoint

**Endpoints**:
- `POST /enroll/upload` - Upload voice sample for enrollment

**Conflicts Checked**:
- [ ] Embedding format (.npy) identical
- [ ] File paths match original
- [ ] Auto-processing works

**Dependencies**:
- FastAPI
- SpeakerService

---

## ✅ **Completed Tasks**

None yet

---

## 🚨 **Known Issues**

- **Duplicate Logic**: Original has 3 separate implementations - MUST consolidate into one
- **K-means Overhead**: Runs on every transcription request - may need caching

---

## 📝 **Notes**

**CRITICAL IMPROVEMENT**: This service eliminates the most egregious code duplication in the original system. Speaker identification logic appears 3 times with slight variations, leading to maintenance nightmares and potential bugs.

**Consolidation Strategy**:
1. Extract common embedding generation
2. Single K-means clustering implementation
3. Single enrollment matching logic
4. Reusable SpeakerMapper class

---

**Next Steps**:
1. Extract and merge all 3 speaker ID implementations
2. Create unified `SpeakerService` class
3. Test with 2-speaker audio
4. Verify enrollment matching works
5. Ensure speaker labels match exactly


