import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/settings/data/profile_store.dart';
import '../../features/settings/domain/connection_profile.dart';
import '../config/app_config.dart';
import '../storage/secure_store.dart';
import 'api_logger.dart';
import 'auth_cookie_jar.dart';
import 'auth_interceptor.dart';
import 'base_url_interceptor.dart';
import 'session_cookie.dart';

/// Pure Dio factory — no feature logic, everything is injected.
///
/// Interceptor order matters: base URL is rewritten first, the cookie jar
/// then loads the session against the final URI, the auth interceptor
/// watches for 401s, and the (optional, debug-only) logger sees the fully
/// assembled request with credentials already redacted.
Dio buildDio({
  required ConnectionProfile Function() activeProfile,
  required Future<void> Function() onUnauthorized,
  required AuthCookieJar cookieJar,
  void Function(String?)? onSessionCookieChanged,
  bool logging = kDebugMode,
}) {
  if (onSessionCookieChanged != null) {
    final void Function(String?)? previous = cookieJar.onSessionChanged;
    cookieJar.onSessionChanged = (String? value) {
      previous?.call(value);
      onSessionCookieChanged(value);
    };
  }

  final Dio dio = Dio(
    BaseOptions(
      connectTimeout: AppConfig.connectTimeout,
      receiveTimeout: AppConfig.receiveTimeout,
      // Web builds: XHR must use the browser's cookie jar (credentials
      // include) — the CookieManager's `Cookie` header is forbidden there.
      // Native ignores this key; CookieManager replays the session itself.
      extra: const <String, dynamic>{'withCredentials': true},
    ),
  );
  dio.interceptors.add(BaseUrlInterceptor(activeProfile));
  dio.interceptors.add(CookieManager(cookieJar));
  dio.interceptors.add(AuthInterceptor(onUnauthorized: onUnauthorized));
  if (logging) {
    dio.interceptors.add(buildApiLogger());
  }
  return dio;
}

/// Supplies the active profile resolver used per request (03 §3.2).
final activeProfileResolverProvider =
    Provider<ConnectionProfile Function()>(
  (ref) => () => ref.watch(activeProfileProvider),
);

/// Forced-logout hook; the auth feature overrides this with a real
/// idempotent implementation (03 §3.4).
final unauthorizedHandlerProvider = Provider<Future<void> Function()>(
  (ref) => () async {},
);

/// Profile-scoped session jar wired to the shared replay header.
final authCookieJarProvider = Provider<AuthCookieJar>(
  (ref) => AuthCookieJar(
    storage: SecureStore.defaultInstance,
    profileId: () => ref.watch(activeProfileProvider).id,
    onSessionChanged: (String? value) =>
        ref.read(sessionCookieHeaderProvider.notifier).set(value),
  ),
);

/// The app-wide Dio instance.
final dioProvider = Provider<Dio>(
  (ref) => buildDio(
    activeProfile: ref.watch(activeProfileResolverProvider),
    onUnauthorized: ref.watch(unauthorizedHandlerProvider),
    cookieJar: ref.watch(authCookieJarProvider),
    logging: kDebugMode,
  ),
);
