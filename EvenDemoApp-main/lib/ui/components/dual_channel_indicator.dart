import 'package:flutter/material.dart';

enum ChannelStatus { pending, sending, success, failed }

class DualChannelIndicator extends StatelessWidget {
  const DualChannelIndicator({
    super.key,
    required this.left,
    required this.right,
    this.showLabels = true,
  });

  final ChannelStatus left;
  final ChannelStatus right;
  final bool showLabels;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _ChannelPill(
          label: showLabels ? 'Left' : null,
          status: left,
          colorScheme: theme.colorScheme,
        ),
        const SizedBox(width: 12),
        _ChannelPill(
          label: showLabels ? 'Right' : null,
          status: right,
          colorScheme: theme.colorScheme,
        ),
      ],
    );
  }
}

class _ChannelPill extends StatelessWidget {
  const _ChannelPill({
    required this.status,
    required this.colorScheme,
    this.label,
  });

  final ChannelStatus status;
  final ColorScheme colorScheme;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final info = _resolve(status, colorScheme);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 250),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: info.background,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: info.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(info.icon, size: 18, color: info.foreground),
          if (label != null) ...[
            const SizedBox(width: 6),
            Text(
              label!,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: info.foreground,
                  ),
            ),
          ],
        ],
      ),
    );
  }

  _ChannelVisual _resolve(ChannelStatus status, ColorScheme scheme) {
    switch (status) {
      case ChannelStatus.pending:
        return _ChannelVisual(
        background: scheme.surface.withOpacity(0.4),
          border: scheme.outline.withOpacity(0.25),
          foreground: scheme.onSurfaceVariant,
          icon: Icons.fiber_manual_record,
        );
      case ChannelStatus.sending:
        return _ChannelVisual(
          background: scheme.primary.withOpacity(0.12),
          border: scheme.primary,
          foreground: scheme.primary,
          icon: Icons.sync_rounded,
        );
      case ChannelStatus.success:
        return _ChannelVisual(
          background: scheme.tertiary.withOpacity(0.12),
          border: scheme.tertiary,
          foreground: scheme.tertiary,
          icon: Icons.check_circle_rounded,
        );
      case ChannelStatus.failed:
        return _ChannelVisual(
          background: scheme.errorContainer,
          border: scheme.error,
          foreground: scheme.error,
          icon: Icons.error_outline,
        );
    }
  }
}

class _ChannelVisual {
  const _ChannelVisual({
    required this.background,
    required this.border,
    required this.foreground,
    required this.icon,
  });

  final Color background;
  final Color border;
  final Color foreground;
  final IconData icon;
}
