import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/local_storage.dart';

class AuthState {
  final bool isAuthenticated;
  final String? token;
  final bool isLoading;

  const AuthState({
    this.isAuthenticated = false,
    this.token,
    this.isLoading = false,
  });

  AuthState copyWith({
    bool? isAuthenticated,
    String? token,
    bool? isLoading,
  }) {
    return AuthState(
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      token: token ?? this.token,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

class AuthNotifier extends StateNotifier<AuthState> {
  final LocalStorage _storage;

  AuthNotifier(this._storage) : super(const AuthState()) {
    _loadToken();
  }

  void _loadToken() {
    final token = _storage.getAuthToken();
    if (token != null) {
      state = AuthState(isAuthenticated: true, token: token);
    }
  }

  Future<void> login(String token) async {
    state = state.copyWith(isLoading: true);
    await _storage.saveAuthToken(token);
    state = AuthState(isAuthenticated: true, token: token);
  }

  Future<void> logout() async {
    await _storage.clearAll();
    state = const AuthState();
  }
}

final localStorageProvider = Provider<LocalStorage>((ref) => LocalStorage());

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(ref.read(localStorageProvider));
});
