import 'package:flutter/material.dart';
import '../views/features/notification/vocabulary_game_page.dart';
import 'settings_page.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Vocabuilder')),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).push(PageRouteBuilder(
                    pageBuilder: (context, animation, secondaryAnimation) => const NotificationPage(),
                    transitionsBuilder: (context, animation, secondaryAnimation, child) {
                      final slide = Tween<Offset>(begin: const Offset(0, 0.08), end: Offset.zero)
                          .chain(CurveTween(curve: Curves.easeOutCubic))
                          .animate(animation);
                      return SlideTransition(position: slide, child: FadeTransition(opacity: animation, child: child));
                    },
                  ));
                },
                child: const Text('Start New Round'),
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).push(PageRouteBuilder(
                    pageBuilder: (context, animation, secondaryAnimation) => const NotificationPage(reviewMode: true),
                    transitionsBuilder: (context, animation, secondaryAnimation, child) {
                      final slide = Tween<Offset>(begin: const Offset(0, 0.08), end: Offset.zero)
                          .chain(CurveTween(curve: Curves.easeOutCubic))
                          .animate(animation);
                      return SlideTransition(position: slide, child: FadeTransition(opacity: animation, child: child));
                    },
                  ));
                },
                child: const Text('Review Missed Words'),
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  Navigator.of(context).push(PageRouteBuilder(
                    pageBuilder: (context, animation, secondaryAnimation) => const SettingsPage(),
                    transitionsBuilder: (context, animation, secondaryAnimation, child) {
                      final slide = Tween<Offset>(begin: const Offset(0, 0.08), end: Offset.zero)
                          .chain(CurveTween(curve: Curves.easeOutCubic))
                          .animate(animation);
                      return SlideTransition(position: slide, child: FadeTransition(opacity: animation, child: child));
                    },
                  ));
                },
                child: const Text('Settings'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
