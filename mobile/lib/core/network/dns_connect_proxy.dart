import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'dns_resolver.dart';

/// Loopback HTTP proxy — the app's DNS-fallback escape hatch.
///
/// The client (Dio, `Image.network`, health probes) is pointed at this proxy
/// for every non-literal host via `HttpOverrides`. The proxy re-resolves the
/// name with [DnsResolver] (system → public UDP chain) and relays bytes, so
/// TLS — and therefore SNI and certificates — stays **end-to-end**: it never
/// sees plaintext, it only picks the IP when the device's own resolver
/// cannot.
///
/// Two request forms are handled:
///
/// * `CONNECT host:port` — used by clients for `https://` targets. A
///   resolution failure answers `502` + `X-Dns-Error` before any TLS begins.
/// * absolute-form `GET http://host/path` — what clients send for plain
///   `http://` through a proxy; the request is re-sent upstream verbatim.
///
/// Origin-form requests (direct probes of the relay itself) get `405`.
class DnsConnectProxy {
  DnsConnectProxy({DnsResolver? resolver})
      : _resolver = resolver ?? DnsResolver();

  final DnsResolver _resolver;
  HttpServer? _server;

  /// Loopback port once [start]ed — consumed by the `PROXY 127.0.0.1:<port>`
  /// directive.
  int? get port => _server?.port;

  bool get isRunning => _server != null;

  Future<void> start() async {
    if (_server != null) {
      return;
    }
    _server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _server!.listen(
      _handle,
      onError: (_) {}, // One broken client must not kill the relay.
      cancelOnError: false,
    );
  }

  Future<void> stop() async {
    final HttpServer? server = _server;
    _server = null;
    if (server != null) {
      await server.close(force: true);
    }
  }

  Future<void> _handle(HttpRequest request) async {
    if (request.method == 'CONNECT') {
      await _handleConnect(request);
      return;
    }
    if (request.uri.isScheme('http') || request.uri.isScheme('https')) {
      await _handleForward(request);
      return;
    }
    request.response.statusCode = HttpStatus.methodNotAllowed;
    await request.response.close();
  }

  /// `CONNECT host:port` → resolve → raw tunnel (TLS passes through).
  Future<void> _handleConnect(HttpRequest request) async {
    final ({String host, int port})? target = _targetOf(request);
    if (target == null) {
      request.response.statusCode = HttpStatus.badRequest;
      await request.response.close();
      return;
    }
    final Socket? upstream = await _connect(target);
    if (upstream == null) {
      await _dnsFailure(request);
      return;
    }

    final Socket client =
        await request.response.detachSocket(writeHeaders: false);
    client.write('HTTP/1.1 200 Connection Established\r\n\r\n');
    await client.flush();
    _pipe(client, upstream);
    _pipe(upstream, client);
  }

  /// Absolute-form request (client already chose the proxy) → re-send
  /// upstream, then pipe the raw exchange (keep-alive included).
  Future<void> _handleForward(HttpRequest request) async {
    final Uri uri = request.uri;
    final ({String host, int port}) target = (
      host: uri.host,
      port: uri.hasPort ? uri.port : (uri.isScheme('https') ? 443 : 80),
    );
    final Socket? upstream = await _connect(target);
    if (upstream == null) {
      await _dnsFailure(request);
      return;
    }
    try {
      final List<int> body =
          await request.fold<List<int>>(<int>[], (a, d) => a..addAll(d));
      final String path = uri.path.isEmpty
          ? '/'
          : uri.path + (uri.hasQuery ? '?${uri.query}' : '');
      final BytesBuilder raw = BytesBuilder();
      raw.add(utf8.encode('${request.method} $path HTTP/1.1\r\n'));
      bool hasHost = false;
      request.headers.forEach((String name, List<String> values) {
        if (name == HttpHeaders.hostHeader) {
          hasHost = true;
        }
        for (final String value in values) {
          raw.add(utf8.encode('$name: $value\r\n'));
        }
      });
      if (!hasHost) {
        raw.add(utf8.encode(
          'Host: ${target.host}${target.port == 80 ? '' : ':${target.port}'}\r\n',
        ));
      }
      raw.add(const <int>[13, 10, 13, 10]);
      raw.add(body);
      upstream.add(raw.takeBytes());
      await upstream.flush();
    } catch (_) {
      upstream.destroy();
      try {
        await request.response.close();
      } on Object {
        // Already gone.
      }
      return;
    }
    final Socket client =
        await request.response.detachSocket(writeHeaders: false);
    _pipe(upstream, client);
    _pipe(client, upstream);
  }

  /// Resolve + TCP connect; `null` = failure (caller answers 502).
  Future<Socket?> _connect(({String host, int port}) target) async {
    try {
      final List<InternetAddress> addrs = await _resolver.lookup(target.host);
      return await Socket.connect(
        addrs.first,
        target.port,
        timeout: const Duration(seconds: 10),
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> _dnsFailure(HttpRequest request) async {
    try {
      request.response.statusCode = HttpStatus.badGateway;
      request.response.headers.set('X-Dns-Error', 'host not resolvable');
      await request.response.close();
    } on Object {
      // Response already detached/closed — nothing left to say.
    }
  }

  /// Bidirectional pipe; either side closing tears the other down.
  void _pipe(Socket from, Socket to) {
    from.listen(
      to.add,
      onDone: to.destroy,
      onError: (_) => to.destroy(),
      cancelOnError: true,
    );
  }

  /// CONNECT's request target is the `host:port` authority form — but the
  /// Dart HTTP parser may hand it back as a scheme-ish [Uri]
  /// (`Uri.parse('a.b:443')` → scheme `a.b`), so all three candidate
  /// sources are consulted: proper host, scheme/path split, `Host` header.
  ({String host, int port})? _targetOf(HttpRequest request) {
    final Uri uri = request.uri;
    String? authority;
    if (uri.host.isNotEmpty) {
      authority = uri.host.contains(':')
          ? '[${uri.host}]:${uri.hasPort ? uri.port : 443}'
          : '${uri.host}:${uri.hasPort ? uri.port : 443}';
    } else if (uri.scheme.isNotEmpty &&
        uri.path.isNotEmpty &&
        !uri.path.contains('/')) {
      // Authority-form parsed as scheme:path → `studio.hotelgo.lk:443`.
      final int port = int.tryParse(uri.path) ?? 443;
      authority = '${uri.scheme}:$port';
    } else {
      authority = request.headers.value(HttpHeaders.hostHeader);
    }
    if (authority == null || authority.isEmpty) {
      return null;
    }
    return _splitAuthority(authority);
  }

  /// `host:443` / `[::1]:443` → record; port defaults to 443 (TLS).
  static ({String host, int port})? _splitAuthority(String authority) {
    String host = authority;
    int port = 443;
    if (authority.startsWith('[')) {
      final int close = authority.indexOf(']');
      if (close <= 0) {
        return null;
      }
      host = authority.substring(1, close);
      final String rest = authority.substring(close + 1);
      if (rest.startsWith(':')) {
        port = int.tryParse(rest.substring(1)) ?? 443;
      }
    } else {
      final int colon = authority.lastIndexOf(':');
      if (colon > 0) {
        host = authority.substring(0, colon);
        port = int.tryParse(authority.substring(colon + 1)) ?? 443;
      }
    }
    if (host.isEmpty || port <= 0 || port > 65535) {
      return null;
    }
    return (host: host, port: port);
  }
}
