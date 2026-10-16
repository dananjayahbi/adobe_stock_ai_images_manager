import 'dart:io';

import 'package:ai_stock_studio/core/network/dns_resolver.dart';
import 'package:flutter_test/flutter_test.dart';

/// Echoes a valid A-record response for a captured query.
List<int> buildAResponse(
  int id,
  String host,
  List<String> ips, {
  int rcode = 0,
}) {
  final List<int> out = <int>[];
  void u16(int v) {
    out
      ..add((v >> 8) & 0xff)
      ..add(v & 0xff);
  }

  out
    ..add((id >> 8) & 0xff)
    ..add(id & 0xff);
  u16(0x8180 | rcode);
  u16(1); // QDCOUNT
  u16(ips.length); // ANCOUNT
  u16(0);
  u16(0);
  for (final String label in host.split('.')) {
    out
      ..add(label.length)
      ..addAll(label.codeUnits);
  }
  out.add(0);
  u16(1); // A
  u16(1); // IN
  for (final String ip in ips) {
    out
      ..add(0xc0)
      ..add(0x0c); // pointer to question name
    u16(1);
    u16(1);
    out.addAll(<int>[0, 0, 0, 60]); // TTL
    u16(4); // RDLENGTH
    for (final String part in ip.split('.')) {
      out.add(int.parse(part));
    }
  }
  return out;
}

/// Extracts the queried host from an encoded question (for fake servers).
String hostFromQuery(List<int> packet) {
  int i = 12;
  final List<String> labels = <String>[];
  while (packet[i] != 0) {
    final int len = packet[i];
    labels.add(String.fromCharCodes(packet.sublist(i + 1, i + 1 + len)));
    i += 1 + len;
  }
  return labels.join('.');
}

