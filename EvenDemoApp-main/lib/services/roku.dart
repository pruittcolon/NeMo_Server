import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class RokuRemote {
  // --- Configuration ---
  final String _baseUrl = dotenv.env['ROKU_BASE_URL'] ?? '';

  late final Dio _dio;

  // --- Constructor ---
  RokuRemote() {
    if (_baseUrl.isEmpty) {
      print(
          "ERROR: ROKU_BASE_URL is not set in .env file. Roku remote will not work.");
    }
    _dio = Dio(BaseOptions(baseUrl: _baseUrl));
  }

  // --- Private Helper Method ---
  /// Sends a keypress command to the Roku TV.
  Future<bool> _sendKeypress(String key) async {
    try {
      final response = await _dio.post('/keypress/$key');
      if (response.statusCode == 200) {
        print('Roku command "$key" sent successfully.');
        return true;
      } else {
        print(
            'Failed to send Roku command "$key". Status: ${response.statusCode}');
        return false;
      }
    } catch (e) {
      print('Error sending Roku command "$key": $e');
      return false;
    }
  }

  // --- Public Control Methods ---

  Future<void> powerOn() async => await _sendKeypress('PowerOn');
  Future<void> powerOff() async => await _sendKeypress('PowerOff');
  Future<void> up() async => await _sendKeypress('Up');
  Future<void> down() async => await _sendKeypress('Down');
  Future<void> left() async => await _sendKeypress('Left');
  Future<void> right() async => await _sendKeypress('Right');
  Future<void> select() async => await _sendKeypress('Select');
  Future<void> home() async => await _sendKeypress('Home');
  Future<void> back() async => await _sendKeypress('Back');

  // Volume controls (supported on Roku TV devices)
  Future<void> volumeUp() async => await _sendKeypress('VolumeUp');
  Future<void> volumeDown() async => await _sendKeypress('VolumeDown');
}
