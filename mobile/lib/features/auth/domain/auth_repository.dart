/// Auth port consumed by presentation (03 layering: presentation → domain).
///
/// Implementations never leak [DioException] — errors surface as the sealed
/// `AppException` hierarchy from `core/utils/app_exception.dart` (03 §4).
abstract interface class AuthRepository {
  /// Exchanges credentials for the `studio_session` cookie
  /// (`POST /api/auth/login`); throws `AuthException` on 401.
  Future<void> login(String username, String password);

  /// `GET /api/auth/me` — `true` on 200, `false` on 401 (no valid session).
  /// Transport/server failures throw mapped `AppException`s.
  Future<bool> sessionAlive();

  /// `POST /api/auth/logout` — best-effort; completes even when unreachable.
  Future<void> logout();
}
