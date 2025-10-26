import 'package:flutter/material.dart';

enum StatusLevel { idle, info, success, warning, error }

class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    required this.icon,
    this.level = StatusLevel.info,
    this.pulsing = false,
  });

  final String label;
  final IconData icon;
  final StatusLevel level;
  final bool pulsing;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final colors = _resolveColors(colorScheme);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeInOut,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: colors.background,
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: colors.border, width: 1),
        boxShadow: [
          if (pulsing)
            BoxShadow(
              color: colors.border.withOpacity(0.35),
              blurRadius: 12,
              spreadRadius: 1,
            ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: colors.foreground),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: colors.foreground,
                ),
          ),
        ],
      ),
    );
  }

  _StatusChipColors _resolveColors(ColorScheme colorScheme) {
    switch (level) {
      case StatusLevel.success:
        return _StatusChipColors(
          background: colorScheme.tertiary.withOpacity(0.12),
          border: colorScheme.tertiary,
          foreground: colorScheme.tertiary,
        );
      case StatusLevel.warning:
        return _StatusChipColors(
          background: const Color(0xFFFFF4E5),
          border: const Color(0xFFF97316),
          foreground: const Color(0xFFD97706),
        );
      case StatusLevel.error:
        return _StatusChipColors(
          background: colorScheme.errorContainer,
          border: colorScheme.error,
          foreground: colorScheme.error,
        );
      case StatusLevel.idle:
        return _StatusChipColors(
          background: colorScheme.surface.withOpacity(0.6),
          border: colorScheme.outline.withOpacity(0.4),
          foreground: colorScheme.onSurface,
        );
      case StatusLevel.info:
      default:
        return _StatusChipColors(
          background: colorScheme.primary.withOpacity(0.12),
          border: colorScheme.primary,
          foreground: colorScheme.primary,
        );
    }
  }
}

class _StatusChipColors {
  const _StatusChipColors({
    required this.background,
    required this.border,
    required this.foreground,
  });

  final Color background;
  final Color border;
  final Color foreground;
}
