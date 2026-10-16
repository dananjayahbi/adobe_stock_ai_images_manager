import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:ai_stock_studio/core/utils/app_exception.dart';
import 'package:ai_stock_studio/features/dashboard/data/dashboard_repository_impl.dart';
import 'package:ai_stock_studio/features/dashboard/domain/dashboard_repository.dart';
import 'package:ai_stock_studio/features/dashboard/domain/dashboard_stats.dart';

class MockDio extends Mock implements Dio {}

/// Captured live from `GET /api/stages/summary` (backend/routers/stages.py)
/// against the running studio server on 2026-10-15.
const String kStagesSummaryJson = '''
{"counts":[{"stage":"COLLECTED","number":1,"name":"Collector","count":0},
{"stage":"OCR_CLEAR","number":2,"name":"OCR Detector","count":0},
{"stage":"OCR_REJECTED","number":2,"name":"OCR Detector","count":0},
{"stage":"UPSCALED","number":3,"name":"Upscale","count":0},
{"stage":"REFINED","number":4,"name":"Image Refiner","count":11},
{"stage":"COMPATIBLE","number":5,"name":"Compatibility Check","count":8},
{"stage":"INCOMPATIBLE","number":5,"name":"Compatibility Check","count":0},
{"stage":"METADATA_READY","number":6,"name":"Metadata & CSV","count":142},
{"stage":"PUBLISHED","number":7,"name":"Gallery","count":0},
{"stage":"QUARANTINED","number":0,"name":"QUARANTINED","count":0}],
"total":161,"ready":0,"rejected":0,"incompatible":0,"average_score":0.882}
''';

/// Captured live from `GET /api/queues/summary` (queues.py).
const String kQueuesSummaryJson =
    '{"counts":{"compatibility":0,"gallery":0,"metadata":0,'
    '"ocr":0,"refine":0,"upscale":0},"total":0}';

/// Realistic `GET /api/jobs?limit=10` payload — the live server returned
/// `[]` (jobs are in-memory), so rows follow `JobResponse`
/// (backend/schemas.py) + `Job.to_dict`, list endpoint without items.
const String kJobsJson = r'''
[{"id":"0f4a9c21","stage":"metadata","kind":"metadata-run","status":"running",
  "message":"","progress_label":"","total":12,"processed":3,"succeeded":3,
  "failed":0,"skipped":0,"progress":0.2841,"created_at":1760500000.5,
  "finished_at":null,"duration_seconds":41.2,
  "current_record_id":"0b91ca23-c3ed-4312-a4fc-74cd0033a240"},
 {"id":"9b31e77d","stage":"refine","kind":"refine-run","status":"completed",
  "message":"Done","progress_label":"","total":4,"processed":4,"succeeded":4,
  "failed":0,"skipped":0,"progress":1.0,"created_at":1760499000.0,
  "finished_at":1760499040.5,"duration_seconds":40.5,
  "current_record_id":null}]
''';

/// Realistic `GET /api/records?limit=8` payload — captured key set from the
/// live server (records.py `RecordResponse`), trimmed to dashboard fields on
/// the second row to prove missing fields parse defensively.
const String kRecordsJson = r'''
{"items":[
 {"id":"0b91ca23-c3ed-4312-a4fc-74cd0033a240",
  "filename":"Wire_loop_trimming_tool_2K_20261013092634.jpg",
  "original_path":"E:\\My_GitHub_Repos\\adobe_stock_ai_images_manager\\storage\\platforms\\adobe_stock\\inbox\\bff31c32fde14005b8ab99e9c1144655.jpg",
  "thumbnail_path":"E:\\My_GitHub_Repos\\adobe_stock_ai_images_manager\\storage\\platforms\\adobe_stock\\thumbnails\\thumb_bff31c32fde14005b8ab99e9c1144655.jpg",
  "status":"PASSED","width":2048,"height":2048,"file_size_bytes":255416,
  "generated_title":"Sculpting tool with wooden handle and wire loop",
  "is_used":true,"stage":"METADATA_READY","queued_stage":null,
  "created_at":"2026-10-13T13:39:06.467163",
  "updated_at":"2026-10-15T00:57:28.202677"},
 {"id":"7e2af1d0-1111-2222-3333-444555666778",
  "filename":"refined_7e2af1d0.jpg",
  "thumbnail_path":"E:\\storage\\platforms\\adobe_stock\\thumbnails\\thumb_7e2af1d0.jpg",
  "stage":"REFINED"}],
"total":161,"page":1,"page_size":8}
''';

