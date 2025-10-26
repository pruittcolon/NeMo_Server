# Even Demo Client

A Flutter demo client that showcases how the WhisperServer backend connects to smart glasses
for real-time transcription, memory recall, and multimodal feedback.

The project bundles BLE control flows, Deepgram/Whisper integrations, Roku remote commands,
and a lightweight UI for triggering backend workflows.

---

## Quick Start

```bash
cd EvenDemoApp-main
flutter pub get
flutter run  # choose your target device/emulator
```

The repository ships with a non-secret `.env` asset so the app loads without extra steps.
Update the values before distributing real builds.

---

## Configuration

Environment variables are loaded from the bundled `.env` file (see `pubspec.yaml`).

| Key | Purpose | Default |
| --- | ------- | ------- |
| `MEMORY_SERVER_BASE` | WhisperServer FastAPI endpoint | `http://127.0.0.1:8000` |
| `WHISPER_SERVER_BASE` | Audio ingestion endpoint | `http://127.0.0.1:8000` |
| `ASR_SERVER_BASE` | Optional ASR service | `http://127.0.0.1:8000` |
| `DEEPGRAM_API_KEY` | Deepgram realtime transcription | _blank_ |
| `OPENAI_API_KEY` | Follow-up responses | _blank_ |
| `VOICEMONKEY_TRIGGER_URL` | Alexa Voice Monkey | _blank_ |
| `ROKU_BASE_URL` | Roku remote integration | _blank_ |

To customize per environment, create a copy (e.g. `.env.prod`) and load it manually in
`lib/main.dart` before building release builds.

---

## Scripts & Commands

| Command | Description |
| ------- | ----------- |
| `flutter run` | Run on the selected device/emulator |
| `flutter build apk` | Produce an Android APK |
| `flutter test` | Execute widget/unit tests |
| `flutter analyze` | Lint the project |

---

## Project Structure

```
lib/
├─ app.dart            # Root widget and theme wiring
├─ controllers/        # GetX controllers for features and BLE interaction
├─ services/           # API, BLE, Deepgram/Whisper helpers, protocol serializers
├─ views/              # Feature screens (BMP, vocabulary, voice enrollment, etc.)
├─ widgets/            # Reusable UI widgets and dialog components
└─ utils/              # Utility extensions and formatters
```

Assets live under `assets/` and include BMP samples, animations, sounds, and vocabulary files.

---

## Testing & Quality

flutter test
flutter analyze


## Known Limitations

- BLE flows assume the dual-arm connection model documented by the hardware vendor.
- Many features rely on optional cloud APIs (Deepgram, OpenAI, Voice Monkey). Leave the env
  values empty to disable them in offline demos.
- Production builds should strip debug prints and secure API keys using platform-specific
  keystores (Keychain/Keystore).

---

Contributions are welcome—keep PRs focused, add Flutter tests where it makes sense, and make
sure the backend API contract is respected.
