import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorageService {
  static const _pinKey = 'app_pin';
  static const _lockEnabledKey = 'lock_enabled';
  static const _lastAuthTimeKey = 'last_auth_time';

  final FlutterSecureStorage _storage;

  SecureStorageService()
      : _storage = const FlutterSecureStorage(
          aOptions: AndroidOptions(encryptedSharedPreferences: true),
          iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
        );

  Future<void> savePin(String pin) async {
    await _storage.write(key: _pinKey, value: pin);
  }

  Future<String?> getPin() async {
    return await _storage.read(key: _pinKey);
  }

  Future<void> saveLockEnabled(bool enabled) async {
    await _storage.write(key: _lockEnabledKey, value: enabled.toString());
  }

  Future<bool> isLockEnabled() async {
    final value = await _storage.read(key: _lockEnabledKey);
    return value == 'true';
  }

  Future<void> saveLastAuthTime(DateTime time) async {
    await _storage.write(
      key: _lastAuthTimeKey,
      value: time.millisecondsSinceEpoch.toString(),
    );
  }

  Future<DateTime?> getLastAuthTime() async {
    final value = await _storage.read(key: _lastAuthTimeKey);
    if (value == null) return null;
    return DateTime.fromMillisecondsSinceEpoch(int.parse(value));
  }

  Future<void> clearAll() async {
    await _storage.deleteAll();
  }
}
