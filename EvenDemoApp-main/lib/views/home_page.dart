import 'dart:async';

import 'package:flutter/material.dart';
import 'package:demo_ai_even/ble_manager.dart';
import 'package:demo_ai_even/services/evenai.dart';
import 'package:demo_ai_even/services/features_services.dart';
// Note: Assuming `SectionHeader` is a simple text widget.
// If it's more complex, its styling might need to be adjusted separately.
import 'package:demo_ai_even/ui/components/components.dart';
import 'package:demo_ai_even/views/even_list_page.dart';
import 'package:demo_ai_even/views/features_page.dart';
import 'package:get/get.dart';
import 'features/notification/vocabulary_game_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  Timer? scanTimer;
  bool isScanning = false;

  // --- Theme Colors (to match other pages) ---
  static const Color primaryColor = Color(0xFF0D1B2A);
  static const Color cardColor = Color(0xFF1B263B);
  static const Color accentColor = Color(0xFF33A1F2);
  static const Color textColor = Colors.white;
  static const Color subtitleColor = Colors.white70;

  @override
  void initState() {
    super.initState();
    print("🔧 [DEBUG] HomePage initState - setting up BLE");
    BleManager.get().setMethodCallHandler();
    BleManager.get().startListening();
    BleManager.get().onStatusChanged = _refreshPage;
    print("🔧 [DEBUG] HomePage initState - BLE setup complete");
  }

  void _refreshPage() {
    print("🔧 [DEBUG] _refreshPage called - connection status: ${BleManager.get().getConnectionStatus()}");
    setState(() {});
  }

  Future<void> _startScan() async {
    print("🔧 [DEBUG] _startScan called");
    setState(() => isScanning = true);
    await BleManager.get().startScan();
    scanTimer?.cancel();
    scanTimer = Timer(const Duration(seconds: 15), () {
      print("🔧 [DEBUG] Scan timer expired, stopping scan");
      _stopScan();
    });
    print("🔧 [DEBUG] Scan started, timer set for 15 seconds");
  }

  Future<void> _stopScan() async {
    if (isScanning) {
      print("🔧 [DEBUG] _stopScan called");
      await BleManager.get().stopScan();
      setState(() => isScanning = false);
      print("🔧 [DEBUG] Scan stopped");
    }
  }

  @override
  void dispose() {
    scanTimer?.cancel();
    isScanning = false;
    BleManager.get().onStatusChanged = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: primaryColor,
      appBar: AppBar(
        title: const Text('Vox Augmented',
            style: TextStyle(fontWeight: FontWeight.bold, color: textColor)),
        backgroundColor: primaryColor,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.menu_rounded, color: textColor),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const FeaturesPage()),
              );
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Assuming SectionHeader is compatible with the new theme
// --- ADD THIS IN ITS PLACE ---
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Glasses Connection',
                    style: TextStyle(
                      color: textColor,
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'Pair and monitor your Even glasses in real time.',
                    style: TextStyle(
                      color: subtitleColor,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _ConnectionCard(
                status: BleManager.get().getConnectionStatus(),
                isScanning: isScanning,
                onTap: () {
                  print("🔧 [DEBUG] Connection card tapped - status: ${BleManager.get().getConnectionStatus()}");
                  if (BleManager.get().getConnectionStatus() ==
                      'Not connected') {
                    print("🔧 [DEBUG] Starting scan from connection card tap");
                    _startScan();
                  } else {
                    print("🔧 [DEBUG] Already connected, not starting scan");
                  }
                },
              ),
              const SizedBox(height: 24),
              _StyledFeatureCard(
                icon: Icons.spellcheck,
                title: 'Vocabulary Builder',
                subtitle: 'Challenge your vocabulary with this fun game.',
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (context) => const NotificationPage()),
                  );
                },
              ),
              const SizedBox(height: 12),
              _StyledFeatureCard(
                icon: Icons.camera_alt,
                title: 'Vision Exam Mode',
                subtitle: 'Take photos of exam questions and get instant answers.',
                highlight: true,
                onTap: () async {
                  print("🎯 [DEBUG] Vision Exam Mode button pressed");
                  // Directly start vision mode
                  await EvenAI.get.startVisionMode();
                },
              ),
              Expanded(
                  child: BleManager.get().isConnected
                      ? _ActiveSessionView(
                          onOpenHistory: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (context) => const EvenAIListPage(),
                              ),
                            );
                          },
                        )
                      : _PairedGlassesList(
                          onConnect: (glasses) async {
                            final channel = glasses['channelNumber']!;
                            await BleManager.get()
                                .connectToGlasses('Pair_$channel');
                            _refreshPage();
                          },
                        ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// --- Re-styled Main Widgets ---

class _ConnectionCard extends StatefulWidget {
  const _ConnectionCard({
    required this.status,
    required this.isScanning,
    required this.onTap,
  });

  final String status;
  final bool isScanning;
  final VoidCallback onTap;

  @override
  State<_ConnectionCard> createState() => _ConnectionCardState();
}

class _ConnectionCardState extends State<_ConnectionCard>
    with TickerProviderStateMixin {
  late final AnimationController _rotationController;
  late final AnimationController _pulseController;
  late final Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _rotationController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 1200),
      vsync: this,
    );
    _pulseAnimation = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _pulseController.addStatusListener((status) {
      if (status == AnimationStatus.completed) {
        _pulseController.reverse();
      } else if (status == AnimationStatus.dismissed) {
        _pulseController.forward();
      }
    });
  }

  @override
  void didUpdateWidget(covariant _ConnectionCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    final isConnectingOrScanning =
        widget.isScanning || widget.status.toLowerCase().contains('connecting');
    if (isConnectingOrScanning) {
      if (!_rotationController.isAnimating) _rotationController.repeat();
      if (!_pulseController.isAnimating) _pulseController.forward();
    } else {
      _rotationController.stop();
      _pulseController.stop();
    }
  }

  @override
  void dispose() {
    _rotationController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final statusLower = widget.status.toLowerCase();
    final isConnected = statusLower.startsWith('connected');
    final isConnecting = statusLower.contains('connecting');
    final isActionable = widget.isScanning || isConnecting;

    String label;
    IconData icon;
    Color chipColor;

    if (widget.isScanning) {
      label = 'Scanning...';
      icon = Icons.sync_rounded;
      chipColor = Colors.blue.shade300;
    } else if (isConnecting) {
      label = 'Connecting...';
      icon = Icons.autorenew_rounded;
      chipColor = Colors.blue.shade300;
    } else if (isConnected) {
      label = 'Connected';
      icon = Icons.check_circle_rounded;
      chipColor = Colors.green.shade400;
    } else {
      label = 'Tap to pair';
      icon = Icons.bluetooth_disabled_rounded;
      chipColor = Colors.orange.shade400;
    }

    return _StyledFeatureCard(
      icon: Icons.bluetooth_searching_rounded,
      title: widget.status,
      subtitle: 'Tap to scan and pair nearby Even glasses.',
      highlight: isConnected,
      onTap: isActionable ? null : widget.onTap,
      trailing: AnimatedBuilder(
          animation: _pulseAnimation,
          builder: (context, child) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: chipColor.withOpacity(0.2),
                borderRadius: BorderRadius.circular(30),
                border: Border.all(color: chipColor.withOpacity(0.5)),
                boxShadow: isActionable
                    ? [
                        BoxShadow(
                          color: _HomePageState.accentColor
                              .withOpacity(_pulseAnimation.value * 0.5),
                          blurRadius: 8.0,
                          spreadRadius: _pulseAnimation.value * 2,
                        ),
                      ]
                    : [],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  RotationTransition(
                    turns: _rotationController,
                    child: Icon(icon, size: 16, color: chipColor),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    label,
                    style: TextStyle(
                        color: chipColor,
                        fontWeight: FontWeight.bold,
                        fontSize: 12),
                  ),
                ],
              ),
            );
          }),
    );
  }
}

