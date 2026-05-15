import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/journal_entry.dart';
import '../services/api_service.dart';
import '../services/local_storage.dart';
import 'auth_provider.dart';
import 'employees_provider.dart';

class JournalState {
  final List<JournalEntry> entries;
  final bool isLoading;
  final String? error;

  const JournalState({
    this.entries = const [],
    this.isLoading = false,
    this.error,
  });

  JournalState copyWith({
    List<JournalEntry>? entries,
    bool? isLoading,
    String? error,
  }) {
    return JournalState(
      entries: entries ?? this.entries,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  double get totalIncome =>
      entries.where((e) => e.type == 'income').fold(0, (s, e) => s + e.amount);

  double get totalExpense =>
      entries.where((e) => e.type == 'expense').fold(0, (s, e) => s + e.amount);

  double get balance => totalIncome - totalExpense;
}

class JournalNotifier extends StateNotifier<JournalState> {
  final ApiService _api;
  final LocalStorage _storage;

  JournalNotifier(this._api, this._storage) : super(const JournalState()) {
    _loadCached();
  }

  void _loadCached() {
    final cached = _storage.getCachedJournal();
    if (cached.isNotEmpty) {
      state = JournalState(entries: cached);
    }
  }

  Future<void> fetch({String? startDate, String? endDate}) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final entries =
          await _api.getJournal(startDate: startDate, endDate: endDate);
      await _storage.cacheJournal(entries);
      state = JournalState(entries: entries);
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> add(JournalEntry entry) async {
    try {
      final created = await _api.addJournalEntry(entry);
      final updated = [...state.entries, created];
      await _storage.cacheJournal(updated);
      state = JournalState(entries: updated);
    } on ApiException catch (e) {
      state = state.copyWith(error: e.message);
    }
  }
}

final journalProvider =
    StateNotifierProvider<JournalNotifier, JournalState>((ref) {
  return JournalNotifier(
    ref.read(apiServiceProvider),
    ref.read(localStorageProvider),
  );
});
