import 'dart:convert';
import 'dart:developer';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:http/http.dart' as http;
import '../config.dart';

class NotificationService {
  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static String? _token;

  static String? get token => _token;

  static Future<void> init() async {
    try {
      await Firebase.initializeApp();

      // Request permission
      final settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );

      if (settings.authorizationStatus == AuthorizationStatus.authorized) {
        _token = await _messaging.getToken();
        if (_token != null) {
          await _saveToken(_token!);
          await _registerTokenWithBackend(_token!);
        }

        // Listen for token refresh
        _messaging.onTokenRefresh.listen((token) {
          _saveToken(token);
          _registerTokenWithBackend(token);
        });

        // Foreground messages
        FirebaseMessaging.onMessage.listen(_onForegroundMessage);
      }
    } catch (e) {
      log('NotificationService init failed: $e');
    }
  }

  static Future<void> _saveToken(String token) async {
    _token = token;
    final box = Hive.box('settings');
    await box.put('fcm_token', token);
  }

  static Future<void> _registerTokenWithBackend(String token) async {
    try {
      await http.post(
        Uri.parse('${AppConfig.apiBaseUrl}/notifications/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'fcm_token': token,
          'chat_id': 0,
          'device_info': 'flutter_mobile',
        }),
      );
    } catch (e) {
      log('Failed to register FCM token with backend: $e');
    }
  }

  static void _onForegroundMessage(RemoteMessage message) {
    log('Foreground message: ${message.notification?.title}');
    // Could show a local notification or snackbar here
  }

  static Future<bool> hasPermission() async {
    try {
      final settings = await _messaging.getNotificationSettings();
      return settings.authorizationStatus == AuthorizationStatus.authorized;
    } catch (e) {
      return false;
    }
  }

  static Future<void> requestPermission() async {
    await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );
  }
}

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  // Handle background message
}
