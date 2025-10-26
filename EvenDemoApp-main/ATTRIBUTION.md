# Attribution

## Based on Even Realities EvenDemoApp

This Flutter application is based on the [Even Realities EvenDemoApp](https://github.com/even-realities/EvenDemoApp), which provides the foundational Bluetooth communication protocol for Even Realities smart glasses.

**Original Repository**: https://github.com/even-realities/EvenDemoApp  
**License**: BSD-2-Clause  
**Copyright**: © Even Realities

---

## Modifications & Extensions

This implementation has been **significantly extended** beyond the original demo app to include:

### Backend Integration
- ✅ **Nemo Server connectivity** - Real-time communication with FastAPI backend
- ✅ **Environment-based configuration** - `.env` file for server settings
- ✅ **Audio streaming** - Continuous audio upload for transcription

### Voice Intelligence Features
- ✅ **Real-time transcription** - Integration with NVIDIA NeMo Parakeet ASR
- ✅ **Speaker diarization** - Multi-speaker identification and tracking
- ✅ **Speaker enrollment** - Voice profile creation from mobile device
- ✅ **Emotion analysis** - Real-time emotion detection in transcripts

### AI Features
- ✅ **Gemma AI chat** - Conversational AI interface
- ✅ **Memory search** - RAG-based conversation history retrieval
- ✅ **Comprehensive analysis** - AI-powered conversation analysis

### Storage & Persistence
- ✅ **Database storage** - SQLite integration for transcript history
- ✅ **Voice profile management** - Persistent speaker embeddings
- ✅ **Session management** - User authentication and authorization

---

## License Compliance

### Original Work (Even Realities)
The base Bluetooth communication layer and smart glasses protocol implementation remain under the BSD-2-Clause license.

### Extended Work (Nemo Server Integration)
The additional features and backend integration are part of the Nemo Server project, licensed under MIT.

---

## Original BSD-2-Clause License

```
BSD 2-Clause License

Copyright (c) Even Realities

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

---

## Credits

- **Even Realities** - Original EvenDemoApp foundation
- **Nemo Server Project** - Voice intelligence and AI features
- **NVIDIA** - NeMo ASR models
- **Google** - Gemma LLM

