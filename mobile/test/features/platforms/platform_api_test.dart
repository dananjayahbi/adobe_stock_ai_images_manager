import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/platforms/data/platform_api.dart';
import 'package:ai_stock_studio/features/platforms/data/platform_repository_impl.dart';
import 'package:ai_stock_studio/features/platforms/domain/platform.dart';

/// Capturing adapter: records the exact path Dio sends and answers with a
/// canned payload — pins the trailing-slash contract (02 §2) end-to-end.
class _CaptureAdapter implements HttpClientAdapter {
  _CaptureAdapter({required this.body, this.statusCode = 200});

  final Object? body;
  int statusCode;
  final List<String> requestedPaths = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requestedPaths.add(options.path);
    return ResponseBody.fromString(
      jsonEncode(body),
      statusCode,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

/// Catalogue JSON captured from `backend/platforms/routers.py::_serialize`
/// — `{id, name, tagline, status, route}` in registry display order.
const List<Map<String, String>> _catalogue = <Map<String, String>>[
  <String, String>{
    'id': 'adobe_stock',
    'name': 'Adobe Stock',
    'tagline':
        'The original pipeline — audit, refine, and deliver AI images.',
    'status': 'available',
    'route': '/adobe-stock',
  },
  <String, String>{
    'id': 'freepik',
    'name': 'Freepik',
    'tagline':
        'Vector-first marketplace — illustrations, PSDs, and photos, coming soon.',
    'status': 'coming_soon',
    'route': '/freepik',
  },
  <String, String>{
    'id': '123rf',
    'name': '123RF',
    'tagline': 'Budget-minded marketplace with global reach — coming soon.',
    'status': 'coming_soon',
    'route': '/123rf',
  },
];

void main() {
  late _CaptureAdapter adapter;
  late Dio dio;
  late PlatformRepositoryImpl repo;

  void build({Object? body, int statusCode = 200}) {
    adapter = _CaptureAdapter(body: body, statusCode: statusCode);
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8001'))
      ..httpClientAdapter = adapter;
    repo = PlatformRepositoryImpl(dio);
  }

  test('list fetch pins GET /api/platforms/ WITH the trailing slash', () async {
    build(body: _catalogue);

    final List<PlatformEntry> entries = await repo.fetchPlatforms();

    // 02 §2: the bare path only answers via a 307 the client must not rely on.
    expect(adapter.requestedPaths, <String>['/api/platforms/']);
    expect(entries, hasLength(3));
  });

  test('maps captured catalogue JSON onto domain PlatformEntry', () async {
    build(body: _catalogue);

    final List<PlatformEntry> entries = await repo.fetchPlatforms();

    expect(entries[0].id, 'adobe_stock');
    expect(entries[0].name, 'Adobe Stock');
    expect(entries[0].tagline, contains('original pipeline'));
    expect(entries[0].status, 'available');
    expect(entries[0].available, isTrue);
    expect(entries[0].route, '/adobe-stock');

    expect(entries[1].id, 'freepik');
    expect(entries[1].available, isFalse);
    expect(entries[1].status, 'coming_soon');
    expect(entries[2].id, '123rf');
    expect(entries[2].available, isFalse);
  });

  test('list preserves registry display order (available first)', () async {
    build(body: _catalogue);

    final List<PlatformEntry> entries = await repo.fetchPlatforms();

    expect(
      entries.map((PlatformEntry e) => e.id).toList(growable: false),
      <String>['adobe_stock', 'freepik', '123rf'],
    );
  });

  test(
      'single fetch hits GET /api/platforms/{id} without a trailing slash',
      () async {
    build(body: _catalogue[1]);

    final PlatformEntry entry = await repo.fetchPlatform('freepik');

    expect(adapter.requestedPaths, <String>['/api/platforms/freepik']);
    expect(entry.id, 'freepik');
    expect(entry.available, isFalse);
  });

  test('404 on unknown id maps to NotFoundException', () async {
    build(
      body: <String, Object>{'detail': 'Unknown platform'},
      statusCode: 404,
    );

    await expectLater(
      repo.fetchPlatform('nope'),
      throwsA(isA<NotFoundException>()),
    );
  });

  test('malformed items are skipped, not crash the picker', () async {
    build(body: <Object>[
      _catalogue[0],
      'garbage',
      42,
      _catalogue[1],
    ]);

    final List<PlatformEntry> entries = await repo.fetchPlatforms();

    expect(entries.map((PlatformEntry e) => e.id).toList(), <String>[
      'adobe_stock',
      'freepik',
    ]);
  });

  test('PlatformApi requests the trailing-slash path verbatim', () async {
    build(body: _catalogue);

    final List<Object?> items = await PlatformApi(dio).fetchPlatformList();

    expect(adapter.requestedPaths.single, '/api/platforms/');
    expect(items, hasLength(3));
  });
}
