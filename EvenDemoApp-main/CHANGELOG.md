## Changelog

### 1.1.0
- Added Chat Mode with on‑glasses guidance and 10‑minute auto‑exit.
- Added Interview Mode (uses optional local assets; degrades gracefully if absent).
- Switched Roku remote to on‑glasses text UI.
- Added Quick Note BLE trigger in `Proto.sendQuickNoteBasic`.
- Fixed authorization loop (attach session cookie to WhisperServer requests).
- Fixed vocabulary game loop/hangs (removed external audio; vibration feedback; lifecycle guards).
- Added app‑level `.gitignore` for `.env`, Flutter build artifacts, and private interview files.

