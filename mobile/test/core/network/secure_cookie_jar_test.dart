import 'dart:io';

import 'package:ai_stock_studio/core/network/auth_cookie_jar.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class MockSecureStorage extends Mock implements FlutterSecureStorage {}

void main() {
  late MockSecureStorage storage;
  late Map<String, String?> values;
  late List<String?> notifications;

  setUp(() {
    storage = MockSecureStorage();
    values = <String, String?>{};
    notifications = <String?>[];

    when(() => storage.write(
          key: any(named: 'key'),
          value: any(named: 'value'),
        )).thenAnswer((invocation) async {
      values[invocation.namedArguments[#key]! as String] =
          invocation.namedArguments[#value] as String?;
    });
    when(() => storage.read(key: any(named: 'key')))
        .thenAnswer((invocation) async {
      return values[invocation.namedArguments[#key]! as String];
    });
    when(() => storage.delete(key: any(named: 'key')))
        .thenAnswer((invocation) async {
      values.remove(invocation.namedArguments[#key]! as String);
    });
  });

  AuthCookieJar jarFor(
    String profile, {
    void Function(String?)? onChanged,
  }) =>
      AuthCookieJar(
        storage: storage,
        profileId: () => profile,
        onSessionChanged: onChanged ?? notifications.add,
      );

  test('save/load round-trips the session pair, attributes dropped',
      () async {
    final AuthCookieJar jar = jarFor('local');
    final Cookie cookie = Cookie('studio_session', 'abc')
      ..expires = DateTime.utc(2030, 1, 1)
      ..httpOnly = true
      ..path = '/';

    await jar.saveFromResponse(
      Uri.parse('http://x/api/auth/login'),
      <Cookie>[cookie],
    );

    // Stored as the bare name=value pair under the profile-scoped key.
    expect(values['studio_session_cookie:local'], 'studio_session=abc');
    expect(notifications, <String?>['studio_session=abc']);

    final List<Cookie> loaded =
        await jar.loadForRequest(Uri.parse('http://x/api/records'));
    expect(loaded, hasLength(1));
    expect(loaded.single.name, 'studio_session');
    expect(loaded.single.value, 'abc');
    expect(loaded.single.expires, isNull);
    expect(loaded.single.httpOnly, isFalse);
  });

  test('cookies are scoped per profile — no cross-profile leakage',
      () async {
    final AuthCookieJar lan = jarFor('local');
    final AuthCookieJar tunnel = jarFor('tunnel');

    await lan.saveFromResponse(
      Uri.parse('http://localhost:8001/api/auth/login'),
      <Cookie>[Cookie('studio_session', 'lan-token')],
    );

    expect(
      await tunnel.loadForRequest(Uri.parse('https://tunnel/api/records')),
      isEmpty,
    );
    expect(
      await lan.loadForRequest(Uri.parse('http://localhost:8001/x')),
      hasLength(1),
    );

    await tunnel.saveFromResponse(
      Uri.parse('https://tunnel/api/auth/login'),
      <Cookie>[Cookie('studio_session', 'tunnel-token')],
    );
    expect(
      (await lan.loadForRequest(Uri.parse('http://localhost/x'))).single.value,
      'lan-token',
    );
    expect(
      (await tunnel.loadForRequest(Uri.parse('https://tunnel/x'))).single.value,
      'tunnel-token',
    );
  });

  test('ignores cookies that are not studio_session', () async {
    final AuthCookieJar jar = jarFor('local');
    await jar.saveFromResponse(
      Uri.parse('http://x/api/auth/login'),
      <Cookie>[Cookie('other', 'value')],
    );
    expect(values, isEmpty);
    expect(notifications, isEmpty);
  });

  test('clear() deletes the profile key and notifies null', () async {
    final AuthCookieJar jar = jarFor('local');
    await jar.saveFromResponse(
      Uri.parse('http://x/api/auth/login'),
      <Cookie>[Cookie('studio_session', 'abc')],
    );
    expect(values.containsKey('studio_session_cookie:local'), isTrue);

    await jar.clear();
    expect(values.containsKey('studio_session_cookie:local'), isFalse);
    expect(notifications, <String?>['studio_session=abc', null]);

    // notify: false stays silent.
    await jar.clear(notify: false);
    expect(notifications, hasLength(2));
  });

  test('missing stored value loads as an empty list', () async {
    final AuthCookieJar jar = jarFor('tunnel');
    expect(await jar.loadForRequest(Uri.parse('http://x/')), isEmpty);
  });
}
