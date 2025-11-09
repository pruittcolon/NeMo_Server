// Imports from all files, combined and de-duplicated
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:deepgram_speech_to_text/deepgram_speech_to_text.dart';
import 'package:demo_ai_even/ble_manager.dart';
import 'package:demo_ai_even/controllers/evenai_model_controller.dart';
import 'package:demo_ai_even/services/features_services.dart';
import 'package:demo_ai_even/services/proto.dart';
import 'package:demo_ai_even/services/text_service.dart';
import 'package:demo_ai_even/services/deepgram_service.dart';
import 'package:demo_ai_even/services/whisperserver_service.dart';
import 'package:dio/dio.dart';
import 'package:demo_ai_even/utils/app_logger.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:get/get.dart';
import 'package:image/image.dart' as img;
import 'package:permission_handler/permission_handler.dart';
import 'roku.dart';

// --- MEMORY SERVER (wake-word) CONFIG ---
// Unique wake word to trigger memory queries. Should be uncommon and easy to pronounce.
const String _kWakeWord = "memory";

// Base URL of the memory server (FastAPI). Adjust via .env -> MEMORY_SERVER_BASE
String get _memoryServerBaseUrl {
  final fromEnv = dotenv.env['MEMORY_SERVER_BASE']?.trim();
  print("🔧 [DEBUG] Loading MEMORY_SERVER_BASE from .env: '$fromEnv'");
  if (fromEnv != null && fromEnv.isNotEmpty) {
    print("✅ [DEBUG] Using server URL: $fromEnv");
    return fromEnv;
  }
  print(
      "❌ [ERROR] MEMORY_SERVER_BASE not set in .env. Memory feature will fail.");
  print("🔧 [DEBUG] Available env vars: ${dotenv.env.keys.toList()}");
  return ""; // fallback
}

/// A lightweight client to communicate with the memory server.
/// It provides methods to submit a question and poll for a result.
class _MemoryServerClient {
  late final Dio _dio;

  _MemoryServerClient({String? baseUrl}) {
    final finalBaseUrl = baseUrl ?? _memoryServerBaseUrl;
    print(
        "🔧 [DEBUG] Creating MemoryServerClient with baseUrl: '$finalBaseUrl'");

    if (finalBaseUrl.isEmpty) {
      print(
          "❌ [ERROR] Empty baseUrl! This will cause 'no host specified' errors.");
    }

    _dio = Dio(
      BaseOptions(
        baseUrl: finalBaseUrl,
        // Timeouts must be Durations (Dio v5+)
        connectTimeout: const Duration(milliseconds: 30000),
        receiveTimeout: const Duration(milliseconds: 100000),
      ),
    );

    // Add request/response logging
    _dio.interceptors.add(LogInterceptor(
      requestBody: true,
      responseBody: true,
      logPrint: (object) => print("🌐 [HTTP] $object"),
    ));
  }

  // For troubleshooting connectivity issues, expose the base URL in logs.
  void debugPrintConfig() {
    try {
      // ignore: avoid_print
      print("MemoryServerClient baseUrl=" + (_dio.options.baseUrl));
    } catch (_) {}
  }

  /// Submit a question to the memory server. Returns a map containing
  /// the `jobId` and any search hits. Using a map avoids the need
  /// for record types which might not be supported on all Dart versions.
  Future<Map<String, dynamic>> submitQuestion(String question,
      {String? sessionId}) async {
    final data = {"question": question};
    if (sessionId != null && sessionId.isNotEmpty) {
      data["session_id"] = sessionId;
    }

    final resp = await _dio.post("/query", data: data);
    if (resp.statusCode != 200 || resp.data == null) {
      throw Exception("Bad /query response: ${resp.statusCode}");
    }
    final responseData = resp.data as Map;
    final jobId = (responseData["job_id"] ?? "").toString();
    final hits = (responseData["hits"] ?? []) as List;
    if (jobId.isEmpty) throw Exception("No job_id from /query");
    return {'jobId': jobId, 'hits': hits};
  }

  /// Poll the memory server until the job completes or times out.
  Future<String?> waitForAnswer(String jobId,
      {Duration total = const Duration(seconds: 30),
      Duration every = const Duration(milliseconds: 500)}) async {
    final sw = Stopwatch()..start();
    while (sw.elapsed < total) {
      final resp = await _dio.get("/result/$jobId");
      if (resp.statusCode == 200 && resp.data is Map) {
        final m = resp.data as Map;
        final status = (m["status"] ?? "").toString().toLowerCase();
        if (status == "complete") {
          final ans = m["answer"]?.toString();
          return (ans != null && ans.isNotEmpty) ? ans : "No answer.";
        } else if (status == "failed") {
          final err = m["answer"]?.toString();
          return (err != null && err.isNotEmpty)
              ? "Error: $err"
              : "Error: job failed.";
        }
      }
      await Future.delayed(every);
    }
    return null; // timed out
  }
}

class EvenAI {
  static EvenAI? _instance;
  static EvenAI get get => _instance ??= EvenAI._();

  // --- Class Variables ---
  final DeepgramService _deepgramService = DeepgramService();
  final WhisperServerService _whisperService = WhisperServerService();
  final RokuRemote _rokuRemote = RokuRemote();
  Future<String>? _transcriptFuture;

  bool _isAwaitingFollowUp = false;
  bool _isMenuMode = false;
  bool _isAwaitingRokuCommand = false;
  bool _isAwaitingAlexaCommand = false; // --- NEW --- Flag for Alexa mode

  // --- CHATGPT CONVERSATION MODE STATE ---
  bool _isChatGPTConversationMode = false;
  List<Map<String, String>> _chatGPTHistory = [];
  Timer? _chatGPTModeTimer;

  // --- VISION MODE STATE ---
  bool _isVisionModeActive = false;
  CameraController? _cameraController;
  Timer? _visionModeTimer;
  Timer? _cameraCaptureTimer;
  String? _latestImageBase64;

  // --- MEMORY MODE STATE ---
  /// Client used to communicate with the memory server.
  final _MemoryServerClient _memoryClient = _MemoryServerClient();

  /// When true, the next recognized transcript is treated as a memory question.
  bool _isAwaitingMemoryQuestion = false;

  /// When true, memory mode is active and we can ask successive questions until terminated.
  bool _isMemoryModeActive = false;

  /// Unique session ID for this memory conversation
  String _memorySessionId = "";

  static bool _isRunning = false;
  static bool get isRunning => _isRunning;

  bool isReceivingAudio = false;

  File? lc3File;
  File? pcmFile;
  int durationS = 0;
  static int maxRetry = 10;
  static int _currentLine = 0;
  static Timer? _timer;
  static List<String> list = [];
  static List<String> sendReplys = [];

  Timer? _recordingTimer;
  final int maxRecordingDuration = 60;
  // Auto-exit timers for persistent modes
  Timer? _rokuModeTimer;
  Timer? _alexaModeTimer;

  static bool _isManual = false;

  static set isRunning(bool value) {
    _isRunning = value;
    isEvenAIOpen.value = value;
    isEvenAISyncing.value = value;
  }

  static RxBool isEvenAIOpen = false.obs;
  static RxBool isEvenAISyncing = false.obs;

  int _lastStartTime = 0;
  int _lastStopTime = 0;
  final int startTimeGap = 500;
  final int stopTimeGap = 500;

  static final StreamController<String> _textStreamController =
      StreamController<String>.broadcast();
  static Stream<String> get textStream => _textStreamController.stream;