void main() {
  group('DnsResolver.isLiteralHost', () {
    test('literals and localhost need no query', () {
      expect(DnsResolver.isLiteralHost('127.0.0.1'), isTrue);
      expect(DnsResolver.isLiteralHost('::1'), isTrue);
      expect(DnsResolver.isLiteralHost('localhost'), isTrue);
      expect(DnsResolver.isLiteralHost('studio.hotelgo.lk'), isFalse);
    });

    test('lookup short-circuits literals without touching seams', () async {
      bool systemCalled = false;
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async {
          systemCalled = true;
          return <InternetAddress>[];
        },
        udpQuery: (String s, List<int> p, Duration t) async => <int>[],
      );
      final List<InternetAddress> addrs =
          await resolver.lookup('127.0.0.1');
      expect(addrs.single.address, '127.0.0.1');
      expect(systemCalled, isFalse);
    });
  });

  group('DnsResolver.lookup chain', () {
    test('system hit returns immediately, UDP never asked', () async {
      int udpCalls = 0;
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async =>
            <InternetAddress>[InternetAddress('93.184.216.34')],
        udpQuery: (String s, List<int> p, Duration t) async {
          udpCalls++;
          return <int>[];
        },
      );
      final List<InternetAddress> addrs =
          await resolver.lookup('example.com');
      expect(addrs.single.address, '93.184.216.34');
      expect(udpCalls, 0);
    });

    test('system failure falls back to the DoH-free UDP chain', () async {
      final List<String> servers = <String>[];
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async =>
            throw SocketException("Failed host lookup: '$h'"),
        dohQuery: (String h) async => const <String>[], // offline here
        udpQuery: (String server, List<int> packet, Duration t) async {
          servers.add(server);
          return buildAResponse(
            (packet[0] << 8) | packet[1],
            hostFromQuery(packet),
            <String>['104.21.73.125'],
          );
        },
      );
      final List<InternetAddress> addrs =
          await resolver.lookup('studio.hotelgo.lk');
      expect(addrs.single.address, '104.21.73.125');
      expect(servers, <String>['8.8.8.8']);
    });

    test('DoH tier resolves before UDP is ever consulted', () async {
      int udpCalls = 0;
      bool dohCalled = false;
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async =>
            throw SocketException("Failed host lookup: '$h'"),
        dohQuery: (String h) async {
          dohCalled = true;
          return <String>['104.21.73.125'];
        },
        udpQuery: (String s, List<int> p, Duration t) async {
          udpCalls++;
          return <int>[];
        },
      );
      final List<InternetAddress> addrs =
          await resolver.lookup('studio.hotelgo.lk');
      expect(dohCalled, isTrue);
      expect(udpCalls, 0);
      expect(addrs.single.address, '104.21.73.125');
    });

    test('dead first server walks the chain in order', () async {
      final List<String> servers = <String>[];
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async =>
            throw SocketException("Failed host lookup: '$h'"),
        dohQuery: (String h) async => const <String>[], // offline here
        udpQuery: (String server, List<int> packet, Duration t) async {
          servers.add(server);
          if (server == '8.8.8.8') {
            throw const SocketException('DNS: no response');
          }
          return buildAResponse(
            (packet[0] << 8) | packet[1],
            hostFromQuery(packet),
            <String>['172.67.190.8'],
          );
        },
      );
      final List<InternetAddress> addrs =
          await resolver.lookup('studio.hotelgo.lk');
      expect(addrs.single.address, '172.67.190.8');
      expect(servers, <String>['8.8.8.8', '1.1.1.1']);
    });

    test('total failure throws the platform-style lookup error', () async {
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async =>
            throw SocketException("Failed host lookup: '$h'"),
        dohQuery: (String h) async => const <String>[], // offline here
        udpQuery: (String s, List<int> p, Duration t) async =>
            throw const SocketException('DNS: unreachable'),
      );
      await expectLater(
        resolver.lookup('gone.example'),
        throwsA(
          isA<SocketException>()
              .having(
                (SocketException e) => e.toString(),
                'message',
                contains("Failed host lookup: 'gone.example'"),
              )
              // Exhaustion says the fallback tiers ran — the support signal
              // when even DoH failed.
              .having(
                (SocketException e) => e.toString(),
                'tiers',
                contains('DoH and public resolvers also failed'),
              ),
        ),
      );
    });

    test('successful answers are memoised for the TTL window', () async {
      int systemCalls = 0;
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async {
          systemCalls++;
          return <InternetAddress>[InternetAddress('10.0.0.1')];
        },
        udpQuery: (String s, List<int> p, Duration t) async => <int>[],
      );
      await resolver.lookup('cached.example');
      await resolver.lookup('cached.example');
      await resolver.lookup('cached.example');
      expect(systemCalls, 1);
    });
  });

  group('DnsResolver pinned fallback', () {
    test('zero-DNS rescue for the tunnel host, others still throw',
        () async {
      final DnsResolver resolver = DnsResolver(
        systemLookup: (String h) async =>
            throw SocketException("Failed host lookup: '$h'"),
        dohQuery: (String h) async => const <String>[],
        udpQuery: (String s, List<int> p, Duration t) async =>
            throw const SocketException('DNS: unreachable'),
      );
      final List<InternetAddress> addrs =
          await resolver.lookup('studio.hotelgo.lk');
      expect(
        addrs.map((InternetAddress a) => a.address).toList(),
        containsAll(<String>[
          '104.21.73.125',
          '2606:4700:3031::6815:497d',
        ]),
      );
      await expectLater(
        resolver.lookup('gone.example'),
        throwsA(isA<SocketException>()),
      );
    });
  });

  group('DnsResolver packet codec', () {
    test('parses A answers behind a CNAME-style chain pointer', () {
      final int id = 0x1234;
      final List<int> packet =
          buildAResponse(id, 'studio.hotelgo.lk', <String>['104.21.73.125']);
      expect(
        DnsResolver.parseARecords(packet, id),
        <String>['104.21.73.125'],
      );
    });

    test('rejects a mismatched transaction id', () {
      final List<int> packet =
          buildAResponse(0x1111, 'a.b', <String>['1.2.3.4']);
      expect(
        () => DnsResolver.parseARecords(packet, 0x2222),
        throwsA(isA<SocketException>()),
      );
    });

    test('rejects short responses', () {
      expect(
        () => DnsResolver.parseARecords(<int>[1, 2, 3], 1),
        throwsA(isA<SocketException>()),
      );
    });

    test('encodes the question section exactly once', () {
      final List<int> packet = DnsResolver.encodeQuery('a.b', 0xabcd);
      expect(packet[0], 0xab);
      expect(packet[1], 0xcd);
      // header 12 + a + b + root + type + class
      expect(packet.length, 12 + 2 + 2 + 1 + 2 + 2);
      expect(hostFromQuery(packet), 'a.b');
    });
  });
}
