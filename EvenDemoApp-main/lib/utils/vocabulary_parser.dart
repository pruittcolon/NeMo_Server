import 'package:flutter/services.dart' show rootBundle;

import '../models/vocabulary_word.dart';

class VocabularyParser {
  static Future<List<VocabularyWord>> parseVocabularyFromAsset(
      String assetPath) async {
    final raw = await rootBundle.loadString(assetPath);
    final lines = raw.split(RegExp(r'\r?\n')).map((e) => e.trim()).toList();

    final List<VocabularyWord> words = [];

    String? currentWord;
    String? definition;
    String? breakdown;
    String? sameRoot;

    void flush() {
      if (currentWord != null &&
          definition != null &&
          breakdown != null &&
          sameRoot != null) {
        words.add(
          VocabularyWord(
            word: currentWord!,
            definition: definition!,
            wordBreakdown: breakdown!,
            sameRootWords: sameRoot!,
          ),
        );
      }
      currentWord = null;
      definition = null;
      breakdown = null;
      sameRoot = null;
    }

    for (final line in lines) {
      if (line.isEmpty) {
        // Ignore empty lines; fields may be separated by blanks
        continue;
      }

      if (line.startsWith('Definition:')) {
        definition = line.replaceFirst('Definition:', '').trim();
      } else if (line.startsWith('Word Breakdown:')) {
        breakdown = line.replaceFirst('Word Breakdown:', '').trim();
      } else if (line.startsWith('Words with the Same Root:')) {
        sameRoot = line.replaceFirst('Words with the Same Root:', '').trim();
      } else {
        // treat as the word title line
        // When we encounter a new word while we still have a previously parsed word, flush previous
        if (currentWord != null &&
            definition != null &&
            breakdown != null &&
            sameRoot != null) {
          flush();
        }
        // Strip numbering like "1." or "12)" at the start
        currentWord = line.replaceFirst(RegExp(r'^\s*\d+[\.)]\s*'), '');
      }
    }

    // flush the last item if file does not end with a blank line
    flush();

    return words;
  }
}
