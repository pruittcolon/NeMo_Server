import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:path_provider/path_provider.dart';
import 'package:demo_ai_even/services/auth_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Service to handle transcription using the local WhisperServer (main3.py)
class WhisperServerService {
  final String _serverBaseUrl =
      dotenv.env['WHISPER_SERVER_BASE']?.trim() ?? 'http://127.0.0.1:8000';
  final Dio _dio = Dio();
  final int _chunkSecs =
      int.tryParse(dotenv.env['WHISPER_CHUNK_SECS'] ?? '') ?? 30;

  StreamController<List<int>>? _audioStreamController;
  Completer<String>? _transcriptCompleter;
  Timer? _chunkTimer;
  List<Uint8List> _audioBuffer = [];

  /// Starts a new streaming transcription session with WhisperServer
  Future<String> startStreaming() {
    print("WhisperServerService: Starting stream...");

    if (_serverBaseUrl.isEmpty) {
      print(
          "WhisperServerService: ERROR - WHISPER_SERVER_BASE not set in .env file.");
      return Future.value('');
    }

    _transcriptCompleter = Completer<String>();
    _audioStreamController = StreamController<List<int>>();
    _audioBuffer.clear();

    // Start chunking audio at configured interval
    _chunkTimer = Timer.periodic(Duration(seconds: _chunkSecs), (timer) {
      _processAudioChunk();
    });

    return _transcriptCompleter!.future;
  }

  /// Sends a chunk of PCM audio data to the WhisperServer
  void sendAudio(Uint8List pcmData) {
    if (_audioStreamController != null && !_audioStreamController!.isClosed) {
      _audioBuffer.add(pcmData);
    }
  }

  /// Processes accumulated audio chunks and sends to WhisperServer
  Future<void> _processAudioChunk() async {
    if (_audioBuffer.isEmpty) return;

    try {
      // Combine audio chunks
      final totalLength =
          _audioBuffer.fold<int>(0, (sum, chunk) => sum + chunk.length);
      final combinedAudio = Uint8List(totalLength);
      int offset = 0;

      for (final chunk in _audioBuffer) {
        combinedAudio.setRange(offset, offset + chunk.length, chunk);
        offset += chunk.length;
      }

      // Clear buffer
      _audioBuffer.clear();

      // Create temporary file
      final tempDir = await getTemporaryDirectory();
      final tempFile = File(
          '${tempDir.path}/audio_chunk_${DateTime.now().millisecondsSinceEpoch}.wav');

      // Convert PCM to WAV format
      await _convertPCMToWAV(combinedAudio, tempFile);

      // Send to WhisperServer
      await _sendToWhisperServer(tempFile);

      // Clean up temp file
      if (await tempFile.exists()) {
        await tempFile.delete();
      }
    } catch (e) {
      print("WhisperServerService: Error processing audio chunk: $e");
    }
  }

  /// Converts PCM audio data to WAV format
  Future<void> _convertPCMToWAV(Uint8List pcmData, File outputFile) async {
    // Simple WAV header for 16kHz, 16-bit, mono
    final sampleRate = 16000;
    final channels = 1;
    final bitsPerSample = 16;
    final byteRate = sampleRate * channels * bitsPerSample ~/ 8;
    final blockAlign = channels * bitsPerSample ~/ 8;
    final dataSize = pcmData.length;
    final fileSize = 36 + dataSize;

    final header = ByteData(44);
    header.setUint8(0, 0x52); // 'R'
    header.setUint8(1, 0x49); // 'I'
    header.setUint8(2, 0x46); // 'F'
    header.setUint8(3, 0x46); // 'F'
    header.setUint32(4, fileSize, Endian.little);
    header.setUint8(8, 0x57); // 'W'
    header.setUint8(9, 0x41); // 'A'
    header.setUint8(10, 0x56); // 'V'
    header.setUint8(11, 0x45); // 'E'
    header.setUint8(12, 0x66); // 'f'
    header.setUint8(13, 0x6D); // 'm'
    header.setUint8(14, 0x74); // 't'
    header.setUint8(15, 0x20); // ' '
    header.setUint32(16, 16, Endian.little);
    header.setUint16(20, 1, Endian.little);
    header.setUint16(22, channels, Endian.little);
    header.setUint32(24, sampleRate, Endian.little);
    header.setUint32(28, byteRate, Endian.little);
    header.setUint16(32, blockAlign, Endian.little);
    header.setUint16(34, bitsPerSample, Endian.little);
    header.setUint8(36, 0x64); // 'd'
    header.setUint8(37, 0x61); // 'a'
    header.setUint8(38, 0x74); // 't'
    header.setUint8(39, 0x61); // 'a'
    header.setUint32(40, dataSize, Endian.little);

    final wavData = Uint8List(44 + pcmData.length);
    wavData.setRange(0, 44, header.buffer.asUint8List());
    wavData.setRange(44, 44 + pcmData.length, pcmData);

    await outputFile.writeAsBytes(wavData);
  }

