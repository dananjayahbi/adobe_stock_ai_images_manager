import 'dart:io';

import 'package:ai_stock_studio/features/settings/data/health_api.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DNS pre-check failure returns host-unreachable copy with the hint',
      () async {
    final HealthApi api = HealthApi(
      Dio(BaseOptions(baseUrl: 'https://studio.hotelgo.lk')),
      hostLookup: (String host) async => throw SocketException(
        "Failed host lookup: '$host'",
        osError: const OSError('No address associated with hostname', 7),
      ),
    );
    final HealthProbeResult result =
        await api.probe('https://studio.hotelgo.lk');
    expect(result.ok, isFalse);
    expect(result.error, contains('Host unreachable.'));
    expect(result.error, contains('Failed host lookup'));
    expect(result.error, contains('Private DNS'));
  });

  test('literal hosts skip the DNS pre-check entirely', () async {
    bool lookupCalled = false;
    final HealthApi api = HealthApi(
      Dio(BaseOptions(baseUrl: 'http://127.0.0.1:9')),
      hostLookup: (String host) async {
        lookupCalled = true;
      },
    );
    final HealthProbeResult result = await api.probe('http://127.0.0.1:9');
    expect(lookupCalled, isFalse);
    expect(result.ok, isFalse); // Port 9 (discard) never listens.
  });

  test('passing pre-check falls through to the network attempt', () async {
    bool lookupCalled = false;
    final HealthApi api = HealthApi(
      Dio(BaseOptions(baseUrl: 'http://no-such-host.invalid.test:9')),
      hostLookup: (String host) async {
        lookupCalled = true;
      },
    );
    final HealthProbeResult result =
        await api.probe('http://no-such-host.invalid.test:9');
    expect(lookupCalled, isTrue);
    // The name then fails to connect for real -> generic unreachable copy,
    // no DNS hint (the pre-check already said it was fine).
    expect(result.ok, isFalse);
    expect(result.error, isNotNull);
  });
}
