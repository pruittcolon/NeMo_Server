import 'package:flutter/material.dart';
import 'package:percent_indicator/circular_percent_indicator.dart';
import 'package:flutter_staggered_animations/flutter_staggered_animations.dart';
import 'package:confetti/confetti.dart';
import 'package:fl_chart/fl_chart.dart';
import '../models/vocabulary_word.dart';
import 'word_details_page.dart';

class ResultsPage extends StatefulWidget {
  final int score;
  final int totalQuestions;
  final List<VocabularyWord> missedWords;
  final bool isNewHighScore;

  const ResultsPage(
      {super.key,
      required this.score,
      required this.totalQuestions,
      this.missedWords = const [],
      this.isNewHighScore = false});

  @override
  State<ResultsPage> createState() => _ResultsPageState();
}

class _ResultsPageState extends State<ResultsPage> {
  late final ConfettiController _confettiController;
  int _animatedScore = 0;

  @override
  void initState() {
    super.initState();
    _confettiController = ConfettiController(duration: const Duration(seconds: 2));
    if (widget.isNewHighScore) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _confettiController.play();
      });
    }
    // Animate score counting up quickly
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final target = widget.score;
      const stepMs = 20;
      final steps = (400 / stepMs).round();
      for (int i = 1; i <= steps; i++) {
        await Future<void>.delayed(const Duration(milliseconds: stepMs));
        if (!mounted) return;
        setState(() {
          _animatedScore = ((target * i) / steps).round();
        });
      }
      if (mounted) setState(() => _animatedScore = target);
    });
  }

  @override
  void dispose() {
    _confettiController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final score = widget.score;
    final totalQuestions = widget.totalQuestions;
    final missedWords = widget.missedWords;
    final isNewHighScore = widget.isNewHighScore;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Results'),
      ),
      body: Stack(
        children: [
          Center(
            child: Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularPercentIndicator(
                    radius: 80.0,
                    lineWidth: 12.0,
                    percent: totalQuestions == 0
                        ? 0
                        : (score / totalQuestions).clamp(0, 1),
                    animation: true,
                    animateFromLastPercent: false,
                    center: Text('$_animatedScore / $totalQuestions',
                        style: Theme.of(context).textTheme.titleLarge),
                    progressColor:
                        Theme.of(context).colorScheme.primary,
                    backgroundColor: Theme.of(context).cardColor,
                    circularStrokeCap: CircularStrokeCap.round,
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    height: 180,
                    child: PieChart(
                      PieChartData(
                        sectionsSpace: 2,
                        centerSpaceRadius: 36,
                        sections: _buildPieSections(context, score, totalQuestions),
                      ),
                    ),
                  ),
                  if (isNewHighScore) ...[
                    const SizedBox(height: 8),
                    const Text('New High Score!',
                        style: TextStyle(
                            color: Colors.amber,
                            fontWeight: FontWeight.bold)),
                  ],
                  const SizedBox(height: 32),
                  SizedBox(
                    width: 220,
                    child: ElevatedButton(
                      onPressed: () {
                        Navigator.of(context).pop('playAgain');
                      },
                      child: const Text('Play Again'),
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (missedWords.isNotEmpty) ...[
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text('Review Missed Words',
                          style: Theme.of(context)
                              .textTheme
                              .titleLarge),
                    ),
                    const SizedBox(height: 8),
                    Expanded(
                      child: AnimationLimiter(
                        child: ListView.builder(
                          itemCount: missedWords.length,
                          itemBuilder: (context, index) {
                            final w = missedWords[index];
                            return AnimationConfiguration.staggeredList(
                              position: index,
                              duration: const Duration(milliseconds: 300),
                              child: SlideAnimation(
                                verticalOffset: 24.0,
                                child: FadeInAnimation(
                                  child: Card(
                                    child: ListTile(
                                      title: Text(w.word),
                                      subtitle: Text(w.definition,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis),
                                      trailing:
                                          const Icon(Icons.chevron_right),
                                      onTap: () {
                                        Navigator.of(context).push(
                                            MaterialPageRoute(
                                                builder: (_) =>
                                                    WordDetailsPage(
                                                        word: w)));
                                      },
                                    ),
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          Align(
            alignment: Alignment.topCenter,
            child: ConfettiWidget(
              confettiController: _confettiController,
              blastDirectionality: BlastDirectionality.explosive,
              maxBlastForce: 20,
              minBlastForce: 5,
              emissionFrequency: 0.05,
              numberOfParticles: 25,
              gravity: 0.3,
            ),
          ),
        ],
      ),
    );
  }

  List<PieChartSectionData> _buildPieSections(BuildContext context, int score, int total) {
    final incorrect = (total - score).clamp(0, total);
    final correct = score.clamp(0, total);
    final primary = Theme.of(context).colorScheme.primary;
    final error = Colors.redAccent;
    return [
      PieChartSectionData(
        color: primary,
        value: correct.toDouble(),
        title: 'Correct',
        radius: 60,
        titleStyle: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
      ),
      PieChartSectionData(
        color: error,
        value: incorrect.toDouble(),
        title: 'Missed',
        radius: 60,
        titleStyle: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
      ),
    ];
  }
}