class _PairedGlassesList extends StatelessWidget {
  const _PairedGlassesList({required this.onConnect});

  final void Function(Map<String, String> glasses) onConnect;

  @override
  Widget build(BuildContext context) {
    final paired = BleManager.get().getPairedGlasses();
    if (paired.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8.0),
          child: Card(
            color: _HomePageState.cardColor,
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
              side: BorderSide(
                  color: _HomePageState.subtitleColor.withOpacity(0.2)),
            ),
            child: Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.bluetooth_disabled_rounded,
                    size: 40,
                    color: _HomePageState.accentColor,
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'No Paired Glasses Discovered',
                    style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: _HomePageState.textColor),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Enable Bluetooth and power on both lenses. They will appear here once found.',
                    style: TextStyle(
                        color: _HomePageState.subtitleColor, fontSize: 13),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.only(bottom: 12),
      itemCount: paired.length,
      separatorBuilder: (_, __) => const SizedBox(height: 12),
      itemBuilder: (context, index) {
        final glasses = paired[index];
        final title = 'Pair ${glasses['channelNumber']}';
        final subtitle =
            'Left: ${glasses['leftDeviceName']}\nRight: ${glasses['rightDeviceName']}';
        return _StyledFeatureCard(
          icon: Icons.devices_other_rounded,
          title: title,
          subtitle: subtitle,
          onTap: () => onConnect(glasses),
        );
      },
    );
  }
}

