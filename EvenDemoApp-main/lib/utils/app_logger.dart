import 'dart:developer' as developer;
import 'package:flutter/foundation.dart';

/// Comprehensive logging utility for the Even Demo App
/// Provides structured logging with different levels and visual formatting
class AppLogger {
  static const String _appName = 'EvenApp';
  
  /// Log levels with emojis for easy visual scanning
  static const String _levelDebug = '🔍 DEBUG';
  static const String _levelInfo = 'ℹ️  INFO';
  static const String _levelWarning = '⚠️  WARN';
  static const String _levelError = '❌ ERROR';
  static const String _levelSuccess = '✅ SUCCESS';
  static const String _levelCamera = '📷 CAMERA';
  static const String _levelNetwork = '🌐 NETWORK';
  static const String _levelBluetooth = '🔵 BLE';
  static const String _levelAudio = '🎤 AUDIO';
  static const String _levelVision = '👁️  VISION';
  
  /// Debug level logging - detailed information for development
  static void debug(String message, {String? tag}) {
    _log(_levelDebug, message, tag: tag);
  }
  
  /// Info level logging - general informational messages
  static void info(String message, {String? tag}) {
    _log(_levelInfo, message, tag: tag);
  }
  
  /// Warning level logging - potential issues that aren't errors
  static void warning(String message, {String? tag}) {
    _log(_levelWarning, message, tag: tag);
  }
  
  /// Error level logging - errors and exceptions
  static void error(String message, {String? tag, Object? error, StackTrace? stackTrace}) {
    _log(_levelError, message, tag: tag);
    if (error != null) {
      _log(_levelError, 'Error Details: $error', tag: tag);
    }
    if (stackTrace != null && kDebugMode) {
      _log(_levelError, 'Stack Trace:\n$stackTrace', tag: tag);
    }
  }
  
  /// Success level logging - successful operations
  static void success(String message, {String? tag}) {
    _log(_levelSuccess, message, tag: tag);
  }
  
  /// Camera-specific logging
  static void camera(String message, {String? tag}) {
    _log(_levelCamera, message, tag: tag ?? 'Camera');
  }
  
  /// Network/API-specific logging
  static void network(String message, {String? tag}) {
    _log(_levelNetwork, message, tag: tag ?? 'Network');
  }
  
  /// Bluetooth/BLE-specific logging
  static void bluetooth(String message, {String? tag}) {
    _log(_levelBluetooth, message, tag: tag ?? 'Bluetooth');
  }
  
  /// Audio/Speech-specific logging
  static void audio(String message, {String? tag}) {
    _log(_levelAudio, message, tag: tag ?? 'Audio');
  }
  
  /// Vision mode specific logging
  static void vision(String message, {String? tag}) {
    _log(_levelVision, message, tag: tag ?? 'VisionMode');
  }
  
  /// Log a section separator for better readability
  static void separator([String? title]) {
    final line = '═' * 80;
    if (title != null) {
      _log(_levelInfo, line);
      _log(_levelInfo, '  $title');
      _log(_levelInfo, line);
    } else {
      _log(_levelInfo, line);
    }
  }
  
  /// Log method entry for debugging flow
  static void methodEntry(String className, String methodName, {Map<String, dynamic>? params}) {
    final paramStr = params != null ? ' with params: $params' : '';
    _log(_levelDebug, '→ Entering $className.$methodName$paramStr', tag: 'Flow');
  }
  
  /// Log method exit for debugging flow
  static void methodExit(String className, String methodName, {dynamic result}) {
    final resultStr = result != null ? ' returning: $result' : '';
    _log(_levelDebug, '← Exiting $className.$methodName$resultStr', tag: 'Flow');
  }
  
  /// Log state changes
  static void stateChange(String stateName, dynamic oldValue, dynamic newValue) {
    _log(_levelInfo, 'State Change: $stateName: $oldValue → $newValue', tag: 'State');
  }
  
  /// Log API requests
  static void apiRequest(String method, String endpoint, {Map<String, dynamic>? data}) {
    _log(_levelNetwork, '→ API Request: $method $endpoint', tag: 'API');
    if (data != null) {
      _log(_levelNetwork, 'Request Data: $data', tag: 'API');
    }
  }
  
  /// Log API responses
  static void apiResponse(String endpoint, int statusCode, {dynamic data}) {
    final status = statusCode >= 200 && statusCode < 300 ? '✓' : '✗';
    _log(_levelNetwork, '← API Response: $status $statusCode from $endpoint', tag: 'API');
    if (data != null && kDebugMode) {
      _log(_levelNetwork, 'Response Data: $data', tag: 'API');
    }
  }
  
  /// Log permission requests
  static void permission(String permissionName, bool granted) {
    final status = granted ? 'GRANTED' : 'DENIED';
    final emoji = granted ? '✅' : '❌';
    _log(_levelInfo, '$emoji Permission $status: $permissionName', tag: 'Permission');
  }
  
  /// Log timer events
  static void timer(String timerName, String action) {
    _log(_levelDebug, 'Timer $timerName: $action', tag: 'Timer');
  }
  
  /// Core logging method
  static void _log(String level, String message, {String? tag}) {
    final timestamp = DateTime.now().toIso8601String().substring(11, 23); // HH:MM:SS.mmm
    final tagStr = tag != null ? '[$tag]' : '';
    final logMessage = '[$timestamp] $level $tagStr $message';
    
    // Use developer.log for better debugging in DevTools
    developer.log(
      message,
      time: DateTime.now(),
      name: tag ?? _appName,
      level: _getLevelValue(level),
    );
    
    // Also print to console for terminal visibility
    // ignore: avoid_print
    print(logMessage);
  }
  
  /// Convert log level to numeric value for developer.log
  static int _getLevelValue(String level) {
    if (level.contains('ERROR')) return 1000;
    if (level.contains('WARN')) return 900;
    if (level.contains('INFO') || level.contains('SUCCESS')) return 800;
    return 500; // DEBUG
  }
  
  /// Log a banner for app lifecycle events
  static void banner(String message) {
    final line = '═' * 80;
    final padding = ' ' * ((80 - message.length - 2) ~/ 2);
    _log(_levelInfo, line);
    _log(_levelInfo, '$padding $message $padding');
    _log(_levelInfo, line);
  }
}
