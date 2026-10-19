import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/process/data/process_repository_impl.dart';
import 'package:ai_stock_studio/features/process/domain/batch.dart';
import 'package:ai_stock_studio/features/process/domain/batch_step.dart';

class MockDio extends Mock implements Dio {}

/// Captured live from `GET /api/batches/{id}` (`BatchDetailResponse`,
/// backend/routers/batches.py) against the running studio server on
/// 2026-10-13 — trimmed to one record, otherwise verbatim.
const String kBatchDetailJson = r'''
{"id":"78a1d369-4690-4ffa-83ec-5308b2b91fd0","name":"Raster photos · 2026-10-13 13:38","media_type":"raster","steps":[{"key":"ocr","config":{}},{"key":"pure_white","config":{"threshold":245,"border_min":248,"protect_subject":true}},{"key":"refine","config":{"use_semantic":true}},{"key":"diversity_gate","config":{"similarity_threshold":0.85,"keep_top":1,"action":"quarantine"}},{"key":"embed_srgb","config":{"jpeg_quality":95}},{"key":"compatibility","config":{"use_semantic":true}},{"key":"metadata","config":{"delay_seconds":2}}],"profile_id":"915ac2a2-fd57-4023-8c89-bc72d77c19ae","status":"completed","step_progress":{"ocr":{"status":"completed","message":"28 ok · 1 failed","counts":{"succeeded":28,"failed":1,"skipped":0,"pending":0}},"pure_white":{"status":"completed","message":"23 ok · 6 skipped","counts":{"succeeded":23,"failed":0,"skipped":6,"pending":0}},"refine":{"status":"completed","message":"28 ok · 1 skipped","counts":{"succeeded":28,"failed":0,"skipped":1,"pending":0}},"diversity_gate":{"status":"completed","message":"28 ok · 1 skipped","counts":{"succeeded":28,"failed":0,"skipped":1,"pending":0}},"embed_srgb":{"status":"completed","message":"0 ok · 29 skipped","counts":{"succeeded":0,"failed":0,"skipped":29,"pending":0}},"compatibility":{"status":"completed","message":"8 ok · 5 failed · 16 skipped","counts":{"succeeded":8,"failed":5,"skipped":16,"pending":0}},"metadata":{"status":"completed","message":"13 ok · 16 skipped","counts":{"succeeded":13,"failed":0,"skipped":16,"pending":0}}},"error":null,"record_count":18,"created_at":"2026-10-13T13:38:39.812348","updated_at":"2026-10-13T14:02:06.870670","finished_at":"2026-10-13T14:02:06.870670","records":[{"id":"d8890c32-c393-4ad6-b090-13fbf3eb28b3","filename":"Wooden_yarn_ball_winder_2K_20261013092036.jpg","thumbnail_path":"E:\\My_GitHub_Repos\\adobe_stock_ai_images_manager\\storage\\platforms\\adobe_stock\\thumbnails\\thumb_9e8d72449c654618acf37190c5e362da.jpg","stage":"METADATA_READY","status":"PASSED","width":2048,"height":2048}]}
''';

/// `GET /api/batches?limit=50` (`BatchListResponse`) — live shape, trimmed.
const String kBatchListJson = r'''
{"items":[{"id":"b-30","name":"Cut-outs · 2026-10-14 09:11","media_type":"png",
"steps":[{"key":"upscale","config":{}}],"profile_id":null,"status":"running",
"step_progress":{"upscale":{"status":"running","message":"2 ok · 3 pending",
"counts":{"succeeded":2,"failed":0,"skipped":0,"pending":3}}},
"error":null,"record_count":5,"created_at":"2026-10-14T09:11:00.000000",
"updated_at":"2026-10-14T09:12:00.000000","finished_at":null},
{"id":"b-29","name":"Raster photos · 2026-10-13 13:38","media_type":"raster",
"steps":[],"profile_id":null,"status":"draft","step_progress":null,
"error":null,"record_count":0,"created_at":"2026-10-13T13:38:39.812348",
"updated_at":"2026-10-13T13:38:39.812348","finished_at":null}],
"total":21}
''';

/// `GET /api/batches/steps?media_type=raster` — `pipeline_defs.step_payload`
/// shape (order / steps / media_types), trimmed to three definitions.
const String kStepCatalogJson = r'''
{"order":["upscale","bg_remove","ocr","refine","compatibility","pure_white",
"diversity_gate","embed_srgb","metadata"],
"steps":[{"key":"upscale","label":"Upscale","description":"Bump the resolution.",
"media_types":["raster","png"],"default_config":{"factor":2}},
{"key":"bg_remove","label":"Remove background","description":"Cut the subject out.",
"media_types":["png"],"default_config":{}},
{"key":"ocr","label":"OCR text","description":"Read visible text.",
"media_types":["raster"],"default_config":{}}],
"media_types":{"raster":["upscale","ocr","refine","compatibility","pure_white",
"diversity_gate","embed_srgb","metadata"],
"png":["upscale","bg_remove","ocr","diversity_gate","embed_srgb","metadata"]}}
''';

