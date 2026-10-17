import 'package:dio/dio.dart';

import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';

/// Thin Dio data source for the batch pipeline (02 §6, backend `batches.py`
/// + `step_profiles.py`).
///
/// Paths are built with `platformPath` so a platform switch flips all
/// endpoints (03 §3.5); raw JSON comes back untouched and
/// `ProcessRepositoryImpl` maps it to domain models. `DioException`s are
/// mapped here with `mapDioError` — no raw Dio error leaves `data/` (03 §4).
///
/// Endpoint list verified against `backend/routers/batches.py` (endpoint
/// function names in brackets): `GET batches/steps` [list_step_catalog],
/// `GET batches` [list_batches], `POST batches` [create_batch], `GET batches/
/// {id}` [get_batch], `POST batches/{id}/run` [run_batch], `POST batches/
/// {id}/queue` (M4 enqueue), `POST batches/{id}/cancel` [cancel_batch],
/// `DELETE batches/{id}` [delete_batch], and
/// `GET step-profiles` (step_profiles.py [list_profiles]).
class BatchApi {
  BatchApi(this._dio);

  final Dio _dio;

  /// `GET batches/steps[?media_type=…]` → `{order, steps, media_types}`.
  Future<Object?> stepCatalog(String platformId, {String? mediaType}) {
    final String query = mediaType == null
        ? ''
        : '?media_type=${Uri.encodeQueryComponent(mediaType)}';
    return _get(platformPath(platformId, 'batches/steps$query'));
  }

  /// `GET batches?limit=…` (1..200, default 50) → `{items, total}`.
  Future<Object?> batches(String platformId, {int limit = 50}) =>
      _get(platformPath(platformId, 'batches?limit=$limit'));

  /// `GET batches/{id}` → `BatchDetailResponse` = `BatchResponse` + `records`.
  Future<Object?> batchDetail(String platformId, String batchId) =>
      _get(platformPath(platformId, 'batches/$batchId'));

  /// `POST batches` → 201 `BatchResponse`. `steps` entries are `{key,
  /// config}`; an empty `profile_id` field is omitted (backend treats both
  /// absent and `""` as "no profile").
  ///
  /// `files` (M4 picker flow) carries source-folder-relative image paths
  /// (`BatchCreateRequest.files`) — the server imports them into the batch;
  /// null keeps the wizard's payload byte-for-byte.
  Future<Object?> createBatch(
    String platformId, {
    required String name,
    required String mediaType,
    required List<Map<String, Object?>> steps,
    String? profileId,
    List<String>? files,
  }) {
    final Map<String, Object?> body = <String, Object?>{
      'name': name,
      'media_type': mediaType,
      'steps': steps,
      if (profileId != null && profileId.isNotEmpty) 'profile_id': profileId,
      'files': ?files,
    };
    return _post(platformPath(platformId, 'batches'), body);
  }

  /// `POST batches/{id}/queue` → `BatchResponse` (200; 409 when running /
  /// queued, no images, or no steps — enqueue semantics identical to
  /// `/run`).
  Future<Object?> queueBatch(String platformId, String batchId) =>
      _post(platformPath(platformId, 'batches/$batchId/queue'), null);

  /// `POST batches/{id}/run` → `BatchResponse` (409 when not draft/failed/
  /// cancelled, no images, or already running).
  Future<Object?> runBatch(String platformId, String batchId) =>
      _post(platformPath(platformId, 'batches/$batchId/run'), null);

  /// `POST batches/{id}/cancel` → `BatchResponse` (409 unless running).
  Future<Object?> cancelBatch(String platformId, String batchId) =>
      _post(platformPath(platformId, 'batches/$batchId/cancel'), null);

  /// `DELETE batches/{id}` → 204 (409 while running).
  Future<void> deleteBatch(String platformId, String batchId) async {
    try {
      await _dio.delete<void>(platformPath(platformId, 'batches/$batchId'));
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  /// `GET step-profiles[?media_type=…]` → `{items, total}`.
  Future<Object?> profiles(String platformId, {String? mediaType}) {
    final String query = mediaType == null
        ? ''
        : '?media_type=${Uri.encodeQueryComponent(mediaType)}';
    return _get(platformPath(platformId, 'step-profiles$query'));
  }

  /// `POST step-profiles` → 201 `ProfileResponse`
  /// (`{name, media_type, steps}` — step_profiles.py [create_profile]).
  Future<Object?> createProfile(
    String platformId, {
    required String name,
    required String mediaType,
    required List<Map<String, Object?>> steps,
  }) => _post(platformPath(platformId, 'step-profiles'), <String, Object?>{
    'name': name,
    'media_type': mediaType,
    'steps': steps,
  });

  Future<Object?> _get(String path) async {
    try {
      final Response<Object?> response = await _dio.get<Object?>(path);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }

  Future<Object?> _post(String path, Object? body) async {
    try {
      final Response<Object?> response = await _dio.post<Object?>(
        path,
        data: body,
      );
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}
