import 'dart:io';

import 'package:ai_stock_studio/features/settings/data/network_diagnostics.dart';
import 'package:flutter_test/flutter_test.dart';

/// Layer-by-layer diagnostics with every transport seam faked — asserts the
/// verdicts, that failure details stay full/verbatim, and that the two
/// end-to-end rows probe with the proxy directives we expect.
void main() {
  NetworkDiagnostics build({
    int? relayPort = 42142,
    bool systemWorks = true,
    List<String?>? seenProxies,
    bool transportOk = true,
  }) {
    return NetworkDiagnostics(
      relayPort: relayPort,
      systemLookup: (String h) async {
        if (!systemWorks) {
          throw SocketException("Failed host lookup: '$h'");
        }
        return <InternetAddress>[InternetAddress('104.21.73.125')];
      },
      dohFetch: (Uri url, Map<String, String> h) async =>
          '{"Status":0,"Answer":[{"name":"x.","type":1,'
          '"TTL":300,"data":"172.67.190.8"}]}',
      // Valid empty NOERROR header (12 bytes) — "server answered, zero
      // A records": echo the query id, QR=1/RA=1, all counts zero.
      udpQuery: (String s, List<int> p, Duration t) async => <int>[
        p[0],
        p[1],
        0x81,
        0x80,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
      ],
      transport: (String url, {String? proxy}) async {
        seenProxies?.add(proxy);
        if (!transportOk) {
          throw const SocketException('connection refused (test)');
        }
        return 'HTTP 200 in 12 ms';
      },
      tcpConnect: (InternetAddress a, int p, Duration t) async {},
    );
  }

  DiagResult byName(List<DiagResult> results, String name) =>
      results.firstWhere((DiagResult r) => r.name == name);

  test('every layer reports; healthy path is all-green', () async {
    final List<DiagResult> results = await build().runAll();
    expect(results, hasLength(9));
    expect(results.every((DiagResult r) => r.ok), isTrue);
    expect(
      byName(results, 'System resolver').detail,
      contains('104.21.73.125'),
    );
    expect(byName(results, 'Relay (CONNECT proxy)').detail, contains('42142'));
    expect(byName(results, 'Tunnel /health — app path').detail,
        'HTTP 200 in 12 ms');
  });

  test('system failure keeps the full platform wording verbatim', () async {
    final List<DiagResult> results = await build(systemWorks: false).runAll();
    final DiagResult row = byName(results, 'System resolver');
    expect(row.ok, isFalse);
    expect(row.detail, contains("Failed host lookup: 'studio.hotelgo.lk'"));
    // DoH rows still answer (seam works) — only the system rung is red.
    expect(byName(results, 'DoH 1.1.1.1 (IPv4)').ok, isTrue);
  });

  test('missing relay is a red row, not a crash', () async {
    final List<DiagResult> results = await build(relayPort: null).runAll();
    final DiagResult row = byName(results, 'Relay (CONNECT proxy)');
    expect(row.ok, isFalse);
    expect(row.detail, contains('relay not running'));
  });

  test('e2e rows probe DIRECT and the real app path respectively',
      () async {
    final List<String?> seen = <String?>[];
    await build(seenProxies: seen, transportOk: false).runAll();
    expect(seen, contains('DIRECT'));
    expect(seen, contains(null)); // null = honour HttpOverrides = app path
  });

  test('transport failure lands full text on both e2e rows', () async {
    final List<DiagResult> results = await build(transportOk: false).runAll();
    expect(byName(results, 'Tunnel /health — direct').ok, isFalse);
    expect(
      byName(results, 'Tunnel /health — direct').detail,
      contains('connection refused (test)'),
    );
    expect(byName(results, 'Tunnel /health — app path').ok, isFalse);
  });
}