  /// Sends audio file to WhisperServer for transcription
  Future<void> _sendToWhisperServer(File audioFile) async {
    try {
      // Get authentication token from storage
      String? sessionToken;
      try {
        final prefs = await SharedPreferences.getInstance();
        sessionToken = prefs.getString('session_token');
      } catch (e) {
        print("WhisperServerService: Could not load session token: $e");
      }

      final formData = FormData.fromMap({
        'audio':
            await MultipartFile.fromFile(audioFile.path, filename: 'audio.wav'),
        'job_id': DateTime.now().millisecondsSinceEpoch.toString(),
      });

      // Build headers with optional authentication
      final headers = <String, dynamic>{};
      if (sessionToken != null && sessionToken.isNotEmpty) {
        headers['Cookie'] = 'ws_session=$sessionToken';
        print("WhisperServerService: Using authenticated session");
      } else {
        print("WhisperServerService: No session token found, making unauthenticated request");
      }

      final response = await _dio.post(
        '$_serverBaseUrl/transcribe',
        data: formData,
        options: Options(
          contentType: 'multipart/form-data',
          sendTimeout: const Duration(seconds: 120),
          receiveTimeout: const Duration(seconds: 240),
          headers: headers.isNotEmpty ? headers : null,
        ),
      );

      if (response.statusCode == 200 && response.data != null) {
        final transcript = _extractTranscript(response.data);
        if (transcript.isNotEmpty && !_transcriptCompleter!.isCompleted) {
          print("WhisperServerService: Received transcript: '$transcript'");
          _transcriptCompleter!.complete(transcript);
        }
      }
    } catch (e) {
      print("WhisperServerService: Error sending to WhisperServer: $e");
      if (!_transcriptCompleter!.isCompleted) {
        _transcriptCompleter!.completeError(e);
      }
    }
  }

  /// Extracts transcript text from WhisperServer response
  String _extractTranscript(dynamic responseData) {
    try {
      if (responseData is Map<String, dynamic>) {
        // Handle structured response
        if (responseData.containsKey('transcript')) {
          return responseData['transcript'].toString();
        }
        if (responseData.containsKey('text')) {
          return responseData['text'].toString();
        }
        if (responseData.containsKey('segments')) {
          final segments = responseData['segments'] as List?;
          if (segments != null && segments.isNotEmpty) {
            // Include speaker labels when available so the UI shows who spoke
            final buf = StringBuffer();
            for (final raw in segments) {
              if (raw is Map) {
                final speaker =
                    (raw['speaker'] ?? raw['speaker_raw'] ?? 'SPK').toString();
                final text = (raw['text'] ?? '').toString().trim();
                if (text.isEmpty) continue;
                if (buf.isNotEmpty) buf.write('\n');
                buf.write('$speaker: $text');
              }
            }
            return buf.toString().trim();
          }
        }
      }

      // Handle plain text response
      if (responseData is String) {
        return responseData.trim();
      }

      return '';
    } catch (e) {
      print("WhisperServerService: Error extracting transcript: $e");
      return '';
    }
  }

  /// Stops the audio stream and signals to WhisperServer to finalize the transcript
  Future<void> stopStreaming() async {
    print("WhisperServerService: Stopping stream...");

    _chunkTimer?.cancel();
    _chunkTimer = null;

    // Process any remaining audio
    if (_audioBuffer.isNotEmpty) {
      await _processAudioChunk();
    }

    await _audioStreamController?.close();
    _audioStreamController = null;

    // If no transcript received yet, complete with empty string
    if (!_transcriptCompleter!.isCompleted) {
      _transcriptCompleter!.complete('');
    }
  }

  /// Checks if WhisperServer is available
  Future<bool> isServerAvailable() async {
    try {
      // Get authentication token from storage
      String? sessionToken;
      try {
        final prefs = await SharedPreferences.getInstance();
        sessionToken = prefs.getString('session_token');
      } catch (e) {
        print("WhisperServerService: Could not load session token for health check: $e");
      }

      // Build headers with optional authentication
      final headers = <String, dynamic>{};
      if (sessionToken != null && sessionToken.isNotEmpty) {
        headers['Cookie'] = 'ws_session=$sessionToken';
      }

      final response = await _dio.get('$_serverBaseUrl/health',
          options: Options(
            sendTimeout: const Duration(seconds: 5),
            headers: headers.isNotEmpty ? headers : null,
          ));
      return response.statusCode == 200;
    } catch (e) {
      print("WhisperServerService: Server not available: $e");
      return false;
    }
  }
}
