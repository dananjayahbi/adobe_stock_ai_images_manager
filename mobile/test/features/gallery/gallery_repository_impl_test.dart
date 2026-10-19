import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/gallery/data/gallery_repository_impl.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_group.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_page.dart';
import 'package:ai_stock_studio/features/gallery/domain/gallery_query.dart';
import 'package:ai_stock_studio/features/gallery/domain/image_record.dart';

/// Returns one canned body verbatim (JSON or an HTML error page) for every
/// request, recording the final URI so path regressions surface here too.
class _RawAdapter implements HttpClientAdapter {
  _RawAdapter(this.response, {this.status = 200, this.contentType = 'application/json'});

  final String response;
  final int status;

  /// Mislabelled JSON (default) or a true error page (`text/html`) — the
  /// transformer only decodes the former, exactly like a real client.
  final String contentType;
  final List<Uri> requests = <Uri>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options.uri);
    return ResponseBody.fromString(
      response,
      status,
      headers: <String, List<String>>{
        Headers.contentTypeHeader: <String>[contentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

/// Captured from the live backend at :8002 (page_size 2, total 142).
String _liveRecords() =>
    File('test/features/gallery/_live_records.json').readAsStringSync();

/// Captured from the live backend at :8002 (wave 2 / wave 3 folders).
String _liveGroups() =>
    File('test/features/gallery/_live_groups.json').readAsStringSync();

GalleryRepositoryImpl _repo(_RawAdapter adapter) => GalleryRepositoryImpl(
      Dio()..httpClientAdapter = adapter,
      'adobe_stock',
    );

void main() {
  group('fetchPage — live :8002 envelope → domain page', () {
    test('parses items and total from the captured records payload', () async {
      final _RawAdapter adapter = _RawAdapter(_liveRecords());
      final GalleryPage page =
          await _repo(adapter).fetchPage(const GalleryQuery());

      expect(page.total, 142);
      expect(page.items, hasLength(2));
      expect(
        adapter.requests.single.path,
        '/api/records',
      );

      final ImageRecord first = page.items.first;
      expect(first.id, '0b91ca23-c3ed-4312-a4fc-74cd0033a240');
      expect(first.filename, 'Wire_loop_trimming_tool_2K_20261013092634.jpg');
      expect(first.status, 'PASSED');
      expect(first.stage, 'METADATA_READY');
      // Legacy payload (no `state`) → best-effort METADATA_READY mapping.
      expect(first.state, 'APPROVED');
      expect(first.flags, isEmpty);
      expect(first.isApprovable, isTrue);
      expect(first.used, isTrue);
      expect(first.thumbnailPath, contains('thumb_bff31c32'));
      expect(first.originalPath, endsWith('.jpg'));
      expect(first.generatedTitle, startsWith('Sculpting tool with wooden handle'));
      expect(first.generatedTitle, contains('wire loop'));
      expect(first.generatedDescription, contains('steel wire loop'));
      expect(first.generatedKeywords, hasLength(40));
      expect(first.acceptanceScore, closeTo(0.91, 0.001));
      expect(first.width, 2048);
      expect(first.height, 2048);
      expect(first.fileSizeBytes, 255416);
      expect(first.groupId, 'e22cdf77-3f7c-40e7-8cde-6af6282d65e7');
      expect(first.createdAt, isNotNull);
      expect(first.createdAt!.year, 2026);

      final ImageRecord second = page.items.last;
      expect(second.filename, startsWith('Acoustic_guitar_bridge_pins'));
      expect(
        second.groupId,
        'e22cdf77-3f7c-40e7-8cde-6af6282d65e7',
      );
    });

    test('missing total converges on the visible items', () async {
      final _RawAdapter adapter = _RawAdapter(
        '{"items":[{"id":"x","filename":"f.jpg","status":"PUBLISHED"}]}',
      );
      final GalleryPage page = await _repo(adapter).fetchPage(
        const GalleryQuery(),
      );

      expect(page.total, 1);
      expect(page.items.single.id, 'x');
      // Minimal row → honest null/empty defaults, never a throw.
      expect(page.items.single.thumbnailPath, isNull);
      expect(page.items.single.used, isNull);
      expect(page.items.single.generatedTitle, isNull);
      expect(page.items.single.generatedKeywords, isNull);
      expect(page.items.single.acceptanceScore, isNull);
      expect(page.items.single.createdAt, isNull);
    });

    test('a broken items container degrades to an empty page', () async {
      final _RawAdapter adapter =
          _RawAdapter('{"items":"nope","total":"???"}');
      final GalleryPage page = await _repo(adapter).fetchPage(
        const GalleryQuery(),
      );
      expect(page.items, isEmpty);
      expect(page.total, 0);
    });

    test('HTML instead of JSON → ServerException (wrong container)', () async {
      final _RawAdapter adapter = _RawAdapter(
        '<html><body>502 Bad Gateway</body></html>',
        contentType: 'text/html',
      );
      await expectLater(
        _repo(adapter).fetchPage(const GalleryQuery()),
        throwsA(isA<ServerException>()),
      );
    });

    test('null body → ServerException', () async {
      final _RawAdapter adapter = _RawAdapter('null');
      await expectLater(
        _repo(adapter).fetchPage(const GalleryQuery()),
        throwsA(isA<ServerException>()),
      );
    });

    test('legacy rows map status/stage to a state when state is missing',
        () async {
      Future<String> stateOf(String row) async {
        final _RawAdapter adapter = _RawAdapter('{"items":[$row]}');
        final GalleryPage page =
            await _repo(adapter).fetchPage(const GalleryQuery());
        return page.items.single.state;
      }

      expect(
        await stateOf('{"id":"a","filename":"a.jpg","stage":"PUBLISHED"}'),
        'PUBLISHED',
      );
      expect(
        await stateOf('{"id":"b","filename":"b.jpg","status":"READY"}'),
        'READY_TO_PUBLISH',
      );
      expect(
        await stateOf('{"id":"c","filename":"c.jpg","status":"FLAGGED"}'),
        'REJECTED',
      );
      expect(
        await stateOf(
          '{"id":"d","filename":"d.jpg","stage":"OCR_REJECTED"}',
        ),
        'REJECTED',
      );
      expect(
        await stateOf('{"id":"e","filename":"e.jpg","stage":"METADATA_READY"}'),
        'APPROVED',
      );
      expect(
        await stateOf('{"id":"f","filename":"f.jpg","status":"PASSED"}'),
        'APPROVED',
      );
      expect(
        await stateOf('{"id":"g","filename":"g.jpg"}'),
        'COLLECTED',
      );
    });

    test('state and flags parse; flags reorder to the contract order', () async {
      final _RawAdapter adapter = _RawAdapter(
        '{"items":[{"id":"r1","filename":"r.jpg","status":"PENDING",'
        '"state":"READY_TO_PUBLISH",'
        '"flags":["UPSCALED","UNUSED","REFINED"],'
        '"is_used":true}]}',
      );
      final GalleryPage page =
          await _repo(adapter).fetchPage(const GalleryQuery());
      final ImageRecord record = page.items.single;

      expect(record.state, 'READY_TO_PUBLISH');
      expect(record.isReadyToPublish, isTrue);
      expect(record.isApprovable, isFalse);
      expect(record.flags, <String>['UNUSED', 'REFINED', 'UPSCALED']);
      // Flags beat the legacy is_used field (UNUSED wins over true).
      expect(record.used, isFalse);
    });

    test('USED flag wins over is_used; unknown state passes through', () async {
      final _RawAdapter adapter = _RawAdapter(
        '{"items":[{"id":"r2","filename":"r.jpg","state":"FUTURE_STATE",'
        '"flags":["USED"],"is_used":false}]}',
      );
      final ImageRecord record =
          (await _repo(adapter).fetchPage(const GalleryQuery()))
              .items
              .single;

      expect(record.state, 'FUTURE_STATE');
      expect(record.used, isTrue);
      expect(record.isApprovable, isFalse);
    });
  });

  group('fetchById / fetchGroups', () {
    test('fetchById parses one RecordResponse and hits records/{id}', () async {
      final _RawAdapter adapter = _RawAdapter(
        '{"id":"r9","filename":"x.jpg","status":"FAILED",'
        '"thumbnail_path":"/tmp/t.jpg","is_used":false,"stage":"QUARANTINED"}',
      );
      final ImageRecord record = await _repo(adapter).fetchById('r9');

      expect(adapter.requests.single.toString(), contains('/api/records/r9'));
      expect(record.id, 'r9');
      expect(record.status, 'FAILED');
      expect(record.stage, 'QUARANTINED');
      expect(record.used, isFalse);
      expect(record.isRejected, isTrue);
    });

    test('fetchGroups parses the live folder payload', () async {
      final _RawAdapter adapter = _RawAdapter(_liveGroups());
      final List<GalleryGroup> groups = await _repo(adapter).fetchGroups();

      expect(adapter.requests.single.path, '/api/groups');
      expect(groups, hasLength(2));
      expect(groups[0].id, '90373154-ae5d-4b61-9471-c1e19f2ecb2f');
      expect(groups[0].name, 'wave 2');
      expect(groups[0].count, 30);
      expect(groups[1].name, 'wave 3');
      expect(groups[1].count, 50);
    });

    test('fetchGroups with an HTML body → ServerException', () async {
      final _RawAdapter adapter = _RawAdapter(
        '<html>oops</html>',
        contentType: 'text/html',
      );
      await expectLater(
        _repo(adapter).fetchGroups(),
        throwsA(isA<ServerException>()),
      );
    });
  });

  group('mutations ride through with api error mapping', () {
    test('delete 404 → NotFoundException', () async {
      final _RawAdapter adapter = _RawAdapter(
        '{"detail":"gone"}',
        status: 404,
      );
      await expectLater(
        _repo(adapter).deleteRecord('missing'),
        throwsA(isA<NotFoundException>()),
      );
      expect(adapter.requests.single.path, '/api/records/missing');
    });

    test('approve 500 → ServerException; used PATCH keeps its body', () async {
      final _RawAdapter adapter = _RawAdapter('{"detail":"boom"}');
      await _repo(adapter).approve('r1', overrideTitle: 'T');
      expect(adapter.requests.single.path, '/api/records/r1/approve');

      final _RawAdapter failing = _RawAdapter('{"detail":"boom"}', status: 500);
      await expectLater(
        _repo(failing).markUsed('r1', used: true),
        throwsA(isA<ServerException>()),
      );
    });

    test('reset-stage hits the endpoint without a body', () async {
      final _RawAdapter adapter = _RawAdapter('{"ok":true}');
      await _repo(adapter).resetStage('r1');
      expect(adapter.requests.single.path, '/api/records/r1/reset-stage');
    });

    test('changeState PATCHes records/{id}/state', () async {
      final _RawAdapter adapter = _RawAdapter('{"ok":true}');
      await _repo(adapter).changeState('r1', 'AS_ACCEPTED');
      expect(adapter.requests.single.path, '/api/records/r1/state');
    });
  });
}
