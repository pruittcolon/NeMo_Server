import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'package:demo_ai_even/models/vocabulary_word.dart';
import 'package:demo_ai_even/vocab_game/game_audio.dart';
import 'package:demo_ai_even/vocab_game/game_preferences.dart';
import 'package:demo_ai_even/vocab_game/game_question.dart';
import 'package:demo_ai_even/vocab_game/game_repository.dart';

class RoundSummary {
  final int score;
  final int totalQuestions;
  final List<VocabularyWord> missedWords;
  final bool isNewHighScore;

  const RoundSummary({
    required this.score,
    required this.totalQuestions,
    required this.missedWords,
    required this.isNewHighScore,
  });
}

class VocabularyGameController extends ChangeNotifier {
  final VocabRepository repository;
  final GamePreferences preferences;
  final GameAudio audio;
  final Random random;

  VocabularyGameController({
    VocabRepository? repository,
    GamePreferences? preferences,
    GameAudio? audio,
    Random? random,
  })  : repository = repository ?? VocabRepository(),
        preferences = preferences ?? GamePreferences(),
        audio = audio ?? DefaultGameAudio(),
        random = random ?? Random();

  bool _reviewMode = false;
  bool _isLoading = true;
  bool _isAnswered = false;
  bool _lastAnswerCorrect = false;
  int _score = 0;
  int _currentQuestionIndex = 0;
  int _highScore = 0;
  GameQuestion? _currentQuestion;
  String? _selectedAnswer;
  List<VocabularyWord> _quizWords = [];
  final List<VocabularyWord> _missedThisRound = [];

  bool get isLoading => _isLoading;
  bool get isAnswered => _isAnswered;
  bool get lastAnswerCorrect => _lastAnswerCorrect;
  int get score => _score;
  int get highScore => _highScore;
  int get currentQuestionIndex => _currentQuestionIndex;
  int get totalQuestions => _quizWords.length;
  GameQuestion? get currentQuestion => _currentQuestion;
  List<String> get options => _currentQuestion?.options ?? const [];
  String? get selectedAnswer => _selectedAnswer;
  List<VocabularyWord> get missedWords => List.unmodifiable(_missedThisRound);
  bool get hasQuestions => _quizWords.isNotEmpty;

  Future<void> initialize({required bool reviewMode}) async {
    print("🎮 [VOCAB GAME] Initializing game controller (reviewMode: $reviewMode)");
    _reviewMode = reviewMode;
    await preferences.ensureLoaded();
    print("🎮 [VOCAB GAME] Preferences loaded - questions per round: ${preferences.questionsPerRound}");
    audio.setEnabled(preferences.soundEnabled);
    _highScore = preferences.highScore;
    await startRound(reviewMode: reviewMode);
  }

  Future<void> startRound({required bool reviewMode}) async {
    print("🎮 [VOCAB GAME] Starting round (reviewMode: $reviewMode)");
    _reviewMode = reviewMode;
    _setLoading(true);
    _score = 0;
    _currentQuestionIndex = 0;
    _missedThisRound.clear();
    _selectedAnswer = null;
    _isAnswered = false;

    print("🎮 [VOCAB GAME] Loading words from repository...");
    final words = await repository.loadRoundWords(
      count: preferences.questionsPerRound,
      reviewMode: reviewMode,
    );
    _quizWords = words;
    print("🎮 [VOCAB GAME] Loaded ${_quizWords.length} words for quiz");
    if (_quizWords.isEmpty) {
      print("❌ [VOCAB GAME] ERROR: No words loaded!");
      _currentQuestion = null;
      _setLoading(false);
      notifyListeners();
      return;
    }
    await _prepareQuestion();
    print("✅ [VOCAB GAME] Round started successfully, first question ready");
    _setLoading(false);
    notifyListeners();
  }

  Future<void> restartRound() => startRound(reviewMode: false);

  Future<void> startReviewRound() => startRound(reviewMode: true);

  Future<void> _prepareQuestion() async {
    if (_currentQuestionIndex >= _quizWords.length) {
      _currentQuestion = null;
      return;
    }
    final word = _quizWords[_currentQuestionIndex];
    print("🎮 [VOCAB GAME] Preparing question ${_currentQuestionIndex + 1}/${_quizWords.length} for word: ${word.word}");
    final distractors = await repository.randomDistractors(
      3,
      excludeId: word.id,
    );
    print("🎮 [VOCAB GAME] Got ${distractors.length} distractors");
    _currentQuestion = GameQuestion.fromWord(
      word: word,
      distractors: distractors,
      random: random,
    );
    _isAnswered = false;
    _selectedAnswer = null;
    print("✅ [VOCAB GAME] Question prepared successfully");
  }

  Future<void> selectAnswer(String answer) async {
    if (_isAnswered || _currentQuestion == null) return;
    _isAnswered = true;
    _selectedAnswer = answer;
    final correct = answer == _currentQuestion!.correctAnswer;
    _lastAnswerCorrect = correct;
    if (correct) {
      _score++;
      await audio.playCorrect();
      await repository.markMissed(_currentQuestion!.promptWord, false);
    } else {
      _missedThisRound.add(_currentQuestion!.promptWord);
      await audio.playIncorrect();
      await repository.markMissed(_currentQuestion!.promptWord, true);
    }
    notifyListeners();
  }

  Future<bool> advanceToNextQuestion() async {
    if (_currentQuestionIndex + 1 >= _quizWords.length) {
      return false;
    }
    _currentQuestionIndex++;
    await _prepareQuestion();
    notifyListeners();
    return true;
  }

  Future<RoundSummary> buildSummary() async {
    final isNewHigh = _score > _highScore;
    if (isNewHigh) {
      _highScore = _score;
      await preferences.setHighScore(_score);
    }
    return RoundSummary(
      score: _score,
      totalQuestions: _quizWords.length,
      missedWords: List<VocabularyWord>.from(_missedThisRound),
      isNewHighScore: isNewHigh,
    );
  }

  void _setLoading(bool value) {
    _isLoading = value;
    if (value) {
      notifyListeners();
    }
  }

  @override
  void dispose() {
    super.dispose();
  }
}
