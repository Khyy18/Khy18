import 'package:local_auth/local_auth.dart';
import 'package:flutter/services.dart';

class BiometricService {
  final LocalAuthentication _auth = LocalAuthentication();

  Future<bool> checkAvailability() async {
    try {
      final canCheck = await _auth.canCheckBiometrics;
      final isDeviceSupported = await _auth.isDeviceSupported();
      return canCheck || isDeviceSupported;
    } on PlatformException {
      return false;
    }
  }

  Future<bool> authenticate() async {
    try {
      final isAvailable = await checkAvailability();
      if (!isAvailable) return false;

      return await _auth.authenticate(
        localizedReason: 'Подтвердите вашу личность',
        options: const AuthenticationOptions(
          stickyAuth: true,
          biometricOnly: false,
        ),
      );
    } on PlatformException {
      return false;
    }
  }

  Future<bool> get isSupported async {
    try {
      return await _auth.isDeviceSupported();
    } on PlatformException {
      return false;
    }
  }
}
