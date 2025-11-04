import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:demo_ai_even/services/app_logger.dart';

/// Authentication Service for WhisperServer backend
class AuthService {
  static final AuthService _instance = AuthService._();
  static AuthService get instance => _instance;

  AuthService._();

  late Dio _dio;
  String _serverBase = '';
  String? _sessionToken;
  Map<String, dynamic>? _currentUser;
  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage();
  static const String _sessionTokenKey = 'session_token';
  static const String _userDataKey = 'user_data';
  static const String _csrfTokenKey = 'csrf_token';
  AndroidOptions _androidOptions() => const AndroidOptions(encryptedSharedPreferences: true);
  IOSOptions _iosOptions() => const IOSOptions(accessibility: KeychainAccessibility.first_unlock);
  
  final StreamController<bool> _authStateController = StreamController<bool>.broadcast();
  Stream<bool> get authStateStream => _authStateController.stream;
  
  bool get isAuthenticated => _sessionToken != null && _currentUser != null;
  Map<String, dynamic>? get currentUser => _currentUser;
  String? get sessionToken => _sessionToken;

  void initialize() {
    _serverBase = dotenv.env['WHISPER_SERVER_BASE']?.trim() ?? 'http://127.0.0.1:8000';
    
    _dio = Dio(
      BaseOptions(
        baseUrl: _serverBase,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 30),
        sendTimeout: const Duration(seconds: 30),
      ),
    );
    
