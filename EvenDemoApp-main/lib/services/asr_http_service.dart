import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:demo_ai_even/services/app_logger.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

class AsrEvent {
  final String type; // 'final' | 'error'
  final String text;
  final String speaker;
  final String? error;
  final Map<String, dynamic>? emotion;

  AsrEvent(this.type, this.text, this.speaker, {this.error, this.emotion});
}

class AsrHttpService {
  static final AsrHttpService _instance = AsrHttpService._();
  static AsrHttpService get I => _instance;

  AsrHttpService._();

  final AudioRecorder _recorder = AudioRecorder();
  final StreamController<AsrEvent> _events =
      StreamController<AsrEvent>.broadcast();

  Stream<AsrEvent> get stream => _events.stream;

  bool _running = false;
  Future<void>? _worker;
  late Dio _dio;

  final Set<Future<void>> _pendingUploads = <Future<void>>{};
  Completer<void>? _stopSignal;

  String _serverBase = dotenv.env['ASR_SERVER_BASE']?.trim() ?? '';

  Duration _chunk = Duration(
    seconds: int.tryParse(dotenv.env['ASR_CHUNK_SECS'] ?? '') ?? 30,
  );

  void _logConfig() {
    print("🔧 [ASR DEBUG] Server Base: '$_serverBase'");
    print("🔧 [ASR DEBUG] Chunk Duration: $_chunk");
    print("🔧 [ASR DEBUG] Stream ID: $_streamId");
    if (_serverBase.isEmpty) {
      print(
          "❌ [ASR ERROR] Empty server base! This will cause 'no host specified' errors.");
    }
  }

  final String _streamId = 'stream-${DateTime.now().millisecondsSinceEpoch}';
  int _seq = 0;

  void configure({int? chunkSeconds}) {
    if (chunkSeconds != null) {
      final seconds = chunkSeconds.clamp(3, 60).toInt();
      _chunk = Duration(seconds: seconds);
    }
  }

  Future<void> start() async {
    if (_running) return;

    if (!await _ensurePerms()) {
      _emitSystem('Microphone permission denied.');
      return;
    }

    _logConfig(); // Log configuration before creating Dio

    _dio = Dio(
      BaseOptions(
        baseUrl: _serverBase,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 240),
        sendTimeout: const Duration(seconds: 180),
      ),
    );

