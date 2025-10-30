import 'package:demo_ai_even/models/vocabulary_word.dart';
import 'package:demo_ai_even/utils/database_helper.dart';
import 'package:demo_ai_even/utils/vocabulary_parser.dart';

/// Initializes the vocabulary database with words from vocab.txt if empty
class VocabularyInitializer {
  static bool _initialized = false;
  
  static Future<void> initialize() async {
    if (_initialized) return;
    
    try {
      print("🔤 [VOCAB] Checking vocabulary database...");
      
      final db = DatabaseHelper.instance;
      final wordCount = await db.getWordCount();
      
      if (wordCount > 0) {
        print("✅ [VOCAB] Database already contains $wordCount words");
        _initialized = true;
        return;
      }
      
      print("📚 [VOCAB] Loading words from vocab.txt...");
      final words = await VocabularyParser.parseVocabularyFromAsset('assets/vocab.txt');
      
      print("💾 [VOCAB] Inserting ${words.length} words into database...");
      for (final word in words) {
        await db.insertWord(word);
      }
      
      // Normalize any numbered entries
      await db.normalizeWordsStripNumbering();
      
      final finalCount = await db.getWordCount();
      print("✅ [VOCAB] Database initialized with $finalCount words");
      
      _initialized = true;
    } catch (e) {
      print("❌ [VOCAB] Error initializing vocabulary database: $e");
      rethrow;
    }
  }
}
