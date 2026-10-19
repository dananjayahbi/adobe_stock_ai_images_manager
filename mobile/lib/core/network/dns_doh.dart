import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Fetch seam for tests: returns the response body or throws.
typedef DohFetch = Future<String> Function(Uri url, Map<String, String> headers);

/// DNS-over-HTTPS tier for [DnsResolver] — the fix for networks where
/// plain UDP/53 fails while HTTPS works (Chrome resolves via its own DoH
/// on exactly such networks).
///
/// **Dual-stack by design**: endpoints are IP literals on *both* families
/// (each with verified certificate SANs — Cloudflare's
/// `2606:4700:4700::1111` and Google's `2001:4860:4860::8888` are in
/// their certs), and every endpoint is asked for **A and AAAA**. A device
/// whose IPv4 egress is broken (but IPv6 fine — or the reverse) still
/// resolves. IP literals need no resolver of their own, and `HttpOverrides`
/// sends literals `DIRECT`, so there is no recursion through the CONNECT
/// relay either.
///
/// Semantics: endpoints race in parallel; the first to answer *any* query
/// type is authoritative for the host. Transport failures fall through —
/// the method **never throws**; on total failure it returns `<String>[]`
/// and the caller continues to the next tier.
class DnsDoh {
  const DnsDoh._();

  /// Budget per type-fetch — short: sibling queries race and the caller has
  /// its own UX budget.
  static const Duration perEndpointTimeout = Duration(milliseconds: 2500);

  /// IP-literal JSON endpoints: Cloudflare and Google, both families.
  /// (Hostnames would need the very resolver this tier exists to repair.)
  static const List<String> endpoints = <String>[
    'https://1.1.1.1/dns-query',
    'https://[2606:4700:4700::1111]/dns-query',
    'https://8.8.8.8/resolve',
    'https://[2001:4860:4860::8888]/resolve',
  ];

  /// Record types every endpoint is asked for.
  static const List<String> queryTypes = <String>['A', 'AAAA'];

  /// Addresses for [host] — see class docs for the never-throws contract.
  static Future<List<String>> lookupIps(
    String host, {
    DohFetch? fetch,
  }) async {
    final DohFetch doFetch = fetch ?? httpFetch;
    final Completer<List<String>> gate = Completer<List<String>>();
    int remaining = endpoints.length;
    for (final String base in endpoints) {
      unawaited(
        _queryEndpoint(doFetch, base, host).then(
          (List<String>? ips) {
            if (ips != null && !gate.isCompleted) {
              gate.complete(ips);
            } else if (--remaining == 0 && !gate.isCompleted) {
              gate.complete(const <String>[]);
            }
          },
          onError: (Object _) {
            if (--remaining == 0 && !gate.isCompleted) {
              gate.complete(const <String>[]);
            }
          },
        ),
      );
    }
    return gate.future;
  }

  /// One endpoint: A and AAAA race in parallel; the endpoint is
  /// "authoritative" when **either** type got an HTTP-level answer
  /// (partial results are merged — a type failure only drops that family).
  /// Both failed → `null` (let the next endpoint decide).
  static Future<List<String>?> _queryEndpoint(
    DohFetch fetch,
    String base,
    String host,
  ) async {
    Future<List<String>?> one(String type) async {
      try {
        return await _queryOne(fetch, base, host, type);
      } on Object {
        return null;
      }
    }

    final List<List<String>?> results =
        await Future.wait(<Future<List<String>?>>[
      one('A'),
      one('AAAA'),
    ]);
    if (results.every((List<String>? r) => r == null)) {
      return null;
    }
    // LinkedHashSet: order-preserving dedup — a CNAME chain (or a stub
    // answer) can surface the same address from both query types.
    return <String>{...?results[0], ...?results[1]}.toList();
  }

  /// One query: HTTP success → parsed answers (throws only when the body
  /// is not JSON — mapped to type-failure by the caller).
  static Future<List<String>> _queryOne(
    DohFetch fetch,
    String base,
    String host,
    String type,
  ) async {
    final Uri url = Uri.parse(
      '$base?name=${Uri.encodeQueryComponent(host)}&type=$type',
    );
    final String body = await fetch(
      url,
      const <String, String>{'Accept': 'application/dns-json'},
    ).timeout(perEndpointTimeout);
    return parseDohJson(body);
  }

  /// Parses the shared Google/Cloudflare JSON shape for A (type 1) and
  /// AAAA (type 28) records. Throws only when the body is not JSON at all;
  /// a non-zero `Status` (NXDOMAIN etc.) is an authoritative empty answer.
  static List<String> parseDohJson(String body) {
    final Object? decoded = jsonDecode(body);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('DoH: unexpected payload shape');
    }
    final Object? status = decoded['Status'];
    if (status is! int || status != 0) {
      return const <String>[];
    }
    final Object? answers = decoded['Answer'];
    if (answers is! List<Object?>) {
      return const <String>[];
    }
    final List<String> ips = <String>[];
    for (final Object? answer in answers) {
      if (answer is! Map<String, dynamic>) {
        continue;
      }
      final Object? data = answer['data'];
      if (data is! String) {
        continue;
      }
      switch (answer['type']) {
        case 1:
          if (_looksIpv4(data)) {
            ips.add(data);
          }
        case 28:
          if (_looksIpv6(data)) {
            ips.add(data);
          }
        // CNAME (5) and friends — only address records are consumed.
      }
    }
    return ips;
  }

  static bool _looksIpv4(String value) {
    final List<String> parts = value.split('.');
    if (parts.length != 4) {
      return false;
    }
    for (final String part in parts) {
      final int? n = int.tryParse(part);
      if (n == null || n < 0 || n > 255) {
        return false;
      }
    }
    return true;
  }

  static bool _looksIpv6(String value) {
    if (!value.contains(':') || value.length > 45) {
      return false;
    }
    final List<String> groups = value.split(':');
    if (groups.length < 2 || groups.length > 8) {
      return false;
    }
    for (final String group in groups) {
      if (group.isEmpty) {
        continue; // '::' compression run.
      }
      if (group.length > 4 ||
          int.tryParse(group, radix: 16) == null) {
        return false;
      }
    }
    return true;
  }

  /// Real transport: a throwaway `HttpClient` (honours `HttpOverrides`,
  /// which sends literals DIRECT) with tight budgets.
  static Future<String> httpFetch(
    Uri url,
    Map<String, String> headers,
  ) async {
    final HttpClient client = HttpClient()
      ..connectionTimeout = perEndpointTimeout;
    try {
      final HttpClientRequest request = await client.getUrl(url);
      headers.forEach(request.headers.set);
      final HttpClientResponse response = await request.close().timeout(
            perEndpointTimeout,
          );
      if (response.statusCode != HttpStatus.ok) {
        await response.drain<void>();
        throw HttpException('DoH endpoint answered ${response.statusCode}');
      }
      final String body = await response
          .transform(utf8.decoder)
          .join()
          .timeout(perEndpointTimeout);
      return body;
    } finally {
      client.close(force: true);
    }
  }
}
