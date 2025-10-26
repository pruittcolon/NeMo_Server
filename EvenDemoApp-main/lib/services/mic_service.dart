import 'package:record/record.dart';

class MicService {
  final AudioRecorder _recorder = AudioRecorder();

  /// Record for a fixed number of seconds
  Future<String?> recordForSeconds(int seconds) async {
    if (await _recorder.hasPermission()) {
      final path =
          '/sdcard/Download/recording_${DateTime.now().millisecondsSinceEpoch}.m4a';

      await _recorder.start(
        const RecordConfig(
          encoder: AudioEncoder.aacLc,
          bitRate: 128000,
          sampleRate: 16000,
        ),
        path: path,
      );

      await Future.delayed(Duration(seconds: seconds));
      return await _recorder.stop();
    }
    return null;
  }

  /// Start continuous recording
  Future<void> startRecording(String path) async {
    if (await _recorder.hasPermission()) {
      await _recorder.start(
        const RecordConfig(
          encoder: AudioEncoder.aacLc,
          bitRate: 128000,
          sampleRate: 16000,
        ),
        path: path,
      );
    }
  }

  /// Stop recording and return file path
  Future<String?> stopRecording() async {
    return await _recorder.stop();
  }

  /// Check if recording is active
  Future<bool> isRecording() async {
    return await _recorder.isRecording();
  }
}
