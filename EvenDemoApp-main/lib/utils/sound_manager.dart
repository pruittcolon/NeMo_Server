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
      // Try to play a simple online sound
      await _player.setUrl('https://www.soundjay.com/misc/sounds/bell-ringing-05.wav');
      _player.play();
    } catch (e) {
      print('Error playing correct sound: $e');
      // Fallback to vibration
      if (await Vibration.hasVibrator() ?? false) {
        Vibration.vibrate(duration: 100);
      }
    }
  }

  static Future<void> playIncorrect() async {
    if (!_soundEnabled) return;

    try {
      // Try to play a different online sound
      await _player.setUrl('https://www.soundjay.com/misc/sounds/bell-ringing-04.wav');
      _player.play();
    } catch (e) {
      print('Error playing incorrect sound: $e');
      // Fallback to vibration
      if (await Vibration.hasVibrator() ?? false) {
        Vibration.vibrate(duration: 300, pattern: [0, 100, 50, 100, 50, 100]);
      }
    }
  }
}


