import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/child_model.dart';
import '../services/api_service.dart';
import '../services/local_storage.dart';
import 'auth_provider.dart';
import 'employees_provider.dart';

class ChildrenState {
  final List<ChildModel> children;
  final bool isLoading;
  final String? error;

  const ChildrenState({
    this.children = const [],
    this.isLoading = false,
    this.error,
  });

  ChildrenState copyWith({
    List<ChildModel>? children,
    bool? isLoading,
    String? error,
  }) {
    return ChildrenState(
      children: children ?? this.children,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

class ChildrenNotifier extends StateNotifier<ChildrenState> {
  final ApiService _api;
  final LocalStorage _storage;

  ChildrenNotifier(this._api, this._storage) : super(const ChildrenState()) {
    _loadCached();
  }

  void _loadCached() {
    final cached = _storage.getCachedChildren();
    if (cached.isNotEmpty) {
      state = ChildrenState(children: cached);
    }
  }

  Future<void> fetch() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final children = await _api.getChildren();
      await _storage.cacheChildren(children);
      state = ChildrenState(children: children);
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, error: e.message);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> add(ChildModel child) async {
    try {
      final created = await _api.createChild(child);
      final updated = [...state.children, created];
      await _storage.cacheChildren(updated);
      state = ChildrenState(children: updated);
    } on ApiException catch (e) {
      state = state.copyWith(error: e.message);
    }
  }

  Future<void> delete(int id) async {
    try {
      await _api.deleteChild(id);
      final updated = state.children.where((c) => c.id != id).toList();
      await _storage.cacheChildren(updated);
      state = ChildrenState(children: updated);
    } on ApiException catch (e) {
      state = state.copyWith(error: e.message);
    }
  }
}

final childrenProvider =
    StateNotifierProvider<ChildrenNotifier, ChildrenState>((ref) {
  return ChildrenNotifier(
    ref.read(apiServiceProvider),
    ref.read(localStorageProvider),
  );
});
