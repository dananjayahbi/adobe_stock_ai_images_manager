import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/features/dashboard/data/dashboard_api.dart';

/// Records every request the API builds and answers with canned JSON, so the
/// tests pin the *final* path+query Dio sends (platformPath output included).
class _RecordingAdapter implements HttpClientAdapter {
  final List<Uri> requests = <Uri>[];

  Object? payload = <String, Object?>{};

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options.uri);
    return ResponseBody.fromString(
      jsonEncode(payload),
      200,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

/// `path?query` as the endpoint contract writes it.
String _target(Uri uri) =>
    uri.hasQuery ? '${uri.path}?${uri.query}' : uri.path;

void main() {
  late _RecordingAdapter adapter;
  late DashboardApi api;

  setUp(() {
    adapter = _RecordingAdapter();
    final Dio dio = Dio()..httpClientAdapter = adapter;
    api = DashboardApi(dio);
  });

  group('adobe_stock keeps the legacy top-level paths (platformPath)', () {
    test('stages summary', () async {
      await api.stagesSummary('adobe_stock');
      expect(_target(adapter.requests.single), '/api/stages/summary');
    });

    test('queues summary', () async {
      await api.queuesSummary('adobe_stock');
      expect(_target(adapter.requests.single), '/api/queues/summary');
    });

    test('jobs with default limit', () async {
      await api.jobs('adobe_stock');
      expect(_target(adapter.requests.single), '/api/jobs?limit=10');
    });

    test('records with default limit (no sort param — gap 12)', () async {
      await api.records('adobe_stock');
      expect(_target(adapter.requests.single), '/api/records?limit=8');
      expect(
        adapter.requests.single.queryParameters.containsKey('sort'),
        isFalse,
      );
    });

    test('leading slashes never double up', () async {
      await api.stagesSummary('/adobe_stock/');
      expect(_target(adapter.requests.single), '/api/stages/summary');
    });
  });

  group('other platforms ride the scoped prefix (02 §2 shape)', () {
    test('freepik endpoints', () async {
      await api.stagesSummary('freepik');
      await api.queuesSummary('freepik');
      await api.jobs('freepik');
      await api.records('freepik');

      expect(
        adapter.requests.map<String>(_target).toList(),
        <String>[
          '/api/platforms/freepik/stages/summary',
          '/api/platforms/freepik/queues/summary',
          '/api/platforms/freepik/jobs?limit=10',
          '/api/platforms/freepik/records?limit=8',
        ],
      );
    });
  });

  group('custom limits ride the query string', () {
    test('jobs limit', () async {
      await api.jobs('adobe_stock', limit: 3);
      expect(_target(adapter.requests.single), '/api/jobs?limit=3');
    });

    test('records limit', () async {
      await api.records('adobe_stock', limit: 5);
      expect(_target(adapter.requests.single), '/api/records?limit=5');
    });
  });
}
