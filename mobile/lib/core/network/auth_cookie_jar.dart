import 'package:cookie_jar/cookie_jar.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Profile-scoped persistent jar for the `studio_session` cookie.
///
/// A file-based `PersistCookieJar` would leave a plaintext bearer token on
/// disk, so the session pair is kept in `flutter_secure_storage`
/// (Keychain/Keystore) under `studio_session_cookie:<profileId>` — LAN and
/// tunnel sessions must never cross (03 §3.3, 06 §5).
///
/// Storage format: the bare `name=value` pair (attributes are dropped —
/// they are request-irrelevant and `Cookie.fromSetCookieValue`
/// parses the pair back cleanly).
class AuthCookieJar implements CookieJar {
  AuthCookieJar({
    required this.storage,
    required this.profileId,
    this.onSessionChanged,
  });

  static const String cookieName = 'studio_session';
  static const String keyPrefix = 'studio_session_cookie:';

  /// Backing secure storage (injectable for tests).
  final FlutterSecureStorage storage;

  /// Resolved per call so saves land under the profile active *now*.
  final String Function() profileId;

  /// Notified with `studio_session=<value>` after each save and with
  /// `null` after [clear] — image loaders subscribe via this hook.
  void Function(String? headerValue)? onSessionChanged;

  @override
  bool get ignoreExpires => false;

  static String keyFor(String profileId) => '$keyPrefix$profileId';

  String get _currentKey => keyFor(profileId());

  @override
  Future<void> saveFromResponse(Uri uri, List<Cookie> cookies) async {
    Cookie? session;
    for (final Cookie cookie in cookies) {
      if (cookie.name == cookieName) {
        session = cookie;
        break;
      }
    }
    if (session == null) {
      return;
    }
    final String pair = '${session.name}=${session.value}';
    await storage.write(key: _currentKey, value: pair);
    onSessionChanged?.call(pair);
  }

  @override
  Future<List<Cookie>> loadForRequest(Uri uri) async {
    final String? raw = await storage.read(key: _currentKey);
    if (raw == null || raw.isEmpty) {
      return const [];
    }
    try {
      final Cookie cookie = Cookie.fromSetCookieValue(raw);
      // Publish the stored pair as the process-wide image-header replay
      // value (R7b): on a cold start with a persisted session no login
      // response ever runs, so without this the loaders would rebuild
      // requests with no `Cookie` header and the backend would 401 every
      // uncached image. Best-effort — the header is a cache of this value.
      onSessionChanged?.call('${cookie.name}=${cookie.value}');
      return <Cookie>[cookie];
    } on Exception catch (_) {
      // Unparseable stored value — behave as logged out.
      return const [];
    }
  }

  /// Clears the current profile's session (e.g. logout or 401).
  Future<void> clear({bool notify = true}) async {
    await storage.delete(key: _currentKey);
    if (notify) {
      onSessionChanged?.call(null);
    }
  }

  @override
  Future<void> deleteAll() => clear();

  @override
  Future<void> delete(
    Uri uri, [
    bool withDomainSharedCookie = false,
  ]) =>
      clear();
}
