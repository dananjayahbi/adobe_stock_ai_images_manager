import 'package:dio/dio.dart';

import '../../../core/utils/platform_paths.dart';
import '../../../core/utils/ui_message.dart';

/// Thin Dio data source for the four dashboard reads (02 §5).
///
/// Every path is built with `platformPath` so a platform switch flips all
/// endpoints at once (03 §3.5); raw JSON comes back untouched and
/// `DashboardRepositoryImpl` maps it to domain models. `DioException`s are
/// mapped here with `mapDioError` — no raw Dio error leaves `data/` (03 §4).
class DashboardApi {
  DashboardApi(this._dio);

  final Dio _dio;

  /// `GET /api/stages/summary` (adobe_stock) → `{counts, total, ready, …,
  /// state_counts}`.
  Future<Object?> stagesSummary(String platformId) =>
      _get(platformPath(platformId, 'stages/summary'));

  /// `GET /api/queues/summary` → `{counts: {stage: n}, total}`.
  Future<Object?> queuesSummary(String platformId) =>
      _get(platformPath(platformId, 'queues/summary'));

  /// `GET /api/jobs?limit={limit}` → `[JobResponse, …]` (limit 1..50).
  Future<Object?> jobs(String platformId, {int limit = 10}) =>
      _get(platformPath(platformId, 'jobs?limit=$limit'));

  /// `GET /api/records?limit={limit}` → `{items, total, page, page_size}`.
  /// Newest-first by server default — no `sort` param exists yet (gap 12).
  Future<Object?> records(String platformId, {int limit = 8}) =>
      _get(platformPath(platformId, 'records?limit=$limit'));

  Future<Object?> _get(String path) async {
    try {
      final Response<dynamic> response = await _dio.get<dynamic>(path);
      return response.data;
    } on DioException catch (e) {
      throw mapDioError(e);
    }
  }
}