  static void updateDynamicText(String newText) {
    _textStreamController.add(newText);
  }

  EvenAI._();

  // --- Core Methods ---

  void onVoiceChunkReceived(Uint8List pcmData) {
    if (isReceivingAudio) {
      // Use WhisperServer for memory mode, Deepgram for regular EvenAI
      if (_isMemoryModeActive || _isAwaitingMemoryQuestion) {
        _whisperService.sendAudio(pcmData);
      } else {
        _deepgramService.sendAudio(pcmData);
      }
    }
  }

  void toStartEvenAIByOS() async {
    print("EvenAI: Received start command from OS.");
    BleManager.get().startSendBeatHeart();

    int currentTime = DateTime.now().millisecondsSinceEpoch;
    if (currentTime - _lastStartTime < startTimeGap) {
      print("EvenAI: Start command received too quickly. Ignoring.");
      return;
    }
    _lastStartTime = currentTime;

    clear();
    isReceivingAudio = true;
    isRunning = true;
    _currentLine = 0;

    _transcriptFuture = _deepgramService.startStreaming();

    _transcriptFuture?.then((transcript) {
      if (transcript.trim().isNotEmpty && isReceivingAudio) {
        print("EvenAI: Proactively processing received transcript.");
        recordOverByOS();
      }
    });

    // Do not send dynamic "Listening" text here to avoid latency.

    await BleManager.invokeMethod("startEvenAI");
    await openEvenAIMic();
    startRecordingTimer();
  }

  void startRecordingTimer() {
    _recordingTimer?.cancel();
    _recordingTimer = Timer(Duration(seconds: maxRecordingDuration), () {
      if (isReceivingAudio) {
        print("EvenAI: Recording timer expired. Forcing end of recording.");
        recordOverByOS();
      }
    });
  }

  Future<void> _robustExitBmp() async {
    if (BleManager.get().isConnected) {
      print("EvenAI: Clearing screen on glasses (attempt 1).");
      await FeaturesServices().exitBmp();
      await Future.delayed(const Duration(milliseconds: 100));
      print("EvenAI: Clearing screen on glasses (attempt 2).");
      await FeaturesServices().exitBmp();
    }
  }

  // Display Roku commands as text
  Future<void> _displayRokuRemoteCard() async {
    if (!BleManager.get().isConnected) {
      print("EvenAI: Cannot display Roku commands; glasses not connected.");
      return;
    }
    try {
      print("EvenAI: Displaying Roku commands on glasses.");
      const rokuCommands = """Roku Remote:
Power On/Off
Up, Down, Left, Right
Select, Home, Back
Volume Up/Down
Say 'Terminate' to exit""";
      await TextService.get.startSendText(rokuCommands);
    } catch (e) {
      print("EvenAI: Failed to display Roku commands: $e");
    }
  }

  void _listenForFollowUpCommand() {
    print("EvenAI: Starting to listen for a follow-up command.");
    isReceivingAudio = true;
    isRunning = true;
    _transcriptFuture = _deepgramService.startStreaming();

    _transcriptFuture?.then((transcript) {
      if (transcript.trim().isNotEmpty && isReceivingAudio) {
        print("EvenAI: Proactively processing follow-up transcript.");
        recordOverByOS();
      }
    });

    BleManager.invokeMethod("startEvenAI");
    openEvenAIMic();
    startRecordingTimer();
  }

  /// Special memory listening method that uses WhisperServer instead of Deepgram
  void _listenForMemoryQuestion() {
    print(
        "EvenAI: Starting to listen for a memory question using WhisperServer.");
    isReceivingAudio = true;
    isRunning = true;
    _transcriptFuture = _whisperService.startStreaming();

    _transcriptFuture?.then((transcript) {
      if (transcript.trim().isNotEmpty && isReceivingAudio) {
        print(
            "EvenAI: Proactively processing memory transcript from WhisperServer.");
        recordOverByOS();
      }
    });

    BleManager.invokeMethod("startEvenAI");
    openEvenAIMic();
    startRecordingTimer();
  }

  // === MEMORY HELPER METHODS ===

  /// Strip the wake word from the given text and return the remainder.
  ///
  /// If the wake word is not found, an empty string is returned.
  String _stripWakeWordAndRemainder(String text) {
    final t = text.trim();
    final idx = t.indexOf(_kWakeWord);
    if (idx == -1) return "";
    final after = t.substring(idx + _kWakeWord.length).trimLeft();
    // Remove leading punctuation and whitespace.
    return after.replaceFirst(RegExp(r'^[,.:;\\-\\s]+'), '').trim();
  }

  /// Handle a memory question by submitting it to the memory server and
  /// displaying the answer on the glasses. This method handles all UI
  /// updates and cleans up state when complete.
  Future<void> _handleMemoryQuery(String question) async {
    try {
      // Log the memory server base URL for troubleshooting
      _memoryClient.debugPrintConfig();
      final displayQ = question.isEmpty ? "(no question captured)" : question;
      // Show that a search is in progress on the glasses.
      updateDynamicText("Memory: searching...\n$displayQ");
      await TextService.get.startSendText("Memory search:\n$displayQ");

      // Submit the question with session ID and poll for the answer.
      final submission = await _memoryClient.submitQuestion(displayQ,
          sessionId: _memorySessionId);
      final jobId = submission['jobId'] as String;
      final answer = await _memoryClient.waitForAnswer(jobId);

      final out = (answer == null || answer.trim().isEmpty)
          ? "No answer yet. Try again later."
          : answer.trim();

      // Display the answer.
      updateDynamicText(out);
      await TextService.get.startSendText(out);
    } catch (e) {
      String reason = e.toString();
      if (e is DioException) {
        final se = e.error;
        if (se is SocketException) {
          reason =
              "Socket error: ${se.osError?.errorCode ?? ''} ${se.osError?.message ?? se.message}";
        } else if (e.type == DioExceptionType.connectionError) {
          reason = "Connection error (server unreachable)";
        }
      }
      final msg = "Memory server error. ($reason)";
      updateDynamicText(msg);
      await TextService.get.startSendText(msg);
    } finally {
      // Brief pause to allow the user to read the response.
      await Future.delayed(const Duration(seconds: 3));
      // If memory mode is active, prompt the user for another question instead of exiting.
      if (_isMemoryModeActive) {
        // Prompt user for the next memory question with better instructions.
        updateDynamicText(
            "Memory Mode Active:\nAsk another question or say 'End Memory' to exit.\n\nContext: Remembering conversation history.");
        await TextService.get.startSendText(
            "Memory Mode Active:\nAsk another question or say 'End Memory' to exit.\n\nContext: Remembering conversation history.");
        _isAwaitingMemoryQuestion = true;
        // Start listening for the next question in memory mode using WhisperServer.
        _listenForMemoryQuestion();
      } else {
        // Not in memory mode, clean up and exit.
        await _robustExitBmp();
        clear();
        isRunning = false;
      }
    }
  }