    AppLogger.instance.log('AuthService', 'Initialized with base $_serverBase');
  }

  /// Login with username and password
  Future<LoginResult> login(String username, String password) async {
    AppLogger.instance.log('AuthService', 'Attempting login for user: $username');
    
    try {
      final response = await _dio.post(
        '/api/auth/login',
        data: {
          'username': username,
          'password': password,
        },
      );

      if (response.statusCode == 200) {
        final data = response.data;
        
        if (data['success'] == true) {
          _sessionToken = data['session_token'];
          _currentUser = data['user'];
          
          // Extract CSRF token from Set-Cookie header
          String? csrfToken;
          try {
            final cookies = response.headers['set-cookie'];
            if (cookies != null) {
              for (final cookie in cookies) {
                if (cookie.startsWith('csrf_token=')) {
                  final parts = cookie.split(';')[0].split('=');
                  if (parts.length == 2) {
                    csrfToken = parts[1];
                    AppLogger.instance.log('AuthService', 'CSRF token extracted from cookie');
                    break;
                  }
                }
              }
            }
          } catch (e) {
            AppLogger.instance.log('AuthService', 'Failed to extract CSRF token: $e', isError: true);
          }
          
          // Persist session token and CSRF token
          await _saveSession(csrfToken: csrfToken);
          
          _authStateController.add(true);
          
          AppLogger.instance.log('AuthService', 'Login successful: ${_currentUser?['username']}');
          
          return LoginResult(
            success: true,
            message: data['message'] ?? 'Login successful',
            user: _currentUser,
          );
        } else {
          return LoginResult(
            success: false,
            message: data['message'] ?? 'Login failed',
          );
        }
      } else {
        return LoginResult(
          success: false,
          message: 'Server error: ${response.statusCode}',
        );
      }
    } on DioException catch (e) {
      AppLogger.instance.log('AuthService', 'Login error: $e', isError: true);
      
      String errorMessage = 'Network error';
      if (e.response?.statusCode == 401) {
        errorMessage = 'Invalid username or password';
      } else if (e.response?.statusCode == 429) {
        errorMessage = 'Too many attempts. Please try again later.';
      } else if (e.type == DioExceptionType.connectionTimeout) {
        errorMessage = 'Connection timeout';
      } else if (e.type == DioExceptionType.connectionError) {
        errorMessage = 'Cannot connect to server';
      }
      
      return LoginResult(
        success: false,
        message: errorMessage,
      );
    } catch (e) {
      AppLogger.instance.log('AuthService', 'Unexpected login error: $e', isError: true);
      return LoginResult(
        success: false,
        message: 'Unexpected error: $e',
      );
    }
  }

  /// Check if current session is valid
  Future<bool> checkSession() async {
    if (_sessionToken == null) {
      // Try to load from storage
      await _loadSession();
      if (_sessionToken == null) {
        return false;
      }
    }

    AppLogger.instance.log('AuthService', 'Checking session validity');
    
    try {
      final response = await _dio.get(
        '/api/auth/check',
        options: Options(
          headers: {
            'Cookie': 'ws_session=$_sessionToken',
          },
        ),
      );

      if (response.statusCode == 200) {
        final data = response.data;
        
        if (data['valid'] == true) {
          _currentUser = data['user'];
          _authStateController.add(true);
          AppLogger.instance.log('AuthService', 'Session valid');
          return true;
        } else {
          await logout();
          return false;
        }
      } else {
        await logout();
        return false;
      }
    } catch (e) {
      AppLogger.instance.log('AuthService', 'Session check failed: $e', isError: true);
      await logout();
      return false;
    }
  }

  /// Logout and clear session
  Future<void> logout() async {
    AppLogger.instance.log('AuthService', 'Logging out');
    
    if (_sessionToken != null) {
      try {
        await _dio.post(
          '/api/auth/logout',
          options: Options(
            headers: {
              'Cookie': 'ws_session=$_sessionToken',
            },
          ),
        );
      } catch (e) {
        AppLogger.instance.log('AuthService', 'Logout API call failed: $e', isError: true);
      }
    }
    
    _sessionToken = null;
    _currentUser = null;
    await _clearSession();
    _authStateController.add(false);
  }

  /// Save session to persistent storage
  Future<void> _saveSession({String? csrfToken}) async {
    if (_sessionToken != null && _currentUser != null) {
      await _secureStorage.write(
        key: _sessionTokenKey,
        value: _sessionToken!,
        aOptions: _androidOptions(),
        iOptions: _iosOptions(),
      );
      await _secureStorage.write(
        key: _userDataKey,
        value: jsonEncode(_currentUser!),
        aOptions: _androidOptions(),
        iOptions: _iosOptions(),
      );
      if (csrfToken != null && csrfToken.isNotEmpty) {
        await _secureStorage.write(
          key: _csrfTokenKey,
          value: csrfToken,
          aOptions: _androidOptions(),
          iOptions: _iosOptions(),
        );
        AppLogger.instance.log('AuthService', 'Session and CSRF token stored securely');
      } else {
        await _secureStorage.delete(
          key: _csrfTokenKey,
          aOptions: _androidOptions(),
          iOptions: _iosOptions(),
        );
        AppLogger.instance.log('AuthService', 'Session stored securely (no CSRF token)');
      }
    }
  }

  /// Load session from persistent storage
  Future<void> _loadSession() async {
    _sessionToken = await _secureStorage.read(
      key: _sessionTokenKey,
      aOptions: _androidOptions(),
      iOptions: _iosOptions(),
    );
    final userData = await _secureStorage.read(
      key: _userDataKey,
      aOptions: _androidOptions(),
      iOptions: _iosOptions(),
    );

    if (userData != null) {
      try {
        _currentUser = jsonDecode(userData);
        AppLogger.instance.log('AuthService', 'Session loaded from secure storage');
      } catch (e) {
        AppLogger.instance.log('AuthService', 'Failed to parse user data: $e', isError: true);
        await _clearSession();
      }
    }
  }

  /// Clear session from persistent storage
  Future<void> _clearSession() async {
    await _secureStorage.delete(
      key: _sessionTokenKey,
      aOptions: _androidOptions(),
      iOptions: _iosOptions(),
    );
    await _secureStorage.delete(
      key: _userDataKey,
      aOptions: _androidOptions(),
      iOptions: _iosOptions(),
    );
    await _secureStorage.delete(
      key: _csrfTokenKey,
      aOptions: _androidOptions(),
      iOptions: _iosOptions(),
    );
    AppLogger.instance.log('AuthService', 'Session cleared from secure storage');
  }

  void dispose() {
    _authStateController.close();
  }
}

class LoginResult {
  final bool success;
  final String message;
  final Map<String, dynamic>? user;

  LoginResult({
    required this.success,
    required this.message,
    this.user,
  });
}
