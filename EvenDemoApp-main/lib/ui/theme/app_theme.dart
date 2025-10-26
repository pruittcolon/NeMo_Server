import 'package:flutter/material.dart';

class AppTheme {
  static const Color _primary = Color(0xFF2D7FF9);
  static const Color _secondary = Color(0xFF8A9EFF);
  static const Color _surface = Color(0xFF0F172A);
  static const Color _surfaceContainer = Color(0xFF1E293B);
  static const Color _error = Color(0xFFFF5252);

  static ThemeData get lightTheme => _baseTheme(Brightness.light);
  static ThemeData get darkTheme => _baseTheme(Brightness.dark);

  static ThemeData _baseTheme(Brightness brightness) {
    final bool isDark = brightness == Brightness.dark;
    final baseScheme =
        ColorScheme.fromSeed(seedColor: _primary, brightness: brightness);
    final colorScheme = baseScheme.copyWith(
      primary: _primary,
      onPrimary: Colors.white,
      secondary: _secondary,
      onSecondary: Colors.white,
      tertiary: const Color(0xFF38BDF8),
      onTertiary: Colors.white,
      error: _error,
      onError: Colors.white,
      surface: isDark ? _surface : Colors.white,
      onSurface: isDark ? Colors.white : const Color(0xFF0F172A),
      primaryContainer:
          isDark ? const Color(0xFF1D4ED8) : const Color(0xFFDCE6FF),
      onPrimaryContainer:
          isDark ? const Color(0xFFC7D2FF) : const Color(0xFF0B1F4B),
      secondaryContainer:
          isDark ? const Color(0xFF312E81) : const Color(0xFFE0E7FF),
      onSecondaryContainer:
          isDark ? const Color(0xFFC7D2FE) : const Color(0xFF111827),
      errorContainer:
          isDark ? const Color(0xFF7F1D1D) : const Color(0xFFFFD8D6),
      onErrorContainer:
          isDark ? const Color(0xFFFECACA) : const Color(0xFF410002),
      outline: isDark ? const Color(0xFF475569) : const Color(0xFF64748B),
      shadow: Colors.black.withOpacity(0.6),
      inverseSurface:
          isDark ? const Color(0xFFE2E8F0) : const Color(0xFF0F172A),
      onInverseSurface: isDark ? const Color(0xFF111827) : Colors.white,
      inversePrimary:
          isDark ? const Color(0xFF93C5FD) : const Color(0xFF1D4ED8),
      surfaceTint: _primary,
    );

    final scaffoldColor =
        isDark ? const Color(0xFF0A1220) : const Color(0xFFF1F5F9);
    final onScaffoldColor =
        isDark ? Colors.white : const Color(0xFF0F172A);
    final surfaceContainerColor =
        isDark ? _surfaceContainer : const Color(0xFFE2E8F0);

    final textTheme = _buildTextTheme(brightness, colorScheme);

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: scaffoldColor,
      cardTheme: CardTheme(
        color: colorScheme.surface,
        shadowColor: colorScheme.shadow,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
        margin: EdgeInsets.zero,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: colorScheme.primary,
          foregroundColor: colorScheme.onPrimary,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          textStyle:
              textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: colorScheme.primary,
          side: BorderSide(color: colorScheme.primary.withOpacity(0.5)),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: colorScheme.primary,
          textStyle:
              textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
        ),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        foregroundColor: onScaffoldColor,
        titleTextStyle: textTheme.titleLarge,
        centerTitle: false,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surfaceContainerColor,
        selectedColor: colorScheme.primary.withOpacity(0.2),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        labelStyle: textTheme.labelLarge,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
      ),
      textTheme: textTheme,
      dividerTheme: DividerThemeData(
        color: colorScheme.outline.withOpacity(0.2),
        space: 32,
        thickness: 1,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colorScheme.surface,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: colorScheme.outline.withOpacity(0.3)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: colorScheme.outline.withOpacity(0.2)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: colorScheme.primary, width: 1.4),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: isDark ? const Color(0xFF243044) : const Color(0xFFD7DFEC),
        contentTextStyle: textTheme.bodyMedium?.copyWith(
          color: onScaffoldColor,
        ),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
      ),
    );
  }

  static TextTheme _buildTextTheme(
      Brightness brightness, ColorScheme colorScheme) {
    final base = brightness == Brightness.dark
        ? Typography.whiteMountainView
        : Typography.blackMountainView;
    return base.copyWith(
      headlineMedium: base.headlineMedium?.copyWith(
        fontWeight: FontWeight.w600,
      ),
      titleLarge: base.titleLarge?.copyWith(
        fontWeight: FontWeight.w700,
        color: colorScheme.onSurface,
      ),
      titleMedium: base.titleMedium?.copyWith(
        fontWeight: FontWeight.w600,
      ),
      labelLarge: base.labelLarge?.copyWith(
        fontWeight: FontWeight.w600,
        letterSpacing: 0.2,
      ),
      bodyLarge: base.bodyLarge?.copyWith(height: 1.4),
      bodyMedium: base.bodyMedium?.copyWith(height: 1.45),
      bodySmall: base.bodySmall?.copyWith(height: 1.45),
    );
  }
}