  // --- NEW ---
  /// Triggers an Alexa routine via a Voicemonkey GET request.
  Future<void> _triggerAlexaRoutine(String deviceName) async {
    final String? voicemonkeyUrl = dotenv.env['VOICEMONKEY_TRIGGER_URL'];

    if (voicemonkeyUrl == null || voicemonkeyUrl.isEmpty) {
      print("EvenAI: VOICEMONKEY_TRIGGER_URL not set in .env file.");
      await TextService.get.startSendText("Voicemonkey URL not configured.");
      return;
    }

    final String encodedDevice = Uri.encodeComponent(deviceName);
    final String fullUrl = "$voicemonkeyUrl&device=$encodedDevice";

    try {
      final dio = Dio();
      final response = await dio.get(fullUrl);
      if (response.statusCode == 200) {
        print(
            "EvenAI: Successfully triggered Alexa routine for '$deviceName'.");
        await TextService.get.startSendText("Sent: $deviceName");
      } else {
        print(
            "EvenAI: Failed to trigger Alexa routine for '$deviceName'. Status: ${response.statusCode}, Body: ${response.data}");
        await TextService.get.startSendText("Error: $deviceName");
      }
    } catch (e) {
      print("EvenAI: Error triggering Alexa routine: $e");
      await TextService.get.startSendText("Error: $deviceName");
    }

    // Wait for 2 seconds to show the confirmation, then clear the screen.
    await Future.delayed(const Duration(seconds: 2));
    await _robustExitBmp();
  }

  // Regex helpers for triggers
  bool _matchesTerminate(String text) {
    final t = text.toLowerCase();
    final re = RegExp(r"\bterminat(?:e|es|ed|ing|ion)?\b");
    return re.hasMatch(t) || t.contains('end memory') || t.contains('end');
  }

  bool _matchesRoku(String text) =>
      RegExp(r"\broku\b", caseSensitive: false).hasMatch(text);
  bool _matchesAlexa(String text) =>
      RegExp(r"\balexa\b", caseSensitive: false).hasMatch(text);
  bool _matchesMenu(String text) =>
      RegExp(r"\bmenu\b", caseSensitive: false).hasMatch(text);
  bool _matchesChatMode(String text) =>
      RegExp(r"\bchat\b", caseSensitive: false).hasMatch(text);
  bool _matchesInterviewMode(String text) =>
      RegExp(r"\binterview\b", caseSensitive: false).hasMatch(text);
  bool _matchesVisionMode(String text) =>
      RegExp(r"\bvision\b", caseSensitive: false).hasMatch(text);