    _running = true;
    _seq = 0;
    _stopSignal = Completer<void>();
    _emitSystem('Streaming started.');
    _worker = _loopChunks();
  }

  Future<void> stop() async {
    if (!_running) return;

    _running = false;
    if (_stopSignal != null && !_stopSignal!.isCompleted) {
      _stopSignal!.complete();
    }
    try {
      await _recorder.stop();
    } catch (_) {}

    if (_worker != null) {
      await _worker;
      _worker = null;
    }

    await _waitForUploads();

    _stopSignal = null;

    _emitSystem('Streaming stopped.');
  }

  Future<void> _loopChunks() async {
    final dir = await getTemporaryDirectory();
    final config = RecordConfig(
      encoder: AudioEncoder.wav,
      sampleRate: 16000,
      numChannels: 1,
    );

    int segmentNumber = 1;
    String currentPath = _buildPath(dir.path);
    await _recorder.start(config, path: currentPath);
    _emitSystem(
        'Segment #$segmentNumber started at ${_formatTime(DateTime.now())}');

    while (_running) {
      final waiters = <Future<void>>[Future.delayed(_chunk)];
      final signal = _stopSignal;
      if (signal != null) {
        waiters.add(signal.future);
      }

      await Future.any(waiters);

      final recordedPath = await _recorder.stop();
      if (!_running) {
        if (recordedPath != null) {
          try {
            File(recordedPath).deleteSync();
          } catch (_) {}
        }
        break;
      }

      if (recordedPath == null) {
        currentPath = _buildPath(dir.path);
        await _recorder.start(config, path: currentPath);
        segmentNumber++;
        _emitSystem(
            'Segment #$segmentNumber started at ${_formatTime(DateTime.now())}');
        continue;
      }

      final completedSegment = segmentNumber;
      _emitSystem('Segment #$completedSegment uploading...');

      currentPath = _buildPath(dir.path);
      await _recorder.start(config, path: currentPath);

      _scheduleUpload(recordedPath, _seq++, completedSegment);

      segmentNumber++;
      _emitSystem(
          'Segment #$segmentNumber started at ${_formatTime(DateTime.now())}');
    }

    try {
      await _recorder.stop();
    } catch (_) {}

    await _waitForUploads();
  }

  void _scheduleUpload(String path, int seq, int segmentNumber) {
    final future = _uploadChunk(path, seq, segmentNumber).then((success) {
      final stamp = _formatTime(DateTime.now());
      if (success) {
        _emitSystem('Segment #$segmentNumber completed at $stamp');
      } else {
        _emitSystem('Segment #$segmentNumber failed (see logs)', isError: true);
      }
    }).catchError((error, stack) {
      _emitSystem('Segment #$segmentNumber upload error: $error',
          isError: true);
    });

    _pendingUploads.add(future);
    future.whenComplete(() {
      _pendingUploads.remove(future);
    });
  }

  Future<void> _waitForUploads() async {
    if (_pendingUploads.isEmpty) return;
    await Future.wait(_pendingUploads.toList());
  }

  Future<bool> _uploadChunk(String path, int seq, int segmentNumber) async {
    bool success = false;
    try {
      final file = File(path);
      if (!await file.exists()) {
        _emitSystem('Segment #$segmentNumber missing audio file.',
            isError: true);
        return false;
      }

      AppLogger.instance
          .log('ASR', 'Uploading segment #$segmentNumber (seq=$seq) to server');

      print("🔧 [ASR DEBUG] Uploading to server: $_serverBase/transcribe");
      print("🔧 [ASR DEBUG] File path: $path");
      print("🔧 [ASR DEBUG] Stream ID: $_streamId, Seq: $seq");

      final form = FormData.fromMap({
        'audio': await MultipartFile.fromFile(path, filename: 'chunk.wav'),
        'format': 'wav',
        'sample_rate': 16000,
        'seq': seq,
        'stream_id': _streamId,
      });

      final response = await _dio.post(
        '/transcribe',
        data: form,
        options: Options(contentType: 'multipart/form-data'),
      );

      if (response.statusCode == 200 && response.data is Map) {
        final data = response.data as Map;
        final segments = (data['segments'] as List?) ?? const [];
        if (segments.isEmpty) {
          _emitSystem('Segment #$segmentNumber contained no speech.');
        }
        for (final item in segments) {
          final speaker = (item['speaker'] ?? 'SPK').toString();
          final text = (item['text'] ?? '').toString();
          if (text.trim().isEmpty) continue;

          // Extract emotion data if available
          final emotion = item['emotion'];
          final emotionConfidence = item['emotion_confidence'];
          final emotions = item['emotions'];

          Map<String, dynamic>? emotionData;
          if (emotion != null ||
              emotionConfidence != null ||
              emotions != null) {
            emotionData = {
              'emotion': emotion,
              'emotion_confidence': emotionConfidence,
              'emotions': emotions,
            };
          }

          _events.add(
              AsrEvent('final', text.trim(), speaker, emotion: emotionData));
        }
        AppLogger.instance.log('ASR',
            'Segment #$segmentNumber upload successful; ${segments.length} segments received');
        success = true;
      } else {
        final msg =
            'Segment #$segmentNumber: unexpected server response (${response.statusCode}).';
        AppLogger.instance.log('ASR', msg, isError: true);
        _emitSystem(msg, isError: true);
      }
    } catch (e) {
      AppLogger.instance.log('ASR', 'Segment #$segmentNumber upload error: $e',
          isError: true);
      _emitSystem('Segment #$segmentNumber upload error: $e', isError: true);
    } finally {
      try {
        File(path).deleteSync();
      } catch (_) {}
    }

    return success;
  }

  Future<bool> _ensurePerms() async {
    final mic = await Permission.microphone.request();
    if (!mic.isGranted) return false;
    final storage = await Permission.storage.request();
    return storage.isGranted ||
        storage.isLimited ||
        storage.isRestricted == false;
  }

  String _buildPath(String dir) =>
      '$dir/chunk_${DateTime.now().millisecondsSinceEpoch}.wav';

  String _formatTime(DateTime dt) {
    final local = dt.toLocal();
    final iso = local.toIso8601String();
    return iso.replaceFirst('T', ' ').split('.').first;
  }

  void _emitSystem(String message, {bool isError = false}) {
    AppLogger.instance.log('ASR', message, isError: isError);
    if (_events.isClosed) return;
    if (isError) {
      _events.add(AsrEvent('error', message, 'SYSTEM', error: message));
    } else {
      _events.add(AsrEvent('final', message, 'SYSTEM'));
    }
  }
}
