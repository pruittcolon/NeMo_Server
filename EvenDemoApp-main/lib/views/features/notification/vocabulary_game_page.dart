import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:lottie/lottie.dart';

import 'package:demo_ai_even/screens/results_page.dart';
import 'package:demo_ai_even/vocab_game/game_audio.dart';
import 'package:demo_ai_even/vocab_game/game_controller.dart';
import 'package:demo_ai_even/vocab_game/game_preferences.dart';
import 'package:demo_ai_even/vocab_game/game_repository.dart';
import 'package:demo_ai_even/vocab_game/game_question.dart';
import 'package:demo_ai_even/widgets/answer_button.dart';

class VocabularyGamePage extends StatefulWidget {
  final bool reviewMode;
  final VocabRepository? repository;
  final GamePreferences? preferences;
  final GameAudio? audio;
  final Duration advanceDelay;

  const VocabularyGamePage({
    super.key,
    this.reviewMode = false,
    this.repository,
    this.preferences,
    this.audio,
    this.advanceDelay = const Duration(milliseconds: 1500),
  });

  @override
  State<VocabularyGamePage> createState() => _VocabularyGamePageState();
}

@Deprecated('Use VocabularyGamePage instead')
class NotificationPage extends VocabularyGamePage {
  const NotificationPage({Key? key, bool reviewMode = false})
      : super(key: key, reviewMode: reviewMode);
}

