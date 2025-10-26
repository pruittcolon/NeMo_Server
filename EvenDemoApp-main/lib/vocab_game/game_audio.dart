import 'package:demo_ai_even/utils/sound_manager.dart';

abstract class GameAudio {
  Future<void> playCorrect();
  Future<void> playIncorrect();
  void setEnabled(bool enabled);
}

class DefaultGameAudio implements GameAudio {
  bool _enabled = true;

  @override
  Future<void> playCorrect() async {
    if (_enabled) {
      await SoundManager.playCorrect();
    }
  }

  @override
  Future<void> playIncorrect() async {
    if (_enabled) {
      await SoundManager.playIncorrect();
    }
  }

  @override
  void setEnabled(bool enabled) {
    _enabled = enabled;
    SoundManager.setSoundEnabled(enabled);
  }
}
