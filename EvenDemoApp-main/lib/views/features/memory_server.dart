import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:demo_ai_even/services/asr_http_service.dart';
import 'package:demo_ai_even/services/app_logger.dart';
import 'package:demo_ai_even/services/memory_service.dart';
import 'package:path_provider/path_provider.dart';
import 'package:flutter/services.dart';

class MemoryServerPage extends StatefulWidget {
  const MemoryServerPage({super.key});

  @override
  State<MemoryServerPage> createState() => _MemoryServerPageState();
}

class _MemoryServerPageState extends State<MemoryServerPage>
    with TickerProviderStateMixin {
  // --- Services and Controllers ---
  final AsrHttpService _asr = AsrHttpService.I;
  final MemoryService _memoryService = MemoryService.instance;
  final TextEditingController _questionController = TextEditingController();
  final TextEditingController _sessionController =
      TextEditingController(text: 'mobile-session');
  late TabController _tabController;

  // --- State Variables ---
  final List<_Line> _lines = [];
  final List<ConversationMessage> _conversation = [];
  final List<LogEntry> _logs = [];
  final List<String> _segmentEvents = [];
  String _segmentStatus = 'Idle';

  StreamSubscription<AsrEvent>? _asrSubscription;
  StreamSubscription<LogEntry>? _logSubscription;
  bool _isRunning = false;
  bool _isConnected = false;
  bool _isLoading = false;
  String _statusMessage = 'Checking connection...';
  String? _latestTranscriptPath;
  List<TranscriptRecord> _transcriptHistory = [];
  static const int _maxTranscriptHistory = 50;

  final RegExp _segmentPattern = RegExp(r'^segment #\d+', caseSensitive: false);

  // --- Theme Colors (to match FeaturesPage) ---
  static const Color primaryColor = Color(0xFF0D1B2A);
  static const Color cardColor = Color(0xFF1B263B);
  static const Color accentColor = Color(0xFF33A1F2);
  static const Color textColor = Colors.white;
  static const Color subtitleColor = Colors.white70;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);

    _asrSubscription = _asr.stream.listen(_handleEvent);
    _logSubscription = AppLogger.instance.stream.listen((entry) {
      if (!mounted) return;
      setState(() {
        if (_logs.length >= 500) {
          _logs.removeAt(0);
        }
        _logs.add(entry);
      });
    });

    _memoryService.initialize();
    unawaited(_loadTranscriptHistory());
    _checkConnection();
    _startAsr();
  }

  @override
  void dispose() {
    _asrSubscription?.cancel();
    _logSubscription?.cancel();
    _asr.stop();
    _tabController.dispose();
    _questionController.dispose();
    _sessionController.dispose();
    super.dispose();
  }

  // --- Event Handling & Business Logic (Unchanged) ---
  void _handleEvent(AsrEvent event) {
    if (!mounted) return;
    setState(() {
      if (event.type == 'error') {
        if (_lines.length >= 400) {
          _lines.removeAt(0);
        }
        _lines.add(
            _Line(event.error ?? event.text, event.speaker, isError: true));
        return;
      }

      final trimmed = event.text.trim();
      if (_isSegmentUpdate(event, trimmed)) {
        final message = trimmed.isEmpty ? event.text : trimmed;
        _segmentStatus = message.isEmpty ? 'Processing segment...' : message;
        _addSegmentEvent(_segmentStatus);
        return;
      }

      if (_lines.length >= 400) {
        _lines.removeAt(0);
      }
      _lines.add(_Line(trimmed.isEmpty ? event.text : trimmed, event.speaker,
          emotion: event.emotion));
    });
  }

  bool _isSegmentUpdate(AsrEvent event, String text) {
    if (event.speaker.toUpperCase() != 'SYSTEM') return false;
    if (text.isEmpty) return false;
    if (_segmentPattern.hasMatch(text)) return true;
    final lower = text.toLowerCase();
    return lower.contains('streaming started') ||
        lower.contains('streaming stopped') ||
        lower.contains('segment #');
  }

  void _addSegmentEvent(String message) {
    final entry = '[${_formatTime(DateTime.now())}] $message';
    _segmentEvents.insert(0, entry);
    if (_segmentEvents.length > 50) {
      _segmentEvents.removeLast();
    }
  }

  Future<void> _startAsr() async {
    if (_isRunning) return;
    try {
      await _asr.start();
      if (mounted) {
        setState(() {
          _isRunning = true;
          _segmentStatus = 'Streaming started';
        });
      }
    } catch (e) {
      _handleEvent(AsrEvent('error', '', 'SYSTEM', error: e.toString()));
    }
  }

  Future<void> _stopAsr() async {
    if (!_isRunning) return;
    await _asr.stop();
    if (mounted) {
      setState(() {
        _isRunning = false;
        _segmentStatus = 'Idle';
      });
    }
  }

  Future<void> _checkConnection() async {
    try {
      final connected = await _memoryService.checkConnection();
      if (!mounted) return;
      setState(() {
        _isConnected = connected;
        _statusMessage = connected ? 'Connected' : 'Not connected';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isConnected = false;
        _statusMessage = 'Connection error';
      });
    }
  }

  Future<void> _askQuestion() async {
    if (!_isConnected) {
      _showSnackBar('Not connected to server', isError: true);
      return;
    }

    final question = _questionController.text.trim();
    if (question.isEmpty) {
      _showSnackBar('Please enter a question', isError: true);
      return;
    }

    final sessionId = _sessionController.text.trim().isEmpty
        ? 'mobile-session'
        : _sessionController.text.trim();

    setState(() {
      _conversation.add(ConversationMessage(
        text: question,
        isUser: true,
        timestamp: DateTime.now(),
        sessionId: sessionId,
      ));
      _isLoading = true;
    });
    unawaited(_persistConversationToFile());

    _questionController.clear();

    try {
      final response =
          await _memoryService.askQuestion(question, sessionId: sessionId);
      if (!mounted) return;

      setState(() {
        _conversation.add(ConversationMessage(
          text: response.answer,
          isUser: false,
          timestamp: DateTime.now(),
          sessionId: sessionId,
          hits: response.hits,
          emotions: response.emotions,
        ));
        _isLoading = false;
      });

      unawaited(_persistConversationToFile());
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _conversation.add(ConversationMessage(
          text: 'Error: $e',
          isUser: false,
          timestamp: DateTime.now(),
          sessionId: sessionId,
          isError: true,
        ));
        _isLoading = false;
      });
      _showSnackBar('Failed to get answer: $e', isError: true);
    }
  }

  Future<void> _clearSession() async {
    if (!_isConnected) {
      _showSnackBar('Not connected to server', isError: true);
      return;
    }

    final sessionId = _sessionController.text.trim().isEmpty
        ? 'mobile-session'
        : _sessionController.text.trim();

    try {
      await _memoryService.clearSession(sessionId: sessionId);
      if (!mounted) return;
      setState(() {
        _conversation.clear();
      });
      unawaited(_persistConversationToFile());
      _showSnackBar('Session cleared');
    } catch (e) {
      _showSnackBar('Failed to clear session: $e', isError: true);
    }
  }

  void _showSnackBar(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message, style: const TextStyle(color: textColor)),
        backgroundColor: isError ? Colors.red.shade800 : cardColor,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  // --- Main Build Method (Styled) ---
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: primaryColor,
      appBar: AppBar(
        title: const Text('Memory Page',
            style: TextStyle(fontWeight: FontWeight.bold, color: textColor)),
        backgroundColor: primaryColor,
        elevation: 0,
        iconTheme: const IconThemeData(color: textColor),
        actions: [
          Container(
            margin: const EdgeInsets.only(right: 16),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: _isConnected ? Colors.green.shade600 : Colors.red.shade600,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              _statusMessage,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: accentColor,
          labelColor: accentColor,
          unselectedLabelColor: subtitleColor,
          tabs: const [
            Tab(icon: Icon(Icons.mic), text: 'Live Transcription'),
            Tab(icon: Icon(Icons.psychology), text: 'Memory Q&A'),
            Tab(icon: Icon(Icons.article), text: 'Logs'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildTranscriptionTab(),
          _buildMemoryTab(),
          _buildLogTab(),
        ],
      ),
    );
  }

  // --- UI Builder Methods (Styled) ---

  Widget _buildTranscriptionTab() {
    final ButtonStyle elevatedButtonStyle = ElevatedButton.styleFrom(
      backgroundColor: accentColor,
      foregroundColor: primaryColor,
      padding: const EdgeInsets.symmetric(vertical: 12),
    );
    final ButtonStyle outlinedButtonStyle = OutlinedButton.styleFrom(
      foregroundColor: accentColor,
      side: const BorderSide(color: accentColor),
      padding: const EdgeInsets.symmetric(vertical: 12),
    );

    return Column(
      children: [
        if (_segmentStatus.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 6),
            child: Align(
              alignment: Alignment.centerRight,
              child: InkWell(
                borderRadius: BorderRadius.circular(18),
                onTap: _segmentEvents.isEmpty ? null : _showSegmentLog,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: cardColor.withOpacity(0.8),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: accentColor.withOpacity(0.5)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.timeline, size: 18, color: accentColor),
                      const SizedBox(width: 8),
                      ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 220),
                        child: Text(
                          _segmentStatus,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: accentColor,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                      if (_segmentEvents.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(left: 6),
                          child: Icon(Icons.expand_more,
                              size: 18, color: accentColor.withOpacity(0.7)),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        Expanded(
          child: _lines.isEmpty
              ? const _EmptyState()
              : ListView.builder(
                  padding: const EdgeInsets.all(12),
                  itemCount: _lines.length,
                  itemBuilder: (context, index) {
                    final line = _lines[index];
                    final isSystem = line.speaker == 'SYSTEM';
                    final color = line.isError
                        ? Colors.red.shade300
                        : (isSystem ? subtitleColor : textColor);
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: isSystem
                                  ? Colors.grey.shade700
                                  : accentColor.withOpacity(0.3),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              line.speaker,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: textColor),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(line.text,
                                      style: TextStyle(color: color)),
                                ),
                                if (line.emotion != null && !isSystem) ...[
                                  const SizedBox(width: 8),
                                  _buildLineEmotionIndicator(line.emotion!),
                                ],
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
          child: Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _isRunning ? null : _startAsr,
                  icon: const Icon(Icons.mic),
                  label: const Text('Start ASR'),
                  style: elevatedButtonStyle,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isRunning ? _stopAsr : null,
                  icon: const Icon(Icons.stop),
                  label: const Text('Stop'),
                  style: outlinedButtonStyle,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  void _showSegmentLog() {
    showModalBottomSheet(
      context: context,
      backgroundColor: cardColor,
      showDragHandle: true,
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: _segmentEvents.isEmpty
                ? const Center(
                    child: Text('No segment activity yet.',
                        style: TextStyle(color: subtitleColor)))
                : ListView.separated(
                    shrinkWrap: true,
                    itemCount: _segmentEvents.length,
                    itemBuilder: (context, index) => Text(_segmentEvents[index],
                        style: const TextStyle(color: textColor)),
                    separatorBuilder: (_, __) =>
                        Divider(color: subtitleColor.withOpacity(0.3)),
                  ),
          ),
        );
      },
    );
  }

  Widget _buildMemoryTab() {
    return Column(
      children: [
        _buildInputCard(),
        const SizedBox(height: 8),
        Expanded(
          child: _conversation.isEmpty
              ? const _ConversationEmptyState()
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _conversation.length,
                  itemBuilder: (context, index) {
                    final message = _conversation[index];
                    return _buildMessageBubble(message);
                  },
                ),
        ),
        if (_isLoading)
          const Padding(
            padding: EdgeInsets.all(16),
            child: Center(child: CircularProgressIndicator(color: accentColor)),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: _buildTranscriptActions(),
        ),
      ],
    );
  }

  Widget _buildInputCard() {
    final ButtonStyle actionButtonStyle = ElevatedButton.styleFrom(
      backgroundColor: cardColor,
      foregroundColor: accentColor,
      side: BorderSide(color: accentColor.withOpacity(0.5)),
      elevation: 0,
    );

    return Card(
      color: cardColor,
      margin: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _sessionController,
                    style: const TextStyle(color: textColor),
                    decoration: InputDecoration(
                      labelText: 'Session ID',
                      labelStyle: const TextStyle(color: subtitleColor),
                      border: const OutlineInputBorder(),
                      enabledBorder: OutlineInputBorder(
                          borderSide: BorderSide(
                              color: subtitleColor.withOpacity(0.5))),
                      focusedBorder: const OutlineInputBorder(
                          borderSide: BorderSide(color: accentColor)),
                      isDense: true,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _isConnected ? _clearSession : null,
                  style: actionButtonStyle,
                  child: const Text('Clear'),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _checkConnection,
                  style: actionButtonStyle,
                  child: const Text('Refresh'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: TextField(
                    controller: _questionController,
                    style: const TextStyle(color: textColor),
                    decoration: InputDecoration(
                      hintText: 'Ask a question...',
                      hintStyle: const TextStyle(color: subtitleColor),
                      border: const OutlineInputBorder(),
                      enabledBorder: OutlineInputBorder(
                          borderSide: BorderSide(
                              color: subtitleColor.withOpacity(0.5))),
                      focusedBorder: const OutlineInputBorder(
                          borderSide: BorderSide(color: accentColor)),
                    ),
                    maxLines: 2,
                    onSubmitted: (_) => _askQuestion(),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _isConnected && !_isLoading ? _askQuestion : null,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: accentColor,
                    foregroundColor: primaryColor,
                    padding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 16),
                  ),
                  child: _isLoading
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: primaryColor),
                        )
                      : const Text('Ask'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTranscriptActions() {
    final path = _latestTranscriptPath;
    final hasHistory = _transcriptHistory.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 8,
          children: [
            ElevatedButton.icon(
              onPressed:
                  _conversation.isEmpty ? null : () => _showTranscriptViewer(),
              icon: const Icon(Icons.chrome_reader_mode),
              label: const Text('View full transcript'),
              style: ElevatedButton.styleFrom(
                  backgroundColor: accentColor, foregroundColor: primaryColor),
            ),
            OutlinedButton.icon(
              onPressed: _conversation.isEmpty
                  ? null
                  : () => unawaited(_persistConversationToFile()),
              icon: const Icon(Icons.download),
              label: const Text('Save latest copy'),
              style: OutlinedButton.styleFrom(
                  foregroundColor: accentColor,
                  side: const BorderSide(color: accentColor)),
            ),
          ],
        ),
        const SizedBox(height: 8),
        SelectableText(
          path == null
              ? 'Transcript file will appear here after you ask a question.'
              : 'Saved to: $path',
          style: const TextStyle(fontSize: 12, color: subtitleColor),
        ),
        if (hasHistory) ...[
          const SizedBox(height: 16),
          const Text(
            'Saved transcripts',
            style: TextStyle(color: textColor, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          _buildTranscriptHistoryList(),
        ],
      ],
    );
  }

  Future<void> _showTranscriptViewer({
    List<ConversationMessage>? messages,
    String? pathOverride,
    String? titleOverride,
  }) async {
    // ... Functionality is the same, only the UI inside the modal needs styling ...
    // This function remains long but the logic is untouched.
    final transcript = messages ?? _conversation;
    if (transcript.isEmpty) {
      _showSnackBar('No transcript available yet', isError: true);
      return;
    }

    final resolvedPath = pathOverride ?? _latestTranscriptPath;
    final headerTitle = titleOverride ?? 'Full conversation transcript';

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor:
          Colors.transparent, // Make it transparent to use our own background
      builder: (sheetContext) {
        return Container(
          decoration: const BoxDecoration(
            color: primaryColor,
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(20),
            ),
          ),
          child: FractionallySizedBox(
            heightFactor: 0.9,
            child: SafeArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 16),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                headerTitle,
                                style: const TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w600,
                                    color: textColor),
                              ),
                              const SizedBox(height: 4),
                              if (resolvedPath != null)
                                SelectableText(
                                  'Saved to: $resolvedPath',
                                  style: const TextStyle(
                                      fontSize: 12, color: subtitleColor),
                                ),
                            ],
                          ),
                        ),
                        if (resolvedPath != null)
                          IconButton(
                            tooltip: 'Copy path',
                            icon: const Icon(Icons.copy_all,
                                color: subtitleColor),
                            onPressed: () =>
                                _copyTranscriptPathFromString(resolvedPath),
                          ),
                        IconButton(
                          icon: const Icon(Icons.close, color: subtitleColor),
                          onPressed: () => Navigator.of(sheetContext).pop(),
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1, color: cardColor),
                  Expanded(
                    child: ListView.separated(
                      padding: const EdgeInsets.all(20),
                      itemCount: transcript.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 12),
                      itemBuilder: (context, index) {
                        final message = transcript[index];
                        final isUser = message.isUser;
                        final bubbleColor =
                            isUser ? accentColor.withOpacity(0.1) : cardColor;
                        final borderColor = isUser
                            ? accentColor.withOpacity(0.3)
                            : subtitleColor.withOpacity(0.3);
                        return Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: bubbleColor,
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: borderColor),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    isUser ? Icons.person : Icons.smart_toy,
                                    size: 16,
                                    color: isUser
                                        ? accentColor
                                        : Colors.green.shade300,
                                  ),
                                  const SizedBox(width: 6),
                                  Text(
                                    isUser ? 'You' : 'Memory Assistant',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w600,
                                        color: textColor),
                                  ),
                                  const Spacer(),
                                  Text(
                                    _formatTime(message.timestamp),
                                    style: const TextStyle(
                                        fontSize: 12, color: subtitleColor),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              SelectableText(
                                message.text,
                                style: TextStyle(
                                  color: message.isError
                                      ? Colors.red.shade300
                                      : textColor,
                                ),
                              ),
                              if (message.hits.isNotEmpty) ...[
                                const SizedBox(height: 12),
                                const Text(
                                  'Sources',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w600,
                                      fontSize: 12,
                                      color: subtitleColor),
                                ),
                                const SizedBox(height: 8),
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: message.hits.map((hit) {
                                    final preview = _formatHitPreview(hit);
                                    return GestureDetector(
                                      onTap: () => _showMemoryHitDetails(
                                          Map<String, dynamic>.from(hit)),
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(
                                            horizontal: 10, vertical: 8),
                                        decoration: BoxDecoration(
                                          color: accentColor.withOpacity(0.1),
                                          borderRadius:
                                              BorderRadius.circular(8),
                                          border: Border.all(
                                              color:
                                                  accentColor.withOpacity(0.2)),
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            const Icon(Icons.notes,
                                                size: 14, color: accentColor),
                                            const SizedBox(width: 6),
                                            ConstrainedBox(
                                              constraints: const BoxConstraints(
                                                  maxWidth: 220),
                                              child: Text(
                                                preview,
                                                style: const TextStyle(
                                                    fontSize: 12,
                                                    color: textColor),
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    );
                                  }).toList(),
                                ),
                              ],
                            ],
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  // --- File I/O (Unchanged) ---
  Future<void> _persistConversationToFile() async {
    // ... Functionality is unchanged ...
    if (_conversation.isEmpty) {
      if (mounted && _latestTranscriptPath != null) {
        setState(() {
          _latestTranscriptPath = null;
        });
      }
      return;
    }

    try {
      final dir = await _getTranscriptDirectory();
      final sessionId = _sessionController.text.trim().isEmpty
          ? 'mobile-session'
          : _sessionController.text.trim();
      final safeSessionId = _sanitizeForFileName(sessionId);
      final now = DateTime.now();
      final fileName =
          'memory_conversation_${safeSessionId}_${now.millisecondsSinceEpoch}.json';
      final file = File('${dir.path}/$fileName');
      final messages = _conversation
          .map(
            (message) => {
              'text': message.text,
              'is_user': message.isUser,
              'timestamp': message.timestamp.toIso8601String(),
              'session_id': message.sessionId,
              'hits': message.hits,
              'is_error': message.isError,
            },
          )
          .toList();
      final payload = {
        'session_id': sessionId,
        'saved_at': now.toIso8601String(),
        'messages': messages,
      };

      await file.writeAsString(jsonEncode(payload));
      final record = TranscriptRecord(
        path: file.path,
        sessionId: sessionId,
        savedAt: now,
        messageCount: messages.length,
      );
      if (!mounted) return;
      setState(() {
        _latestTranscriptPath = file.path;
        _upsertTranscriptRecord(record);
      });
    } catch (e) {
      if (!mounted) return;
      _showSnackBar('Failed to save transcript: $e', isError: true);
    }
  }

  Future<Directory> _getTranscriptDirectory() async {
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/transcripts');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  Future<void> _loadTranscriptHistory() async {
    // ... Functionality is unchanged ...
    try {
      final dir = await _getTranscriptDirectory();
      if (!await dir.exists()) {
        return;
      }

      final files = await dir
          .list()
          .where((entity) => entity is File && entity.path.endsWith('.json'))
          .cast<File>()
          .toList();

      final records = <TranscriptRecord>[];
      for (final file in files) {
        try {
          final content = await file.readAsString();
          final data = jsonDecode(content) as Map<String, dynamic>;
          final messages = (data['messages'] as List?) ?? const [];
          final savedAtString = data['saved_at']?.toString();
          final savedAt = savedAtString != null
              ? DateTime.tryParse(savedAtString) ?? (await file.lastModified())
              : await file.lastModified();
          final sessionId = data['session_id']?.toString() ?? 'unknown';
          records.add(
            TranscriptRecord(
              path: file.path,
              sessionId: sessionId,
              savedAt: savedAt,
              messageCount: messages.length,
            ),
          );
        } catch (_) {
          continue;
        }
      }

      records.sort((a, b) => b.savedAt.compareTo(a.savedAt));
      if (!mounted) return;
      setState(() {
        _transcriptHistory = records.take(_maxTranscriptHistory).toList();
      });
    } catch (e) {
      AppLogger.instance.log(
          'MemoryServerPage', 'Failed to load transcripts: $e',
          isError: true);
    }
  }

  void _upsertTranscriptRecord(TranscriptRecord record) {
    _transcriptHistory.removeWhere((item) => item.path == record.path);
    _transcriptHistory.insert(0, record);
    if (_transcriptHistory.length > _maxTranscriptHistory) {
      _transcriptHistory =
          _transcriptHistory.take(_maxTranscriptHistory).toList();
    }
  }

  Future<void> _openTranscriptRecord(TranscriptRecord record) async {
    // ... Functionality is unchanged ...
    try {
      final file = File(record.path);
      if (!await file.exists()) {
        if (!mounted) return;
        setState(() {
          _transcriptHistory.removeWhere((item) => item.path == record.path);
        });
        _showSnackBar('Transcript not found on disk', isError: true);
        return;
      }
      final content = await file.readAsString();
      final data = jsonDecode(content) as Map<String, dynamic>;
      final messages = _decodeMessages((data['messages'] as List?) ?? const []);
      _showTranscriptViewer(
        messages: messages,
        pathOverride: record.path,
        titleOverride:
            'Transcript (${record.sessionId}) • ${_formatTimestamp(record.savedAt)}',
      );
    } catch (e) {
      _showSnackBar('Failed to open transcript: $e', isError: true);
    }
  }

  Future<void> _deleteTranscriptRecord(TranscriptRecord record) async {
    // ... Functionality is unchanged ...
    try {
      final file = File(record.path);
      if (await file.exists()) {
        await file.delete();
      }
      if (!mounted) return;
      setState(() {
        _transcriptHistory.removeWhere((item) => item.path == record.path);
        if (_latestTranscriptPath == record.path) {
          _latestTranscriptPath = null;
        }
      });
      _showSnackBar('Transcript deleted');
    } catch (e) {
      _showSnackBar('Failed to delete transcript: $e', isError: true);
    }
  }

  Future<void> _copyTranscriptPath(TranscriptRecord record) async {
    await Clipboard.setData(ClipboardData(text: record.path));
    _showSnackBar('Transcript path copied');
  }

  Future<void> _copyTranscriptPathFromString(String path) async {
    await Clipboard.setData(ClipboardData(text: path));
    _showSnackBar('Transcript path copied');
  }

  Widget _buildTranscriptHistoryList() {
    return ListView.separated(
      shrinkWrap: true,
      physics:
          const ClampingScrollPhysics(), // Use clamping to prevent nested scroll conflicts
      itemCount: _transcriptHistory.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final record = _transcriptHistory[index];
        return Card(
          color: cardColor,
          elevation: 2,
          child: ListTile(
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            leading: const Icon(Icons.insert_drive_file_outlined,
                color: accentColor),
            title: Text(
              _formatTimestamp(record.savedAt),
              style: const TextStyle(color: textColor),
            ),
            subtitle: Text(
              '${record.sessionId} | ${record.messageCount} message${record.messageCount == 1 ? '' : 's'}',
              style: const TextStyle(color: subtitleColor, fontSize: 12),
            ),
            trailing: PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert, color: subtitleColor),
              color: cardColor,
              itemBuilder: (context) => [
                // --- FIX: Added the 'value:' named parameter ---
                const PopupMenuItem(
                    value: 'open',
                    child: Text('Open', style: TextStyle(color: textColor))),
                const PopupMenuItem(
                    value: 'copy',
                    child:
                        Text('Copy path', style: TextStyle(color: textColor))),
                const PopupMenuItem(
                    value: 'delete',
                    child: Text('Delete', style: TextStyle(color: textColor))),
              ],
              onSelected: (value) {
                if (value == 'open') _openTranscriptRecord(record);
                if (value == 'copy') _copyTranscriptPath(record);
                if (value == 'delete') _deleteTranscriptRecord(record);
              },
            ),
            onTap: () => _openTranscriptRecord(record),
          ),
        );
      },
    );
  }

  List<ConversationMessage> _decodeMessages(List<dynamic> raw) {
    // ... Functionality is unchanged ...
    final result = <ConversationMessage>[];
    for (final entry in raw) {
      if (entry is Map<String, dynamic>) {
        final timestampRaw = entry['timestamp']?.toString();
        final timestamp =
            timestampRaw != null ? DateTime.tryParse(timestampRaw) : null;
        result.add(
          ConversationMessage(
            text: entry['text']?.toString() ?? '',
            isUser: entry['is_user'] == true,
            timestamp: timestamp ?? DateTime.now(),
            sessionId: entry['session_id']?.toString() ?? 'session',
            hits: (entry['hits'] as List?)
                    ?.map((hit) => Map<String, dynamic>.from(
                        hit is Map ? hit : <String, dynamic>{}))
                    .toList() ??
                const [],
            isError: entry['is_error'] == true,
          ),
        );
      }
    }
    return result;
  }

  String _formatTimestamp(DateTime dateTime) {
    final y = dateTime.year.toString().padLeft(4, '0');
    final m = dateTime.month.toString().padLeft(2, '0');
    final d = dateTime.day.toString().padLeft(2, '0');
    return '$y-$m-$d ${_formatTime(dateTime)}';
  }

  String _sanitizeForFileName(String input) {
    return input.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
  }

  Widget _buildLogTab() {
    if (_logs.isEmpty) {
      return const Center(
          child: Text('No logs yet', style: TextStyle(color: subtitleColor)));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _logs.length,
      itemBuilder: (context, index) {
        final entry = _logs[_logs.length - 1 - index]; // Show latest first
        final timestamp = _formatTime(entry.timestamp);
        final color = entry.isError ? Colors.red.shade300 : subtitleColor;
        return Padding(
          padding: const EdgeInsets.only(bottom: 8.0),
          child: Text.rich(
            TextSpan(children: [
              TextSpan(
                text: '[$timestamp][${entry.tag}] ',
                style: TextStyle(fontSize: 11, color: color.withOpacity(0.7)),
              ),
              TextSpan(
                text: entry.message,
                style: TextStyle(color: color, fontSize: 12),
              ),
            ]),
          ),
        );
      },
    );
  }

  // --- Helpers & Other UI (Unchanged logic, styled) ---
  String _getEmotionEmoji(String emotion) {
    // ... Unchanged ...
    switch (emotion.toLowerCase()) {
      case 'joy':
        return '😀';
      case 'anger':
        return '🤬';
      case 'disgust':
        return '🤢';
      case 'fear':
        return '😨';
      case 'sadness':
        return '😭';
      case 'surprise':
        return '😲';
      case 'neutral':
      default:
        return '😐';
    }
  }

  Widget _buildEmotionIndicator(Map<String, dynamic> emotions) {
    // ... Unchanged ...
    final answerEmotion = emotions['answer_emotion'];
    if (answerEmotion == null) return const SizedBox.shrink();

    final dominantEmotion = answerEmotion['dominant_emotion'] ?? 'neutral';
    final confidence = answerEmotion['confidence'] ?? 0.0;

    return Tooltip(
      message:
          'Emotion: $dominantEmotion (${(confidence * 100).toStringAsFixed(1)}%)',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: Colors.blue.withOpacity(0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.blue.withOpacity(0.3)),
        ),
        child: Text(
          _getEmotionEmoji(dominantEmotion),
          style: const TextStyle(fontSize: 16),
        ),
      ),
    );
  }

  Widget _buildLineEmotionIndicator(Map<String, dynamic> emotion) {
    // ... Unchanged ...
    final dominantEmotion = emotion['emotion'] ?? 'neutral';
    final confidence = emotion['emotion_confidence'] ?? 0.0;

    return Tooltip(
      message:
          'Emotion: $dominantEmotion (${(confidence * 100).toStringAsFixed(1)}%)',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
        decoration: BoxDecoration(
          color: Colors.green.withOpacity(0.1),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.green.withOpacity(0.3)),
        ),
        child: Text(
          _getEmotionEmoji(dominantEmotion),
          style: const TextStyle(fontSize: 14),
        ),
      ),
    );
  }

  Widget _buildMessageBubble(ConversationMessage message) {
    final isUser = message.isUser;
    final color = isUser ? accentColor : Colors.green.shade300;

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      child: Row(
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            CircleAvatar(
              radius: 16,
              backgroundColor: cardColor,
              child: Icon(Icons.smart_toy, size: 16, color: color),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isUser ? accentColor.withOpacity(0.15) : cardColor,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                    color: isUser
                        ? accentColor.withOpacity(0.3)
                        : subtitleColor.withOpacity(0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          message.text,
                          style: TextStyle(
                              color: message.isError
                                  ? Colors.red.shade300
                                  : textColor),
                        ),
                      ),
                      if (message.emotions != null && !isUser) ...[
                        const SizedBox(width: 8),
                        _buildEmotionIndicator(message.emotions!),
                      ],
                    ],
                  ),
                  if (message.hits.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    const Text(
                      'Sources:',
                      style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                          color: subtitleColor),
                    ),
                    ...message.hits.take(5).map((hit) {
                      final preview = _formatHitPreview(hit);
                      return Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: GestureDetector(
                          onTap: () => _showMemoryHitDetails(
                              Map<String, dynamic>.from(hit)),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 8),
                            decoration: BoxDecoration(
                              color: primaryColor.withOpacity(0.5),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                  color: subtitleColor.withOpacity(0.2)),
                            ),
                            child: Row(
                              children: [
                                Icon(Icons.search,
                                    size: 14, color: accentColor),
                                const SizedBox(width: 6),
                                Expanded(
                                    child: Text(preview,
                                        style: const TextStyle(
                                            fontSize: 11,
                                            color: subtitleColor))),
                                Icon(Icons.open_in_new,
                                    size: 14,
                                    color: accentColor.withOpacity(0.7)),
                              ],
                            ),
                          ),
                        ),
                      );
                    }),
                  ],
                  const SizedBox(height: 4),
                  Text(
                    '${message.sessionId} • ${_formatTime(message.timestamp)}',
                    style: const TextStyle(fontSize: 10, color: subtitleColor),
                  ),
                ],
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 8),
            CircleAvatar(
              radius: 16,
              backgroundColor: cardColor,
              child: Icon(Icons.person, size: 16, color: color),
            ),
          ],
        ],
      ),
    );
  }

  String _formatTime(DateTime dateTime) {
    // ... Unchanged ...
    final h = dateTime.hour.toString().padLeft(2, '0');
    final m = dateTime.minute.toString().padLeft(2, '0');
    final s = dateTime.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  String _formatHitPreview(Map<String, dynamic> hit) {
    // ... Unchanged ...
    final primary = (hit['text'] ?? hit['body'] ?? hit['content'] ?? '')
        .toString()
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (primary.isNotEmpty) {
      return primary.length <= 90 ? primary : '${primary.substring(0, 90)}...';
    }

    final fallback = hit.entries
        .where((entry) =>
            entry.value != null && entry.value.toString().trim().isNotEmpty)
        .take(2)
        .map((entry) => '${entry.key}: ${entry.value}')
        .join(' • ');
    return fallback.isEmpty ? 'View memory details' : fallback;
  }

  void _showMemoryHitDetails(Map<String, dynamic> hit) {
    // ... Functionality is the same, only the UI inside the modal needs styling ...
    final details = Map<String, dynamic>.from(hit);
    final textCandidate = (details.remove('text') ??
            details.remove('body') ??
            details.remove('content') ??
            '')
        .toString();
    final normalizedText = textCandidate.trim();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: cardColor,
      builder: (sheetContext) {
        final entries = details.entries.toList()
          ..sort((a, b) => a.key.compareTo(b.key));
        return FractionallySizedBox(
          heightFactor: 0.75,
          child: SafeArea(
            child: Padding(
              padding: EdgeInsets.only(
                left: 20,
                right: 20,
                top: 16,
                bottom: MediaQuery.of(sheetContext).viewInsets.bottom + 20,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: subtitleColor.withOpacity(0.5),
                        borderRadius: BorderRadius.circular(30),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Memory reference',
                    style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        color: textColor),
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: SingleChildScrollView(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (normalizedText.isNotEmpty) ...[
                            const Text('Excerpt',
                                style: TextStyle(
                                    fontWeight: FontWeight.w600,
                                    color: accentColor)),
                            const SizedBox(height: 6),
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: primaryColor,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: SelectableText(normalizedText,
                                  style: const TextStyle(color: textColor)),
                            ),
                            const SizedBox(height: 16),
                          ],
                          if (entries.isNotEmpty) ...[
                            const Text('Metadata',
                                style: TextStyle(
                                    fontWeight: FontWeight.w600,
                                    color: accentColor)),
                            const SizedBox(height: 8),
                            ...entries.map(
                              (entry) => Padding(
                                padding: const EdgeInsets.only(bottom: 12),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      entry.key,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w600,
                                          fontSize: 12,
                                          color: subtitleColor),
                                    ),
                                    const SizedBox(height: 4),
                                    Container(
                                      width: double.infinity,
                                      padding: const EdgeInsets.all(10),
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(8),
                                        border: Border.all(
                                            color:
                                                subtitleColor.withOpacity(0.3)),
                                      ),
                                      child: SelectableText(
                                        _stringifyValue(entry.value),
                                        style: const TextStyle(
                                            fontSize: 12, color: textColor),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton.icon(
                      onPressed: () => Navigator.of(sheetContext).pop(),
                      icon: const Icon(Icons.close, color: subtitleColor),
                      label: const Text('Close',
                          style: TextStyle(color: subtitleColor)),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  String _stringifyValue(dynamic value) {
    // ... Unchanged ...
    if (value == null) return 'null';
    if (value is String) return value;
    if (value is num || value is bool) return value.toString();

    try {
      final encoder = JsonEncoder.withIndent('  ');
      return encoder.convert(value);
    } catch (_) {
      return value.toString();
    }
  }
}

// --- Data Models (Unchanged) ---
class ConversationMessage {
  // ... Unchanged ...
  final String text;
  final bool isUser;
  final DateTime timestamp;
  final String sessionId;
  final List<Map<String, dynamic>> hits;
  final bool isError;
  final Map<String, dynamic>? emotions;

  ConversationMessage({
    required this.text,
    required this.isUser,
    required this.timestamp,
    required this.sessionId,
    this.hits = const [],
    this.isError = false,
    this.emotions,
  });
}

class _Line {
  // ... Unchanged ...
  final String text;
  final String speaker;
  final bool isError;
  final Map<String, dynamic>? emotion;

  const _Line(this.text, this.speaker, {this.isError = false, this.emotion});
}

class TranscriptRecord {
  // ... Unchanged ...
  final String path;
  final String sessionId;
  final DateTime savedAt;
  final int messageCount;

  TranscriptRecord({
    required this.path,
    required this.sessionId,
    required this.savedAt,
    required this.messageCount,
  });
}

// --- Empty State Widgets (Styled) ---
class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: const [
          Icon(Icons.graphic_eq, size: 64, color: Colors.grey),
          SizedBox(height: 16),
          Text(
            'No transcripts yet',
            style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: _MemoryServerPageState.textColor),
          ),
          SizedBox(height: 12),
          Text(
            'Tap Start to begin streaming audio to the server.',
            textAlign: TextAlign.center,
            style: TextStyle(color: _MemoryServerPageState.subtitleColor),
          ),
        ],
      ),
    );
  }
}

class _ConversationEmptyState extends StatelessWidget {
  const _ConversationEmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: const [
          Icon(Icons.chat_bubble_outline, size: 64, color: Colors.grey),
          SizedBox(height: 16),
          Text(
            'No conversation yet',
            style: TextStyle(
                fontSize: 18, color: _MemoryServerPageState.subtitleColor),
          ),
          SizedBox(height: 8),
          Text(
            'Ask a question to start chatting with your memory assistant.',
            textAlign: TextAlign.center,
            style: TextStyle(color: _MemoryServerPageState.subtitleColor),
          ),
        ],
      ),
    );
  }
}
