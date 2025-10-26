import 'package:flutter/material.dart';
import '../models/vocabulary_word.dart';

class WordDetailsPage extends StatelessWidget {
  final VocabularyWord word;

  const WordDetailsPage({super.key, required this.word});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(word.word)),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Definition', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(word.definition),
            const SizedBox(height: 16),
            Text('Word Breakdown',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(word.wordBreakdown),
            const SizedBox(height: 16),
            Text('Words with the Same Root',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(word.sameRootWords),
          ],
        ),
      ),
    );
  }
}






