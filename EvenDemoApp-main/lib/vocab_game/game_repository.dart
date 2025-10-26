import 'dart:math';

import 'package:demo_ai_even/models/vocabulary_word.dart';
import 'package:demo_ai_even/utils/database_helper.dart';

/// Interface used for fetching words. Enables in-memory fakes for tests.
abstract class VocabularyDataSource {
  Future<List<VocabularyWord>> randomWords(int count);
  Future<List<VocabularyWord>> missedWords();
  Future<List<VocabularyWord>> randomDistractors(int count, {int? excludeId});
  Future<void> setMissed(int wordId, bool isMissed);
}

class DatabaseVocabularyDataSource implements VocabularyDataSource {
  final DatabaseHelper _helper;

  DatabaseVocabularyDataSource([DatabaseHelper? helper])
      : _helper = helper ?? DatabaseHelper.instance;

  @override
  Future<List<VocabularyWord>> randomWords(int count) =>
      _helper.getRandomWords(count);

  @override
  Future<List<VocabularyWord>> missedWords() => _helper.getMissedWords();

  @override
  Future<List<VocabularyWord>> randomDistractors(int count, {int? excludeId}) =>
      _helper.getRandomDistractors(count, excludeId: excludeId);

  @override
  Future<void> setMissed(int wordId, bool isMissed) async {
    await _helper.updateWordAsMissed(wordId, isMissed);
  }
}

class VocabRepository {
  final VocabularyDataSource _dataSource;
  final Random _random;

  VocabRepository({
    VocabularyDataSource? dataSource,
    Random? random,
  })  : _dataSource = dataSource ?? DatabaseVocabularyDataSource(),
        _random = random ?? Random();

  Random get random => _random;

  Future<List<VocabularyWord>> loadRoundWords({
    required int count,
    required bool reviewMode,
  }) async {
    if (reviewMode) {
      final missed = await _dataSource.missedWords();
      if (missed.isNotEmpty) {
        return missed.take(count).toList();
      }
    }
    return _dataSource.randomWords(count);
  }

  Future<List<VocabularyWord>> randomDistractors(int count, {int? excludeId}) =>
      _dataSource.randomDistractors(count, excludeId: excludeId);

  Future<void> markMissed(VocabularyWord word, bool missed) async {
    if (word.id == null) return;
    await _dataSource.setMissed(word.id!, missed);
  }
}
