import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/employee.dart';
import '../services/api_service.dart';
import '../services/local_storage.dart';
import 'auth_provider.dart';

class EmployeesState {
  final List<Employee> employees;
  final bool isLoading;
  final String? error;

  const EmployeesState({
    this.employees = const [],
    this.isLoading = false,
    this.error,
  });

  EmployeesState copyWith({
    List<Employee>? employees,
    bool? isLoading,
    String? error,
  }) {
    return EmployeesState(
      employees: employees ?? this.employees,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class EmployeesNotifier extends StateNotifier<EmployeesState> {
  final ApiService _api;
  final LocalStorage _storage;

  EmployeesNotifier(this._api, this._storage) : super(const EmployeesState()) {
    _loadCached();
  }

  void _loadCached() {
    final cached = _storage.getCachedEmployees();
    if (cached.isNotEmpty) {
      state = EmployeesState(employees: cached);
    }
  }

  Future<void> fetch() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final employees = await _api.getEmployees();
      await _storage.cacheEmployees(employees);
      state = EmployeesState(employees: employees);
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> add(Employee employee) async {
    try {
      final created = await _api.createEmployee(employee);
      final updated = [...state.employees, created];
      await _storage.cacheEmployees(updated);
      state = EmployeesState(employees: updated);
    } on ApiException catch (e) {
      state = state.copyWith(error: e.message);
    }
  }

  Future<void> delete(int id) async {
    try {
      await _api.deleteEmployee(id);
      final updated = state.employees.where((e) => e.id != id).toList();
      await _storage.cacheEmployees(updated);
      state = EmployeesState(employees: updated);
    } on ApiException catch (e) {
      state = state.copyWith(error: e.message);
    }
  }
}

final apiServiceProvider = Provider<ApiService>((ref) => ApiService());

final employeesProvider =
    StateNotifierProvider<EmployeesNotifier, EmployeesState>((ref) {
  return EmployeesNotifier(
    ref.read(apiServiceProvider),
    ref.read(localStorageProvider),
  );
});
