# Vocabulary Game Testing Guide

This mini-playbook keeps the game continuously testable without navigating through the full app.

## 1. Standalone Runner

```
flutter run lib/vocab_game/devtools/vocab_game_sandbox.dart
```

This boots the game page directly so you can iterate on UI/UX in isolation.

## 2. Automated Suites

```
tool/run_vocab_game_tests.sh
```

The script executes:

1. `test/vocab_game/game_controller_test.dart` – engine + scoring logic.
2. `test/vocab_game/vocabulary_game_page_test.dart` – widget smoke test with fake data.

Add it to your CI or run on file save for continuous coverage.

## 3. Manual Regression Checklist

1. Clear app data (or uninstall/install) to reset SharedPreferences.
2. Launch the sandbox app, play a new round, verify scoring & animations.
3. Trigger Review Mode from the menu, ensure fallback to random words if none missed.
4. Return to the main app and open the game via Home → Features → Vocabulary Game.
5. Confirm high score persists and Settings toggles (sound/questions per round) apply.

Repeat steps 2–5 after every content or engine change.