/// `GET /api/step-profiles?media_type=raster` — `ProfileListResponse` shape.
const String kProfilesJson = r'''
{"items":[{"id":"pr-01","name":"Raster presets","media_type":"raster",
"steps":[{"key":"upscale","config":{"factor":2}},{"key":"ocr","config":{}}]},
{"id":"pr-02","name":"Cut-outs","media_type":"png",
"steps":[{"key":"bg_remove","config":{}}]}],
"total":2}
''';

void main() {
  late MockDio dio;
  late ProcessRepositoryImpl repo;
  final Map<String, Object?> payloads = <String, Object?>{
    '/api/batches/b-78': jsonDecode(kBatchDetailJson),
    '/api/batches?limit=50': jsonDecode(kBatchListJson),
    '/api/batches/steps?media_type=raster': jsonDecode(kStepCatalogJson),
    '/api/step-profiles?media_type=raster': jsonDecode(kProfilesJson),
  };

  setUp(() {
    dio = MockDio();
    repo = ProcessRepositoryImpl(dio, 'adobe_stock');
    when(() => dio.get<Object?>(any())).thenAnswer((invocation) async {
      final String path = invocation.positionalArguments.first! as String;
      return Response<Object?>(
        requestOptions: RequestOptions(path: path),
        statusCode: 200,
        data: payloads[path] ?? <String, Object?>{},
      );
    });
    when(() => dio.post<Object?>(any(), data: any(named: 'data')))
        .thenAnswer((invocation) async {
          final String path = invocation.positionalArguments.first! as String;
          return Response<Object?>(
            requestOptions: RequestOptions(path: path),
            statusCode: 201,
            data: payloads[path] ?? <String, Object?>{},
          );
        });
    when(() => dio.delete<void>(any())).thenAnswer(
      (invocation) async => Response<void>(
        requestOptions: RequestOptions(
          path: invocation.positionalArguments.first! as String,
        ),
        statusCode: 204,
      ),
    );
  });

  test('fetchBatchDetail parses the captured BatchDetailResponse', () async {
    final BatchDetail detail = await repo.fetchBatchDetail('b-78');

    expect(detail.id, '78a1d369-4690-4ffa-83ec-5308b2b91fd0');
    expect(detail.name, startsWith('Raster photos'));
    expect(detail.mediaType, 'raster');
    expect(detail.status, 'completed');
    expect(detail.steps, hasLength(7));
    expect(detail.steps.first.key, 'ocr');
    expect(detail.profileId, '915ac2a2-fd57-4023-8c89-bc72d77c19ae');
    expect(detail.recordCount, 18);
    expect(detail.progress, 1.0); // completed → full bar
    expect(detail.stepProgress, isNotNull);
    expect(detail.stepProgress!['ocr']!.counts!['succeeded'], 28);
    expect(detail.stepProgress!['ocr']!.message, contains('ok'));
    expect(detail.finishedAt, isNotNull);

    expect(detail.records, hasLength(1));
    final BatchRecord record = detail.records.single;
    expect(record.filename, 'Wooden_yarn_ball_winder_2K_20261013092036.jpg');
    expect(record.stage, 'METADATA_READY');
    expect(record.status, 'PASSED');
    expect(record.thumbnailPath, contains('thumbnails'));
  });

  test('fetchBatches parses BatchListResponse with live statuses', () async {
    final BatchList list = await repo.fetchBatches();

    expect(list.total, 21);
    expect(list.items, hasLength(2));
    final Batch running = list.items.first;
    expect(running.id, 'b-30');
    expect(running.isRunning, isTrue);
    expect(running.mediaType, 'png');
    expect(running.stepProgress!['upscale']!.counts!['pending'], 3);
    // Derived fraction: 2 processed of 5 → 0.4 (no progress field on wire).
    expect(running.progress, closeTo(0.4, 0.0001));
    expect(list.items.last.status, 'draft');
    expect(list.items.last.progress, isNull); // draft → indeterminate
  });

  test('fetchStepCatalog parses order + labels + media filter', () async {
    final StepCatalog catalog = await repo.fetchStepCatalog(
      mediaType: 'raster',
    );

    expect(catalog.order, hasLength(9));
    expect(catalog.order.first, 'upscale');
    expect(catalog.order.last, 'metadata');
    expect(catalog.steps, hasLength(3));
    expect(catalog.labelFor('bg_remove'), 'Remove background');
    expect(catalog.labelFor('unknown_key'), 'unknown_key'); // fallback
    expect(catalog.descriptionFor('ocr'), 'Read visible text.');
    expect(
      catalog.steps
          .firstWhere((StepDefinition s) => s.key == 'upscale')
          .defaultConfig['factor'],
      2,
    );

    verify(() => dio.get<Object?>('/api/batches/steps?media_type=raster'))
        .called(1);
  });

  test('fetchProfiles parses ProfileListResponse items', () async {
    final List<StepProfile> profiles = await repo.fetchProfiles(
      mediaType: 'raster',
    );

    expect(profiles, hasLength(2));
    expect(profiles.first.id, 'pr-01');
    expect(profiles.first.name, 'Raster presets');
    expect(profiles.first.steps, hasLength(2));
    expect(profiles.first.steps.first.key, 'upscale');
    expect(profiles.first.steps.first.config['factor'], 2);
    expect(profiles.last.mediaType, 'png');
  });

  test('createBatch serialises steps to {key, config} + profile_id', () async {
    final Batch created = await repo.createBatch(
      name: 'My run',
      mediaType: 'raster',
      steps: const <BatchStep>[BatchStep(key: 'ocr')],
      profileId: 'pr-01',
    );

    expect(created.id, '');
    final VerificationResult captured = verify(
      () => dio.post<Object?>(any(), data: captureAny(named: 'data')),
    );
    final Object? body = captured.captured.single;
    expect(body, isA<Map<String, Object?>>());
    final Map<String, Object?> map = body! as Map<String, Object?>;
    expect(map['name'], 'My run');
    expect(map['media_type'], 'raster');
    expect(map['profile_id'], 'pr-01');
    expect(map['steps'], <Object?>[
      <String, Object?>{'key': 'ocr', 'config': <String, Object?>{}},
    ]);
    expect(map.containsKey('files'), isFalse); // wizard payload unchanged
  });

  test('createBatch with files passes the rel paths through', () async {
    await repo.createBatch(
      name: 'Picker run',
      mediaType: 'raster',
      steps: const <BatchStep>[BatchStep(key: 'ocr')],
      files: const <String>['a.jpg', 'sub/b.jpg'],
    );

    final VerificationResult captured = verify(
      () => dio.post<Object?>(any(), data: captureAny(named: 'data')),
    );
    final Map<String, Object?> map =
        captured.captured.single! as Map<String, Object?>;
    expect(map['files'], <Object?>['a.jpg', 'sub/b.jpg']);
  });

  test('queueBatch posts to /queue and parses the queued response', () async {
    payloads['/api/batches/b-31/queue'] = <String, Object?>{
      'id': 'b-31',
      'name': 'On deck',
      'media_type': 'raster',
      'steps': <Object?>[
        <String, Object?>{'key': 'ocr', 'config': <String, Object?>{}},
      ],
      'profile_id': null,
      'status': 'queued',
      'step_progress': null,
      'error': null,
      'record_count': 6,
      'created_at': '2026-10-17T07:00:00',
      'updated_at': '2026-10-17T08:00:00',
      'finished_at': null,
      'queued_at': '2026-10-17T08:00:00',
    };

    final Batch batch = await repo.queueBatch('b-31');

    expect(batch.status, 'queued');
    expect(batch.isQueued, isTrue);
    expect(batch.isActive, isTrue);
    expect(batch.queuedAt, DateTime(2026, 10, 17, 8));
    verify(() => dio.post<Object?>('/api/batches/b-31/queue', data: null))
        .called(1);
  });

  test(
    'runBatch posts to /run and parses the returned BatchResponse',
    () async {
      payloads['/api/batches/b-30/run'] = <String, Object?>{
        'id': 'b-30',
        'name': 'Cut-outs',
        'media_type': 'png',
        'steps': <Object?>[],
        'profile_id': null,
        'status': 'running',
        'step_progress': null,
        'error': null,
        'record_count': 5,
        'created_at': '2026-10-14T09:11:00.000000',
        'updated_at': '2026-10-14T09:12:00.000000',
        'finished_at': null,
      };

      final Batch batch = await repo.runBatch('b-30');
      expect(batch.status, 'running');
      verify(() => dio.post<Object?>('/api/batches/b-30/run', data: null))
          .called(1);
    },
  );

  test('cancelBatch posts to /cancel', () async {
    payloads['/api/batches/b-30/cancel'] = <String, Object?>{
      'id': 'b-30',
      'name': 'Cut-outs',
      'media_type': 'png',
      'steps': <Object?>[],
      'profile_id': null,
      'status': 'cancelled',
      'step_progress': null,
      'error': null,
      'record_count': 5,
      'created_at': '2026-10-14T09:11:00.000000',
      'updated_at': '2026-10-14T09:13:00.000000',
      'finished_at': null,
    };

    final Batch batch = await repo.cancelBatch('b-30');
    expect(batch.status, 'cancelled');
    verify(() => dio.post<Object?>('/api/batches/b-30/cancel', data: null))
        .called(1);
  });

  test('deleteBatch issues DELETE on the batch path', () async {
    await repo.deleteBatch('b-29');
    verify(() => dio.delete<void>('/api/batches/b-29')).called(1);
  });

  test('a wrong container is rejected as ServerException', () async {
    payloads['/api/batches/b-odd'] = <Object?>[];
    await expectLater(
      repo.fetchBatchDetail('b-odd'),
      throwsA(isA<ServerException>()),
    );
  });
}
