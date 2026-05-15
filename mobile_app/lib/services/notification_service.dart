import 'dart:developer';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:hive_flutter/hive_flutter.dart';

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
        }

        // Listen for token refresh
        _messaging.onTokenRefresh.listen(_saveToken);

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
