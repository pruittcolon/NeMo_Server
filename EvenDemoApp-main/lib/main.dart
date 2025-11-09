import 'package:demo_ai_even/ble_manager.dart';
import 'package:demo_ai_even/controllers/evenai_model_controller.dart';
import 'package:demo_ai_even/views/home_page.dart';
import 'package:demo_ai_even/views/login_page.dart';
import 'package:demo_ai_even/views/vision_mode_page.dart';
import 'package:demo_ai_even/services/auth_service.dart';
import 'package:demo_ai_even/utils/vocabulary_initializer.dart';
import 'package:demo_ai_even/utils/app_logger.dart';
import 'package:flutter/material.dart';
import 'package:get/get.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

Future<void> main() async {
  // Start app initialization logging
  AppLogger.banner('EVEN DEMO APP STARTING');
  
  WidgetsFlutterBinding.ensureInitialized();
  AppLogger.info('Flutter binding initialized');
  
  // Load environment variables
  try {
    AppLogger.info('Loading environment variables from .env');
    await dotenv.load(fileName: ".env");
    AppLogger.success('.env loaded successfully');
    AppLogger.debug('Available env keys: ${dotenv.env.keys.toList()}');
  } catch (e) {
    AppLogger.error('Failed to load .env file', error: e);
  }
  
  // Initialize services
  AppLogger.separator('Initializing Services');
  
  try {
    AppLogger.info('Initializing BLE Manager');
    BleManager.get();
    AppLogger.success('BLE Manager initialized');
  } catch (e) {
    AppLogger.error('Failed to initialize BLE Manager', error: e);
  }
  
  try {
    AppLogger.info('Initializing EvenAI Model Controller');
    Get.put(EvenaiModelController());
    AppLogger.success('EvenAI Model Controller initialized');
  } catch (e) {
    AppLogger.error('Failed to initialize EvenAI Model Controller', error: e);
  }
  
  try {
    AppLogger.info('Initializing Auth Service');
    AuthService.instance.initialize();
    AppLogger.success('Auth Service initialized');
  } catch (e) {
    AppLogger.error('Failed to initialize Auth Service', error: e);
  }
  
  // Initialize vocabulary database
  try {
    AppLogger.info('Initializing Vocabulary Database');
    await VocabularyInitializer.initialize();
    AppLogger.success('Vocabulary Database initialized');
  } catch (e) {
    AppLogger.error('Failed to initialize Vocabulary Database', error: e);
  }
  
  AppLogger.separator();
  AppLogger.success('All services initialized - Starting app');
  
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return GetMaterialApp(
      title: 'Vox Augmented',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        brightness: Brightness.dark,
      ),
      debugShowCheckedModeBanner: false,
      // Start with LoginPage - user can authenticate or skip
      home: const LoginPage(),
      // Add named routes for navigation
      getPages: [
        GetPage(
          name: '/vision',
          page: () => const VisionModePage(),
        ),
      ],
    );
  }
}