  Future<void> recordOverByOS() async {
    // --- MEMORY MODE ---
    // Handle memory mode queries if active. The user can ask successive questions until they say 'terminate'.
    if (_isMemoryModeActive && _isAwaitingMemoryQuestion) {
      isReceivingAudio = false;
      await _whisperService.stopStreaming();
      final transcript = await _transcriptFuture;
      String cleanTranscript = transcript?.toLowerCase().trim() ?? "";
      // Allow user to exit memory mode by saying terminate, end, or end memory.
      if (_matchesTerminate(cleanTranscript)) {
        _isAwaitingMemoryQuestion = false;
        _isMemoryModeActive = false;
        _memorySessionId = ""; // Clear session
        await _robustExitBmp();
        clear();
        isRunning = false;
        return;
      }
      if (cleanTranscript.isNotEmpty) {
        _isAwaitingMemoryQuestion = false;
        await _handleMemoryQuery(cleanTranscript);
        // _handleMemoryQuery will prompt for next question if memory mode remains active.
        return;
      } else {
        // No speech detected while in memory mode. Restart listening.
        print("EvenAI: No speech detected in Memory mode. Listening again.");
        _listenForMemoryQuestion();
        return;
      }
    }

    // --- PERSISTENT ROKU REMOTE MODE ---
    if (_isAwaitingRokuCommand) {
      isReceivingAudio = false;
      await _deepgramService.stopStreaming();

      final transcript = await _transcriptFuture;
      String cleanTranscript = transcript?.toLowerCase().trim() ?? "";

      if (_matchesTerminate(cleanTranscript)) {
        print("EvenAI: User terminated Roku mode.");
        await _robustExitBmp();
        clear();
        isRunning = false;
        return;
      }

      if (cleanTranscript.isNotEmpty) {
        if (cleanTranscript.contains("volume up") ||
            (cleanTranscript.contains("volume") &&
                cleanTranscript.contains("up"))) {
          await _rokuRemote.volumeUp();
          await _rokuRemote.volumeUp();
          await _rokuRemote.volumeUp();
        } else if (cleanTranscript.contains("volume down") ||
            (cleanTranscript.contains("volume") &&
                cleanTranscript.contains("down"))) {
          await _rokuRemote.volumeDown();
          await _rokuRemote.volumeDown();
          await _rokuRemote.volumeDown();
        } else if (cleanTranscript.contains("on"))
          await _rokuRemote.powerOn();
        else if (cleanTranscript.contains("off"))
          await _rokuRemote.powerOff();
        else if (cleanTranscript.contains("up"))
          await _rokuRemote.up();
        else if (cleanTranscript.contains("down"))
          await _rokuRemote.down();
        else if (cleanTranscript.contains("left"))
          await _rokuRemote.left();
        else if (cleanTranscript.contains("right"))
          await _rokuRemote.right();
        else if (cleanTranscript.contains("select") ||
            cleanTranscript.contains("okay")) await _rokuRemote.select();

        print("EvenAI: Roku command sent. Listening for next command.");
        _listenForFollowUpCommand();
        return;
      } else {
        print("EvenAI: No speech detected in Roku mode. Listening again.");
        _listenForFollowUpCommand();
        return;
      }
    }

    // --- NEW: PERSISTENT ALEXA REMOTE MODE ---
    if (_isAwaitingAlexaCommand) {
      isReceivingAudio = false;
      await _deepgramService.stopStreaming();

      final transcript = await _transcriptFuture;
      String cleanTranscript = transcript?.toLowerCase().trim() ?? "";

      if (_matchesTerminate(cleanTranscript)) {
        print("EvenAI: User terminated Alexa mode.");
        await _robustExitBmp();
        clear();
        isRunning = false;
        return;
      }

      if (cleanTranscript.isNotEmpty) {
        if (cleanTranscript.contains("all lights"))
          await _triggerAlexaRoutine("alllights");
        else if (cleanTranscript.contains("bedroom light"))
          await _triggerAlexaRoutine("bedroomlight");
        else if (cleanTranscript.contains("tv off"))
          await _triggerAlexaRoutine("tvoff");
        else if (cleanTranscript.contains("kitchen lights") ||
            cleanTranscript.contains("kitchen light") ||
            cleanTranscript.contains("kitchenlights"))
          await _triggerAlexaRoutine("kitchenlights");

        print("EvenAI: Alexa command sent. Listening for next command.");
        _listenForFollowUpCommand();
        return;
      } else {
        print("EvenAI: No speech detected in Alexa mode. Listening again.");
        _listenForFollowUpCommand();
        return;
      }
    }

    // --- END OF PERSISTENT MODES ---

    if (!isReceivingAudio && !_isRunning) {
      print(
          "EvenAI: recordOverByOS called but not in a receiving state. Ignoring.");
      return;
    }

    print('EvenAI: Received stop command from OS.');
    int currentTime = DateTime.now().millisecondsSinceEpoch;
    if (currentTime - _lastStopTime < stopTimeGap) {
      print("EvenAI: Stop command received too quickly. Ignoring.");
      return;
    }
    _lastStopTime = currentTime;
    isReceivingAudio = false;
    _recordingTimer?.cancel();
    _recordingTimer = null;
    updateDynamicText("Processing...");
    // Use appropriate service based on mode
    if (_isMemoryModeActive || _isAwaitingMemoryQuestion) {
      await _whisperService.stopStreaming();
    } else {
      await _deepgramService.stopStreaming();
    }
    await BleManager.invokeMethod("stopEvenAI");

    try {
      final transcript = await _transcriptFuture;
      print("EvenAI: Final transcript from Deepgram: '$transcript'");

      if (transcript == null || transcript.trim().isEmpty) {
        updateDynamicText("No Speech Recognized");
        isEvenAISyncing.value = false;
        await TextService.get.startSendText("No Speech Recognized");
        isRunning = false;
        return;
      }

      String cleanTranscript = transcript.toLowerCase().trim();

      // --- MEMORY WAKE-WORD LOGIC ---
      // If the transcript contains the wake word, either trigger a memory query immediately
      // or enter memory mode awaiting the next question.
      if (cleanTranscript.contains(_kWakeWord)) {
        final remainder = _stripWakeWordAndRemainder(cleanTranscript);
        // Activate memory mode and create new session.
        _isMemoryModeActive = true;
        _memorySessionId = DateTime.now()
            .millisecondsSinceEpoch
            .toString(); // Unique session ID

        if (remainder.isNotEmpty) {
          // Immediate question following the wake word. Treat remainder as the first memory query.
          _isAwaitingMemoryQuestion = false;
          await _handleMemoryQuery(remainder);
          // _handleMemoryQuery will prompt for next question if memory mode remains active.
          return;
        } else {
          // Only the wake word was spoken. Prompt for the first question in memory mode.
          updateDynamicText(
              "Memory Mode Started:\nAsk your question.\nSay 'End Memory' to exit.\n\nContext: Will remember conversation history.");
          await TextService.get.startSendText(
              "Memory Mode Started:\nAsk your question.\nSay 'End Memory' to exit.\n\nContext: Will remember conversation history.");
          _isAwaitingMemoryQuestion = true;
          // Start listening for the memory question using WhisperServer.
          _listenForMemoryQuestion();
          return;
        }
      }

      // --- ENTER CHATGPT CONVERSATION MODE ---
      if (_matchesChatMode(cleanTranscript)) {
        print("EvenAI: Entering ChatGPT Conversation Mode.");
        _isChatGPTConversationMode = true;
        _chatGPTHistory.clear();
        await TextService.get.startSendText(
            "Chat Mode:\nI'll remember our conversation.\nSay 'Terminate' to exit.");
        _chatGPTModeTimer?.cancel();
        _chatGPTModeTimer = Timer(const Duration(minutes: 10), () async {
          print("EvenAI: ChatGPT mode FORCE EXIT after 10 minutes.");
          _isChatGPTConversationMode = false;
          _chatGPTHistory.clear();
          await _robustExitBmp();
          clear();
          isRunning = false;
        });
        toStartEvenAIByOS();  // Immediately start listening for first question
        return;
      }

      // --- ENTER INTERVIEW MODE ---
      if (_matchesInterviewMode(cleanTranscript)) {
        print("EvenAI: Entering Interview Mode.");
        _isChatGPTConversationMode = true;  // Use same conversation mode
        _chatGPTHistory.clear();
        
        // Load resume and context from assets
        String resumeContext = "";
        try {
          final resumeText = await rootBundle.loadString('assets/interview/resume.txt');
          final projectContext = await rootBundle.loadString('assets/interview/projects.txt');
          resumeContext = "CANDIDATE BACKGROUND:\n$resumeText\n\nKEY PROJECTS:\n$projectContext";
          print("EvenAI: Loaded resume and project context (${resumeContext.length} chars)");
        } catch (e) {
          print("EvenAI: Could not load resume/projects context: $e");
          print("EvenAI: Using generic interview mode without custom context");
        }
        
        // Set up Interview Mode system prompt with resume context
        String systemPrompt = "You are an expert interview coach helping during a live job interview. "
            "Keep ALL responses under 50 words - concise and direct. "
            "Provide confident, professional answers that showcase skills and experience. "
            "If asked a technical question, give the core concept first, then a brief example. "
            "If asked behavioral questions, use STAR method (Situation, Task, Action, Result) briefly. "
            "Sound natural and conversational, not robotic.";
        
        if (resumeContext.isNotEmpty) {
          systemPrompt += "\n\n$resumeContext\n\n"
              "Use the above background to provide accurate, personalized answers. "
              "Draw from real projects and experience when answering. "
              "Stay consistent with the resume details.";
        } else {
          systemPrompt += " If you don't have enough context, provide a strong general answer that works for most situations.";
        }
        
        _chatGPTHistory.add({
          "role": "system",
          "content": systemPrompt
        });
        
        await TextService.get.startSendText(
            "Interview Mode:\nI'll help you answer interview questions.\nSay 'Terminate' to exit.");
        _chatGPTModeTimer?.cancel();
        _chatGPTModeTimer = Timer(const Duration(minutes: 10), () async {
          print("EvenAI: Interview mode FORCE EXIT after 10 minutes.");
          _isChatGPTConversationMode = false;
          _chatGPTHistory.clear();
          await _robustExitBmp();
          clear();
          isRunning = false;
        });
        toStartEvenAIByOS();  // Immediately start listening for first question
        return;
      }

      // --- ENTER VISION MODE ---
      if (_matchesVisionMode(cleanTranscript)) {
        print("🎯🎯🎯 VISION MODE DETECTED! Transcript: '$cleanTranscript' 🎯🎯🎯");
        AppLogger.banner('VISION MODE TRIGGERED');
        AppLogger.vision('Transcript matched vision mode: "$cleanTranscript"');
        print("EvenAI: Entering Vision Mode.");
        print("🚀 About to call _startVisionMode()...");
        await _startVisionMode();
        print("✅ _startVisionMode() completed!");
        return;
      }

      // --- NEW: ENTER ALEXA MODE ---
      if (_matchesAlexa(cleanTranscript)) {
        print("EvenAI: Entering Alexa Remote Mode.");
        await TextService.get.startSendText(
            "Alexa:\nAll Lights, Bedroom Light, TV Off, Kitchen Lights, Terminate");
        _isAwaitingAlexaCommand = true;
        _alexaModeTimer?.cancel();
        _alexaModeTimer = Timer(const Duration(seconds: 30), () async {
          print("EvenAI: Alexa mode auto-exit after 30 seconds.");
          await _robustExitBmp();
          clear();
          isRunning = false;
        });
        _listenForFollowUpCommand();
        return;
      }

      // --- ENTER ROKU MODE ---
      if (_matchesRoku(cleanTranscript)) {
        print("EvenAI: Entering Roku Remote Mode.");
        await _displayRokuRemoteCard();
        _isAwaitingRokuCommand = true;
        _rokuModeTimer?.cancel();
        _rokuModeTimer = Timer(const Duration(seconds: 30), () async {
          print("EvenAI: Roku mode auto-exit after 30 seconds.");
          await _robustExitBmp();
          clear();
          isRunning = false;
        });
        _listenForFollowUpCommand();
        return;
      }

      // --- MENU COMMAND ---
      if (_matchesMenu(cleanTranscript)) {
        print("EvenAI: User spoke 'menu', displaying menu options.");
        await TextService.get.startSendText("Menu Item 1\nMenu Item 2");
        _isMenuMode = true;
        _listenForFollowUpCommand();
        return;
      }

      // --- HANDLE MENU SELECTION ---
      if (_isMenuMode) {
        _isMenuMode = false;
        String responseText = "";

        if (cleanTranscript.contains("one") || cleanTranscript.contains("1")) {
          responseText = "This is menu item one.";
        } else if (cleanTranscript.contains("two") ||
            cleanTranscript.contains("2")) {
          responseText = "This is menu item two.";
        } else {
          await TextService.get
              .startSendText("Sorry, I didn't recognize that option.");
          await Future.delayed(const Duration(seconds: 3));
          await _robustExitBmp();
          clear();
          isRunning = false;
          return;
        }

        if (responseText.isNotEmpty) {
          print("EvenAI: User selected an item, displaying: '$responseText'");
          updateDynamicText(responseText);
          await TextService.get.startSendText(responseText);
          await Future.delayed(const Duration(seconds: 5));
          await _robustExitBmp();
          clear();
          isRunning = false;
          return;
        }
      }

      // --- FOLLOW UP LOGIC ---
      if (_isAwaitingFollowUp) {
        if (cleanTranscript.contains("continue")) {
          print(
              "EvenAI: User spoke 'continue', restarting listening for new question.");
          toStartEvenAIByOS();
          return;
        }

        if (cleanTranscript.contains("terminate") ||
            cleanTranscript.contains("end")) {
          print("EvenAI: User spoke 'terminate', ending session.");
          
          // Exit vision mode if active
          if (_isVisionModeActive) {
            await _exitVisionMode();
            return;
          }
          
          // Clear ChatGPT conversation mode if active
          if (_isChatGPTConversationMode) {
            print("EvenAI: Exiting ChatGPT/Interview mode. Clearing ${_chatGPTHistory.length} messages.");
            _isChatGPTConversationMode = false;
            _chatGPTHistory.clear();
            _chatGPTModeTimer?.cancel();
          }
          
          _isAwaitingFollowUp = false;
          await _robustExitBmp();
          clear();
          isRunning = false;
          return;
        }
        _isAwaitingFollowUp = false;
      }

      // --- DEFAULT AI CHAT LOGIC ---
      updateDynamicText("Answering Question Asked: $transcript");
      await TextService.get.startSendText("Q: $transcript");
      final apiService = ApiDeepSeekService();
      
      // Pass conversation history and image if in vision mode
      final answer = await apiService.sendChatRequest(
        transcript, 
        conversationHistory: _isChatGPTConversationMode ? _chatGPTHistory : null,
        imageBase64: _isVisionModeActive ? _latestImageBase64 : null,
      );
      
      print("EvenAI: Answer from OpenAI: '$answer'");
      
      // If in conversation mode, add to history
      if (_isChatGPTConversationMode) {
        _chatGPTHistory.add({"role": "user", "content": transcript});
        _chatGPTHistory.add({"role": "assistant", "content": answer});
        print("ChatGPT: Conversation history now has ${_chatGPTHistory.length} messages");
      }
      
      updateDynamicText("$transcript\n\n$answer");
      isEvenAISyncing.value = false;
      saveQuestionItem(transcript, answer);
      await TextService.get.startSendText(answer);

      _isAwaitingFollowUp = true;
      await Future.delayed(const Duration(seconds: 1));
      
      // Show different prompt if in conversation mode
      if (_isChatGPTConversationMode) {
        await TextService.get
            .startSendText("$answer\n\n'Continue' for more or 'Terminate' to exit");
      } else {
        await TextService.get
            .startSendText("$answer\n\n'Continue Asking' or say 'Terminate' to End");
      }
      _listenForFollowUpCommand();
    } catch (e) {
      print("EvenAI: Error during transcription or API call: $e");
      updateDynamicText("Sorry, an error occurred.");
      isEvenAISyncing.value = false;
      await TextService.get.startSendText("Sorry, an error occurred.");
      isRunning = false;
    }
  }

