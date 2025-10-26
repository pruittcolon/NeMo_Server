import 'package:demo_ai_even/ble_manager.dart';
import 'package:demo_ai_even/controllers/evenai_model_controller.dart';
import 'package:demo_ai_even/views/home_page.dart';
import 'package:demo_ai_even/views/login_page.dart';
import 'package:demo_ai_even/services/auth_service.dart';
import 'package:flutter/material.dart';
import 'package:get/get.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Load environment variables
  try {
    await dotenv.load(fileName: ".env");
    print("✅ [DEBUG] .env loaded successfully");
  } catch (e) {
    print("❌ [ERROR] Failed to load .env: $e");
  }
  
  // Initialize services
  BleManager.get();
  Get.put(EvenaiModelController());
  AuthService.instance.initialize();
  
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Vox Augmented',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        brightness: Brightness.dark,
      ),
      // Start with LoginPage instead of HomePage
      home: LoginPage(), 
    );
  }
}