void main() {
  late MockDio dio;
  late DashboardRepository repo;
  final Map<String, Object?> payloads = <String, Object?>{
    '/api/stages/summary': jsonDecode(kStagesSummaryJson),
    '/api/queues/summary': jsonDecode(kQueuesSummaryJson),
    '/api/jobs?limit=10': jsonDecode(kJobsJson),
    '/api/records?limit=8': jsonDecode(kRecordsJson),
  };

  setUp(() {
    dio = MockDio();
    repo = DashboardRepositoryImpl(dio);
    when(() => dio.get<dynamic>(any())).thenAnswer((invocation) async {
      final String path = invocation.positionalArguments.first! as String;
      return Response<dynamic>(
        requestOptions: RequestOptions(path: path),
        statusCode: 200,
        data: payloads[path] ?? <String, Object?>{},
      );
    });
  });

  group('GET paths (platformPath contract)', () {
    test('four endpoints, defaults limit=10 / limit=8, no sort', () async {
      await repo.fetchStagesSummary('adobe_stock');
      await repo.fetchQueuesSummary('adobe_stock');
      await repo.fetchJobs('adobe_stock');
      await repo.fetchLatest('adobe_stock');

      verify(() => dio.get<dynamic>('/api/stages/summary')).called(1);
      verify(() => dio.get<dynamic>('/api/queues/summary')).called(1);
      verify(() => dio.get<dynamic>('/api/jobs?limit=10')).called(1);
      verify(() => dio.get<dynamic>('/api/records?limit=8')).called(1);
    });

    test('scoped platforms prefix every path', () async {
      await repo.fetchStagesSummary('freepik');
      verify(() => dio.get<dynamic>('/api/platforms/freepik/stages/summary'))
          .called(1);
    });
  });

  group('stages summary parses the captured payload', () {
    test('headline metrics and per-stage counts', () async {
      final StagesSummary summary = await repo.fetchStagesSummary('adobe_stock');

      expect(summary.total, 161);
      expect(summary.ready, 0);
      expect(summary.rejected, 0);
      expect(summary.incompatible, 0);
      expect(summary.averageScore, closeTo(0.882, 0.0001));
      expect(summary.counts, hasLength(10));

      final StageCount metadata = summary.counts.firstWhere(
        (StageCount c) => c.stage == 'METADATA_READY',
      );
      expect(metadata.number, 6);
      expect(metadata.name, 'Metadata & CSV');
      expect(metadata.count, 142);
    });

    test('a payload without state_counts stays empty for the legacy '
        'fallback', () async {
      final StagesSummary summary =
          await repo.fetchStagesSummary('adobe_stock');

      expect(summary.stateCounts, isEmpty);
      expect(
        summary.stateCount('READY_TO_PUBLISH', fallback: summary.ready),
        summary.ready,
      );
      expect(summary.stateCount('APPROVED'), 0);
    });

    test('state_counts parses {STATE: n} and answers stateCount', () async {
      when(() => dio.get<dynamic>('/api/stages/summary')).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/api/stages/summary'),
          statusCode: 200,
          data: <String, Object?>{
            'counts': <Object?>[],
            'total': 21,
            'ready': 7, // legacy — ignored while state_counts is present
            'rejected': 9,
            'incompatible': 0,
            'state_counts': <String, Object?>{
              'COLLECTED': 1,
              'APPROVED': 2,
              'REJECTED': 0,
              'READY_TO_PUBLISH': 3,
              'PUBLISHED': 4,
              'AS_ACCEPTED': 5,
            },
          },
        ),
      );

      final StagesSummary summary =
          await repo.fetchStagesSummary('adobe_stock');

      expect(summary.stateCounts, <String, int>{
        'COLLECTED': 1,
        'APPROVED': 2,
        'REJECTED': 0,
        'READY_TO_PUBLISH': 3,
        'PUBLISHED': 4,
        'AS_ACCEPTED': 5,
      });
      expect(summary.stateCount('READY_TO_PUBLISH', fallback: summary.ready), 3);
      expect(summary.stateCount('APPROVED'), 2);
      expect(summary.stateCount('REJECTED', fallback: summary.rejected), 0);
      expect(summary.stateCount('UNKNOWN_STATE', fallback: summary.ready), 0);
    });

    test('missing total falls back to the sum of counts', () async {
      when(() => dio.get<dynamic>('/api/stages/summary')).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/api/stages/summary'),
          statusCode: 200,
          data: <String, Object?>{
            'counts': <Object?>[
              <String, Object?>{
                'stage': 'REFINED',
                'number': 4,
                'name': 'Image Refiner',
                'count': 11,
              },
              <String, Object?>{
                'stage': 'PUBLISHED',
                'number': 7,
                'name': 'Gallery',
                'count': 2,
              },
            ],
          },
        ),
      );

      final StagesSummary summary = await repo.fetchStagesSummary('adobe_stock');
      expect(summary.total, 13);
      expect(summary.averageScore, isNull);
      expect(summary.ready, 0);
    });
  });

  group('queues summary', () {
    test('captured zero-depth payload', () async {
      final QueuesSummary summary = await repo.fetchQueuesSummary('adobe_stock');
      expect(summary.total, 0);
      expect(
        summary.counts,
        <String, int>{
          'compatibility': 0,
          'gallery': 0,
          'metadata': 0,
          'ocr': 0,
          'refine': 0,
          'upscale': 0,
        },
      );
    });

    test('pending depth parses per key', () async {
      when(() => dio.get<dynamic>('/api/queues/summary')).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/api/queues/summary'),
          statusCode: 200,
          data: <String, Object?>{
            'counts': <String, Object?>{'metadata': 3, 'ocr': 1},
            'total': 4,
          },
        ),
      );

      final QueuesSummary summary = await repo.fetchQueuesSummary('adobe_stock');
      expect(summary.total, 4);
      expect(summary.counts['metadata'], 3);
      expect(summary.counts['ocr'], 1);
    });
  });

  group('jobs list', () {
    test('running + completed rows with displayName and fraction', () async {
      final List<JobSummary> jobs = await repo.fetchJobs('adobe_stock');

      expect(jobs, hasLength(2));

      final JobSummary running = jobs[0];
      expect(running.status, 'running');
      expect(running.isRunning, isTrue);
      expect(running.displayName, 'metadata-run'); // empty progress_label
      expect(running.total, 12);
      expect(running.processed, 3);
      expect(running.progress, closeTo(0.2841, 0.0001));
      expect(running.finishedAt, isNull);

      final JobSummary done = jobs[1];
      expect(done.isRunning, isFalse);
      expect(done.progress, 1.0);
      expect(done.finishedAt, closeTo(1760499040.5, 0.001));
    });

    test('legacy 0-100 progress normalises to a fraction', () async {
      when(() => dio.get<dynamic>('/api/jobs?limit=10')).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/api/jobs?limit=10'),
          statusCode: 200,
          data: <Object?>[
            <String, Object?>{
              'id': 'legacy',
              'stage': 'upscale',
              'kind': 'upscale-run',
              'status': 'running',
              'total': 10,
              'processed': 5,
              'succeeded': 5,
              'failed': 0,
              'skipped': 0,
              'progress': 50,
            },
          ],
        ),
      );

      final List<JobSummary> jobs = await repo.fetchJobs('adobe_stock');
      expect(jobs.single.progress, 0.5);
    });

    test('wrong container (not a list) throws ServerException', () async {
      when(() => dio.get<dynamic>('/api/jobs?limit=10')).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/api/jobs?limit=10'),
          statusCode: 200,
          data: <String, Object?>{'detail': 'nope'},
        ),
      );

      await expectLater(
        repo.fetchJobs('adobe_stock'),
        throwsA(isA<ServerException>()),
      );
    });
  });

  group('records → Latest images', () {
    test('captures thumbnail basename source, title and stage', () async {
      final List<LatestImage> latest = await repo.fetchLatest('adobe_stock');

      expect(latest, hasLength(2));
      expect(latest[0].id, '0b91ca23-c3ed-4312-a4fc-74cd0033a240');
      expect(latest[0].stage, 'METADATA_READY');
      expect(latest[0].title, 'Sculpting tool with wooden handle and wire loop');
      expect(latest[0].hasThumbnail, isTrue);
      expect(
        latest[0].thumbnailPath!.endsWith('thumb_bff31c32fde14005b8ab99e9c1144655.jpg'),
        isTrue,
      );
    });

    test('missing fields fall back instead of failing the card', () async {
      final LatestImage sparse = (await repo.fetchLatest('adobe_stock'))[1];
      expect(sparse.title, isNull);
      expect(sparse.hasThumbnail, isTrue);
      expect(sparse.filename, 'refined_7e2af1d0.jpg');

      // A row without thumbnail/title at all stays renderable.
      when(() => dio.get<dynamic>('/api/records?limit=8')).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/api/records?limit=8'),
          statusCode: 200,
          data: <String, Object?>{
            'items': <Object?>[<String, Object?>{'id': 'x'}],
            'total': 1,
          },
        ),
      );
      final LatestImage bare = (await repo.fetchLatest('adobe_stock')).single;
      expect(bare.id, 'x');
      expect(bare.stage, isEmpty);
      expect(bare.hasThumbnail, isFalse);
      expect(bare.title, isNull);
    });
  });

  group('transport mapping (03 §4)', () {
    test('DioException surfaces as NetworkException, never DioException',
        () async {
      when(() => dio.get<dynamic>(any())).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/api/stages/summary'),
          type: DioExceptionType.connectionError,
          message: 'connection refused',
        ),
      );

      await expectLater(
        repo.fetchStagesSummary('adobe_stock'),
        throwsA(isA<NetworkException>()),
      );
    });

    test('HTML/string body for records throws ServerException', () async {
      when(() => dio.get<dynamic>('/api/records?limit=8')).thenAnswer(
        (_) async => Response<dynamic>(
          requestOptions: RequestOptions(path: '/api/records?limit=8'),
          statusCode: 200,
          data: '<html>gateway error</html>',
        ),
      );

      await expectLater(
        repo.fetchLatest('adobe_stock'),
        throwsA(isA<ServerException>()),
      );
    });
  });
}