  void saveQuestionItem(String title, String content) {
    final controller = Get.find<EvenaiModelController>();
    controller.addItem(title, content);
  }

  // --- VISION MODE METHODS ---
  
  /// Public method to start Vision Mode (can be called from UI)
  Future<void> startVisionMode() async {
    await _startVisionMode();
  }
  
  Future<void> _startVisionMode() async {
    try {
      // Prevent double-activation if already active
      if (_isVisionModeActive) {
        AppLogger.warning('Vision Mode already active - ignoring re-entry');
        return;
      }
      print("📍 _startVisionMode: ENTRY POINT");
      AppLogger.separator('VISION MODE ACTIVATION');
      AppLogger.vision('Starting Vision Mode initialization');
      
      // Check camera permission
      print("📍 _startVisionMode: Checking camera permission...");
      AppLogger.vision('Checking camera permission');
      final hasPermission = await Permission.camera.isGranted;
      print("📍 _startVisionMode: Has permission = $hasPermission");
      
      if (!hasPermission) {
        print("📍 _startVisionMode: Requesting camera permission...");
        AppLogger.warning('Camera permission not granted, requesting permission');
        final status = await Permission.camera.request();
        print("📍 _startVisionMode: Permission status = ${status.isGranted}");
        AppLogger.permission('Camera', status.isGranted);
        
        if (!status.isGranted) {
          print("📍 _startVisionMode: Permission DENIED - exiting");
          AppLogger.error('Camera permission denied by user');
          await TextService.get.startSendText("Camera permission required for Vision Mode.");
          return;
        }
      } else {
        print("📍 _startVisionMode: Permission already granted");
        AppLogger.success('Camera permission already granted');
      }
      
      print("📍 _startVisionMode: Setting state variables...");
      AppLogger.stateChange('Vision Mode Active', false, true);
      _isVisionModeActive = true;
      _isChatGPTConversationMode = true;
      _chatGPTHistory.clear();
      
      // Set up system prompt for vision mode
      print("📍 _startVisionMode: Setting up system prompt...");
      AppLogger.vision('Setting up vision mode system prompt');
      _chatGPTHistory.add({
        "role": "system",
        "content": "You are a helpful AI assistant with vision. "
            "Analyze images and answer questions about what you see. "
            "Keep ALL responses under 50 words - concise and clear. "
            "Focus on the most important details. "
            "If asked about text, read it accurately. "
            "If asked about objects, describe them briefly."
      });
      print("📍 _startVisionMode: System prompt added");
      AppLogger.debug('Conversation history initialized with ${_chatGPTHistory.length} messages');
      
      print("📍 _startVisionMode: Sending text to glasses...");
      AppLogger.bluetooth('Sending activation message to glasses');
      await TextService.get.startSendText(
          "Vision Mode:\nOpening camera. Press capture button to analyze.\nSay 'Terminate' to exit.");
      print("📍 _startVisionMode: Text sent to glasses");
      
      // Navigate to vision mode page (no auto-capture)
      print("📍 _startVisionMode: About to navigate to /vision route...");
      AppLogger.info('Navigating to Vision Mode page');
      Get.toNamed('/vision');
      print("📍 _startVisionMode: Navigation called (sync)");
      
      // Auto-exit after 10 minutes
      print("📍 _startVisionMode: Setting up 10-minute timer...");
      AppLogger.timer('Vision Mode Auto-Exit Timer', 'Starting (10 min)');
      _visionModeTimer?.cancel();
      _visionModeTimer = Timer(const Duration(minutes: 10), () async {
        AppLogger.warning('Vision mode auto-exit triggered after 10 minutes');
        await _exitVisionMode();
      });
      print("📍 _startVisionMode: Timer set");
      
      print("📍 _startVisionMode: SUCCESS - Vision mode fully activated!");
      AppLogger.success('Vision Mode fully activated and ready');
      AppLogger.separator();
      
    } catch (e, stackTrace) {
      AppLogger.error('Failed to start vision mode', error: e, stackTrace: stackTrace);
      await TextService.get.startSendText("Camera error. Vision mode unavailable.");
      await _exitVisionMode();
    }
  }
  
