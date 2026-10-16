import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/gallery/data/gallery_api.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_query.dart';

/// Records every request's final URI, method and body, and answers with
/// canned JSON (or raw bytes for the ZIP), so the tests pin the *exact*
/// path+query Dio sends — `platformPath` output and encoding included.
class _RecordingAdapter implements HttpClientAdapter {
  final List<Uri> requests = <Uri>[];
  final List<String> methods = <String>[];
  final List<Object?> bodies = <Object?>[];

  Object? payload = <String, Object?>{};
  List<int>? bytes;
  int status = 200;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options.uri);
    methods.add(options.method);
    bodies.add(options.data);
    final Map<String, List<String>> headers = <String, List<String>>{
      Headers.contentTypeHeader: <String>[Headers.jsonContentType],
    };
    final List<int>? body = bytes;
    if (body != null) {
      return ResponseBody.fromBytes(body, status, headers: headers);
    }
    return ResponseBody.fromString(jsonEncode(payload), status, headers: headers);
  }

  @override
  void close({bool force = false}) {}
}

/// `path?query` exactly as the endpoint contract writes it.
String _target(Uri uri) => uri.hasQuery ? '${uri.path}?${uri.query}' : uri.path;

/// The POST/PATCH body as Dio handed it to the adapter (already encoded by
/// the transformer in some versions, raw map in others).
Map<String, Object?>? _body(Object? data) => switch (data) {
      null => null,
      final String raw => jsonDecode(raw) as Map<String, Object?>,
      final Map<String, Object?> map => map,
      final Map<Object?, Object?> map => map
          .map<String, Object?>((Object? key, Object? value) =>
              MapEntry<String, Object?>(key?.toString() ?? '', value)),
      _ => null,
    };

