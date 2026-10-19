import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/app_exception.dart';
import '../data/auth_repository_impl.dart';
import '../domain/auth_repository.dart';

/// Where the router stands relative to the local session (05 §3).
enum AuthStatus {
  /// Bootstrap not finished — splash still owns navigation.
  unknown,

  /// Valid `studio_session` cookie (or a just-completed login).
  authenticated,

  /// No usable session — login screen may render.
  unauthenticated,
}

/// Single source of truth for the auth redirect (see `app/router.dart`).
final authControllerProvider =
    AsyncNotifierProvider<AuthController, AuthStatus>(AuthController.new);

class AuthController extends AsyncNotifier<AuthStatus> {
  AuthRepository get _repository => ref.read(authRepositoryProvider);

  /// Re-entry guard so a burst of 401s runs teardown exactly once.
  bool _endingSession = false;

  /// Cold start resolves immediately; the splash screen drives [refresh]
  /// (and its 2.5 s cap) so no network call is duplicated in [build].
  @override
  Future<AuthStatus> build() async => AuthStatus.unknown;

  /// Interactive sign-in: on success the status flips to [authenticated] and
  /// the router refresh takes the user to `/hub`. Failures rethrow the mapped
  /// [AppException] so the form can render it inline (04 error-near-field).
  Future<void> login(String username, String password) async {
    await _repository.login(username, password);
    state = const AsyncData(AuthStatus.authenticated);
  }

  /// User-initiated sign-out — same teardown as [forceLogout].
  Future<void> logout() => forceLogout();

  /// Idempotent 401 teardown (03 §3.4): best-effort `POST /logout`, clear the
  /// profile-scoped cookie jar, then set [AuthStatus.unauthenticated].
  /// Never throws — the backend may be exactly what is down.
  Future<void> forceLogout() async {
    if (_endingSession) return;
    _endingSession = true;
    try {
      try {
        await _repository.logout();
      } on AppException {
        // Best-effort: local teardown must proceed regardless.
      }
      try {
        await ref.read(authCookieJarProvider).clear();
      } on Object {
        // Best-effort: a missing/unwritable jar still ends the session locally.
      }
      state = const AsyncData(AuthStatus.unauthenticated);
    } finally {
      _endingSession = false;
    }
  }

  /// `GET /api/auth/me` revalidation. Auth/server answers update the status;
  /// transport failures keep the previous status so an offline resume can
  /// never log the user out (03 §4, 05 §3).
  Future<void> refresh() async {
    try {
      final bool alive = await _repository.sessionAlive();
      state = AsyncData(
        alive ? AuthStatus.authenticated : AuthStatus.unauthenticated,
      );
    } on AuthException {
      state = const AsyncData(AuthStatus.unauthenticated);
    } on AppException {
      // Network/server error: keep the previous status.
    }
  }
}
