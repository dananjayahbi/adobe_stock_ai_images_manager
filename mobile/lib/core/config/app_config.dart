import 'env.dart';

/// Static configuration shared by the core layers (network, health probes).
///
/// Timeouts and environment-derived defaults only — per-user settings live
/// in connection profiles, not here.
abstract final class AppConfig {
  /// TCP handshake budget for every Dio request.
  static const Duration connectTimeout = Duration(seconds: 10);

  /// Idle budget between streamed response chunks (SSE keep-alives count).
  static const Duration receiveTimeout = Duration(seconds: 60);

  /// Tight budget for connection health probes (`/health`, `/api/auth/me`).
  static const Duration healthTimeout = Duration(seconds: 3);

  /// Backend URL pre-filled for dev builds (03 §4).
  static const String devBaseUrl = 'http://localhost:8007';

  /// Named-tunnel base URL (user's Cloudflare tunnel, 06 §5) — the app's
  /// only default; local/loopback profiles are added manually if ever needed.
  static const String tunnelBaseUrl = 'https://studio.hotelgo.lk';

  /// Dev builds log request/response details; prod stays quiet unless a
  /// caller opts in explicitly.
  static bool get verboseLogging => AppEnv.current.isDev;
}
