import 'package:dio/dio.dart';

import 'app_exception.dart';

/// Maps any [DioException] onto the sealed [AppException] hierarchy so no
/// `DioException` ever escapes the `data/` layer (03 §4).
///
/// Table: timeouts/connection failures → [NetworkException]; 401 →
/// [AuthException]; 404 → [NotFoundException]; 400/422 →
/// [ValidationException]; 5xx and other statuses → [ServerException].
AppException mapDioError(DioException e) {
  switch (e.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
    case DioExceptionType.connectionError:
    case DioExceptionType.badCertificate:
    case DioExceptionType.cancel:
    case DioExceptionType.transformTimeout:
      return NetworkException(message: e.message, cause: e);
    case DioExceptionType.badResponse:
    case DioExceptionType.unknown:
      break;
  }

  final int? status = e.response?.statusCode;
  final String? detail = _extractDetail(e.response?.data) ?? e.message;

  // Socket/DNS failures surface as `unknown` with no response attached.
  if (status == null && e.type == DioExceptionType.unknown) {
    return NetworkException(message: detail, cause: e);
  }
  if (status == 401) {
    return AuthException(message: detail, cause: e);
  }
  if (status == 404) {
    return NotFoundException(message: detail, cause: e);
  }
  if (status == 400 || status == 422) {
    return ValidationException(message: detail, cause: e);
  }
  return ServerException(message: detail, cause: e);
}

/// Short, human copy for each failure — offline flavor for network issues.
String uiMessageFor(AppException e) {
  return switch (e) {
    NetworkException() =>
      "Can't reach the studio server. Check your network and connection profile.",
    AuthException() =>
      'Your session has ended. Please sign in again.',
    NotFoundException() =>
      'That item could not be found on the server.',
    ValidationException() =>
      e.message ?? 'The server rejected this request.',
    ServerException() =>
      'The studio server hit an error. Please try again.',
  };
}

/// Pulls FastAPI's `{"detail": ...}` body out of a response payload.
String? _extractDetail(Object? data) {
  if (data is Map && data['detail'] != null) {
    return data['detail'].toString();
  }
  if (data is String && data.isNotEmpty) {
    return data;
  }
  return null;
}
