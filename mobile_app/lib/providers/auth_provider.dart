import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/local_storage.dart';

enum UserRole { admin, cashier, director }

class AuthState {
  final bool isAuthenticated;
  final String? token;
  final bool isLoading;
  final UserRole role;

  const AuthState({
    this.isAuthenticated = false,
    this.token,
    this.isLoading = false,
    this.role = UserRole.admin,
  });

  AuthState copyWith({
    bool? isAuthenticated,
    String? token,
    bool? isLoading,
    UserRole? role,
  }) {
    return AuthState(
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      token: token ?? this.token,
      isLoading: isLoading ?? this.isLoading,
      role: role ?? this.role,
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
      final role = _storage.getUserRole();
      state = AuthState(
        isAuthenticated: true,
        token: token,
        role: _parseRole(role),
      );
    }
  }

  UserRole _parseRole(String? roleStr) {
    switch (roleStr) {
      case 'cashier':
        return UserRole.cashier;
      case 'director':
        return UserRole.director;
      case 'admin':
      default:
        return UserRole.admin;
    }
  }

  Future<void> login(String token, {String? role}) async {
    state = state.copyWith(isLoading: true);
    await _storage.saveAuthToken(token);
    if (role != null) {
      await _storage.saveUserRole(role);
    }
    state = AuthState(
      isAuthenticated: true,
      token: token,
      role: _parseRole(role),
    );
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
