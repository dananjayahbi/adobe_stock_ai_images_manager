/// Web no-op: the browser owns DNS (and typically prefers DoH — which is
/// exactly why the same tunnel URL opens fine in a phone browser while a
/// device-level resolver can fail). Nothing to relay.
Future<void> enableDnsFallback() async {}

Future<void> ensureResolves(String host) async {}

/// The browser owns DNS on web — never pre-check.
bool needsDnsCheck(String host) => false;

/// No native relay on web.
int? currentRelayPort() => null;