  /// Public method to capture and analyze image (called by vision mode page)
  /// Requires the camera controller from the vision page
  Future<String> captureAndAnalyzeImage(CameraController cameraController) async {
    try {
      AppLogger.camera('Capture triggered - using vision page camera');
      
      if (!cameraController.value.isInitialized) {
        AppLogger.error('Camera controller not initialized!');
        return "Error: Camera not ready";
      }
      
      // Capture image using the existing camera controller
      AppLogger.camera('Taking picture with camera controller...');
      final image = await cameraController.takePicture();
      final bytes = await image.readAsBytes();
      final originalSize = bytes.length;
      
      AppLogger.success('Image captured: ${originalSize} bytes');
      
      // Compress image
      AppLogger.camera('Decoding and compressing image');
      final decodedImage = img.decodeImage(bytes);
      
      String? imageBase64;
      if (decodedImage != null) {
        AppLogger.debug('Original image size: ${decodedImage.width}x${decodedImage.height}');
        
        // Resize to max 800px width while maintaining aspect ratio
        final resized = img.copyResize(decodedImage, width: 800);
        AppLogger.debug('Resized to: ${resized.width}x${resized.height}');
        
        final compressed = img.encodeJpg(resized, quality: 70);
        imageBase64 = base64Encode(compressed);
        
        final compressionRatio = ((1 - compressed.length / originalSize) * 100).toStringAsFixed(1);
        AppLogger.success('Image compressed: ${compressed.length} bytes ($compressionRatio% reduction)');
      }
      
      if (imageBase64 == null) {
        return "Error: Failed to process image";
      }
      
      // Two-step process: GPT-4o Vision analyzes, then GPT-5 refines the answer
      AppLogger.vision('Step 1: Sending image to GPT-4o vision for analysis');
      final apiService = ApiDeepSeekService();
      
      // Step 1: GPT-4o Vision reads and extracts the question + context from the image
      String visionPrompt = "Extract and describe the exam question shown in this image. Include the question text, any answer choices, and relevant context. Be precise and complete.";
      
      AppLogger.apiRequest('GPT-4o Vision', visionPrompt);
      final visionAnalysis = await apiService.sendChatRequest(
        visionPrompt,
        conversationHistory: null,
        imageBase64: imageBase64,
      );
      
      AppLogger.success('Vision analysis received: ${visionAnalysis.length} characters');
      AppLogger.debug('Vision extracted: ${visionAnalysis.substring(0, visionAnalysis.length > 150 ? 150 : visionAnalysis.length)}...');
      
      // Step 2: GPT-5 generates a concise, accurate answer based on the vision analysis
      AppLogger.vision('Step 2: Sending to GPT-5 for refined answer');
      String refinementPrompt = "Based on this exam question analysis, provide a brief, direct answer (40 words max):\n\n$visionAnalysis";
      
      AppLogger.apiRequest('GPT-5', refinementPrompt);
      final response = await apiService.sendChatRequest(
        refinementPrompt,
        conversationHistory: null,
        imageBase64: null, // No image for GPT-5, just text
      );
      
      AppLogger.success('Received refined answer: ${response.length} characters');
      
      // Add to conversation history (store the vision analysis as context)
      _chatGPTHistory.add({"role": "user", "content": "Image: $visionAnalysis"});
      _chatGPTHistory.add({"role": "assistant", "content": response});
      
      // Send response to glasses
      AppLogger.bluetooth('Sending response to glasses');
      await TextService.get.startSendText(response);
      
      return response;
      
    } catch (e, stackTrace) {
      AppLogger.error('Error capturing and analyzing image', error: e, stackTrace: stackTrace);
      return "Error: ${e.toString()}";
    }
  }
  
