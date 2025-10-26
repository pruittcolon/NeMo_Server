class VocabularyWord {
  final int? id;
  final String word;
  final String definition;
  final String wordBreakdown;
  final String sameRootWords; // comma-separated in DB
  bool isMissed;

  VocabularyWord({
    this.id,
    required this.word,
    required this.definition,
    required this.wordBreakdown,
    required this.sameRootWords,
    this.isMissed = false,
  });

  factory VocabularyWord.fromMap(Map<String, dynamic> map) {
    return VocabularyWord(
      id: map['id'] as int?,
      word: map['word'] as String,
      definition: map['definition'] as String,
      wordBreakdown: map['wordBreakdown'] as String,
      sameRootWords: map['sameRootWords'] as String,
      isMissed: (map['isMissed'] is int
          ? map['isMissed'] == 1
          : map['isMissed'] as bool? ?? false),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'word': word,
      'definition': definition,
      'wordBreakdown': wordBreakdown,
      'sameRootWords': sameRootWords,
      'isMissed': isMissed ? 1 : 0,
    };
  }
}






