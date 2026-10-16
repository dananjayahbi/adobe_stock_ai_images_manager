import 'package:dio/dio.dart';

import '../domain/user_session.dart';

/// Thin Dio data source for `/api/auth/*` — no error mapping here (03 §4):
/// raw `DioException`s propagate to the repository, except where the contract
/// below explicitly absorbs them (401 probe → null, logout → best-effort).
///
/// The `studio_session` cookie travels in `Set-Cookie` and is captured
/// automatically by the Dio cookie manager wired in `dio_factory.dart`.
class AuthApi {
  AuthApi(this._dio);

  final Dio _dio;

  /// `POST /api/auth/login {username, password}` — 401 throws (bad credentials).
  Future<void> login({
    required String username,
    required String password,
  }) async {
    await _dio.post(
      '/api/auth/login',
      data: <String, Object>{'username': username, 'password': password},
    );
  }

  /// `GET /api/auth/me` — `null` when the session is missing/invalid (401).
  Future<UserSession?> me() async {
    try {
      final Object? data = (await _dio.get('/api/auth/me')).data;
      return _sessionFrom(data);
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        return null; // middleware's standard "Not authenticated"
      }
      rethrow;
    }
  }

  /// `POST /api/auth/logout` — always completes: the endpoint is exempt and
  /// returns 200 even without a session, and a dead backend must never block
  /// local session teardown (02 §17.4).
  Future<void> logout() async {
    try {
      await _dio.post('/api/auth/logout');
    } on DioException {
      // Swallowed by contract — the cookie jar is cleared client-side anyway.
    }
  }

  /// Parses the shared payload shape: `{"user": {"username": "..."}}`.
  UserSession _sessionFrom(Object? data) {
    final Object? user = data is Map<Object?, Object?> ? data['user'] : null;
    final String? username = user is Map<Object?, Object?>
        ? user['username'] as String?
        : null;
    return UserSession(isAuthenticated: true, username: username);
  }
}
