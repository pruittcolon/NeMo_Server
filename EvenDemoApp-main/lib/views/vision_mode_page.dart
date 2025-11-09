import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:get/get.dart';
import 'package:demo_ai_even/services/evenai.dart';
import 'package:demo_ai_even/utils/app_logger.dart';

class VisionModePage extends StatefulWidget {
  const VisionModePage({Key? key}) : super(key: key);

  @override
  State<VisionModePage> createState() => _VisionModePageState();
}

class _VisionModePageState extends State<VisionModePage> {
  CameraController? _cameraController;
  bool _isCapturing = false;
  bool _isCameraReady = false;
  String _lastResponse = '';
  
  // Zoom state
  double _minZoom = 1.0;
  double _maxZoom = 1.0;
  double _currentZoom = 1.0;
  static const double _targetZoom = 2.1; // requested zoom level
  
  // Auto-capture timer
  Timer? _autoCaptureTimer;
  Timer? _countdownTimer;
  int _secondsUntilNextCapture = 20;
  int _totalCaptureCount = 0;
  static const int _captureInterval = 20; // seconds

  @override
  void initState() {
    super.initState();
    AppLogger.separator('VISION MODE PAGE INITIALIZED');
    _initCamera();
    _startAutoCaptureTimer();
  }

  Future<void> _initCamera() async {
    try {
      AppLogger.camera('Initializing camera for vision mode page');
      final cameras = await availableCameras();

      if (cameras.isEmpty) {
        AppLogger.error('No cameras available');
        return;
      }

      // Find rear camera (back camera)
      CameraDescription? rearCamera;
      for (final camera in cameras) {
        if (camera.lensDirection == CameraLensDirection.back) {
          rearCamera = camera;
          break;
        }
      }

      rearCamera ??= cameras.first;
      AppLogger.camera('Selected camera: ${rearCamera.name}');

      _cameraController = CameraController(
        rearCamera,
        ResolutionPreset.medium,
        enableAudio: false,
      );

      await _cameraController!.initialize();
      
      // Turn OFF flash/torch
      AppLogger.camera('Setting flash mode to OFF');
      await _cameraController!.setFlashMode(FlashMode.off);
      AppLogger.success('Flash disabled');
      
      // Configure zoom levels
      try {
        _minZoom = await _cameraController!.getMinZoomLevel();
        _maxZoom = await _cameraController!.getMaxZoomLevel();
        AppLogger.camera('Zoom capabilities -> min: ' + _minZoom.toStringAsFixed(2) + ', max: ' + _maxZoom.toStringAsFixed(2));
        
        // Clamp requested zoom to supported range
        final num clamped = _targetZoom.clamp(_minZoom, _maxZoom);
        final double desiredZoom = clamped.toDouble();
        if (desiredZoom != _targetZoom) {
          AppLogger.warning('Requested zoom $_targetZoom clamped to ${desiredZoom.toStringAsFixed(2)}x');
        } else {
          AppLogger.info('Applying requested zoom ${desiredZoom.toStringAsFixed(2)}x');
        }
        await _cameraController!.setZoomLevel(desiredZoom);
        _currentZoom = desiredZoom;
        AppLogger.success('Zoom set to ${_currentZoom.toStringAsFixed(2)}x');
      } catch (e, st) {
        AppLogger.error('Failed to configure zoom', error: e, stackTrace: st);
      }
      
      if (mounted) {
        setState(() {
          _isCameraReady = true;
        });
        AppLogger.success('Camera initialized and ready');
      }
    } catch (e) {
      AppLogger.error('Failed to initialize camera', error: e);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Camera error: ${e.toString()}')),
        );
      }
    }
  }

  void _startAutoCaptureTimer() {
    AppLogger.timer('Auto-Capture Timer', 'Starting ($_captureInterval second interval)');
    
    // Reset countdown
    _secondsUntilNextCapture = _captureInterval;
    
    // Countdown timer (updates every second)
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() {
          _secondsUntilNextCapture--;
          if (_secondsUntilNextCapture < 0) {
            _secondsUntilNextCapture = _captureInterval;
          }
        });
      }
    });
    
    // Auto-capture timer
    _autoCaptureTimer = Timer.periodic(Duration(seconds: _captureInterval), (timer) {
      if (_isCameraReady && !_isCapturing) {
        AppLogger.banner('AUTO-CAPTURE TRIGGERED');
        AppLogger.info('Capture #${_totalCaptureCount + 1} - Auto-triggered after $_captureInterval seconds');
        _captureAndSend(isAutoCapture: true);
      } else {
        AppLogger.warning('Skipping auto-capture - Camera ready: $_isCameraReady, Already capturing: $_isCapturing');
      }
    });
  }

  Future<void> _captureAndSend({bool isAutoCapture = false}) async {
    if (_cameraController == null || !_cameraController!.value.isInitialized) {
      AppLogger.error('Camera not ready for capture');
      return;
    }

    if (_isCapturing) {
      AppLogger.warning('Capture already in progress, ignoring request');
      return;
    }

    _totalCaptureCount++;
    
    setState(() {
      _isCapturing = true;
      _lastResponse = '📸 Processing image...';
      _secondsUntilNextCapture = _captureInterval; // Reset countdown
    });

    final captureStartTime = DateTime.now();
    AppLogger.separator('IMAGE CAPTURE #$_totalCaptureCount');
    AppLogger.camera('${isAutoCapture ? "🤖 AUTO" : "👆 MANUAL"} Capture initiated');
    AppLogger.info('Timestamp: ${captureStartTime.toIso8601String()}');
  AppLogger.camera('Current zoom ${_currentZoom.toStringAsFixed(2)}x (range ${_minZoom.toStringAsFixed(2)}-${_maxZoom.toStringAsFixed(2)}x)');

    try {
      // Trigger the capture through EvenAI service, passing our camera controller
      AppLogger.camera('Calling EvenAI.captureAndAnalyzeImage() with camera controller...');
      final response = await EvenAI.get.captureAndAnalyzeImage(_cameraController!);
      
      final captureDuration = DateTime.now().difference(captureStartTime);
      AppLogger.success('✅ Image captured and analyzed in ${captureDuration.inMilliseconds}ms');
      AppLogger.info('Response length: ${response.length} characters');
      
      if (mounted) {
        setState(() {
          _lastResponse = response;
          _isCapturing = false;
        });
      }
      
      AppLogger.info('Next capture in $_captureInterval seconds');
      AppLogger.separator();
      
    } catch (e, stackTrace) {
      final captureDuration = DateTime.now().difference(captureStartTime);
      AppLogger.error('❌ Capture failed after ${captureDuration.inMilliseconds}ms', error: e, stackTrace: stackTrace);
      
      if (mounted) {
        setState(() {
          _lastResponse = 'Error: ${e.toString()}';
          _isCapturing = false;
        });
      }
    }
  }

  @override
  void dispose() {
    AppLogger.separator('VISION MODE PAGE DISPOSAL');
    AppLogger.info('Total captures completed: $_totalCaptureCount');
    
    AppLogger.timer('Auto-Capture Timer', 'Cancelling');
    _autoCaptureTimer?.cancel();
    
    AppLogger.timer('Countdown Timer', 'Cancelling');
    _countdownTimer?.cancel();
    
    AppLogger.camera('Disposing vision mode camera');
    _cameraController?.dispose();
    
    AppLogger.separator();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('Vision Mode'),
        backgroundColor: Colors.black87,
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () {
            AppLogger.info('Exiting vision mode via close button');
            Get.back();
          },
        ),
      ),
      body: Column(
        children: [
          // Camera Preview
          Expanded(
            flex: 3,
            child: Container(
              color: Colors.black,
              child: _isCameraReady && _cameraController != null
                  ? CameraPreview(_cameraController!)
                  : const Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          CircularProgressIndicator(color: Colors.white),
                          SizedBox(height: 20),
                          Text(
                            'Initializing camera...',
                            style: TextStyle(color: Colors.white),
                          ),
                        ],
                      ),
                    ),
            ),
          ),

          // Status Bar with Countdown
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 20),
            color: Colors.blue[900],
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Icon(
                      _isCapturing ? Icons.camera : Icons.timer,
                      color: Colors.white,
                      size: 20,
                    ),
                    const SizedBox(width: 10),
                    Text(
                      _isCapturing
                          ? '📸 Capturing...'
                          : '⏱️ Next in ${_secondsUntilNextCapture}s',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.blue[700],
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    'Total: $_totalCaptureCount',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Response Area
          Expanded(
            flex: 2,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.grey[900]!, Colors.grey[850]!],
                ),
              ),
              child: Column(
                children: [
                  const Text(
                    'AI Response',
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 15),
                  Expanded(
                    child: SingleChildScrollView(
                      child: Text(
                        _lastResponse.isEmpty
                            ? 'Auto-capture every 20 seconds.\nPress button for manual capture.'
                            : _lastResponse,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          height: 1.4,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Capture Button
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            color: Colors.black,
            child: Column(
              children: [
                ElevatedButton(
                  onPressed: _isCameraReady && !_isCapturing
                      ? () => _captureAndSend(isAutoCapture: false)
                      : null,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blue[600],
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 50,
                      vertical: 20,
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(30),
                    ),
                    elevation: 5,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (_isCapturing)
                        const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      else
                        const Icon(Icons.camera_alt, size: 28),
                      const SizedBox(width: 12),
                      Text(
                        _isCapturing ? 'Processing...' : 'Manual Capture',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  'Auto-capture every 20s • Say "terminate" to exit',
                  style: TextStyle(
                    color: Colors.white54,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