class _VocabularyGamePageState extends State<VocabularyGamePage>
    with TickerProviderStateMixin {
  static const Color primaryColor = Color(0xFF0D1B2A);
  static const Color cardColor = Color(0xFF1B263B);
  static const Color accentColor = Color(0xFF33A1F2);
  static const Color textColor = Colors.white;
  static const Color subtitleColor = Colors.white70;

  late final VocabularyGameController _controller;
  Timer? _advanceTimer;
  Future<bool>? _idleAnimExists;
  bool _showCorrectAnimation = false;

  @override
  void initState() {
    super.initState();
    _idleAnimExists = _assetExists('assets/anim/idle_animation.json');
    _controller = VocabularyGameController(
      repository: widget.repository,
      preferences: widget.preferences,
      audio: widget.audio,
    )..addListener(_onControllerChanged);
    _controller.initialize(reviewMode: widget.reviewMode);
  }

  void _onControllerChanged() {
    if (!mounted) return;
    setState(() {});
  }

  @override
  void dispose() {
    _advanceTimer?.cancel();
    _controller.removeListener(_onControllerChanged);
    _controller.dispose();
    super.dispose();
  }

  void _handleAnswer(String option) async {
    if (_controller.isAnswered || _controller.isLoading) return;
    await _controller.selectAnswer(option);
    _showCorrectAnimation = _controller.lastAnswerCorrect;
    if (_controller.lastAnswerCorrect) {
      HapticFeedback.lightImpact();
    } else {
      HapticFeedback.mediumImpact();
    }
    setState(() {});
    _scheduleAdvance();
  }

  void _scheduleAdvance() {
    _advanceTimer?.cancel();
    if (widget.advanceDelay == Duration.zero) {
      unawaited(_advanceOrComplete());
    } else {
      _advanceTimer = Timer(widget.advanceDelay, () {
        unawaited(_advanceOrComplete());
      });
    }
  }

  Future<void> _advanceOrComplete() async {
    if (!mounted || _controller.isLoading) return;
    final hasNext = await _controller.advanceToNextQuestion();
    if (!hasNext) {
      await _showResults();
    } else if (mounted) {
      setState(() {
        _showCorrectAnimation = false;
      });
    }
  }

  Future<void> _showResults() async {
    final summary = await _controller.buildSummary();
    if (!mounted) return;
    final result = await Navigator.of(context).push(_buildSlideRoute(
      ResultsPage(
        score: summary.score,
        totalQuestions: summary.totalQuestions,
        missedWords: summary.missedWords,
        isNewHighScore: summary.isNewHighScore,
      ),
    ));
    if (!mounted) return;
    if (result == 'playAgain') {
      await _controller.restartRound();
    } else if (result == 'reviewMode') {
      await _controller.startReviewRound();
    } else {
      setState(() => _showCorrectAnimation = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isLoading = _controller.isLoading;
    final question = _controller.currentQuestion;
    return Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        title: const Text(
          'Vocabulary Game',
          style: TextStyle(fontWeight: FontWeight.bold, color: textColor),
        ),
        backgroundColor: primaryColor,
        elevation: 0,
        iconTheme: const IconThemeData(color: textColor),
        actions: [
          TextButton(
            onPressed: isLoading ? null : () => _controller.startReviewRound(),
            child: const Text('Review Mode', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
      body: Stack(
        children: [
          _AnimatedBackground(),
          const _AmbientParticles(),
          FutureBuilder<bool>(
            future: _idleAnimExists,
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.done &&
                  (snapshot.data ?? false)) {
                return IgnorePointer(
                  child: Opacity(
                    opacity: 0.25,
                    child: Center(
                      child: Lottie.asset(
                        'assets/anim/idle_animation.json',
                        repeat: true,
                        frameRate: FrameRate.max,
                        width: MediaQuery.of(context).size.width * 0.6,
                      ),
                    ),
                  ),
                );
              }
              return const SizedBox.shrink();
            },
          ),
          if (isLoading)
            const Center(child: CircularProgressIndicator(color: accentColor))
          else if (!_controller.hasQuestions)
            _EmptyState(onRetry: () => _controller.restartRound())
          else
            Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                children: [
                  _ScoreHeader(score: _controller.score, highScore: _controller.highScore),
                  const SizedBox(height: 8),
                  _ProgressBar(
                    progress: _controller.totalQuestions == 0
                        ? 0
                        : (_controller.currentQuestionIndex + 1) /
                            _controller.totalQuestions,
                  ),
                  const Spacer(),
                  _QuestionCard(question: question!, accent: accentColor),
                  const Spacer(),
                  ..._controller.options.map((value) {
                    final correct = question.correctAnswer;
                    final state = !_controller.isAnswered
                        ? AnswerState.normal
                        : (value == correct
                            ? AnswerState.correct
                            : (value == _controller.selectedAnswer
                                ? AnswerState.incorrect
                                : AnswerState.disabled));
                    return AnswerButton(
                      text: value,
                      state: state,
                      onPressed: _controller.isAnswered ? null : () => _handleAnswer(value),
                    );
                  }),
                  const Spacer(),
                ],
              ),
            ),
          if (_showCorrectAnimation && _controller.lastAnswerCorrect)
            _buildFeedbackOverlay('assets/anim/correct_animation.json'),
          if (_controller.isAnswered && !_controller.lastAnswerCorrect)
            _buildFeedbackOverlay('assets/anim/incorrect_animation.json'),
        ],
      ),
    );
  }

  Widget _buildFeedbackOverlay(String assetPath) {
    final media = MediaQuery.of(context);
    final double topPadding = media.padding.top + kToolbarHeight + 90;
    final bool isPositive = assetPath.contains('correct');
    return Positioned.fill(
      child: IgnorePointer(
        child: Padding(
          padding: EdgeInsets.only(top: topPadding),
          child: Align(
            alignment: Alignment.topCenter,
            child: FutureBuilder<bool>(
              future: _assetExists(assetPath),
              builder: (context, snapshot) {
                final available =
                    snapshot.connectionState == ConnectionState.done && (snapshot.data ?? false);
                if (available) {
                  return Lottie.asset(
                    assetPath,
                    repeat: false,
                    frameRate: FrameRate.max,
                    width: media.size.width * 0.5,
                  );
                }
                return AnimatedOpacity(
                  opacity: _showCorrectAnimation || _controller.isAnswered ? 1.0 : 0.0,
                  duration: const Duration(milliseconds: 250),
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.35),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    child: Text(
                      isPositive ? '+1 Correct!' : 'Try Again',
                      style: TextStyle(
                        color: isPositive ? Colors.greenAccent : Colors.redAccent,
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  PageRouteBuilder _buildSlideRoute(Widget page) {
    return PageRouteBuilder(
      pageBuilder: (context, animation, secondaryAnimation) => page,
      transitionsBuilder: (context, animation, secondaryAnimation, child) {
        final offsetAnimation = Tween<Offset>(
          begin: const Offset(0.1, 0.0),
          end: Offset.zero,
        ).chain(CurveTween(curve: Curves.easeOutCubic)).animate(animation);
        final fade = CurvedAnimation(parent: animation, curve: Curves.easeOut);
        return SlideTransition(
          position: offsetAnimation,
          child: FadeTransition(opacity: fade, child: child),
        );
      },
    );
  }

  Future<bool> _assetExists(String assetPath) async {
    try {
      await rootBundle.load(assetPath);
      return true;
    } catch (_) {
      return false;
    }
  }
}

class _ScoreHeader extends StatelessWidget {
  const _ScoreHeader({required this.score, required this.highScore});
  final int score;
  final int highScore;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 80,
      child: Stack(
        alignment: Alignment.center,
        children: [
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            transitionBuilder: (child, animation) => SlideTransition(
              position: Tween<Offset>(begin: const Offset(0.0, 0.4), end: Offset.zero)
                  .chain(CurveTween(curve: Curves.easeOutCubic))
                  .animate(animation),
              child: FadeTransition(opacity: animation, child: child),
            ),
            child: Text(
              'Score: $score   •   High: $highScore',
              key: ValueKey<int>(score),
              style: const TextStyle(
                color: _VocabularyGamePageState.textColor,
                fontSize: 32,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProgressBar extends StatelessWidget {
  const _ProgressBar({required this.progress});
  final double progress;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      decoration: BoxDecoration(
        color: Colors.transparent,
        boxShadow: [
          BoxShadow(
            color: _VocabularyGamePageState.accentColor.withOpacity(0.35),
            blurRadius: 14,
            spreadRadius: 1,
          ),
        ],
        borderRadius: BorderRadius.circular(8),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: LinearProgressIndicator(
          value: progress.clamp(0, 1),
          color: _VocabularyGamePageState.accentColor,
          backgroundColor: _VocabularyGamePageState.cardColor,
          minHeight: 8,
        ),
      ),
    );
  }
}

class _QuestionCard extends StatelessWidget {
  const _QuestionCard({required this.question, required this.accent});

  final GameQuestion question;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 300),
      transitionBuilder: (child, animation) => SlideTransition(
        position: Tween<Offset>(begin: const Offset(0.1, 0), end: Offset.zero)
            .chain(CurveTween(curve: Curves.easeOutCubic))
            .animate(animation),
        child: FadeTransition(opacity: animation, child: child),
      ),
      child: Container(
        key: ValueKey(question.prompt),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF1B263B), Color(0xFF22304A)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              blurRadius: 12,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            children: [
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 250),
                child: Text(
                  question.type == QuestionType.definitionToWord
                      ? 'Select the word for this definition'
                      : 'What does this word mean?',
                  key: ValueKey(question.type),
                  style: const TextStyle(
                    color: _VocabularyGamePageState.subtitleColor,
                    fontSize: 16,
                  ),
                ),
              ),
              const SizedBox(height: 12),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                transitionBuilder: (child, animation) => FadeTransition(
                  opacity: animation,
                  child: SlideTransition(
                    position: Tween<Offset>(begin: const Offset(0, 0.1), end: Offset.zero)
                        .animate(animation),
                    child: child,
                  ),
                ),
                child: Text(
                  question.prompt,
                  key: ValueKey(question.prompt),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: accent,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.menu_book_rounded, size: 56, color: Colors.white70),
          const SizedBox(height: 16),
          const Text(
            'No vocabulary entries found.\nAdd words to start playing.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: onRetry,
            child: const Text('Try Again'),
          ),
        ],
      ),
    );
  }
}

class _AmbientParticles extends StatefulWidget {
  const _AmbientParticles();

  @override
  State<_AmbientParticles> createState() => _AmbientParticlesState();
}

class _AmbientParticlesState extends State<_AmbientParticles>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  final List<_Particle> _particles =
      List.generate(30, (_) => _Particle.random());

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 30),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: CustomPaint(
        painter: _ParticlesPainter(_particles, _controller.value),
        size: Size.infinite,
      ),
    );
  }
}

class _Particle {
  double x;
  double y;
  double radius;
  double speedX;
  double speedY;
  double phase;

  _Particle({
    required this.x,
    required this.y,
    required this.radius,
    required this.speedX,
    required this.speedY,
    required this.phase,
  });

  factory _Particle.random() {
    final rnd = math.Random();
    return _Particle(
      x: rnd.nextDouble(),
      y: rnd.nextDouble(),
      radius: 0.002 + rnd.nextDouble() * 0.006,
      speedX: (rnd.nextDouble() - 0.5) * 0.0006,
      speedY: (rnd.nextDouble() - 0.5) * 0.0006,
      phase: rnd.nextDouble() * math.pi * 2,
    );
  }
}

class _ParticlesPainter extends CustomPainter {
  final List<_Particle> particles;
  final double t;

  _ParticlesPainter(this.particles, this.t);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..style = PaintingStyle.fill
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);

    for (final p in particles) {
      p.x += p.speedX + 0.0002 * math.sin(t * math.pi * 2 + p.phase);
      p.y += p.speedY + 0.0002 * math.cos(t * math.pi * 2 + p.phase);

      if (p.x < -0.05) p.x = 1.05;
      if (p.x > 1.05) p.x = -0.05;
      if (p.y < -0.05) p.y = 1.05;
      if (p.y > 1.05) p.y = -0.05;

      final offset = Offset(p.x * size.width, p.y * size.height);
      final r = p.radius * size.shortestSide * 1.2;

      final hueMix =
          (0.5 + 0.5 * math.sin(p.phase + t * 2)).clamp(0.0, 1.0);
      final color = Color.lerp(const Color(0xFF33A1F2), const Color(0xFF8A2BE2), hueMix)!
          .withOpacity(0.08);
      paint.color = color;
      canvas.drawCircle(offset, r, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _ParticlesPainter oldDelegate) => true;
}

class _AnimatedBackground extends StatefulWidget {
  @override
  State<_AnimatedBackground> createState() => _AnimatedBackgroundState();
}

class _AnimatedBackgroundState extends State<_AnimatedBackground>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final t = _controller.value;
        return Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color.lerp(const Color(0xFF0D1B2A), const Color(0xFF1B263B), t)!,
                Color.lerp(const Color(0xFF1B263B), const Color(0xFF3A0CA3), t)!,
              ],
            ),
          ),
        );
      },
    );
  }
}
