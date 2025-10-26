import 'package:flutter/material.dart';

enum InlineInfoType { info, success, warning, error }

class InlineInfo extends StatelessWidget {
  const InlineInfo({
    super.key,
    required this.title,
    this.subtitle,
    this.type = InlineInfoType.info,
    this.leading,
    this.trailing,
  });

  final String title;
  final String? subtitle;
  final InlineInfoType type;
  final Widget? leading;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colors = _resolve(scheme);
    final icon =
        leading ?? Icon(colors.icon, color: colors.foreground, size: 18);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: colors.background,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          icon,
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: colors.foreground,
                      ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    subtitle!,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: colors.foreground.withOpacity(0.85),
                        ),
                  ),
                ],
              ],
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: 12),
            trailing!,
          ],
        ],
      ),
    );
  }

  _InlineInfoColors _resolve(ColorScheme scheme) {
    switch (type) {
      case InlineInfoType.success:
        return _InlineInfoColors(
          background: scheme.tertiary.withOpacity(0.12),
          border: scheme.tertiary.withOpacity(0.3),
          foreground: scheme.tertiary,
          icon: Icons.check_circle,
        );
      case InlineInfoType.warning:
        return const _InlineInfoColors(
          background: Color(0xFFFFF4E5),
          border: Color(0xFFFBBF24),
          foreground: Color(0xFFB45309),
          icon: Icons.warning_rounded,
        );
      case InlineInfoType.error:
        return _InlineInfoColors(
          background: scheme.errorContainer,
          border: scheme.error.withOpacity(0.4),
          foreground: scheme.error,
          icon: Icons.error_outline_rounded,
        );
      case InlineInfoType.info:
      default:
        return _InlineInfoColors(
          background: scheme.primary.withOpacity(0.08),
          border: scheme.primary.withOpacity(0.25),
          foreground: scheme.primary,
          icon: Icons.info_outline_rounded,
        );
    }
  }
}

class _InlineInfoColors {
  const _InlineInfoColors({
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
