import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

/// Signature of the platform resolver (`InternetAddress.lookup`) — seam for
/// tests.
typedef SystemLookup = Future<List<InternetAddress>> Function(String host);

/// Signature of one UDP/53 DNS exchange — seam for tests.
typedef UdpDnsQuery = Future<List<int>> Function(
  String server,
  List<int> packet,
  Duration timeout,
);

/// Hostname → IPv4 lookup with a public-resolver fallback chain.
///
/// Why this exists: some Android devices' **system** resolver fails for
/// names that Chrome resolves fine (Chrome runs its own DoH). The app must
/// not depend on a Private DNS setting the user may not know about, so the
/// lookup order is:
///
///   1. the system resolver — fastest, honours local configuration;
///   2. plain UDP/53 to a public chain (Google / Cloudflare / NextDNS) —
///      works whenever the network allows classic DNS at all.
///
/// Only A records are used (IPv4 is sufficient for the transports on this
/// stack). Successful answers are memoised for [cacheTtl] so a burst of
/// requests costs one round trip, not one per request.
class DnsResolver {
  DnsResolver({SystemLookup? systemLookup, UdpDnsQuery? udpQuery})
      : _system = systemLookup ?? InternetAddress.lookup,
        _udp = udpQuery ?? udpQueryDefault;

  final SystemLookup _system;
  final UdpDnsQuery _udp;

  /// Public resolvers tried in order when the system fails.
  static const List<String> publicResolvers = <String>[
    '8.8.8.8', // Google
    '1.1.1.1', // Cloudflare
    '94.140.14.14', // NextDNS
    '94.140.15.15',
  ];

  /// Budget per resolver server — a black-holed UDP packet must not stall
  /// the chain beyond the health-probe window.
  static const Duration perServerTimeout = Duration(seconds: 3);

  /// Answer memoisation window.
  static const Duration cacheTtl = Duration(seconds: 60);

  final Map<String, ({List<InternetAddress> addrs, DateTime at})> _cache =
      <String, ({List<InternetAddress> addrs, DateTime at})>{};

  /// Resolves [host] or throws a `SocketException`-style error carrying
  /// `Failed host lookup: '<host>'` (the exact wording HealthApi surfaces).
  ///
  /// Literal IPs and `localhost` short-circuit without any query.
  Future<List<InternetAddress>> lookup(String host) async {
    if (isLiteralHost(host)) {
      return <InternetAddress>[InternetAddress(host)];
    }
    final ({List<InternetAddress> addrs, DateTime at})? cached = _cache[host];
    if (cached != null &&
        DateTime.now().difference(cached.at) < cacheTtl &&
        cached.addrs.isNotEmpty) {
      return cached.addrs;
    }

    Object? systemFailure;
    try {
      final List<InternetAddress> addrs = await _system(host);
      if (addrs.isNotEmpty) {
        return _remember(host, addrs);
      }
      systemFailure = failedLookup(host);
    } catch (e) {
      systemFailure = e;
    }

    // Public chain — errors are absorbed per server: the system error
    // above already carries the platform's canonical wording and wins on
    // exhaustion so HealthApi's copy (and its DNS hint) stays exact.
    for (final String server in publicResolvers) {
      try {
        final List<String> ips = await _queryA(server, host);
        if (ips.isNotEmpty) {
          return _remember(
            host,
            ips.map(InternetAddress.new).toList(growable: false),
          );
        }
      } on Object {
        // Next server in the chain.
      }
    }
    throw systemFailure;
  }

  List<InternetAddress> _remember(String host, List<InternetAddress> addrs) {
    _cache[host] = (addrs: addrs, at: DateTime.now());
    return addrs;
  }

  Future<List<String>> _queryA(String server, String host) async {
    final int id = Random.secure().nextInt(0x10000);
    final List<int> packet = encodeQuery(host, id);
    final List<int> response = await _udp(server, packet, perServerTimeout);
    return parseARecords(response, id);
  }

  /// `192.168.1.4`, `::1`, `localhost`… — anything that needs no query.
  static bool isLiteralHost(String host) {
    if (host.isEmpty || host == 'localhost') {
      return true;
    }
    try {
      InternetAddress(host);
      return true;
    } on Object {
      return false;
    }
  }

