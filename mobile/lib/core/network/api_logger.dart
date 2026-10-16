import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Debug logging interceptor with credential redaction (03 §4: never log
/// cookies or credentials).
///
/// Any header or body key whose name contains `cookie`, `authorization`,
/// `password`, or `username` is replaced with `***`.
Interceptor buildApiLogger() => _ApiLogger();

const List<String> _sensitiveFragments = [
  'cookie',
  'authorization',
  'password',
  'username',
];

bool _isSensitive(String name) {
  final String lower = name.toLowerCase();
  return _sensitiveFragments.any(lower.contains);
}

/// Returns a copy of [headers] with sensitive values masked.
Map<String, dynamic> _redactHeaders(Map<String, dynamic> headers) =>
    <String, dynamic>{
      for (final MapEntry<String, dynamic> entry in headers.entries)
        entry.key: _isSensitive(entry.key) ? '***' : entry.value,
    };

/// Recursively masks sensitive keys inside a request/response body.
Object? _redactBody(Object? body) {
  if (body is Map) {
    return <String, Object?>{
      for (final MapEntry<dynamic, dynamic> entry in body.entries)
        '${entry.key}': _isSensitive('${entry.key}')
            ? '***'
            : _redactBody(entry.value),
    };
  }
  if (body is List) {
    return body.map<Object?>(_redactBody).toList();
  }
  if (body is String) {
    // Avoid dumping whole JSON documents twice when already encoded.
    final String trimmed = body.trimLeft();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        return _redactBody(jsonDecode(body));
      } on FormatException {
        return body;
      }
    }
    return body;
  }
  return body;
}

class _ApiLogger extends Interceptor {
  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) {
    debugPrint('→ ${options.method} ${options.uri}');
    final Map<String, dynamic> headers = _redactHeaders(options.headers);
    if (headers.isNotEmpty) {
      debugPrint('  headers: $headers');
    }
    if (options.data != null) {
      debugPrint('  body: ${_redactBody(options.data)}');
    }
    handler.next(options);
  }

  @override
  void onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) {
    final RequestOptions options = response.requestOptions;
    debugPrint('← ${response.statusCode} ${options.method} ${options.uri}');
    final Map<String, dynamic> headers = _redactHeaders(response.headers.map);
    if (headers.containsKey('set-cookie')) {
      debugPrint('  headers: $headers');
    }
    if (response.data != null && response.data is! List<int>) {
      debugPrint('  body: ${_redactBody(response.data)}');
    }
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    final RequestOptions options = err.requestOptions;
    debugPrint(
      '✗ ${err.response?.statusCode ?? err.type.name} '
      '${options.method} ${options.uri}',
    );
    if (err.response?.data != null) {
      debugPrint('  error body: ${_redactBody(err.response?.data)}');
    }
    handler.next(err);
  }
}
