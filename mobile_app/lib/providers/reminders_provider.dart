import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/reminder.dart';
import '../services/api_service.dart';
import '../services/local_storage.dart';
import 'auth_provider.dart';
import 'employees_provider.dart';

class RemindersState {
  final List<Reminder> reminders;
  final bool isLoading;
  final String? error;

  const RemindersState({
    this.reminders = const [],
    this.isLoading = false,
    this.error,
  });

  RemindersState copyWith({
    List<Reminder>? reminders,
    bool? isLoading,
    String? error,
  }) {
    return RemindersState(
      reminders: reminders ?? this.reminders,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class RemindersNotifier extends StateNotifier<RemindersState> {
  final ApiService _api;
  final LocalStorage _storage;

  RemindersNotifier(this._api, this._storage) : super(const RemindersState()) {
    _loadCached();
  }

  void _loadCached() {
    final cached = _storage.getCachedReminders();
    if (cached.isNotEmpty) {
      state = RemindersState(reminders: cached);
    }
  }

  Future<void> fetch() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final reminders = await _api.getReminders();
      await _storage.cacheReminders(reminders);
      state = RemindersState(reminders: reminders);
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }
}

final remindersProvider =
    StateNotifierProvider<RemindersNotifier, RemindersState>((ref) {
  return RemindersNotifier(
    ref.read(apiServiceProvider),
    ref.read(localStorageProvider),
  );
});
