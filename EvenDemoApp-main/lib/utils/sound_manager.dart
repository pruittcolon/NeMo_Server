import 'package:just_audio/just_audio.dart';
import 'package:vibration/vibration.dart';

class SoundManager {
  static bool _soundEnabled = true;
  static final AudioPlayer _player = AudioPlayer();

  static void setSoundEnabled(bool enabled) {
    _soundEnabled = enabled;
  }

  static Future<void> playCorrect() async {
    if (!_soundEnabled) return;

    try {
      // Use vibration feedback for correct answer
      if (await Vibration.hasVibrator() ?? false) {
        Vibration.vibrate(duration: 100);
      }
    } catch (e) {
      print('Error playing correct sound: $e');
    }
  }

  static Future<void> playIncorrect() async {
    if (!_soundEnabled) return;

    try {
      // Use vibration feedback for incorrect answer
      if (await Vibration.hasVibrator() ?? false) {
        Vibration.vibrate(duration: 300, pattern: [0, 100, 50, 100, 50, 100]);
      }
    } catch (e) {
      print('Error playing incorrect sound: $e');
    }
  }
}


