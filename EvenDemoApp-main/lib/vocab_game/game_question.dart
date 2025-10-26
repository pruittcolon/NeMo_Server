import 'dart:math';

import 'package:demo_ai_even/models/vocabulary_word.dart';

/// Type of prompt shown to the player.
enum QuestionType {
  definitionToWord,
  wordToDefinition,
}

/// Immutable representation of a single multiple-choice prompt.
class GameQuestion {
  final VocabularyWord promptWord;
  final QuestionType type;
  final List<String> options;

  const GameQuestion({
    required this.promptWord,
    required this.type,
    required this.options,
  });

  String get prompt =>
      type == QuestionType.definitionToWord ? promptWord.definition : promptWord.word;

  String get correctAnswer => type == QuestionType.definitionToWord
      ? promptWord.word
      : promptWord.definition;

  /// Builds a shuffled question from a target word plus distractors.
  factory GameQuestion.fromWord({
    required VocabularyWord word,
    required List<VocabularyWord> distractors,
    required Random random,
  }) {
    final type =
        random.nextBool() ? QuestionType.definitionToWord : QuestionType.wordToDefinition;
    final List<String> rawOptions = [
      if (type == QuestionType.definitionToWord) word.word else word.definition,
      ...distractors.map(
        (d) => type == QuestionType.definitionToWord ? d.word : d.definition,
      )
    ];
    rawOptions.shuffle(random);
    return GameQuestion(promptWord: word, type: type, options: rawOptions);
  }
}
