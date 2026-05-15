import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';
import '../models/employee.dart';
import '../models/child_model.dart';
import '../models/journal_entry.dart';
import '../models/salary_result.dart';
import '../models/vacation_result.dart';
import '../models/sick_result.dart';
import '../models/payment_order.dart';
import '../models/reminder.dart';
import '../models/kbk_code.dart';

class ApiService {
  final String baseUrl;
  String? _authToken;

  ApiService({String? baseUrl}) : baseUrl = baseUrl ?? AppConfig.apiBaseUrl;

  void setAuthToken(String token) {
    _authToken = token;
  }

  Map<String, String> get _headers {
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    if (_authToken != null) {
      headers['Authorization'] = 'Bearer $_authToken';
    }
    return headers;
  }

  // Employees
  Future<List<Employee>> getEmployees() async {
    final response = await http.get(
      Uri.parse('$baseUrl/employees'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final List<dynamic> data = json.decode(response.body);
      return data.map((e) => Employee.fromJson(e)).toList();
    }
    throw ApiException('Failed to load employees', response.statusCode);
  }

  Future<Employee> createEmployee(Employee employee) async {
    final response = await http.post(
      Uri.parse('$baseUrl/employees'),
      headers: _headers,
      body: json.encode(employee.toJson()),
    );
    if (response.statusCode == 200 || response.statusCode == 201) {
      return Employee.fromJson(json.decode(response.body));
    }
    throw ApiException('Failed to create employee', response.statusCode);
  }

  Future<void> deleteEmployee(int id) async {
    final response = await http.delete(
      Uri.parse('$baseUrl/employees/$id'),
      headers: _headers,
    );
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw ApiException('Failed to delete employee', response.statusCode);
    }
  }

  // Salary
  Future<SalaryResult> calculateSalary({
    required double oklad,
    required double rate,
    required double stazhPercent,
    required double categoryPercent,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/salary/calculate'),
      headers: _headers,
      body: json.encode({
        'oklad': oklad,
        'rate': rate,
        'stazh_percent': stazhPercent,
        'category_percent': categoryPercent,
      }),
    );
    if (response.statusCode == 200) {
      return SalaryResult.fromJson(json.decode(response.body));
    }
    throw ApiException('Failed to calculate salary', response.statusCode);
  }

  // Vacation
  Future<VacationResult> calculateVacation({
    required double totalEarnings,
    required int days,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/vacation/calculate'),
      headers: _headers,
      body: json.encode({
        'total_12_months': totalEarnings,
        'days': days,
      }),
    );
    if (response.statusCode == 200) {
      return VacationResult.fromJson(json.decode(response.body));
    }
    throw ApiException('Failed to calculate vacation', response.statusCode);
  }

  // Sick leave
  Future<SickResult> calculateSick({
    required double earnings2y,
    required String stazhBracket,
    required int days,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/sick/calculate'),
      headers: _headers,
      body: json.encode({
        'earnings_2y': earnings2y,
        'stazh_bracket': stazhBracket,
        'days': days,
      }),
    );
    if (response.statusCode == 200) {
      return SickResult.fromJson(json.decode(response.body));
    }
    throw ApiException('Failed to calculate sick leave', response.statusCode);
  }

  // Timesheet
  Future<Map<String, dynamic>> getTimesheetSummary(
      int employeeId, int year, int month) async {
    final response = await http.get(
      Uri.parse(
          '$baseUrl/timesheet/summary/$employeeId?year=$year&month=$month'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      return json.decode(response.body) as Map<String, dynamic>;
    }
    throw ApiException('Failed to load timesheet', response.statusCode);
  }

  // Journal
  Future<List<JournalEntry>> getJournal({
    String? startDate,
    String? endDate,
  }) async {
    String url = '$baseUrl/journal';
    final params = <String>[];
    if (startDate != null) params.add('start_date=$startDate');
    if (endDate != null) params.add('end_date=$endDate');
    if (params.isNotEmpty) url += '?${params.join('&')}';

    final response = await http.get(Uri.parse(url), headers: _headers);
    if (response.statusCode == 200) {
      final List<dynamic> data = json.decode(response.body);
      return data.map((e) => JournalEntry.fromJson(e)).toList();
    }
    throw ApiException('Failed to load journal', response.statusCode);
  }

  Future<JournalEntry> addJournalEntry(JournalEntry entry) async {
    final response = await http.post(
      Uri.parse('$baseUrl/journal'),
      headers: _headers,
      body: json.encode(entry.toJson()),
    );
    if (response.statusCode == 200 || response.statusCode == 201) {
      return JournalEntry.fromJson(json.decode(response.body));
    }
    throw ApiException('Failed to add journal entry', response.statusCode);
  }

  // KBK
  Future<List<KbkCode>> searchKbk(String query) async {
    final response = await http.get(
      Uri.parse('$baseUrl/kbk/search?q=${Uri.encodeComponent(query)}'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final List<dynamic> data = json.decode(response.body);
      return data.map((e) => KbkCode.fromJson(e)).toList();
    }
    throw ApiException('Failed to search KBK', response.statusCode);
  }

  // Children
  Future<List<ChildModel>> getChildren() async {
    final response = await http.get(
      Uri.parse('$baseUrl/children'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final List<dynamic> data = json.decode(response.body);
      return data.map((e) => ChildModel.fromJson(e)).toList();
    }
    throw ApiException('Failed to load children', response.statusCode);
  }

  Future<ChildModel> createChild(ChildModel child) async {
    final response = await http.post(
      Uri.parse('$baseUrl/children'),
      headers: _headers,
      body: json.encode(child.toJson()),
    );
    if (response.statusCode == 200 || response.statusCode == 201) {
      return ChildModel.fromJson(json.decode(response.body));
    }
    throw ApiException('Failed to create child', response.statusCode);
  }

  Future<void> deleteChild(int id) async {
    final response = await http.delete(
      Uri.parse('$baseUrl/children/$id'),
      headers: _headers,
    );
    if (response.statusCode != 200 && response.statusCode != 204) {
      throw ApiException('Failed to delete child', response.statusCode);
    }
  }

  // Reminders
  Future<List<Reminder>> getReminders() async {
    final response = await http.get(
      Uri.parse('$baseUrl/reminders'),
      headers: _headers,
    );
    if (response.statusCode == 200) {
      final List<dynamic> data = json.decode(response.body);
      return data.map((e) => Reminder.fromJson(e)).toList();
    }
    throw ApiException('Failed to load reminders', response.statusCode);
  }

  // Payments
  Future<Map<String, dynamic>> generatePayment(PaymentOrder order) async {
    final response = await http.post(
      Uri.parse('$baseUrl/payments/generate'),
      headers: _headers,
      body: json.encode(order.toJson()),
    );
    if (response.statusCode == 200) {
      return json.decode(response.body) as Map<String, dynamic>;
    }
    throw ApiException('Failed to generate payment', response.statusCode);
  }

  // AI Chat
  Future<String> chatAI(String message) async {
    final response = await http.post(
      Uri.parse('$baseUrl/ai/chat'),
      headers: _headers,
      body: json.encode({
        'message': message,
        'chat_id': 0,
      }),
    );
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      return data['response'] as String? ?? '';
    }
    throw ApiException('Failed to get AI response', response.statusCode);
  }
}

class ApiException implements Exception {
  final String message;
  final int statusCode;

  ApiException(this.message, this.statusCode);

  @override
  String toString() => 'ApiException($statusCode): $message';
}