class _ActiveSessionView extends StatelessWidget {
  const _ActiveSessionView({required this.onOpenHistory});

  final VoidCallback onOpenHistory;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _StyledFeatureCard(
          icon: Icons.history_rounded,
          title: 'Even AI Session History',
          subtitle: 'Tap to review conversation history and synced output.',
          onTap: onOpenHistory,
          highlight: true,
          trailing: OutlinedButton(
            onPressed: () async {
              await FeaturesServices().exitBmp();
              EvenAI.isRunning = false;
              EvenAI.get.clear();
              EvenAI.updateDynamicText('');
            },
            style: OutlinedButton.styleFrom(
              foregroundColor: _HomePageState.subtitleColor,
              side: BorderSide(
                  color: _HomePageState.subtitleColor.withOpacity(0.5)),
              padding: const EdgeInsets.symmetric(horizontal: 16),
            ),
            child: const Text('Clear'),
          ),
        ),
        const SizedBox(height: 16),
        Expanded(
          child: InkWell(
            borderRadius: BorderRadius.circular(20),
            onTap: onOpenHistory,
            child: Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: _HomePageState.cardColor,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(
                    color: _HomePageState.subtitleColor.withOpacity(0.2)),
              ),
              child: StreamBuilder<String>(
                stream: EvenAI.textStream,
                initialData:
                    'Press and hold the left touch bar to engage Even AI.',
                builder: (context, snapshot) {
                  return Obx(
                    () => EvenAI.isEvenAISyncing.value
                        ? const Center(
                            child: SizedBox(
                              width: 50,
                              height: 50,
                              child: CircularProgressIndicator(
                                  color: _HomePageState.accentColor),
                            ),
                          )
                        : Center(
                            child: SingleChildScrollView(
                              child: Text(
                                snapshot.data ?? "Loading...",
                                style: TextStyle(
                                  fontSize: 14,
                                  color: BleManager.get().isConnected
                                      ? _HomePageState.textColor
                                      : Colors.grey.withOpacity(0.5),
                                ),
                                textAlign: TextAlign.center,
                              ),
                            ),
                          ),
                  );
                },
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// --- Re-styled Helper Widget ---

/// A reusable, styled card to ensure a consistent UI.
class _StyledFeatureCard extends StatelessWidget {
  const _StyledFeatureCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.onTap,
    this.trailing,
    this.highlight = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;
  final Widget? trailing;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: _HomePageState.cardColor,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 4),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: highlight
              ? _HomePageState.accentColor.withOpacity(0.7)
              : _HomePageState.subtitleColor.withOpacity(0.2),
          width: highlight ? 1.5 : 1.0,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12.0),
          child: Row(
            children: [
              Icon(icon, color: _HomePageState.accentColor, size: 28),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: _HomePageState.textColor,
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          color: _HomePageState.subtitleColor, fontSize: 13),
                    ),
                  ],
                ),
              ),
              if (trailing != null) ...[
                const SizedBox(width: 12),
                trailing!,
              ] else if (onTap != null) ...[
                const SizedBox(width: 12),
                const Icon(Icons.arrow_forward_ios,
                    color: Colors.white30, size: 16),
              ]
            ],
          ),
        ),
      ),
    );
  }
}
