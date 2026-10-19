import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';

/// App-wide handle on the promote data source (the queue runner is the
/// only consumer today).
final promoteApiProvider = Provider<PromoteApi>(
  (ref) => PromoteApi(ref.watch(dioProvider)),
);

/// Thin Dio data source for the promote endpoints — request/response
/// shapes mirror `backend/routers/promote.py` + `backend/schemas.py`
/// exactly (read-only contract copy, R3):
///
/// * `POST /api/promote/check {record_ids}` →
///   `{items: [{record_id, filename, stage, eligible, blocker, steps}],
///   missing: []}`
/// * `POST /api/promote/run {record_ids, use_semantic}` → `JobResponse`
/// * `GET  /api/jobs/{id}` → `JobResponse` (poll until not `running`)
///
/// Paths ride `platformPath` like every other client (03 §3.5); Dio's
/// CookieManager attaches the session, and `mapDioError` keeps raw
/// `DioException`s out of `data/` (03 §4).
class PromoteApi {
  PromoteApi(this._dio);

  final Dio _dio;

  /// Pre-flight: which requirements are missing per record (nothing runs).
  Future<PromoteCheckResult> check(
    String platformId,
    List<String> recordIds,
  ) async {
    final Object? json = await _post(
      platformPath(platformId, 'promote/check'),
      data: <String, Object?>{'record_ids': recordIds},
    );
    return PromoteCheckResult.fromJson(json);
  }

  /// Run the missing steps per record, then promote the ones that pass —
  /// returns the background [PromoteJob] to poll.
  Future<PromoteJob> run(
    String platformId,
    List<String> recordIds, {
    bool useSemantic = false,
  }) async {
    final Object? json = await _post(
      platformPath(platformId, 'promote/run'),
      data: <String, Object?>{
        'record_ids': recordIds,
        'use_semantic': useSemantic,
      },
    );
    return PromoteJob.fromJson(json);
  }

  /// Poll `GET /api/jobs/{id}` — job status is `running` until finish.
  Future<PromoteJob> job(String platformId, String jobId) async {
    final Object? json = await _get(
      platformPath(platformId, 'jobs/$jobId'),
    );
    return PromoteJob.fromJson(json);
  }

  Future<Object?> _get(String path) async {
    try {
      final Response<dynamic> response = await _dio.get<dynamic>(path);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  Future<Object?> _post(String path, {Object? data}) async {
    try {
      final Response<dynamic> response =
          await _dio.post<dynamic>(path, data: data);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}

/// One pre-flight step (`PromoteStepStatus`): `key/label/ok/detail`.
class PromoteStep {
  const PromoteStep({
    required this.key,
    required this.label,
    required this.ok,
    this.detail = '',
  });

  final String key;
  final String label;
  final bool ok;
  final String detail;

  factory PromoteStep.fromJson(Map<String, dynamic> json) => PromoteStep(
        key: json['key'] as String? ?? '',
        label: json['label'] as String? ?? '',
        ok: json['ok'] as bool? ?? false,
        detail: json['detail'] as String? ?? '',
      );
}

/// One record's pre-flight report (`PromoteCheckItem`).
class PromoteCheckItem {
  const PromoteCheckItem({
    required this.recordId,
    required this.filename,
    required this.stage,
    this.eligible = true,
    this.blocker,
    this.steps = const <PromoteStep>[],
  });

  final String recordId;
  final String filename;
  final String stage;

  /// False → the record must not be promoted (e.g. OCR_REJECTED).
  final bool eligible;

  /// Why promotion is refused, when [eligible] is false.
  final String? blocker;

  final List<PromoteStep> steps;

  factory PromoteCheckItem.fromJson(Map<String, dynamic> json) =>
      PromoteCheckItem(
        recordId: json['record_id'] as String? ?? '',
        filename: json['filename'] as String? ?? '',
        stage: json['stage'] as String? ?? '',
        eligible: json['eligible'] as bool? ?? true,
        blocker: json['blocker'] as String?,
        steps: ((json['steps'] as List<dynamic>? ?? <dynamic>[])
                .whereType<Map<String, dynamic>>())
            .map(PromoteStep.fromJson)
            .toList(growable: false),
      );
}

/// `PromoteCheckResponse` — `items` + ids the server could not find.
class PromoteCheckResult {
  const PromoteCheckResult({
    this.items = const <PromoteCheckItem>[],
    this.missing = const <String>[],
  });

  final List<PromoteCheckItem> items;
  final List<String> missing;

  PromoteCheckItem? itemFor(String recordId) {
    for (final PromoteCheckItem item in items) {
      if (item.recordId == recordId) {
        return item;
      }
    }
    return null;
  }

  factory PromoteCheckResult.fromJson(Object? json) {
    if (json is! Map<String, dynamic>) {
      return const PromoteCheckResult();
    }
    return PromoteCheckResult(
      items: ((json['items'] as List<dynamic>? ?? <dynamic>[])
              .whereType<Map<String, dynamic>>())
          .map(PromoteCheckItem.fromJson)
          .toList(growable: false),
      missing: (json['missing'] as List<dynamic>? ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
    );
  }
}

/// One record's line inside a job (`JobItemResponse`): `status` is one of
/// pending · running · succeeded · failed · skipped (skipped = blocked or
/// cancelled — the orchestrator's refusal path).
class PromoteJobItem {
  const PromoteJobItem({
    required this.recordId,
    required this.filename,
    required this.status,
    this.message = '',
    this.detail = '',
  });

  final String recordId;
  final String filename;
  final String status;
  final String message;
  final String detail;

  factory PromoteJobItem.fromJson(Map<String, dynamic> json) => PromoteJobItem(
        recordId: json['record_id'] as String? ?? '',
        filename: json['filename'] as String? ?? '',
        status: json['status'] as String? ?? 'pending',
        message: json['message'] as String? ?? '',
        detail: json['detail'] as String? ?? '',
      );
}

/// `JobResponse` from `promote/run` / `jobs/{id}` — status is one of
/// running · completed · failed · cancelled.
class PromoteJob {
  const PromoteJob({
    required this.id,
    required this.status,
    this.message = '',
    this.items = const <PromoteJobItem>[],
  });

  final String id;
  final String status;
  final String message;
  final List<PromoteJobItem> items;

  bool get isRunning => status == 'running';

  PromoteJobItem? itemFor(String recordId) {
    for (final PromoteJobItem item in items) {
      if (item.recordId == recordId) {
        return item;
      }
    }
    return null;
  }

  factory PromoteJob.fromJson(Object? json) {
    if (json is! Map<String, dynamic>) {
      return const PromoteJob(id: '', status: 'failed');
    }
    return PromoteJob(
      id: json['id'] as String? ?? '',
      status: json['status'] as String? ?? 'failed',
      message: json['message'] as String? ?? '',
      items: ((json['items'] as List<dynamic>? ?? <dynamic>[])
              .whereType<Map<String, dynamic>>())
          .map(PromoteJobItem.fromJson)
          .toList(growable: false),
    );
  }
}