  Future<void> _initCamera() async {
    try {
      AppLogger.camera('Querying available cameras');
      final cameras = await availableCameras();
      
      if (cameras.isEmpty) {
        AppLogger.error('No cameras available on device');
        throw Exception("No cameras available");
      }
      
      AppLogger.debug('Found ${cameras.length} camera(s)');
      for (var i = 0; i < cameras.length; i++) {
        AppLogger.debug('Camera $i: ${cameras[i].name} (${cameras[i].lensDirection})');
      }
      
      // Find rear camera
      final rearCamera = cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      
      AppLogger.camera('Selected camera: ${rearCamera.name} (${rearCamera.lensDirection})');
      
      _cameraController = CameraController(
        rearCamera,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      
      AppLogger.camera('Initializing camera controller...');
      await _cameraController!.initialize();
      
      AppLogger.success('Camera initialized successfully');
      AppLogger.debug('Camera resolution: ${_cameraController!.value.previewSize}');
      
    } catch (e, stackTrace) {
      AppLogger.error('Camera initialization failed', error: e, stackTrace: stackTrace);
      rethrow;
    }
  }
  
  Future<void> _captureImage() async {
    if (_cameraController == null || !_cameraController!.value.isInitialized) {
      AppLogger.warning('Camera not ready for capture');
      return;
    }
    
    try {
      AppLogger.camera('Capturing image...');
      final image = await _cameraController!.takePicture();
      final bytes = await image.readAsBytes();
      final originalSize = bytes.length;
      
      AppLogger.debug('Image captured: ${originalSize} bytes');
      
      // Compress image to reduce size
      AppLogger.camera('Decoding and compressing image');
      final decodedImage = img.decodeImage(bytes);
      
      if (decodedImage != null) {
        AppLogger.debug('Original image size: ${decodedImage.width}x${decodedImage.height}');
        
        // Resize to max 800px width while maintaining aspect ratio
        final resized = img.copyResize(decodedImage, width: 800);
        AppLogger.debug('Resized to: ${resized.width}x${resized.height}');
        
        final compressed = img.encodeJpg(resized, quality: 70);
        _latestImageBase64 = base64Encode(compressed);
        
        final compressionRatio = ((1 - compressed.length / originalSize) * 100).toStringAsFixed(1);
        AppLogger.success('Image compressed: ${compressed.length} bytes ($compressionRatio% reduction)');
      } else {
        AppLogger.error('Failed to decode image');
      }
      
    } catch (e, stackTrace) {
      AppLogger.error('Error capturing image', error: e, stackTrace: stackTrace);
    }
  }
  
  void _stopCamera() {
    AppLogger.camera('Stopping camera and disposing controller');
    _cameraController?.dispose();
    _cameraController = null;
    _latestImageBase64 = null;
    AppLogger.success('Camera stopped and disposed');
  }
  
  Future<void> _exitVisionMode() async {
    AppLogger.separator('VISION MODE EXIT');
    AppLogger.vision('Exiting Vision Mode');
    
    AppLogger.stateChange('Vision Mode Active', true, false);
    _isVisionModeActive = false;
    _isChatGPTConversationMode = false;
    
    AppLogger.debug('Clearing conversation history (${_chatGPTHistory.length} messages)');
    _chatGPTHistory.clear();
    
    AppLogger.timer('Camera Capture Timer', 'Cancelling');
    _cameraCaptureTimer?.cancel();
    
    AppLogger.timer('Vision Mode Timer', 'Cancelling');
    _visionModeTimer?.cancel();
    
    _stopCamera();

    // Ensure the Vision page is closed so its timers and camera are disposed
    try {
      if (Get.currentRoute == '/vision' && Get.key.currentState != null) {
        AppLogger.info('Popping /vision route');
        Get.back();
      } else {
        // Attempt to remove any lingering /vision route from the stack
        AppLogger.debug('Ensuring /vision route is not on stack');
        Get.until((route) => route.settings.name != '/vision');
      }
    } catch (e) {
      AppLogger.warning('Could not pop /vision route (might already be closed): $e');
    }
    
    AppLogger.bluetooth('Clearing glasses display');
    await _robustExitBmp();
    
    clear();
    isRunning = false;
    
    AppLogger.success('Vision Mode exited successfully');
    AppLogger.separator();
  }

  void clear() {
    print("EvenAI: Clearing state.");
    _isAwaitingFollowUp = false;
    _isMenuMode = false;
    _isAwaitingRokuCommand = false;
    _isAwaitingAlexaCommand = false; // --- NEW ---
    _isAwaitingMemoryQuestion = false; // Reset memory mode question flag
    _isMemoryModeActive = false; // Reset memory mode active flag
    _isVisionModeActive = false; // Reset vision mode flag
    isReceivingAudio = false;
    _isManual = false;
    _currentLine = 0;
    _recordingTimer?.cancel();
    _recordingTimer = null;
    _rokuModeTimer?.cancel();
    _rokuModeTimer = null;
    _alexaModeTimer?.cancel();
    _alexaModeTimer = null;
    _visionModeTimer?.cancel();
    _visionModeTimer = null;
    _cameraCaptureTimer?.cancel();
    _cameraCaptureTimer = null;
    _timer?.cancel();
    _timer = null;
    list.clear();
    sendReplys.clear();
    durationS = 0;
    retryCount = 0;
    _transcriptFuture = null;
    _stopCamera();
  }

  Future<void> openEvenAIMic() async {
    final (_, isStartSucc) = await Proto.micOn(lr: "R");
    print('EvenAI: Mic activation success: $isStartSucc');
    if (!isStartSucc && isReceivingAudio) {
      await Future.delayed(const Duration(milliseconds: 500));
      await openEvenAIMic();
    }
  }

  int retryCount = 0;
  Future<bool> sendEvenAIReply(
      String text, int type, int status, int pos) async {
    print(
        'EvenAI: Sending to glasses - Text: "$text", Status: 0x${status.toRadixString(16)}');
    bool isSuccess = await Proto.sendEvenAIData(text,
        newScreen: EvenAIDataMethod.transferToNewScreen(type, status),
        pos: pos,
        current_page_num: getCurrentPage(),
        max_page_num: getTotalPages());
    if (!isSuccess && retryCount < maxRetry) {
      retryCount++;
      print("EvenAI: Send failed, retrying... ($retryCount/$maxRetry)");
      await Future.delayed(const Duration(milliseconds: 200));
      return await sendEvenAIReply(text, type, status, pos);
    }
    if (!isSuccess) print("EvenAI: Send failed after all retries.");
    retryCount = 0;
    return isSuccess;
  }

  // --- Helper and Utility Methods (No changes needed below this line) ---

  int getTotalPages() {
    if (list.isEmpty) return 0;
    if (list.length < 6) return 1;
    return (list.length / 5).ceil();
  }

  int getCurrentPage() {
    if (_currentLine == 0) return 1;
    return (_currentLine / 5).floor() + 1;
  }

  Future sendNetworkErrorReply(String text) async {
    _currentLine = 0;
    list = EvenAIDataMethod.measureStringList(text);
    String ryplyWords =
        list.sublist(0, min(3, list.length)).map((str) => '$str\n').join();
    String headString = '\n\n';
    ryplyWords = headString + ryplyWords;
    await sendEvenAIReply(ryplyWords, 0x01, 0x60, 0);
    clear();
  }

  Future startSendReply(String text) async {
    _currentLine = 0;
    list = EvenAIDataMethod.measureStringList(text);
    if (list.length < 4) {
      String startScreenWords =
          list.sublist(0, min(3, list.length)).map((str) => '$str\n').join();
      String headString = '\n\n';
      startScreenWords = headString + startScreenWords;
      bool isSuccess = await sendEvenAIReply(startScreenWords, 0x01, 0x30, 0);
      await Future.delayed(Duration(seconds: 3));
      if (_isManual) {
        return;
      }
      isSuccess = await sendEvenAIReply(startScreenWords, 0x01, 0x40, 0);
      return;
    }
    if (list.length == 4) {
      String startScreenWords =
          list.sublist(0, 4).map((str) => '$str\n').join();
      String headString = '\n';
      startScreenWords = headString + startScreenWords;
      bool isSuccess = await sendEvenAIReply(startScreenWords, 0x01, 0x30, 0);
      await Future.delayed(Duration(seconds: 3));
      if (_isManual) {
        return;
      }
      isSuccess = await sendEvenAIReply(startScreenWords, 0x01, 0x40, 0);
      return;
    }
    if (list.length == 5) {
      String startScreenWords =
          list.sublist(0, 5).map((str) => '$str\n').join();
      bool isSuccess = await sendEvenAIReply(startScreenWords, 0x01, 0x30, 0);
      await Future.delayed(Duration(seconds: 3));
      if (_isManual) {
        return;
      }
      isSuccess = await sendEvenAIReply(startScreenWords, 0x01, 0x40, 0);
      return;
    }
    String startScreenWords = list.sublist(0, 5).map((str) => '$str\n').join();
    bool isSuccess = await sendEvenAIReply(startScreenWords, 0x01, 0x30, 0);
    if (isSuccess) {
      _currentLine = 0;
      await updateReplyToOSByTimer();
    } else {
      clear();
    }
  }

  Future updateReplyToOSByTimer() async {
    int interval = 5;
    _timer?.cancel();
    _timer = Timer.periodic(Duration(seconds: interval), (timer) async {
      if (_isManual) {
        _timer?.cancel();
        _timer = null;
        return;
      }
      _currentLine = min(_currentLine + 5, list.length - 1);
      sendReplys = list.sublist(_currentLine);
      if (_currentLine >= list.length - 1) {
        _timer?.cancel();
        _timer = null;
      } else {
        if (sendReplys.length < 4) {
          var mergedStr = sendReplys
              .sublist(0, sendReplys.length)
              .map((str) => '$str\n')
              .join();
          if (_currentLine >= list.length - 5) {
            await sendEvenAIReply(mergedStr, 0x01, 0x40, 0);
            _timer?.cancel();
            _timer = null;
          } else {
            await sendEvenAIReply(mergedStr, 0x01, 0x30, 0);
          }
        } else {
          var mergedStr = sendReplys
              .sublist(0, min(5, sendReplys.length))
              .map((str) => '$str\n')
              .join();
          if (_currentLine >= list.length - 5) {
            await sendEvenAIReply(mergedStr, 0x01, 0x40, 0);
            _timer?.cancel();
            _timer = null;
          } else {
            await sendEvenAIReply(mergedStr, 0x01, 0x30, 0);
          }
        }
      }
    });
  }

  void nextPageByTouchpad() {
    if (!isRunning) return;
    _isManual = true;
    _timer?.cancel();
    _timer = null;
    if (getTotalPages() < 2) {
      manualForJustOnePage();
      return;
    }
    if (_currentLine + 5 > list.length - 1) {
      return;
    } else {
      _currentLine += 5;
    }
    updateReplyToOSByManual();
  }

  void lastPageByTouchpad() {
    if (!isRunning) return;
    _isManual = true;
    _timer?.cancel();
    _timer = null;
    if (getTotalPages() < 2) {
      manualForJustOnePage();
      return;
    }
    if (_currentLine - 5 < 0) {
      _currentLine = 0;
    } else {
      _currentLine -= 5;
    }
    updateReplyToOSByManual();
  }

  Future updateReplyToOSByManual() async {
    if (_currentLine < 0 || _currentLine > list.length - 1) {
      return;
    }
    sendReplys = list.sublist(_currentLine);
    if (sendReplys.length < 4) {
      var mergedStr = sendReplys
          .sublist(0, sendReplys.length)
          .map((str) => '$str\n')
          .join();
      await sendEvenAIReply(mergedStr, 0x01, 0x50, 0);
    } else {
      var mergedStr = sendReplys
          .sublist(0, min(5, sendReplys.length))
          .map((str) => '$str\n')
          .join();
      await sendEvenAIReply(mergedStr, 0x01, 0x50, 0);
    }
  }

  Future manualForJustOnePage() async {
    if (list.length < 4) {
      String screenWords =
          list.sublist(0, min(3, list.length)).map((str) => '$str\n').join();
      String headString = '\n\n';
      screenWords = headString + screenWords;
      await sendEvenAIReply(screenWords, 0x01, 0x50, 0);
      return;
    }
    if (list.length == 4) {
      String screenWords = list.sublist(0, 4).map((str) => '$str\n').join();
      String headString = '\n';
      screenWords = headString + screenWords;
      await sendEvenAIReply(screenWords, 0x01, 0x50, 0);
      return;
    }
    if (list.length == 5) {
      String screenWords = list.sublist(0, 5).map((str) => '$str\n').join();
      await sendEvenAIReply(screenWords, 0x01, 0x50, 0);
      return;
    }
  }

  Future stopEvenAIByOS() async {
    isRunning = false;
    clear();
    await BleManager.invokeMethod("stopEvenAI");
  }

  static void dispose() {
    _textStreamController.close();
  }
}

// ========================================================================
// API Service Class (Handles communication with the AI model)
// ========================================================================
class ApiDeepSeekService {
  late Dio _dio;

