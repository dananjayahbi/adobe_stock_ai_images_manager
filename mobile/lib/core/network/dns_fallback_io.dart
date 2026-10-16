import 'dart:io';

import 'dns_connect_proxy.dart';
import 'dns_resolver.dart';

/// Shared resolver — one memo across proxies and HealthApi pre-checks.
final DnsResolver _resolver = DnsResolver();

DnsConnectProxy? _proxy;

/// Starts the loopback CONNECT relay and routes every non-literal host
/// through it (native only — the web build uses the browser's own resolver,
/// which already prefers DoH).
///
/// Failures degrade to direct connections: a phone whose DNS *and* relay are
/// both broken still gets plain connectivity whenever the system resolver
/// works.
Future<void> enableDnsFallback() async {
  if (_proxy?.isRunning ?? false) {
    return;
  }
  try {
    final DnsConnectProxy proxy = DnsConnectProxy(resolver: _resolver);
    await proxy.start();
    _proxy = proxy;
    HttpOverrides.global = _ProxyHttpOverrides();
  } on Object {
    // Leave the defaults alone — direct mode.
  }
}

/// HealthApi pre-check: resolves [host] once (system → public chain) so a
/// DNS failure can be reported with full copy *before* any socket attempt.
/// Literal hosts return immediately.
Future<void> ensureResolves(String host) async {
  if (DnsResolver.isLiteralHost(host)) {
    return;
  }
  await _resolver.lookup(host);
}

/// Names need the check; literals/loopback never do.
bool needsDnsCheck(String host) => !DnsResolver.isLiteralHost(host);

/// Direct for literals/loopback; relay for names (where the system resolver
/// may be the broken part).
bool useProxyFor(String host) => !DnsResolver.isLiteralHost(host);

class _ProxyHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final HttpClient client = super.createHttpClient(context);
    client.findProxy = (Uri uri) {
      final int? port = _proxy?.port;
      if (port == null || !useProxyFor(uri.host)) {
        return 'DIRECT';
      }
      return 'PROXY 127.0.0.1:$port';
    };
    return client;
  }
}