void main() {
  late _RecordingAdapter adapter;
  late GalleryApi api;

  setUp(() {
    adapter = _RecordingAdapter();
    final Dio dio = Dio()..httpClientAdapter = adapter;
    api = GalleryApi(dio);
  });

  group('records lens encoding (frontend-new fetchRecords parity)', () {
    test('default lens: default state CSV, group_id none, no sort', () async {
      await api.records('adobe_stock', const GalleryQuery());
      expect(
        _target(adapter.requests.single),
        '/api/records?limit=60&offset=0'
        '&state=READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED'
        '&group_id=none&stage_updated=true',
      );
      expect(adapter.requests.single.queryParameters.containsKey('sort'), isFalse);
      // The CSV travels with a literal comma (axios un-escapes %2C).
      expect(
        adapter.requests.single.queryParameters['state'],
        'READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED',
      );
    });

    test('search, used and group ride in web order with axios bytes', () async {
      await api.records(
        'adobe_stock',
        const GalleryQuery(
          search: 'red fox',
          state: 'COLLECTED',
          used: 'used',
          groupId: 'g1',
          offset: 120,
        ),
      );
      expect(
        _target(adapter.requests.single),
        '/api/records?limit=60&offset=120&search=red+fox&state=COLLECTED'
        '&used=used&group_id=g1&stage_updated=true',
      );
      expect(
        adapter.requests.single.queryParameters['search'],
        'red fox',
      );
    });

    test('used=unused and Any state (empty state omits the param)', () async {
      await api.records(
        'adobe_stock',
        const GalleryQuery(state: '', used: 'unused', offset: 60),
      );
      expect(
        _target(adapter.requests.single),
        '/api/records?limit=60&offset=60&used=unused&group_id=none'
        '&stage_updated=true',
      );
      expect(adapter.requests.single.queryParameters.containsKey('state'), isFalse);
    });

    test('stage_updated=false drops the flag; search stays encoded', () async {
      await api.records(
        'adobe_stock',
        const GalleryQuery(
          search: 'caf\u00e9 & cr\u00e8me',
          stageUpdated: false,
        ),
      );
      expect(
        _target(adapter.requests.single),
        '/api/records?limit=60&offset=0'
        '&search=caf%C3%A9+%26+cr%C3%A8me'
        '&state=READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED&group_id=none',
      );
      expect(adapter.requests.single.queryParameters.containsKey('sort'), isFalse);
    });
  });

  group('paths (platformPath)', () {
    test('adobe_stock keeps top-level paths; odd ids stay single-segment',
        () async {
      await api.record('adobe_stock', 'r1');
      await api.groups('adobe_stock');
      expect(
        adapter.requests.map<String>(_target).toList(),
        <String>['/api/records/r1', '/api/groups'],
      );
      expect(adapter.methods, <String>['GET', 'GET']);
    });

    test('other platforms ride the scoped prefix', () async {
      await api.records('freepik', const GalleryQuery(limit: 1, offset: 0));
      await api.groups('freepik');
      expect(
        adapter.requests.map<String>(_target).toList(),
        <String>[
          '/api/platforms/freepik/records?limit=1&offset=0'
          '&state=READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED'
          '&group_id=none&stage_updated=true',
          '/api/platforms/freepik/groups',
        ],
      );
    });

    test('leading/trailing slashes never double up', () async {
      await api.records('/adobe_stock/', const GalleryQuery(limit: 1));
      expect(
        _target(adapter.requests.single).startsWith('/api/records?limit=1&'),
        isTrue,
      );
      expect(_target(adapter.requests.single).contains('//'), isFalse);
    });
  });

  group('mutations (method + path + body)', () {
    test('approve without overrides sends no body', () async {
      await api.approve('adobe_stock', 'r1');
      expect(adapter.methods.single, 'POST');
      expect(_target(adapter.requests.single), '/api/records/r1/approve');
      expect(_body(adapter.bodies.single), isNull);
    });

    test('approve with overrides sends ApproveRequest keys', () async {
      await api.approve(
        'adobe_stock',
        'r1',
        overrideTitle: 'Fresh title',
        overrideDescription: 'Fresh description',
        overrideKeywords: <String>['alpha', 'beta'],
      );
      expect(
        _body(adapter.bodies.single),
        <String, Object?>{
          'override_title': 'Fresh title',
          'override_description': 'Fresh description',
          'override_keywords': <String>['alpha', 'beta'],
        },
      );
    });

    test('setUsed mirrors UsedRequest {is_used} on PATCH', () async {
      await api.setUsed('adobe_stock', 'r1', used: true);
      expect(adapter.methods.single, 'PATCH');
      expect(_target(adapter.requests.single), '/api/records/r1/used');
      expect(_body(adapter.bodies.single), <String, Object?>{'is_used': true});
    });

    test('changeState PATCHes {state} on records/{id}/state', () async {
      await api.changeState('adobe_stock', 'r1', 'AS_ACCEPTED');
      expect(adapter.methods.single, 'PATCH');
      expect(_target(adapter.requests.single), '/api/records/r1/state');
      expect(
        _body(adapter.bodies.single),
        <String, Object?>{'state': 'AS_ACCEPTED'},
      );
    });

    test('reset-stage is a bodyless POST; delete is a DELETE', () async {
      await api.resetStage('adobe_stock', 'r1');
      await api.deleteRecord('adobe_stock', 'r1');
      expect(adapter.methods, <String>['POST', 'DELETE']);
      expect(
        adapter.requests.map<String>(_target).toList(),
        <String>[
          '/api/records/r1/reset-stage',
          '/api/records/r1',
        ],
      );
      expect(_body(adapter.bodies.first), isNull);
    });

    test('file-zip posts {record_ids} and yields the raw bytes', () async {
      adapter.bytes = <int>[0x50, 0x4b, 0x03, 0x04];
      final List<int> bytes = await api.fileZip(
        'adobe_stock',
        <String>['a', 'b'],
      );
      expect(adapter.methods.single, 'POST');
      expect(_target(adapter.requests.single), '/api/records/file-zip');
      expect(
        _body(adapter.bodies.single),
        <String, Object?>{'record_ids': <String>['a', 'b']},
      );
      expect(bytes, <int>[0x50, 0x4b, 0x03, 0x04]);
    });
  });

  group('error mapping (no raw Dio error leaves data/)', () {
    test('500 → ServerException', () async {
      adapter.status = 500;
      adapter.payload = <String, Object?>{'detail': 'boom'};
      await expectLater(
        api.records('adobe_stock', const GalleryQuery()),
        throwsA(isA<ServerException>()),
      );
    });

    test('404 → NotFoundException', () async {
      adapter.status = 404;
      adapter.payload = <String, Object?>{'detail': 'gone'};
      await expectLater(
        api.record('adobe_stock', 'missing'),
        throwsA(isA<NotFoundException>()),
      );
    });

    test('422 → ValidationException', () async {
      adapter.status = 422;
      adapter.payload = <String, Object?>{'detail': 'bad ids'};
      await expectLater(
        api.fileZip('adobe_stock', <String>['a']),
        throwsA(isA<ValidationException>()),
      );
    });
  });
}
