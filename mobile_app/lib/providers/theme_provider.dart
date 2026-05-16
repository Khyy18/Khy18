import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

final themeProvider = StateNotifierProvider<ThemeNotifier, ThemeMode>((ref) {
  return ThemeNotifier();
});

class ThemeNotifier extends StateNotifier<ThemeMode> {
  static const _boxName = 'settings';
  static const _key = 'theme_mode';

  ThemeNotifier() : super(ThemeMode.light) {
    _loadTheme();
  }

  void _loadTheme() {
    final box = Hive.box<String>(_boxName);
    final value = box.get(_key, defaultValue: 'light')!;
    switch (value) {
      case 'dark':
        state = ThemeMode.dark;
        break;
      case 'system':
        state = ThemeMode.system;
        break;
      default:
        state = ThemeMode.light;
    }
  }

  void toggle() {
    if (state == ThemeMode.dark) {
      state = ThemeMode.light;
      _persist('light');
    } else {
      state = ThemeMode.dark;
      _persist('dark');
    }
  }

  void setThemeMode(ThemeMode mode) {
    state = mode;
    switch (mode) {
      case ThemeMode.dark:
        _persist('dark');
        break;
      case ThemeMode.system:
        _persist('system');
        break;
      default:
        _persist('light');
    }
  }

  void _persist(String value) {
    final box = Hive.box<String>(_boxName);
    box.put(_key, value);
  }
}
