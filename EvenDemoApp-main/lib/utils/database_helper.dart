import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/vocabulary_word.dart';

class DatabaseHelper {
  DatabaseHelper._internal();
  static final DatabaseHelper instance = DatabaseHelper._internal();

  static const String _dbName = 'vocab_game.db';
  static const int _dbVersion = 1;

  static const String tableWords = 'words';

  Database? _database;

  Future<Database> get database async {
    final existing = _database;
    if (existing != null) return existing;
    _database = await _initDB();
    return _database!;
  }

  Future<Database> _initDB() async {
    final dbPath = await getDatabasesPath();
    final path = p.join(dbPath, _dbName);
    return openDatabase(
      path,
      version: _dbVersion,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE $tableWords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            definition TEXT NOT NULL,
            wordBreakdown TEXT NOT NULL,
            sameRootWords TEXT NOT NULL,
            isMissed INTEGER NOT NULL DEFAULT 0
          )
        ''');
      },
    );
  }

  Future<int> insertWord(VocabularyWord word) async {
    final db = await database;
    return db.insert(tableWords, word.toMap(),
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<List<VocabularyWord>> getAllWords() async {
    final db = await database;
    final maps = await db.query(tableWords);
    return maps.map((m) => VocabularyWord.fromMap(m)).toList();
  }

  Future<int> getWordCount() async {
    final db = await database;
    final result =
        await db.rawQuery('SELECT COUNT(*) as count FROM $tableWords');
    final count = Sqflite.firstIntValue(result) ?? 0;
    return count;
  }

  Future<void> normalizeWordsStripNumbering() async {
    final db = await database;
    final maps = await db.query(tableWords, columns: ['id', 'word']);
    final regex = RegExp(r'^\s*\d+[\.)]\s*');
    final batch = db.batch();
    for (final m in maps) {
      final id = m['id'] as int;
      final word = (m['word'] as String?) ?? '';
      final cleaned = word.replaceFirst(regex, '');
      if (cleaned != word) {
        batch.update(tableWords, {'word': cleaned}, where: 'id = ?', whereArgs: [id]);
      }
    }
    await batch.commit(noResult: true, continueOnError: true);
  }

  Future<List<VocabularyWord>> getRandomWords(int count) async {
    final db = await database;
    // Use SQL random order for simplicity; platform-specific random is fine for MVP
    final maps = await db.query(
      tableWords,
      orderBy: 'RANDOM() LIMIT $count',
    );
    return maps.map((m) => VocabularyWord.fromMap(m)).toList();
  }

  Future<List<VocabularyWord>> getRandomDistractors(int count,
      {int? excludeId}) async {
    final db = await database;
    final where = excludeId != null ? 'WHERE id != ?' : '';
    final args = excludeId != null ? [excludeId] : null;
    final maps = await db.rawQuery(
        'SELECT * FROM $tableWords $where ORDER BY RANDOM() LIMIT $count',
        args);
    return maps.map((m) => VocabularyWord.fromMap(m)).toList();
  }

  Future<int> updateWordAsMissed(int wordId, bool isMissed) async {
    final db = await database;
    return db.update(
      tableWords,
      {'isMissed': isMissed ? 1 : 0},
      where: 'id = ?',
      whereArgs: [wordId],
    );
  }

  Future<List<VocabularyWord>> getMissedWords() async {
    final db = await database;
    final maps = await db.query(tableWords, where: 'isMissed = 1');
    return maps.map((m) => VocabularyWord.fromMap(m)).toList();
  }
}
