import 'dart:math';

import 'package:demo_ai_even/models/vocabulary_word.dart';
import 'package:demo_ai_even/vocab_game/game_audio.dart';
import 'package:demo_ai_even/vocab_game/game_controller.dart';
import 'package:demo_ai_even/vocab_game/game_preferences.dart';
import 'package:demo_ai_even/vocab_game/game_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeAudio implements GameAudio {
  bool enabled = true;
  int correctCount = 0;
  int incorrectCount = 0;

  @override
  Future<void> playCorrect() async {
    correctCount++;
  }

  @override
  Future<void> playIncorrect() async {
    incorrectCount++;
  }

  @override
  void setEnabled(bool enabled) {
    this.enabled = enabled;
  }
}

class FakeDataSource implements VocabularyDataSource {
  final List<VocabularyWord> words;

  FakeDataSource(this.words);

  @override
  Future<List<VocabularyWord>> missedWords() async => words.take(2).toList();

  @override
  Future<List<VocabularyWord>> randomDistractors(int count, {int? excludeId}) async {
    return words.where((w) => w.id != excludeId).take(count).toList();
  }

  @override
  Future<List<VocabularyWord>> randomWords(int count) async =>
      words.take(count).toList();

  @override
  Future<void> setMissed(int wordId, bool isMissed) async {}
}

VocabularyWord buildWord(int id, String word, String definition) => VocabularyWord(
      id: id,
      word: word,
      definition: definition,
      wordBreakdown: 'Breakdown of $word',
      sameRootWords: 'root',
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeAudio audio;
  late VocabularyGameController controller;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'questionsPerRound': 3});
    final prefs = await SharedPreferences.getInstance();
    audio = FakeAudio();
    controller = VocabularyGameController(
      repository: VocabRepository(
        dataSource: FakeDataSource([
          buildWord(1, 'abate', 'to lessen'),
          buildWord(2, 'banal', 'commonplace'),
          buildWord(3, 'cajole', 'coax'),
          buildWord(4, 'decimate', 'destroy'),
        ]),
        random: Random(1),
      ),
      preferences: GamePreferences(prefOverride: prefs),
      audio: audio,
      random: Random(2),
    );
    await controller.initialize(reviewMode: false);
  });

  test('loads questions and updates score', () async {
    expect(controller.isLoading, isFalse);
    expect(controller.currentQuestion, isNotNull);

    final correct = controller.currentQuestion!.correctAnswer;
    await controller.selectAnswer(correct);

    expect(controller.score, 1);
    expect(audio.correctCount, 1);
    expect(controller.isAnswered, true);
  });

  test('marks incorrect answers and tracks missed words', () async {
    final wrongOption =
        controller.options.firstWhere((o) => o != controller.currentQuestion!.correctAnswer);
    await controller.selectAnswer(wrongOption);
    expect(controller.score, 0);
    expect(controller.missedWords.length, 1);
    expect(audio.incorrectCount, 1);
  });

  test('advances questions and builds summary', () async {
    for (var i = 0; i < controller.totalQuestions; i++) {
      await controller.selectAnswer(controller.currentQuestion!.correctAnswer);
      await controller.advanceToNextQuestion();
    }

    final summary = await controller.buildSummary();
    expect(summary.score, controller.totalQuestions);
    expect(summary.isNewHighScore, true);
  });
}
