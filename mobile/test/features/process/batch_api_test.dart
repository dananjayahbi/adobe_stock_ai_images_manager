import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/features/process/data/batch_api.dart';

/// Records every request the API builds (method, final path+query, decoded
/// body) and answers with canned JSON, so the tests pin the *exact* path
/// Dio sends — `platformPath` output included (same pattern as
/// `dashboard_api_test`).
class _RecordingAdapter implements HttpClientAdapter {
  final List<Uri> requests = <Uri>[];
  final List<String> methods = <String>[];
  final List<Object?> bodies = <Object?>[];

  Object? payload = <String, Object?>{};

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options.uri);
    methods.add(options.method);
    final List<int> bytes = <int>[];
    if (requestStream != null) {
      await for (final Uint8List chunk in requestStream) {
        bytes.addAll(chunk);
      }
    }
    bodies.add(bytes.isEmpty ? null : jsonDecode(utf8.decode(bytes)));
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
String _target(Uri uri) => uri.hasQuery ? '${uri.path}?${uri.query}' : uri.path;

void main() {
  late _RecordingAdapter adapter;
  late BatchApi api;

  setUp(() {
    adapter = _RecordingAdapter();
    final Dio dio = Dio()..httpClientAdapter = adapter;
    api = BatchApi(dio);
  });

  group('adobe_stock keeps the legacy top-level paths (platformPath)', () {
    test('step catalog with default limit-free path', () async {
      await api.stepCatalog('adobe_stock');
      expect(_target(adapter.requests.single), '/api/batches/steps');
      expect(adapter.methods.single, 'GET');
    });

    test('step catalog media type rides the query', () async {
      await api.stepCatalog('adobe_stock', mediaType: 'png');
      expect(
        _target(adapter.requests.single),
        '/api/batches/steps?media_type=png',
      );
    });

    test('batch list default limit is 50', () async {
      await api.batches('adobe_stock');
      expect(_target(adapter.requests.single), '/api/batches?limit=50');
    });

    test('batch list custom limit', () async {
      await api.batches('adobe_stock', limit: 7);
      expect(_target(adapter.requests.single), '/api/batches?limit=7');
    });

    test('batch detail', () async {
      await api.batchDetail('adobe_stock', 'b-42');
      expect(_target(adapter.requests.single), '/api/batches/b-42');
    });

    test('profiles list', () async {
      await api.profiles('adobe_stock', mediaType: 'raster');
      expect(
        _target(adapter.requests.single),
        '/api/step-profiles?media_type=raster',
      );
    });
  });

  group('other platforms ride the scoped prefix (02 §2 shape)', () {
    test('freepik batch endpoints', () async {
      await api.batches('freepik');
      await api.batchDetail('freepik', 'b-1');
      await api.runBatch('freepik', 'b-1');

      expect(adapter.requests.map<String>(_target).toList(), <String>[
        '/api/platforms/freepik/batches?limit=50',
        '/api/platforms/freepik/batches/b-1',
        '/api/platforms/freepik/batches/b-1/run',
      ]);
    });
  });

  group('write endpoints pin method + body', () {
    test('create batch posts name/media_type/steps/profile_id', () async {
      await api.createBatch(
        'adobe_stock',
        name: 'My run',
        mediaType: 'png',
        steps: <Map<String, Object?>>[
          <String, Object?>{'key': 'upscale', 'config': <String, Object?>{}},
          <String, Object?>{
            'key': 'metadata',
            'config': <String, Object?>{'delay_seconds': 2},
          },
        ],
        profileId: 'p-9',
      );

      expect(_target(adapter.requests.single), '/api/batches');
      expect(adapter.methods.single, 'POST');
      expect(adapter.bodies.single, <String, Object?>{
        'name': 'My run',
        'media_type': 'png',
        'steps': <Object?>[
          <String, Object?>{'key': 'upscale', 'config': <String, Object?>{}},
          <String, Object?>{
            'key': 'metadata',
            'config': <String, Object?>{'delay_seconds': 2},
          },
        ],
        'profile_id': 'p-9',
      });
    });

    test('create batch omits profile_id when absent', () async {
      await api.createBatch(
        'adobe_stock',
        name: '',
        mediaType: 'raster',
        steps: const <Map<String, Object?>>[],
      );

      final Object? body = adapter.bodies.single;
      expect(body, isA<Map<String, Object?>>());
      expect(
        (body! as Map<String, Object?>).containsKey('profile_id'),
        isFalse,
      );
      // Wizard parity: no files key unless the picker supplied them.
      expect((body as Map<String, Object?>).containsKey('files'), isFalse);
    });

    test('create batch carries files for the picker flow', () async {
      await api.createBatch(
        'adobe_stock',
        name: 'Picker run',
        mediaType: 'raster',
        steps: const <Map<String, Object?>>[],
        files: <String>['a.jpg', 'sub/b.jpg'],
      );

      expect(_target(adapter.requests.single), '/api/batches');
      expect(adapter.methods.single, 'POST');
      expect(adapter.bodies.single, <String, Object?>{
        'name': 'Picker run',
        'media_type': 'raster',
        'steps': <Object?>[],
        'files': <Object?>['a.jpg', 'sub/b.jpg'],
      });
    });

    test('queue posts to /queue with no body', () async {
      await api.queueBatch('adobe_stock', 'b-7');
      expect(_target(adapter.requests.single), '/api/batches/b-7/queue');
      expect(adapter.methods.single, 'POST');
      expect(adapter.bodies.single, isNull);
    });

    test('run posts to /run with no body', () async {
      await api.runBatch('adobe_stock', 'b-7');
      expect(_target(adapter.requests.single), '/api/batches/b-7/run');
      expect(adapter.methods.single, 'POST');
      expect(adapter.bodies.single, isNull);
    });

    test('cancel posts to /cancel with no body', () async {
      await api.cancelBatch('adobe_stock', 'b-7');
      expect(_target(adapter.requests.single), '/api/batches/b-7/cancel');
      expect(adapter.methods.single, 'POST');
      expect(adapter.bodies.single, isNull);
    });

    test('delete issues DELETE', () async {
      await api.deleteBatch('adobe_stock', 'b-7');
      expect(_target(adapter.requests.single), '/api/batches/b-7');
      expect(adapter.methods.single, 'DELETE');
    });

    test('create profile posts to step-profiles', () async {
      await api.createProfile(
        'adobe_stock',
        name: 'My recipe',
        mediaType: 'raster',
        steps: <Map<String, Object?>>[
          <String, Object?>{'key': 'ocr', 'config': <String, Object?>{}},
        ],
      );
      expect(_target(adapter.requests.single), '/api/step-profiles');
      expect(adapter.methods.single, 'POST');
      expect(adapter.bodies.single, <String, Object?>{
        'name': 'My recipe',
        'media_type': 'raster',
        'steps': <Object?>[
          <String, Object?>{'key': 'ocr', 'config': <String, Object?>{}},
        ],
      });
    });
  });
}
