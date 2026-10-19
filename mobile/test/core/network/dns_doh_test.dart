import 'dart:convert';

import 'package:ai_stock_studio/core/network/dns_doh.dart';
import 'package:flutter_test/flutter_test.dart';

/// DNS-over-HTTPS tier: shared Google/Cloudflare JSON schema, per-endpoint
/// independence, and the never-throws contract that lets the UDP chain
/// remain as the last resort.
void main() {
  String payload({int status = 0, List<Map<String, Object>>? answers}) =>
      jsonEncode(<String, Object?>{
        'Status': status,
        'Answer': ?answers,
      });

  Map<String, Object> aRecord(String ip) => <String, Object>{
        'name': 'studio.hotelgo.lk.',
        'type': 1,
        'TTL': 300,
        'data': ip,
      };

  group('DnsDoh.parseDohJson', () {
    test('parses both A answers in the shared schema', () {
      expect(
        DnsDoh.parseDohJson(payload(answers: <Map<String, Object>>[
          aRecord('104.21.73.125'),
          aRecord('172.67.190.8'),
        ])),
        <String>['104.21.73.125', '172.67.190.8'],
      );
    });

    test('keeps only type-A records (CNAME chain entries skipped)', () {
      expect(
        DnsDoh.parseDohJson(payload(answers: <Map<String, Object>>[
          <String, Object>{'name': 'x', 'type': 5, 'data': 'cdn.example.'},
          aRecord('1.2.3.4'),
        ])),
        <String>['1.2.3.4'],
      );
    });

    test('parses AAAA (type 28) records and rejects malformed ones', () {
      expect(
        DnsDoh.parseDohJson(payload(answers: <Map<String, Object>>[
          <String, Object>{
            'type': 28,
            'data': '2606:4700:3031::6815:497d',
          },
          <String, Object>{'type': 28, 'data': 'not:a:v6:!!'},
        ])),
        <String>['2606:4700:3031::6815:497d'],
      );
    });

    test('non-zero Status is an authoritative empty answer', () {
      expect(DnsDoh.parseDohJson(payload(status: 3)), <String>[]);
    });

    test('missing Answer section yields empty', () {
      expect(DnsDoh.parseDohJson(payload()), <String>[]);
    });

    test('malformed data is skipped, not fatal', () {
      expect(
        DnsDoh.parseDohJson(payload(answers: <Map<String, Object>>[
          <String, Object>{'type': 1, 'data': 'not-an-ip'},
          aRecord('9.9.9.9'),
        ])),
        <String>['9.9.9.9'],
      );
    });

    test('non-JSON body throws (endpoint failure for the caller)', () {
      expect(
        () => DnsDoh.parseDohJson('<html>captive portal</html>'),
        throwsFormatException,
      );
    });
  });

  group('DnsDoh.lookupIps', () {
    Future<String> failAll(Uri url, Map<String, String> h) async =>
        throw Exception('transport down');

    test('falls to the second endpoint when the first is down', () async {
      final List<String> hits = <String>[];
      final List<String> ips = await DnsDoh.lookupIps(
        'studio.hotelgo.lk',
        fetch: (Uri url, Map<String, String> h) async {
          hits.add(url.host);
          if (url.host == '1.1.1.1') {
            throw Exception('blocked');
          }
          return payload(answers: <Map<String, Object>>[
            aRecord('172.67.190.8'),
          ]);
        },
      );
      expect(hits, containsAll(<String>['1.1.1.1', '8.8.8.8']));
      expect(ips, <String>['172.67.190.8']);
    });

    test('never throws: total transport failure yields an empty list',
        () async {
      expect(
        await DnsDoh.lookupIps('gone.example', fetch: failAll),
        <String>[],
      );
    });

    test('endpoints are IP literals with type=A/AAAA (no chicken-and-egg)',
        () async {
      final List<Uri> seen = <Uri>[];
      await DnsDoh.lookupIps(
        'studio.hotelgo.lk',
        fetch: (Uri url, Map<String, String> h) async {
          seen.add(url);
          throw Exception('down');
        },
      );
      // 4 endpoints x (A + AAAA) — every combination was attempted.
      expect(seen, hasLength(8));
      for (final Uri url in seen) {
        final bool literal = RegExp(r'^\d+\.\d+\.\d+\.\d+$').hasMatch(url.host)
            || url.host.contains(':'); // bracketed IPv6 literal
        expect(literal, isTrue, reason: '${url.host} must be an IP literal');
        expect(DnsDoh.queryTypes, contains(url.queryParameters['type']));
        expect(url.queryParameters['name'], 'studio.hotelgo.lk');
      }
    });

    test('a captive-portal HTML body is failure, not an answer', () async {
      expect(
        await DnsDoh.lookupIps(
          'studio.hotelgo.lk',
          fetch: (Uri url, Map<String, String> h) async =>
              '<html>login</html>',
        ),
        <String>[],
      );
    });
  });
}
