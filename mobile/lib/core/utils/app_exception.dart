/// Every failure that may cross the `data/` layer boundary, per
/// mobile-plan/03 §4. Datasources throw these — `DioException` never
/// escapes; repositories map with `mapDioError()` from `ui_message.dart`.
sealed class AppException implements Exception {
  const AppException({this.message, this.cause});

  /// Optional human-readable detail (backend `detail` verbatim when known).
  final String? message;

  /// The original error, when wrapping one.
  final Object? cause;

  @override
  String toString() =>
      '$runtimeType${message == null ? '' : ': $message'}';
}

/// Host unreachable: timeouts, socket failures, offline device.
final class NetworkException extends AppException {
  const NetworkException({super.message, super.cause});
}

/// Session invalid or missing — route to login.
final class AuthException extends AppException {
  const AuthException({super.message, super.cause});
}

/// Backend answered 5xx (or an unexpected failure while responding).
final class ServerException extends AppException {
  const ServerException({super.message, super.cause});
}

/// Requested resource does not exist (404).
final class NotFoundException extends AppException {
  const NotFoundException({super.message, super.cause});
}

/// Request rejected as invalid (400 / 422) — usually a form problem.
final class ValidationException extends AppException {
  const ValidationException({super.message, super.cause});
}
