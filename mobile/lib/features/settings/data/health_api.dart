import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/network/dns_fallback.dart';
import '../../../core/network/dio_factory.dart';

/// Outcome of a candidate-base-URL probe (06 §5 health check on switch).
class HealthProbeResult {
  const HealthProbeResult.success(this.latencyMs)
      : ok = true,
        error = null;

  const HealthProbeResult.failure(this.error)
      : ok = false,
        latencyMs = null;

  /// True only when `GET {baseUrl}/health` answered 200 within the budget.
  final bool ok;

  /// Round-trip milliseconds for a success — shown as a `42 ms` caption.
  final int? latencyMs;

  /// Human-readable failure reason (timeout, HTTP code, bad URL).
  final String? error;
}

/// Connection health probes for the active profile (06 §5).
///
/// The legacy probes are deliberately lenient: any failure — timeout, DNS,
/// 401, 5xx — collapses to `false` so callers never see an exception.
class HealthApi {
  HealthApi(this._dio, {Future<void> Function(String host)? hostLookup})
      : _hostLookup = hostLookup ?? ensureResolves;

  final Dio _dio;

  /// DNS pre-check seam — the default resolves through the app's
  /// system → public-UDP chain (07 §2); tests inject their own.
  final Future<void> Function(String host) _hostLookup;

  /// `GET /health` → true only on a 200 (unauthenticated liveness).
  Future<bool> ping() async {
    try {
      final Response<void> response = await _dio.get<void>(
        '/health',
        options: Options(
          sendTimeout: AppConfig.healthTimeout,
          receiveTimeout: AppConfig.healthTimeout,
        ),
      );
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// `GET {baseUrl}/health` with [AppConfig.healthTimeout] budgets — used to
  /// gate a profile switch (06 §5): runs against the **candidate** URL, not
  /// the active profile, so it builds a one-off client instead of touching
  /// the shared cookie-bearing Dio.
  ///
  /// Connection-level failures (refused, DNS, TLS, timeout) get **one quick
  /// retry** — mobile radios frequently flake on the first attempt — and the
  /// failure text carries the OS-level reason so users can report *why* a
  /// host was unreachable, not just that it was.
  Future<HealthProbeResult> probe(String baseUrl) async {
    final String trimmed = baseUrl.trim().replaceFirst(RegExp(r'/+$'), '');
    final Uri? uri = Uri.tryParse(trimmed);
    if (uri == null ||
        !(uri.isScheme('http') || uri.isScheme('https')) ||
        uri.host.isEmpty) {
      return const HealthProbeResult.failure(
        'Enter a full http:// or https:// URL.',
      );
    }
    // DNS pre-check: resolve once (system → public chain) before any socket
    // work — but only for names (literals/loopback never need it). A miss
    // here returns the exact connection-error copy with the DNS hint — no
    // timeout budget wasted on a name that cannot resolve.
    if (needsDnsCheck(uri.host)) {
      try {
        await _hostLookup(uri.host);
      } catch (e) {
        final String raw =
            e.toString().replaceFirst('SocketException: ', '');
        return HealthProbeResult.failure(
          'Host unreachable. ($raw)${_dnsHint(raw)}',
        );
      }
    }
    final Dio dio = Dio(
      BaseOptions(
        baseUrl: trimmed,
        connectTimeout: AppConfig.healthTimeout,
        sendTimeout: AppConfig.healthTimeout,
        receiveTimeout: AppConfig.healthTimeout,
      ),
    );
    HealthProbeResult? lastFailure;
    for (int attempt = 0; attempt < 2; attempt++) {
      if (attempt > 0) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
      }
      final Stopwatch stopwatch = Stopwatch()..start();
      try {
        final Response<void> response = await dio.get<void>('/health');
        stopwatch.stop();
        if (response.statusCode == 200) {
          return HealthProbeResult.success(stopwatch.elapsedMilliseconds);
        }
        // An HTTP answer (even an error page) means the host is reachable.
        return HealthProbeResult.failure('HTTP ${response.statusCode}');
      } on DioException catch (e) {
        stopwatch.stop();
        lastFailure = HealthProbeResult.failure(_reasonFor(e));
        if (!_isRetryable(e)) {
          return lastFailure;
        }
      } catch (_) {
        stopwatch.stop();
        return const HealthProbeResult.failure('Host unreachable.');
      }
    }
    return lastFailure!;
  }

  /// Connection-level Dio failures are worth one immediate retry.
  static bool _isRetryable(DioException e) => switch (e.type) {
        DioExceptionType.connectionTimeout ||
        DioExceptionType.connectionError ||
        DioExceptionType.receiveTimeout =>
          true,
        _ => false,
      };

  /// Failure copy for a probe — terse, non-technical, never throws. For
  /// connection-level failures the OS reason is appended in parentheses
  /// (e.g. `Failed host lookup: 'studio.hotelgo.lk'`) so the inline sheet
  /// error identifies the actual cause.
  static String _reasonFor(DioException e) => switch (e.type) {
        DioExceptionType.connectionTimeout ||
        DioExceptionType.sendTimeout ||
        DioExceptionType.receiveTimeout =>
          'Timed out after ${AppConfig.healthTimeout.inSeconds} s.',
        DioExceptionType.connectionError =>
          'Host unreachable. (${_osReason(e)})${_dnsHint(_osReason(e))}',
        DioExceptionType.badCertificate => 'TLS certificate rejected.',
        DioExceptionType.badResponse =>
          'HTTP ${e.response?.statusCode ?? 500}.',
        _ => 'Host unreachable.',
      };

  /// The platform's underlying error, prefix-stripped for readability.
  static String _osReason(DioException e) {
    final Object? error = e.error;
    final String raw = error?.toString() ?? e.message ?? 'connection failed';
    return raw.replaceFirst('SocketException: ', '');
  }

  /// DNS-lookup misses are device/network issues, not server ones — give the
  /// exact fix (a DoH provider resolves the name even when the local
  /// resolver can't; "Off/Automatic" would keep using the broken resolver).
  static String _dnsHint(String reason) {
    if (reason.contains('Failed host lookup') ||
        reason.contains('No address associated')) {
      return '\nDNS lookup failed — set Settings → Private DNS to '
          '`one.one.one.one` (or `dns.google`) and retry.';
    }
    return '';
  }

  /// `GET /api/auth/me` → true on 200; 401 and any other failure → false.
  Future<bool> sessionAlive() async {
    try {
      final Response<void> response = await _dio.get<void>(
        '/api/auth/me',
        options: Options(
          sendTimeout: AppConfig.healthTimeout,
          receiveTimeout: AppConfig.healthTimeout,
        ),
      );
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}

final healthApiProvider = Provider<HealthApi>(
  (ref) => HealthApi(ref.watch(dioProvider)),
);

/// One-shot `GET /health` for the **active** profile — the About row and
/// any other surface that wants the current verdict without scripting its
/// own probe. Invalidate to re-run.
final activeHealthProvider = FutureProvider<bool>(
  (ref) => ref.watch(healthApiProvider).ping(),
);
