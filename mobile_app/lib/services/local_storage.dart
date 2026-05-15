import 'dart:convert';
import 'package:hive_flutter/hive_flutter.dart';
import '../models/employee.dart';
import '../models/child_model.dart';
import '../models/journal_entry.dart';
import '../models/reminder.dart';

class LocalStorage {
  static const String _employeesBox = 'employees_cache';
  static const String _childrenBox = 'children_cache';
  static const String _journalBox = 'journal_cache';
  static const String _remindersBox = 'reminders_cache';
  static const String _settingsBox = 'settings';

  static Future<void> init() async {
    await Hive.initFlutter();
    await Hive.openBox<String>(_employeesBox);
    await Hive.openBox<String>(_childrenBox);
    await Hive.openBox<String>(_journalBox);
    await Hive.openBox<String>(_remindersBox);
    await Hive.openBox<String>(_settingsBox);
  }

  // Employees
  Future<void> cacheEmployees(List<Employee> employees) async {
    final box = Hive.box<String>(_employeesBox);
    await box.put(
      'data',
      json.encode(employees.map((e) => e.toJson()).toList()),
    );
  }

  List<Employee> getCachedEmployees() {
    final box = Hive.box<String>(_employeesBox);
    final data = box.get('data');
    if (data == null) return [];
    final List<dynamic> decoded = json.decode(data);
    return decoded.map((e) => Employee.fromJson(e)).toList();
  }

  // Children
  Future<void> cacheChildren(List<ChildModel> children) async {
    final box = Hive.box<String>(_childrenBox);
    await box.put(
      'data',
      json.encode(children.map((c) => c.toJson()).toList()),
    );
  }

  List<ChildModel> getCachedChildren() {
    final box = Hive.box<String>(_childrenBox);
    final data = box.get('data');
    if (data == null) return [];
    final List<dynamic> decoded = json.decode(data);
    return decoded.map((c) => ChildModel.fromJson(c)).toList();
  }

  // Journal
  Future<void> cacheJournal(List<JournalEntry> entries) async {
    final box = Hive.box<String>(_journalBox);
    await box.put(
      'data',
      json.encode(entries.map((e) => e.toJson()).toList()),
    );
  }

  List<JournalEntry> getCachedJournal() {
    final box = Hive.box<String>(_journalBox);
    final data = box.get('data');
    if (data == null) return [];
    final List<dynamic> decoded = json.decode(data);
    return decoded.map((e) => JournalEntry.fromJson(e)).toList();
  }

  // Reminders
  Future<void> cacheReminders(List<Reminder> reminders) async {
    final box = Hive.box<String>(_remindersBox);
    await box.put(
      'data',
      json.encode(reminders.map((r) => r.toJson()).toList()),
    );
  }

  List<Reminder> getCachedReminders() {
    final box = Hive.box<String>(_remindersBox);
    final data = box.get('data');
    if (data == null) return [];
    final List<dynamic> decoded = json.decode(data);
    return decoded.map((r) => Reminder.fromJson(r)).toList();
  }

  // Settings
  Future<void> saveAuthToken(String token) async {
    final box = Hive.box<String>(_settingsBox);
    await box.put('auth_token', token);
  }

  String? getAuthToken() {
    final box = Hive.box<String>(_settingsBox);
    return box.get('auth_token');
  }

  Future<void> clearAll() async {
    await Hive.box<String>(_employeesBox).clear();
    await Hive.box<String>(_childrenBox).clear();
    await Hive.box<String>(_journalBox).clear();
    await Hive.box<String>(_remindersBox).clear();
    await Hive.box<String>(_settingsBox).clear();
  }
}