  ApiDeepSeekService() {
    _dio = Dio(
      BaseOptions(
        baseUrl: 'https://api.openai.com/v1',
        headers: {
          'Authorization': 'Bearer ${dotenv.env['OPENAI_API_KEY']}',
          'Content-Type': 'application/json',
        },
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 30),
      ),
    );
  }

  Future<String> sendChatRequest(
    String question, {
    List<Map<String, String>>? conversationHistory,
    String? imageBase64,
  }) async {
    AppLogger.methodEntry('ApiDeepSeekService', 'sendChatRequest', params: {
      'question_length': question.length,
      'has_history': conversationHistory != null,
      'has_image': imageBase64 != null,
    });

    String modelToUse;
    if (question.toLowerCase().contains("research")) {
      modelToUse = "gpt-5";
      AppLogger.debug('Selected gpt-5 model (keyword: "research")');
    } else if (imageBase64 != null) {
      modelToUse = "gpt-4o";
      AppLogger.vision('Selected gpt-4o model for vision request');
    } else {
      modelToUse = "gpt-4o";
      AppLogger.debug('Selected gpt-4o model (default)');
    }

    // Build messages array with conversation history
    List<Map<String, dynamic>> messages;
    
    if (conversationHistory != null && conversationHistory.isNotEmpty) {
      AppLogger.debug('Using conversation history with ${conversationHistory.length} messages');
      messages = List<Map<String, dynamic>>.from(conversationHistory);
      
      // Add current user message with optional image
      if (imageBase64 != null) {
        final imageSize = (imageBase64.length * 3 / 4 / 1024).toStringAsFixed(1);
        AppLogger.vision('Adding message with text and image ($imageSize KB)');
        messages.add({
          "role": "user",
          "content": [
            {"type": "text", "text": question},
            {
              "type": "image_url",
              "image_url": {"url": "data:image/jpeg;base64,$imageBase64"}
            }
          ]
        });
      } else {
        AppLogger.debug('Adding text-only message to history');
        messages.add({"role": "user", "content": question});
      }
    } else {
      AppLogger.debug('Creating new conversation (no history)');
      if (imageBase64 != null) {
        final imageSize = (imageBase64.length * 3 / 4 / 1024).toStringAsFixed(1);
        AppLogger.vision('Building vision request with image ($imageSize KB)');
        messages = [
          {"role": "system", "content": "You are a helpful assistant. Keep responses concise for smart glasses display."},
          {
            "role": "user",
            "content": [
              {"type": "text", "text": question},
              {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,$imageBase64"}
              }
            ]
          }
        ];
      } else {
        AppLogger.debug('Building text-only request');
        messages = [
          {"role": "system", "content": "You are a helpful assistant. Keep responses concise for smart glasses display."},
          {"role": "user", "content": question}
        ];
      }
    }

    final data = {
      "model": modelToUse,
      "messages": messages,
      "max_tokens": 150,
    };

    AppLogger.apiRequest('POST', '/chat/completions', data: {
      'model': modelToUse,
      'message_count': messages.length,
      'max_tokens': 150,
    });

    try {
      AppLogger.network('Sending request to OpenAI API...');
      final response = await _dio.post('/chat/completions', data: data);

      if (response.statusCode == 200) {
        AppLogger.apiResponse('/chat/completions', response.statusCode!);
        final data = response.data;
        final content = data['choices']?[0]?['message']?['content'] ??
            "Unable to answer the question";
        
        AppLogger.success('Received response: ${content.length} characters');
        AppLogger.debug('Response preview: ${content.substring(0, content.length > 100 ? 100 : content.length)}...');
        
        AppLogger.methodExit('ApiDeepSeekService', 'sendChatRequest', result: 'Success');
        return content;
      } else {
        AppLogger.apiResponse('/chat/completions', response.statusCode!);
        AppLogger.error('Request failed with status: ${response.statusCode}');
        return "Request failed with status: ${response.statusCode}";
      }
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      final data = e.response?.data;
      
      if (status != null) {
        AppLogger.apiResponse('/chat/completions', status, data: data);
        AppLogger.error('OpenAI API error: $status', error: data);
        return "AI request error: $status, $data";
      } else {
        final message = e.message ?? e.error?.toString() ?? 'Unknown error';
        AppLogger.error('Network error during API request', error: e);
        return "AI request error: $message";
      }
    } catch (e, stackTrace) {
      AppLogger.error('Unexpected error in sendChatRequest', error: e, stackTrace: stackTrace);
      return "Unexpected error: $e";
    }
  }
}

// ========================================================================
// Extension Method Class
// ========================================================================
extension EvenAIDataMethod on EvenAI {
  static int transferToNewScreen(int type, int status) {
    return status | type;
  }

  static List<String> measureStringList(String text, [double? maxW]) {
    final double maxWidth = maxW ?? 488;
    const double fontSize = 21;
    List<String> paragraphs = text
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList();
    List<String> ret = [];
    TextStyle ts = TextStyle(fontSize: fontSize);
    for (String paragraph in paragraphs) {
      final textSpan = TextSpan(text: paragraph, style: ts);
      final textPainter = TextPainter(
        text: textSpan,
        textDirection: TextDirection.ltr,
        maxLines: null,
      );
      textPainter.layout(maxWidth: maxWidth);
      final lineCount = textPainter.computeLineMetrics().length;
      var start = 0;
      for (var i = 0; i < lineCount; i++) {
        final line = textPainter.getLineBoundary(TextPosition(offset: start));
        ret.add(paragraph.substring(line.start, line.end).trim());
        start = line.end;
      }
    }
    return ret;
  }
}
