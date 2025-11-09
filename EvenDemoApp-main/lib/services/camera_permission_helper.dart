import 'package:permission_handler/permission_handler.dart';

/// Helper class to manage camera permissions for Vision Mode
class CameraPermissionHelper {
  /// Request camera permission from the user
  /// Returns true if permission is granted
  static Future<bool> requestCameraPermission() async {
    final status = await Permission.camera.request();
    
    if (status.isGranted) {
      print("Camera permission granted");
      return true;
    } else if (status.isDenied) {
      print("Camera permission denied");
      return false;
    } else if (status.isPermanentlyDenied) {
      print("Camera permission permanently denied. Opening app settings...");
      await openAppSettings();
      return false;
    }
    
    return false;
  }
  
  /// Check if camera permission is already granted
  static Future<bool> hasPermission() async {
    final status = await Permission.camera.status;
    return status.isGranted;
  }
}
