import 'package:flutter/material.dart';

enum AnswerState { normal, correct, incorrect, disabled }

class AnswerButton extends StatefulWidget {
  final String text;
  final AnswerState state;
  final VoidCallback? onPressed;

  const AnswerButton({super.key, required this.text, required this.state, this.onPressed});

  @override
  State<AnswerButton> createState() => _AnswerButtonState();
}

class _AnswerButtonState extends State<AnswerButton> {
  double _scale = 1.0;

  void _onTapDown(TapDownDetails _) => setState(() => _scale = 0.98);
  void _onTapCancel() => setState(() => _scale = 1.0);
  void _onTap() {
    setState(() => _scale = 1.0);
    widget.onPressed?.call();
  }

  @override
  Widget build(BuildContext context) {
    final bool disabled = widget.state == AnswerState.disabled;
    final Gradient gradient = switch (widget.state) {
      AnswerState.correct => const LinearGradient(colors: [Color(0xFF2E7D32), Color(0xFF43A047)]),
      AnswerState.incorrect => const LinearGradient(colors: [Color(0xFFC62828), Color(0xFFE53935)]),
      AnswerState.disabled => LinearGradient(colors: [Colors.grey.shade700, Colors.grey.shade600]),
      AnswerState.normal => const LinearGradient(colors: [Color(0xFF1B263B), Color(0xFF22304A)]),
    };

    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Transform.scale(
        scale: _scale,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: gradient,
            borderRadius: BorderRadius.circular(12),
            boxShadow: [
              if (widget.state == AnswerState.correct)
                BoxShadow(color: Colors.green.withOpacity(0.3), blurRadius: 12, spreadRadius: 1),
              if (widget.state == AnswerState.incorrect)
                BoxShadow(color: Colors.red.withOpacity(0.3), blurRadius: 12, spreadRadius: 1),
            ],
            border: Border.all(color: Colors.white24),
          ),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTapDown: disabled ? null : _onTapDown,
            onTapCancel: disabled ? null : _onTapCancel,
            onTap: disabled ? null : _onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(
                children: [
                  Expanded(
                    child: Text(widget.text, style: const TextStyle(fontSize: 16, color: Colors.white)),
                  ),
                  if (widget.state == AnswerState.correct)
                    const Icon(Icons.check, color: Colors.greenAccent)
                  else if (widget.state == AnswerState.incorrect)
                    const Icon(Icons.close, color: Colors.redAccent),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
