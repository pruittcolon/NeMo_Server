import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  static const Color primaryColor = Color(0xFF0D1B2A);
  static const Color scaffoldBackground = Color(0xFF0D1B2A);
  static const Color cardColor = Color(0xFF1B263B);
  static const Color accentColor = Color(0xFF33A1F2);

  static ThemeData theme = (() {
    final baseScheme =
        ColorScheme.fromSeed(seedColor: accentColor, brightness: Brightness.dark);
    final scheme = baseScheme.copyWith(
      primary: accentColor,
      secondary: accentColor,
      surface: cardColor,
      surfaceTint: accentColor,
    );

    return ThemeData(
      colorScheme: scheme,
      scaffoldBackgroundColor: scaffoldBackground,
      cardColor: cardColor,
      appBarTheme: const AppBarTheme(
        backgroundColor: primaryColor,
        foregroundColor: Colors.white,
        elevation: 0,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: cardColor,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      textTheme: GoogleFonts.montserratTextTheme()
          .merge(
            GoogleFonts.latoTextTheme(),
          )
          .apply(
            bodyColor: Colors.white,
            displayColor: Colors.white,
          ),
      useMaterial3: true,
    );
  })();
}





