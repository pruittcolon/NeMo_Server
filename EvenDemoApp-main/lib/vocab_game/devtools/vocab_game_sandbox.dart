import 'package:flutter/material.dart';

import 'package:demo_ai_even/views/features/notification/vocabulary_game_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const VocabGameSandboxApp());
}

/// Minimal standalone runner so developers can iterate on the vocabulary game
/// without navigating through the rest of the app.
class VocabGameSandboxApp extends StatelessWidget {
  const VocabGameSandboxApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        body: SafeArea(child: VocabularyGamePage()),
      ),
    );
  }
}
