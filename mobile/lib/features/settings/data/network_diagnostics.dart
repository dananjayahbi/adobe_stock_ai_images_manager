import 'dart:io';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/app_config.dart';
import '../../../core/network/dns_doh.dart';
import '../../../core/network/dns_fallback.dart';
import '../../../core/network/dns_resolver.dart';

/// One diagnostics probe: [ok] verdict, **full** [detail] (never truncated —
/// this screen exists precisely so failures are legible), and elapsed ms.
class DiagResult {
  const DiagResult({
    required this.name,
    required this.ok,
    required this.detail,
    required this.ms,
  });

  final String name;
  final bool ok;
  final String detail;
  final int ms;
}

typedef DiagSystemLookup = Future<List<InternetAddress>> Function(String host);

/// Raw TCP connect seam (TLS-egress check) — tests inject their own.
typedef DiagTcpConnect = Future<void> Function(
  InternetAddress address,
  int port,
  Duration timeout,
);

/// HTTP probe seam — [proxy] is `null` (honour the app's `HttpOverrides`,
/// i.e. the real path), `'DIRECT'`, or an explicit `PROXY host:port`.
typedef DiagTransport = Future<String> Function(String url, {String? proxy});

/// Layer-by-layer reachability diagnostics (07 §2, "which rung of the
/// ladder is broken?"): system resolver → per-endpoint DoH (v4/v6) → UDP →
/// full resolver chain (pins included) → relay liveness → raw TLS egress →
/// end-to-end `/health` direct vs through the relay.
///
/// Everything runs on the device, on demand, in parallel — the screen just
/// renders [runAll] verbatim so one screenshot answers "where does it stop".
class NetworkDiagnostics {
  NetworkDiagnostics({
    this.tunnelHost = 'studio.hotelgo.lk',
    this.relayPort,
    DiagSystemLookup? systemLookup,
    DohFetch? dohFetch,
    UdpDnsQuery? udpQuery,
    DiagTransport? transport,
    DiagTcpConnect? tcpConnect,
  })  : _system = systemLookup ?? InternetAddress.lookup,
        _dohFetch = dohFetch ?? DnsDoh.httpFetch,
        _udp = udpQuery ?? DnsResolver.udpQueryDefault,
        _transport = transport ?? _defaultTransport,
        _tcp = tcpConnect ?? _defaultTcp;

  /// Host under test (the tunnel the app must reach).
  final String tunnelHost;

  /// Loopback CONNECT relay port (`null` = relay not running).
  final int? relayPort;

  final DiagSystemLookup _system;
  final DohFetch _dohFetch;
  final UdpDnsQuery _udp;
  final DiagTransport _transport;
  final DiagTcpConnect _tcp;

  String get _healthUrl => '${AppConfig.tunnelBaseUrl}/health';

  /// Runs every check in parallel; never throws.
  Future<List<DiagResult>> runAll() => Future.wait(<Future<DiagResult>>[
        _check('System resolver', () async {
          final List<InternetAddress> addrs = await _system(tunnelHost);
          if (addrs.isEmpty) {
            throw SocketException("Failed host lookup: '$tunnelHost'");
          }
          return _join(addrs.map((InternetAddress a) => a.address));
        }),
        _check('DoH 1.1.1.1 (IPv4)', () => _dohCheck('https://1.1.1.1/dns-query')),
        _check(
          'DoH 2606:4700:4700::1111 (IPv6)',
          () => _dohCheck('https://[2606:4700:4700::1111]/dns-query'),
        ),
        _check('UDP 8.8.8.8:53', _udpCheck),
        _check('Full resolver chain', () async {
          final DnsResolver resolver = DnsResolver(
            systemLookup: _system,
            udpQuery: _udp,
            dohQuery: (String h) => DnsDoh.lookupIps(h, fetch: _dohFetch),
          );
          final List<InternetAddress> addrs = await resolver.lookup(tunnelHost);
          return _join(addrs.map((InternetAddress a) => a.address));
        }),
        _check('Relay (CONNECT proxy)', () async {
          final int? port = relayPort;
          if (port == null) {
            throw StateError('relay not running — HttpOverrides inactive');
          }
          return 'listening on 127.0.0.1:$port';
        }),
        _check('TLS egress 1.1.1.1:443', () async {
          await _tcp(
            InternetAddress('1.1.1.1'),
            443,
            const Duration(seconds: 3),
          );
          return 'tcp connected';
        }),
        _check(
          'Tunnel /health — direct',
          () => _transport(_healthUrl, proxy: 'DIRECT'),
        ),
        _check(
          'Tunnel /health — app path',
          () => _transport(_healthUrl), // null → real HttpOverrides routing
        ),
      ]);

  Future<DiagResult> _check(String name, Future<String> Function() body) async {
    final Stopwatch stopwatch = Stopwatch()..start();
    try {
      final String detail = await body();
      return DiagResult(
        name: name,
        ok: true,
        detail: detail,
        ms: stopwatch.elapsedMilliseconds,
      );
    } catch (e) {
      return DiagResult(
        name: name,
        ok: false,
        detail: '$e',
        ms: stopwatch.elapsedMilliseconds,
      );
    }
  }

  /// One endpoint, both record types — "server answered" is the verdict we
  /// care about (an empty-but-valid answer still proves reachability).
  Future<String> _dohCheck(String base) async {
    final List<String> lines = <String>[];
    for (final String type in DnsDoh.queryTypes) {
      final Uri url = Uri.parse(
        '$base?name=${Uri.encodeQueryComponent(tunnelHost)}&type=$type',
      );
      final String body = await _dohFetch(
        url,
        const <String, String>{'Accept': 'application/dns-json'},
      );
      final List<String> ips = DnsDoh.parseDohJson(body);
      lines.add('$type: ${ips.isEmpty ? 'no records' : _join(ips)}');
    }
    return lines.join(' · ');
  }

  Future<String> _udpCheck() async {
    final int id = Random.secure().nextInt(0x10000);
    final List<int> packet = DnsResolver.encodeQuery(tunnelHost, id);
    final List<int> response = await _udp(
      '8.8.8.8',
      packet,
      DnsResolver.perServerTimeout,
    );
    return _join(DnsResolver.parseARecords(response, id));
  }

  static String _join(Iterable<String> values) => values.join(', ');

  /// Real TCP connect + immediate teardown.
  static Future<void> _defaultTcp(
    InternetAddress address,
    int port,
    Duration timeout,
  ) async {
    final Socket socket =
        await Socket.connect(address, port, timeout: timeout);
    socket.destroy();
  }

  /// Real HTTP probe with an optional forced proxy directive.
  static Future<String> _defaultTransport(String url, {String? proxy}) async {
    final HttpClient client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 5);
    if (proxy != null) {
      client.findProxy = (Uri _) => proxy;
    }
    // proxy == null → whatever HttpOverrides injected = the app's real path.
    try {
      final Stopwatch stopwatch = Stopwatch()..start();
      final HttpClientResponse response = await client
          .getUrl(Uri.parse(url))
          .then((HttpClientRequest request) => request.close())
          .timeout(const Duration(seconds: 6));
      await response.drain<void>();
      return 'HTTP ${response.statusCode} in '
          '${stopwatch.elapsedMilliseconds} ms';
    } finally {
      client.close(force: true);
    }
  }
}

/// Built once per screen-open — [relayPort] reflects the live relay started
/// in bootstrap. Tests override with a fake service.
final diagnosticsProvider = Provider<NetworkDiagnostics>(
  (ref) => NetworkDiagnostics(relayPort: currentRelayPort()),
);
