// ignore_for_file: library_private_types_in_public_api

import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

class VoiceEnrollmentPage extends StatefulWidget {
  const VoiceEnrollmentPage({super.key});

  @override
  _VoiceEnrollmentPageState createState() => _VoiceEnrollmentPageState();
}

class _VoiceEnrollmentPageState extends State<VoiceEnrollmentPage> {
  // Recording state
  final AudioRecorder _recorder = AudioRecorder();
  bool _isRecording = false;
  bool _uploading = false;
  int _elapsedSecs = 0;
  Timer? _timer;
  String? _recordedPath;
  String _speakerName = 'pruitt';

  // Server
  late final String _baseUrl = () {
    final a = dotenv.env['ASR_SERVER_BASE']?.trim();
    if (a != null && a.isNotEmpty) return a;
    final w = dotenv.env['WHISPER_SERVER_BASE']?.trim();
    if (w != null && w.isNotEmpty) return w;
    final m = dotenv.env['MEMORY_SERVER_BASE']?.trim();
    if (m != null && m.isNotEmpty) return m;
    return 'http://127.0.0.1:8000';
  }();
  late final Dio _dio = Dio(
    BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 240),
      sendTimeout: const Duration(seconds: 180),
    ),
  );

  // Styling (align with TextPage)
  static const Color primaryColor = Color(0xFF0D1B2A);
  static const Color cardColor = Color(0xFF1B263B);
  static const Color accentColor = Color(0xFF33A1F2);
  static const Color textColor = Colors.white;
  static const Color subtitleColor = Colors.white70;
  String _serverStatus = 'Not checked';
  final List<String> _logs = <String>[];

  @override
  void dispose() {
    _timer?.cancel();
    _timer = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: primaryColor,
        appBar: AppBar(
          title: const Text(
            'VoxAugmented • Voice Enrollment',
            style: TextStyle(color: textColor, fontWeight: FontWeight.bold),
          ),
          backgroundColor: primaryColor,
          elevation: 0,
          iconTheme: const IconThemeData(color: textColor),
          actions: [
            Container(
              margin: const EdgeInsets.only(right: 16),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: _serverStatus == 'OK'
                    ? Colors.green.shade600
                    : Colors.red.shade600,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                _serverStatus,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        body: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            children: [
              // Server block
              Card(
                color: cardColor,
                elevation: 3,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Server',
                          style: TextStyle(
                              color: textColor, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 8),
                      SelectableText(_baseUrl,
                          style: const TextStyle(
                              color: subtitleColor, fontSize: 12)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          ElevatedButton.icon(
                            onPressed: _checkServer,
                            icon: const Icon(Icons.health_and_safety),
                            label: const Text('Check Connection'),
                            style: ElevatedButton.styleFrom(
                                backgroundColor: accentColor,
                                foregroundColor: primaryColor),
                          ),
                          const SizedBox(width: 12),
                          OutlinedButton.icon(
                            onPressed: _isRecording || _uploading
                                ? null
                                : () async {
                                    final name = await _promptForSpeakerName(
                                        initial: _speakerName);
                                    if (name != null &&
                                        name.trim().isNotEmpty) {
                                      setState(
                                          () => _speakerName = name.trim());
                                      _log('Speaker set to "$_speakerName"');
                                    }
                                  },
                            icon: const Icon(Icons.edit),
                            label: Text('Speaker: $_speakerName'),
                            style: OutlinedButton.styleFrom(
                                foregroundColor: accentColor,
                                side: const BorderSide(color: accentColor)),
                          ),
                        ],
                      )
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 12),

              // Recording block
              Card(
                color: cardColor,
                elevation: 3,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Create Voice Profile (2 minutes)',
                          style: TextStyle(
                              color: textColor, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 8),
                      Text(
                        _isRecording
                            ? 'Recording as "$_speakerName"... ${_formatTimer(_elapsedSecs)}'
                            : 'Tip: Quiet room, natural speech ~2 minutes. Current: "$_speakerName"',
                        style: TextStyle(
                            color: _isRecording
                                ? Colors.orange.shade300
                                : subtitleColor),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: ElevatedButton.icon(
                              onPressed: _isRecording || _uploading
                                  ? null
                                  : _startEnrollmentRecording,
                              icon: const Icon(Icons.mic),
                              label: const Text('Start Recording'),
                              style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.green,
                                  foregroundColor: Colors.white),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: ElevatedButton.icon(
                              onPressed: _isRecording &&
                                      _elapsedSecs >= 90 &&
                                      !_uploading
                                  ? _finishAndSubmit
                                  : null,
                              icon: const Icon(Icons.stop),
                              label: const Text('Finish & Submit'),
                              style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.blue,
                                  foregroundColor: Colors.white),
                            ),
                          ),
                        ],
                      ),
                      if (_uploading) ...[
                        const SizedBox(height: 12),
                        const Center(
                            child:
                                CircularProgressIndicator(color: accentColor)),
                      ],
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 12),

              // Activity log
              Expanded(
                child: Card(
                  color: cardColor,
                  elevation: 2,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: _logs.isEmpty
                        ? const Center(
                            child: Text('No activity yet',
                                style: TextStyle(color: subtitleColor)))
                        : ListView.builder(
                            itemCount: _logs.length,
                            itemBuilder: (context, i) => Padding(
                              padding: const EdgeInsets.symmetric(vertical: 4),
                              child: Text(_logs[i],
                                  style: const TextStyle(
                                      color: textColor, fontSize: 12)),
                            ),
                          ),
                  ),
                ),
              ),

              // Legacy buttons kept as syntax (hidden)
              const SizedBox(height: 0),
              // GestureDetector(
              //   onTap: () async {
              //     if (BleManager.get().isConnected == false) return;
              //     FeaturesServices().sendBmp("assets/images/image_1.bmp");
              //   },
              //   child: SizedBox.shrink(),
              // ),
              // GestureDetector(
              //   onTap: () async {
              //     if (BleManager.get().isConnected == false) return;
              //     FeaturesServices().sendBmp("assets/images/image_2.bmp");
              //   },
              //   child: SizedBox.shrink(),
              // ),
            ],
          ),
        ),
      );

  // Logic
  Future<void> _startEnrollmentRecording() async {
    try {
      debugPrint('[VoiceEnrollment] Start enrollment recording tapped');
      final name = await _promptForSpeakerName(initial: _speakerName);
      if (name == null) {
        _log('Speaker prompt cancelled');
        return;
      }
      setState(
          () => _speakerName = name.trim().isEmpty ? 'pruitt' : name.trim());

      if (!await _recorder.hasPermission()) {
        _showSnack('Microphone permission denied', isError: true);
        _log('Microphone permission denied');
        return;
      }

      final dir = await getTemporaryDirectory();
      final path =
          '${dir.path}/enroll_${DateTime.now().millisecondsSinceEpoch}.wav';
      await _recorder.start(
        const RecordConfig(
            encoder: AudioEncoder.wav, sampleRate: 16000, numChannels: 1),
        path: path,
      );
      _log('Recorder started path=$path');

      setState(() {
        _isRecording = true;
        _elapsedSecs = 0;
        _recordedPath = null;
      });

      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 1), (t) async {
        if (!mounted) return;
        final next = _elapsedSecs + 1;
        setState(() => _elapsedSecs = next);
        if (next % 5 == 0) _log('Tick ${_formatTimer(next)}');
        if (next >= 120) {
          t.cancel();
          _log('Auto-finish at 2:00');
          await _finishAndSubmit();
        }
      });
    } catch (e) {
      _showSnack('Failed to start: $e', isError: true);
      _log('Start error=$e');
    }
  }

  Future<void> _finishAndSubmit() async {
    if (!_isRecording) return;
    try {
      _log('Finish tapped at ${_formatTimer(_elapsedSecs)}');
      final path = await _recorder.stop();
      _timer?.cancel();
      _timer = null;

      setState(() {
        _isRecording = false;
        _recordedPath = path;
      });
      if (_recordedPath != null) {
        _log('Recording saved at $_recordedPath');
      }

      if (_elapsedSecs < 90) {
        _showSnack('Please record at least 90 seconds before submitting.',
            isError: true);
        _log('Duration too short: ${_elapsedSecs}s');
        return;
      }

      if (path == null || !(await File(path).exists())) {
        _showSnack('No audio file captured', isError: true);
        _log('Missing audio file path=$path');
        return;
      }

      await _uploadEnrollment(path);
    } catch (e) {
      _showSnack('Failed to stop: $e', isError: true);
      _log('Stop error=$e');
    }
  }

  Future<void> _uploadEnrollment(String path) async {
    if (_uploading) return;
    setState(() => _uploading = true);
    try {
      final size = await File(path).length();
      _log(
          'Upload start size=${size}B url=$_baseUrl/enroll/upload speaker=$_speakerName');
      final form = FormData.fromMap({
        'audio': await MultipartFile.fromFile(path, filename: 'enrollment.wav'),
        'speaker': _speakerName,
      });
      final resp = await _dio.post('/enroll/upload',
          data: form, options: Options(contentType: 'multipart/form-data'));
      if (resp.statusCode == 200) {
        _showSnack('Enrollment submitted. Run create_enrollment.py next.');
        _log('Upload success status=${resp.statusCode} data=${resp.data}');
        setState(() {
          _recordedPath = null;
          _elapsedSecs = 0;
        });
      } else {
        _showSnack('Upload failed (${resp.statusCode}).', isError: true);
        _log('Upload fail status=${resp.statusCode} data=${resp.data}');
      }
    } catch (e) {
      _showSnack('Upload error: $e', isError: true);
      _log('Upload error=$e');
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<String?> _promptForSpeakerName({String? initial}) async {
    final controller = TextEditingController(text: initial ?? '');
    return showDialog<String>(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => AlertDialog(
        title: const Text('Who is speaking?'),
        content: TextField(
            controller: controller,
            autofocus: true,
            decoration: const InputDecoration(
                hintText: 'Enter a name (e.g., pruitt, alice)')),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(null),
              child: const Text('Cancel')),
          ElevatedButton(
              onPressed: () => Navigator.of(ctx).pop(controller.text.trim()),
              child: const Text('OK')),
        ],
      ),
    );
  }

  Future<void> _checkServer() async {
    try {
      final resp = await _dio.get('/health',
          options: Options(sendTimeout: const Duration(seconds: 6)));
      setState(() => _serverStatus = resp.statusCode == 200 ? 'OK' : 'Fail');
      _log('Server check: ${resp.statusCode}');
    } catch (e) {
      setState(() => _serverStatus = 'Fail');
      _log('Server check error: $e');
    }
  }

  // Helpers
  String _formatTimer(int secs) {
    final mm = (secs ~/ 60).toString().padLeft(2, '0');
    final ss = (secs % 60).toString().padLeft(2, '0');
    return '$mm:$ss';
  }

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content: Text(msg),
          backgroundColor: isError ? Colors.red.shade700 : Colors.black87),
    );
  }

  void _log(String message) {
    debugPrint('[VoiceEnrollment] $message');
    if (!mounted) return;
    setState(() {
      _logs.add(
          '[${DateTime.now().toLocal().toIso8601String().replaceFirst('T', ' ').split('.').first}] $message');
      if (_logs.length > 400) _logs.removeAt(0);
    });
  }
}