  /// The error every failure path converges on — mirrors the platform's own
  /// wording so HealthApi's copy stays identical.
  static SocketException failedLookup(String host) => SocketException(
        "Failed host lookup: '$host'",
        osError: const OSError('No address associated with hostname', 7),
      );

  /// Encodes a classic IN/A question (no EDNS, no recursion desire needed —
  /// recursion is on by default in the header flags).
  static List<int> encodeQuery(String host, int id) {
    final BytesBuilder out = BytesBuilder();
    void u16(int v) => out.add(<int>[(v >> 8) & 0xff, v & 0xff]);
    u16(id);
    u16(0x0100); // QR=0, opcode=0, RD=1
    u16(1); // QDCOUNT
    u16(0); // ANCOUNT
    u16(0); // NSCOUNT
    u16(0); // ARCOUNT
    for (final String label in host.split('.')) {
      if (label.isEmpty || label.length > 63) {
        throw FormatException('Invalid host label in DNS query: $host');
      }
      out.add(<int>[label.length]);
      out.add(label.codeUnits);
    }
    out.add(const <int>[0]);
    u16(1); // QTYPE A
    u16(1); // QCLASS IN
    return out.takeBytes();
  }

  /// Parses A records out of a response, validating id and rcode. Answers
  /// are typically `CNAME → A` chains, so every record is walked; name
  /// fields honour 0xC0 compression pointers.
  static List<String> parseARecords(List<int> data, int expectId) {
    if (data.length < 12) {
      throw const SocketException('DNS: short response');
    }
    final int id = (data[0] << 8) | data[1];
    if (id != expectId) {
      throw const SocketException('DNS: response id mismatch');
    }
    final int flags = (data[2] << 8) | data[3];
    final int rcode = flags & 0xf;
    if (rcode != 0) {
      throw SocketException('DNS: server failure rcode=$rcode');
    }
    final int qd = (data[4] << 8) | data[5];
    final int an = (data[6] << 8) | data[7];
    int offset = 12;
    for (int i = 0; i < qd; i++) {
      offset = _skipName(data, offset);
      offset += 4; // qtype + qclass
    }
    final List<String> ips = <String>[];
    for (int i = 0; i < an; i++) {
      offset = _skipName(data, offset);
      if (offset + 10 > data.length) {
        throw const SocketException('DNS: truncated answer');
      }
      final int type = (data[offset] << 8) | data[offset + 1];
      final int klass = (data[offset + 2] << 8) | data[offset + 3];
      final int rdLength =
          (data[offset + 8] << 8) | data[offset + 9];
      offset += 10;
      if (offset + rdLength > data.length) {
        throw const SocketException('DNS: truncated rdata');
      }
      if (type == 1 && klass == 1 && rdLength == 4) {
        ips.add('${data[offset]}.${data[offset + 1]}.'
            '${data[offset + 2]}.${data[offset + 3]}');
      }
      offset += rdLength;
    }
    return ips;
  }

  /// Advances past a (possibly compressed) domain name.
  static int _skipName(List<int> data, int start) {
    int i = start;
    while (true) {
      if (i >= data.length) {
        throw const SocketException('DNS: truncated name');
      }
      final int len = data[i];
      if (len == 0) {
        return i + 1;
      }
      if (len & 0xc0 == 0xc0) {
        return i + 2;
      }
      i += 1 + len;
    }
  }

  /// Real UDP/53 exchange — [server] is an IP literal, [packet] the encoded
  /// question; returns the first datagram with enough bytes.
  static Future<List<int>> udpQueryDefault(
    String server,
    List<int> packet,
    Duration timeout,
  ) async {
    final RawDatagramSocket socket =
        await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    try {
      socket.send(packet, InternetAddress(server), 53);
      await for (final RawSocketEvent event in socket.timeout(timeout)) {
        if (event != RawSocketEvent.read) {
          continue;
        }
        final Datagram? datagram = socket.receive();
        if (datagram == null) {
          continue;
        }
        if (datagram.address.address != server) {
          continue; // Stray packet from someone else.
        }
        if (datagram.data.length >= 12) {
          return datagram.data;
        }
      }
      throw SocketException('DNS: no response from $server');
    } finally {
      socket.close();
    }
  }
}
