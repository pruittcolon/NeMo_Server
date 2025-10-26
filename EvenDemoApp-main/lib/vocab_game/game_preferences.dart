import 'package:shared_preferences/shared_preferences.dart';

class GamePreferences {
  static const _questionsKey = 'questionsPerRound';
  static const _soundKey = 'soundEnabled';
  static const _highScoreKey = 'vocab_high_score';

  final SharedPreferences? _providedPrefs;
  SharedPreferences? _prefs;

  GamePreferences({SharedPreferences? prefOverride})
      : _providedPrefs = prefOverride;

  Future<void> ensureLoaded() async {
    _prefs ??= _providedPrefs ?? await SharedPreferences.getInstance();
  }

  int get questionsPerRound => _prefs?.getInt(_questionsKey) ?? 10;
  bool get soundEnabled => _prefs?.getBool(_soundKey) ?? true;
  int get highScore => _prefs?.getInt(_highScoreKey) ?? 0;

  Future<void> setHighScore(int score) async {
    await _prefs?.setInt(_highScoreKey, score);
  }
}
