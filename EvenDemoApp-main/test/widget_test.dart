// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:demo_ai_even/views/home_page.dart';
import 'package:flutter/material.dart';

void main() {
  testWidgets('Home page renders connection overview', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: HomePage(),
      ),
    );

    // allow initial animations/timers to settle
    await tester.pumpAndSettle(const Duration(milliseconds: 100));

    expect(find.text('Vox Augmented'), findsOneWidget);
    expect(find.text('Glasses Connection'), findsOneWidget);
    expect(find.textContaining('Pair and monitor'), findsOneWidget);
  });
}
