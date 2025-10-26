import 'dart:math';

import 'package:demo_ai_even/models/vocabulary_word.dart';
import 'package:demo_ai_even/vocab_game/game_audio.dart';
import 'package:demo_ai_even/vocab_game/game_preferences.dart';
import 'package:demo_ai_even/vocab_game/game_repository.dart';
import 'package:demo_ai_even/views/features/notification/vocabulary_game_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SilentAudio implements GameAudio {
  @override
  Future<void> playCorrect() async {}

  @override
  Future<void> playIncorrect() async {}

  @override
  void setEnabled(bool enabled) {}
}

class TestRepository extends VocabRepository {
  TestRepository(List<VocabularyWord> words)
      : super(
          dataSource: _TestDataSource(words),
          random: Random(3),
        );
}

class _TestDataSource implements VocabularyDataSource {
  final List<VocabularyWord> words;
  _TestDataSource(this.words);

  @override
  Future<List<VocabularyWord>> missedWords() async => [];

  @override
  Future<List<VocabularyWord>> randomDistractors(int count, {int? excludeId}) async =>
      words.where((w) => w.id != excludeId).take(count).toList();

  @override
  Future<List<VocabularyWord>> randomWords(int count) async =>
      words.take(count).toList();

  @override
  Future<void> setMissed(int wordId, bool isMissed) async {}
}

VocabularyWord w(int id, String word, String definition) => VocabularyWord(
      id: id,
      word: word,
      definition: definition,
      wordBreakdown: '',
      sameRootWords: '',
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({'questionsPerRound': 2});
  });

  testWidgets('renders question and accepts answers', (tester) async {
    final prefs = await SharedPreferences.getInstance();
    final repository = TestRepository([
      w(1, 'abate', 'to lessen'),
      w(2, 'banal', 'common'),
      w(3, 'cajole', 'coax'),
    ]);

    await tester.pumpWidget(MaterialApp(
      home: VocabularyGamePage(
        repository: repository,
        preferences: GamePreferences(prefOverride: prefs),
        audio: SilentAudio(),
        advanceDelay: const Duration(milliseconds: 10),
      ),
    ));

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.textContaining('Score'), findsOneWidget);
    expect(find.byType(ElevatedButton), findsNothing);

    final optionFinder = find.byType(Text).first;
    await tester.tap(optionFinder);
    await tester.pump(const Duration(milliseconds: 20));
  });
}
