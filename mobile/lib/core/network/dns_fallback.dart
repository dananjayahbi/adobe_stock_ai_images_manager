/// Platform-split DNS fallback facade (07 §2 reachability):
///
/// * **Native** — starts a loopback CONNECT relay, routes name-based
///   requests through it, and exposes a resolver with a public-UDP fallback
///   chain for HealthApi's pre-check.
/// * **Web** — no-op; the browser resolves (usually via DoH).
library;

import 'dns_fallback_web.dart' if (dart.library.io) 'dns_fallback_io.dart' as impl;

/// Start the relay + `HttpOverrides` wiring. Idempotent; failures degrade to
/// direct connections.
Future<void> enableDnsFallback() => impl.enableDnsFallback();

/// Resolve [host] up front (throws `SocketException` when unresolvable) so
/// callers can report DNS failures with precise copy.
Future<void> ensureResolves(String host) => impl.ensureResolves(host);

/// Whether a host needs a DNS pre-check at all — literals/loopback never
/// do, and the web build never does (the browser resolves, usually via DoH).
bool needsDnsCheck(String host) => impl.needsDnsCheck(host);

/// Live loopback port of the CONNECT relay (`null` when not running —
/// diagnostics renders this as "relay not running").
int? currentRelayPort() => impl.currentRelayPort();
