import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:demo_ai_even/services/app_logger.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class MemoryService {
  static final MemoryService _instance = MemoryService._();
  static MemoryService get instance => _instance;

  MemoryService._();

  late Dio _dio;
  String _serverBase = '';
  String _activeSessionId = 'mobile-session';
  final ValueNotifier<String> sessionNotifier =
      ValueNotifier<String>('mobile-session');
  final StreamController<MemoryQueryEvent> _queryStreamController =
      StreamController<MemoryQueryEvent>.broadcast();

  String get activeSessionId => _activeSessionId;

  void setActiveSessionId(String sessionId) {
    final trimmed = sessionId.trim();
    if (trimmed.isEmpty) return;
    _activeSessionId = trimmed;
    AppLogger.instance
        .log('MemoryService', 'Active session updated: $_activeSessionId');
    if (sessionNotifier.value != _activeSessionId) {
      sessionNotifier.value = _activeSessionId;
    }
  }

  Stream<MemoryQueryEvent> get queryStream => _queryStreamController.stream;

  void initialize() {
    // Read the server base URL from .env at initialization time
    _serverBase = dotenv.env['MEMORY_SERVER_BASE']?.trim() ?? '';
    
    _dio = Dio(
      BaseOptions(
        baseUrl: _serverBase,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 60),
        sendTimeout: const Duration(seconds: 60),
      ),
    );
    AppLogger.instance
        .log('MemoryService', 'Dio initialized with base $_serverBase');
  }

  Future<bool> checkConnection() async {
    try {
      final response = await _dio.get('/health');
      final ok = response.statusCode == 200;
      AppLogger.instance
          .log('MemoryService', 'Health check status: ${response.statusCode}');
      return ok;
    } catch (e) {
      AppLogger.instance
          .log('MemoryService', 'Health check failed: $e', isError: true);
      return false;
    }
  }

  Future<MemoryResponse> askQuestion(String question,
      {String? sessionId}) async {
    final resolvedSessionId = (sessionId == null || sessionId.trim().isEmpty)
        ? _activeSessionId
        : sessionId.trim();
    if (sessionId == null || sessionId.trim().isEmpty) {
      AppLogger.instance
          .log('MemoryService', 'Using active session: $resolvedSessionId');
    } else {
      setActiveSessionId(resolvedSessionId);
    }
    AppLogger.instance.log('MemoryService',
        "Asking question (session: $resolvedSessionId): $question");
    print("[MEMORY_SERVICE] Making request to: $_serverBase/query");
    print(
        "[MEMORY_SERVICE] Request data: {'question': '$question', 'session_id': '$resolvedSessionId'}");
    try {
      final response = await _dio.post(
        '/query',
        data: {
          'question': question,
          'session_id': resolvedSessionId,
        },
      );
      print("[MEMORY_SERVICE] Response status: ${response.statusCode}");
      print("[MEMORY_SERVICE] Response headers: ${response.headers}");

      if (response.statusCode == 200) {
        final data = response.data;
        print("[MEMORY_SERVICE] Raw response data type: ${data.runtimeType}");
        print("[MEMORY_SERVICE] Raw response data: $data");

        // Handle different response formats
        String answer = '';
        if (data is Map<String, dynamic>) {
          answer = data['answer'] ?? '';
        } else if (data is String) {
          // Try to parse JSON string
          try {
            final parsedData = jsonDecode(data);
            answer = parsedData['answer'] ?? '';
          } catch (e) {
            print("[MEMORY_SERVICE] Failed to parse JSON: $e");
            answer = data; // Use raw string as answer
          }
        }

        print("[MEMORY_SERVICE] Answer from server: '$answer'");
        print("[MEMORY_SERVICE] Answer length: ${answer.length}");
        AppLogger.instance.log('MemoryService', 'Received answer: $answer');

        final memoryResponse = (data is Map<String, dynamic>)
            ? MemoryResponse(
                answer: answer,
                hits: List<Map<String, dynamic>>.from(data['hits'] ?? []),
                jobId: data['job_id'],
                emotions: data['emotions'],
              )
            : MemoryResponse(
                answer: answer,
                hits: [],
                jobId: null,
                emotions: null,
              );

        _queryStreamController.add(
          MemoryQueryEvent(
            sessionId: resolvedSessionId,
            question: question,
            response: memoryResponse,
          ),
        );

        return memoryResponse;
      } else {
        throw Exception('Server error: ${response.statusCode}');
      }
    } catch (e) {
      AppLogger.instance
          .log('MemoryService', 'Question failed: $e', isError: true);
      throw Exception('Failed to ask question: $e');
    }
  }

  Future<void> clearSession({String? sessionId}) async {
    final resolvedSessionId = (sessionId == null || sessionId.trim().isEmpty)
        ? _activeSessionId
        : sessionId.trim();
    setActiveSessionId(resolvedSessionId);
    AppLogger.instance
        .log('MemoryService', 'Clearing session $resolvedSessionId');
    try {
      await _dio.post(
        '/memory/clear_session',
        data: {'session_id': resolvedSessionId},
      );
    } catch (e) {
      AppLogger.instance
          .log('MemoryService', 'Failed to clear session: $e', isError: true);
      throw Exception('Failed to clear session: $e');
    }
  }

  Future<List<Memory>> getMemories({int limit = 20}) async {
    AppLogger.instance
        .log('MemoryService', 'Fetching memories (limit: $limit)');
    try {
      final response =
          await _dio.get('/memory/list', queryParameters: {'limit': limit});

      if (response.statusCode == 200) {
        final data = response.data;
        final memories =
            List<Map<String, dynamic>>.from(data['memories'] ?? []);
        AppLogger.instance
            .log('MemoryService', 'Fetched ${memories.length} memories');
        return memories.map((m) => Memory.fromJson(m)).toList();
      } else {
        throw Exception('Server error: ${response.statusCode}');
      }
    } catch (e) {
      AppLogger.instance
          .log('MemoryService', 'Failed to get memories: $e', isError: true);
      throw Exception('Failed to get memories: $e');
    }
  }

  Future<String> getLatestTranscription() async {
    AppLogger.instance.log('MemoryService', 'Requesting latest transcription');
    try {
      final response = await _dio.get('/latest_result');
      if (response.statusCode == 200) {
        final text = response.data.toString();
        AppLogger.instance.log('MemoryService',
            'Latest transcription received (${text.length} chars)');
        return text;
      } else {
        throw Exception('Server error: ${response.statusCode}');
      }
    } catch (e) {
      AppLogger.instance.log(
          'MemoryService', 'Failed to get latest transcription: $e',
          isError: true);
      throw Exception('Failed to get latest transcription: $e');
    }
  }
}

class MemoryQueryEvent {
  final String sessionId;
  final String question;
  final MemoryResponse response;

  MemoryQueryEvent({
    required this.sessionId,
    required this.question,
    required this.response,
  });
}

class MemoryResponse {
  final String answer;
  final List<Map<String, dynamic>> hits;
  final String? jobId;
  final Map<String, dynamic>? emotions;

  MemoryResponse({
    required this.answer,
    required this.hits,
    this.jobId,
    this.emotions,
  });
}

class Memory {
  final int id;
  final String title;
  final String body;
  final List<String> tags;
  final String sourceJobId;
  final String createdAt;

  Memory({
    required this.id,
    required this.title,
    required this.body,
    required this.tags,
    required this.sourceJobId,
    required this.createdAt,
  });

  factory Memory.fromJson(Map<String, dynamic> json) {
    return Memory(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      body: json['body'] ?? '',
      tags: List<String>.from(json['tags'] ?? []),
      sourceJobId: json['source_job_id'] ?? '',
      createdAt: json['created_at'] ?? '',
    );
  }
}
