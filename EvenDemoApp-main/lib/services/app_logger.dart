import 'dart:async';

import 'package:flutter/foundation.dart';

class LogEntry {
  final DateTime timestamp;
  final String tag;
  final String message;
  final bool isError;

  LogEntry({
    required this.timestamp,
    required this.tag,
    required this.message,
    required this.isError,
  });
}

class AppLogger {
  AppLogger._();

  static final AppLogger instance = AppLogger._();

  final StreamController<LogEntry> _controller =
      StreamController<LogEntry>.broadcast();

  Stream<LogEntry> get stream => _controller.stream;

  void log(String tag, String message, {bool isError = false}) {
    final entry = LogEntry(
      timestamp: DateTime.now(),
      tag: tag,
      message: message,
      isError: isError,
    );
    debugPrint('[][] ');
    if (!_controller.isClosed) {
      _controller.add(entry);
    }
  }

  void dispose() {
    _controller.close();
  }
}
