import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/salary_result.dart';
import '../models/vacation_result.dart';
import '../models/sick_result.dart';
import '../services/api_service.dart';
import 'employees_provider.dart';

class CalculationState {
  final SalaryResult? salaryResult;
  final VacationResult? vacationResult;
  final SickResult? sickResult;
  final bool isLoading;
  final String? error;

  const CalculationState({
    this.salaryResult,
    this.vacationResult,
    this.sickResult,
    this.isLoading = false,
    this.error,
  });

  CalculationState copyWith({
    SalaryResult? salaryResult,
    VacationResult? vacationResult,
    SickResult? sickResult,
    bool? isLoading,
    String? error,
  }) {
    return CalculationState(
      salaryResult: salaryResult ?? this.salaryResult,
      vacationResult: vacationResult ?? this.vacationResult,
      sickResult: sickResult ?? this.sickResult,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class CalculationNotifier extends StateNotifier<CalculationState> {
  final ApiService _api;

  CalculationNotifier(this._api) : super(const CalculationState());

  Future<void> calculateSalary({
    required double oklad,
    required double rate,
    required double stazhPercent,
    required double categoryPercent,
  }) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _api.calculateSalary(
        oklad: oklad,
        rate: rate,
        stazhPercent: stazhPercent,
        categoryPercent: categoryPercent,
      );
      state = CalculationState(salaryResult: result);
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> calculateVacation({
    required double totalEarnings,
    required int days,
  }) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _api.calculateVacation(
        totalEarnings: totalEarnings,
        days: days,
      );
      state = CalculationState(vacationResult: result);
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> calculateSick({
    required double earnings2y,
    required String stazhBracket,
    required int days,
  }) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final result = await _api.calculateSick(
        earnings2y: earnings2y,
        stazhBracket: stazhBracket,
        days: days,
      );
      state = CalculationState(sickResult: result);
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  void clear() {
    state = const CalculationState();
  }
}

final calculationProvider =
    StateNotifierProvider<CalculationNotifier, CalculationState>((ref) {
  return CalculationNotifier(ref.read(apiServiceProvider));
});
