import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Handles 401 responses like the web client's axios interceptor
/// (`frontend-new/src/lib/client.ts`, 03 §3.4):
///
/// * 401 on anything **except** `POST /api/auth/login` triggers
///   [onUnauthorized] (an idempotent forced logout) exactly **once per
///   error propagation** — a re-entry guard suppresses duplicate invocations
///   while the first one is still in flight (e.g. the same error observed
///   twice in one chain), then re-arms automatically, and via [resetGuard]
///   in tests.
/// * Login's own 401 surfaces as a form error — no redirect loop.
/// * Every error, including the 401 itself, keeps propagating downstream;
///   nothing is ever swallowed.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({required this.onUnauthorized});

  final Future<void> Function() onUnauthorized;
  bool _handlingUnauthorized = false;

  /// Clears the re-entry guard (test seam).
  @visibleForTesting
  void resetGuard() => _handlingUnauthorized = false;

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    final int? status = err.response?.statusCode;
    final bool isLogin =
        err.requestOptions.path.endsWith('/api/auth/login');
    if (status == 401 &&
        !isLogin &&
        !_handlingUnauthorized) {
      _handlingUnauthorized = true;
      unawaited(_runOnUnauthorized());
    }
    handler.next(err);
  }

  Future<void> _runOnUnauthorized() async {
    try {
      await onUnauthorized();
    } catch (_) {
      // forceLogout is best-effort — the backend may be what's down.
    } finally {
      _handlingUnauthorized = false;
    }
  }
}
