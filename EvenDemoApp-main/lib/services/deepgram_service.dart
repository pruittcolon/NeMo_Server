import 'dart:async';
import 'dart:typed_data';
import 'package:deepgram_speech_to_text/deepgram_speech_to_text.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class DeepgramService {
  final String _apiKey = dotenv.env['DEEPGRAM_API_KEY'] ?? '';

  Deepgram? _deepgram;
  StreamSubscription<DeepgramListenResult>? _responseSubscription;
  StreamController<List<int>>? _audioStreamController;
  Completer<String>? _transcriptCompleter;
  int _chunksSent = 0;

  /// Starts a new streaming transcription session with Deepgram.
  ///
  /// Returns a Future that completes with the final transcript once the stream is closed.
  Future<String> startStreaming() {
    print("DeepgramService: Starting stream...");
    if (_apiKey.isEmpty) {
      print("DeepgramService: ERROR - DEEPGRAM_API_KEY is not set in .env file.");
      return Future.value('');
    }
    print("DeepgramService: API key found, initializing stream");

    _transcriptCompleter = Completer<String>();
    _audioStreamController = StreamController<List<int>>();
    _deepgram = Deepgram(_apiKey);

    print("DeepgramService: Initializing live transcription stream");
    String lastInterim = '';
    
    try {
      // Corrected: Use the `listen` instance method and provide the correct type.
      _responseSubscription = _deepgram!.listen.live(
        _audioStreamController!.stream,
        queryParams: {
          'encoding': 'linear16',
          'sampleRate': 16000,
          'interim_results': true,
          'smart_format': true,
        },
      ).listen(
        (response) {
          final transcript = response.transcript ?? '';
          // Corrected: Check the 'is_final' key in the response map to determine if it is a final result.
          final isFinal = response.map['is_final'] == true;

          if (transcript.isNotEmpty) {
            if (isFinal) {
              print("DeepgramService: Received FINAL transcript: '$transcript'");
              if (!_transcriptCompleter!.isCompleted) {
                _transcriptCompleter!.complete(transcript);
              }
            } else {
              print("DeepgramService: Interim result: '$transcript'");
              lastInterim = transcript;
            }
          }
        },
        onDone: () {
          print("DeepgramService: Stream 'onDone' called");
          if (!_transcriptCompleter!.isCompleted) {
            // Use the last interim transcript if no final was received
            _transcriptCompleter!.complete(lastInterim);
          }
        },
        onError: (error) {
          print("DeepgramService: Stream error: $error");
          if (!_transcriptCompleter!.isCompleted) {
            _transcriptCompleter!.completeError(error);
          }
        },
      );
      
      print("DeepgramService: Stream listener attached successfully");
    } catch (e) {
      print("DeepgramService: Failed to initialize stream: $e");
      if (!_transcriptCompleter!.isCompleted) {
        _transcriptCompleter!.completeError(e);
      }
    }

    return _transcriptCompleter!.future;
  }

  /// Sends a chunk of PCM audio data to the Deepgram stream.
  void sendAudio(Uint8List pcmData) {
    if (_audioStreamController != null && !_audioStreamController!.isClosed) {
      _audioStreamController!.add(pcmData);
      // Throttled debug: log every 10th chunk to confirm audio flow
      _chunksSent++;
      if (_chunksSent % 10 == 0) {
        print("DeepgramService: Audio chunk #$_chunksSent, ${pcmData.length} bytes");
      }
    } else {
      print("DeepgramService: Cannot send audio - stream controller is null or closed");
    }
  }

  /// Stops the audio stream and signals to Deepgram to finalize the transcript.
  Future<void> stopStreaming() async {
    print("DeepgramService: Stopping stream...");
    try {
      await _audioStreamController?.close();
      await _responseSubscription?.cancel();
      _audioStreamController = null;
      _responseSubscription = null;
      _deepgram = null;
      _chunksSent = 0;
      print("DeepgramService: Stream stopped successfully");
    } catch (e) {
      print("DeepgramService: Error stopping stream: $e");
    }
  }
}
