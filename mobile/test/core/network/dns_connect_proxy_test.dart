import 'dart:convert';
import 'dart:io';

import 'package:ai_stock_studio/core/network/dns_connect_proxy.dart';
import 'package:ai_stock_studio/core/network/dns_resolver.dart';
import 'package:flutter_test/flutter_test.dart';

/// Test-only self-signed cert (CN/SAN: relay.test, localhost, 127.0.0.1) —
/// generated once into `fixtures/`; clients bypass validation via
/// `badCertificateCallback`.
List<int> _fixture(String name) => File(
      'test/core/network/fixtures/$name',
    ).readAsBytesSync();

void main() {
  /// Loopback upstream speaking TLS — stands in for the tunneled backend.
  Future<HttpServer> secureUpstream() async {
    final SecurityContext context = SecurityContext()
      ..useCertificateChainBytes(_fixture('test_cert.pem'))
      ..usePrivateKeyBytes(_fixture('test_key.pem'));
    final HttpServer server =
        await HttpServer.bindSecure(InternetAddress.loopbackIPv4, 0, context);
    server.listen((HttpRequest request) async {
      request.response.write('relay-ok');
      await request.response.close();
    });
    return server;
  }

  test('CONNECT relay pipes an https request through the resolved address',
      () async {
    final HttpServer upstream = await secureUpstream();
    final DnsConnectProxy proxy = DnsConnectProxy(
      resolver: DnsResolver(
        // The fake system resolver always lands on our loopback upstream.
        systemLookup: (String h) async =>
            <InternetAddress>[InternetAddress('127.0.0.1')],
      ),
    );
    await proxy.start();
    addTearDown(() async {
      await proxy.stop();
      await upstream.close(force: true);
    });

    final HttpClient client = HttpClient();
    client.findProxy = (Uri uri) => 'PROXY 127.0.0.1:${proxy.port}';
    // Self-signed upstream cert — trust it for the test only.
    client.badCertificateCallback = (X509Certificate c, String h, int p) => true;
    addTearDown(() => client.close(force: true));

    final HttpClientRequest request = await client.getUrl(
      Uri.parse('https://relay.test:${upstream.port}/ping'),
    );
    final HttpClientResponse response = await request.close();
    expect(response.statusCode, HttpStatus.ok);
    expect(await response.transform(utf8.decoder).join(), 'relay-ok');
  });

  test('absolute-form plain-http request is forwarded upstream', () async {
    final HttpServer upstream =
        await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    upstream.listen((HttpRequest request) async {
      request.response.write('forward-ok:${request.uri.path}');
      await request.response.close();
    });
    final DnsConnectProxy proxy = DnsConnectProxy(
      resolver: DnsResolver(
        systemLookup: (String h) async =>
            <InternetAddress>[InternetAddress('127.0.0.1')],
      ),
    );
    await proxy.start();
    addTearDown(() async {
      await proxy.stop();
      await upstream.close(force: true);
    });

    final HttpClient client = HttpClient()
      ..findProxy = (Uri uri) => 'PROXY 127.0.0.1:${proxy.port}';
    addTearDown(() => client.close(force: true));

    final HttpClientRequest request = await client.getUrl(
      Uri.parse('http://relay.test:${upstream.port}/plain'),
    );
    final HttpClientResponse response = await request.close();
    expect(response.statusCode, HttpStatus.ok);
    expect(
      await response.transform(utf8.decoder).join(),
      'forward-ok:/plain',
    );
  });

  test('resolver failure aborts the CONNECT before any bytes flow', () async {
    final DnsConnectProxy proxy = DnsConnectProxy(
      resolver: DnsResolver(
        systemLookup: (String h) async =>
            throw SocketException("Failed host lookup: '$h'"),
        dohQuery: (String h) async => const <String>[], // offline here
        // Empty -> malformed -> every public server "answers" nothing.
        udpQuery: (String s, List<int> p, Duration t) async => <int>[],
      ),
    );
    await proxy.start();
    addTearDown(() => proxy.stop());

    final HttpClient client = HttpClient()
      ..findProxy = (Uri uri) => 'PROXY 127.0.0.1:${proxy.port}';
    addTearDown(() => client.close(force: true));

    Object? failure;
    try {
      final HttpClientRequest request =
          await client.getUrl(Uri.parse('https://gone.test:8080/'));
      final HttpClientResponse response = await request.close();
      await response.drain<void>();
    } catch (e) {
      failure = e;
    }
    expect(failure, isNotNull);
  });

  test('origin-form (direct probe) requests are rejected with 405', () async {
    final DnsConnectProxy proxy = DnsConnectProxy();
    await proxy.start();
    addTearDown(() => proxy.stop());

    final HttpClient client = HttpClient();
    addTearDown(() => client.close(force: true));

    final HttpClientRequest request =
        await client.getUrl(Uri.parse('http://127.0.0.1:${proxy.port}/'));
    final HttpClientResponse response = await request.close();
    expect(response.statusCode, HttpStatus.methodNotAllowed);
    await response.drain<void>();
  });
}
