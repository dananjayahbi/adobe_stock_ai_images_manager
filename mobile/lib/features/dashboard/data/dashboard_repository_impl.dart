import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_factory.dart';
import '../../../core/utils/app_exception.dart';
import '../domain/dashboard_repository.dart';
import '../domain/dashboard_stats.dart';
import 'dashboard_api.dart';

/// Repository wired to the shared Dio client (cookie jar + profile base URL
/// handled by `core/network`). Widget tests override this provider to fake
/// the backend without touching Dio.
final dashboardRepositoryProvider = Provider<DashboardRepository>(
  (ref) => DashboardRepositoryImpl(ref.watch(dioProvider)),
);

/// Maps dashboard JSON to domain models (03 §"API model → domain entity").
///
/// Parsing is defensive per the M2 contract: missing *fields* fall back to
/// zero/empty/null defaults so one odd row never fails a whole card; a
/// wrong container (HTML error page, `null` body) throws [ServerException]
/// so the card renders its inline ErrorView + retry instead of fake zeros.
class DashboardRepositoryImpl implements DashboardRepository {
  DashboardRepositoryImpl(Dio dio) : _api = DashboardApi(dio);

  final DashboardApi _api;

  @override
  Future<StagesSummary> fetchStagesSummary(String platformId) async {
    final Map<String, Object?> map =
        _expectMap(await _api.stagesSummary(platformId));

    final List<StageCount> counts = <StageCount>[];
    for (final Object? row in _list(map['counts'])) {
      if (row is! Map<Object?, Object?>) continue;
      counts.add(
        StageCount(
          stage: _text(row['stage']),
          number: _int(row['number']),
          name: _text(row['name']),
          count: _int(row['count']),
        ),
      );
    }

    // `total` is mandatory server-side, but recomputing from the per-stage
    // counts keeps a partial payload honest instead of showing 0.
    final int total = map.containsKey('total')
        ? _int(map['total'])
        : counts.fold<int>(
            0,
            (int sum, StageCount c) => sum + c.count,
          );

    return StagesSummary(
      counts: counts,
      total: total,
      ready: _int(map['ready']),
      rejected: _int(map['rejected']),
      incompatible: _int(map['incompatible']),
      averageScore: _doubleOrNull(map['average_score']),
      stateCounts: _stateCounts(map['state_counts']),
    );
  }

  /// `state_counts: {STATE: n}` — non-int values become 0 so one odd key
  /// never fails the whole card.
  Map<String, int> _stateCounts(Object? raw) {
    if (raw is! Map<Object?, Object?>) {
      return const <String, int>{};
    }
    return raw.map<String, int>(
      (Object? key, Object? value) => MapEntry<String, int>(
        key?.toString() ?? '',
        value is num ? value.toInt() : 0,
      ),
    );
  }

  @override
  Future<QueuesSummary> fetchQueuesSummary(String platformId) async {
    final Map<String, Object?> map =
        _expectMap(await _api.queuesSummary(platformId));

    final Map<String, int> counts = <String, int>{};
    int total = 0;
    final Object? raw = map['counts'];
    if (raw is Map<Object?, Object?>) {
      for (final MapEntry<Object?, Object?> entry in raw.entries) {
        final int depth = _int(entry.value);
        counts[entry.key.toString()] = depth;
        total += depth;
      }
    }

    return QueuesSummary(
      counts: counts,
      // Server sends `total`; summing the map covers a payload missing it.
      total: map.containsKey('total') ? _int(map['total']) : total,
    );
  }

  @override
  Future<List<JobSummary>> fetchJobs(
    String platformId, {
    int limit = 10,
  }) async {
    final Object? json = await _api.jobs(platformId, limit: limit);
    if (json is! List<Object?>) {
      throw const ServerException(message: 'Unexpected jobs payload.');
    }

    final List<JobSummary> jobs = <JobSummary>[];
    for (final Object? row in json) {
      if (row is! Map<Object?, Object?>) continue;
      jobs.add(
        JobSummary(
          id: _text(row['id']),
          stage: _text(row['stage']),
          kind: _text(row['kind']),
          status: _text(row['status']),
          message: _text(row['message']),
          progressLabel: _text(row['progress_label']),
          total: _int(row['total']),
          processed: _int(row['processed']),
          succeeded: _int(row['succeeded']),
          failed: _int(row['failed']),
          skipped: _int(row['skipped']),
          progress: _fraction(row['progress']),
          finishedAt: _doubleOrNull(row['finished_at']),
        ),
      );
    }
    return jobs;
  }

  @override
  Future<List<LatestImage>> fetchLatest(
    String platformId, {
    int limit = 8,
  }) async {
    final Map<String, Object?> map =
        _expectMap(await _api.records(platformId, limit: limit));

    final List<LatestImage> images = <LatestImage>[];
    for (final Object? row in _list(map['items'])) {
      if (row is! Map<Object?, Object?>) continue;
      images.add(
        LatestImage(
          id: _text(row['id']),
          filename: _text(row['filename']),
          stage: _text(row['stage']),
          thumbnailPath: _textOrNull(row['thumbnail_path']),
          title: _textOrNull(row['generated_title']),
        ),
      );
    }
    return images;
  }

  Map<String, Object?> _expectMap(Object? json) {
    if (json is Map<Object?, Object?>) {
      return json.map<String, Object?>(
        (Object? key, Object? value) => MapEntry<String, Object?>(
          key?.toString() ?? '',
          value,
        ),
      );
    }
    throw const ServerException(
      message: 'The studio server returned an unexpected payload.',
    );
  }

  List<Object?> _list(Object? value) =>
      value is List<Object?> ? value : const <Object?>[];

  int _int(Object? value) => value is num ? value.toInt() : 0;

  double? _doubleOrNull(Object? value) => value is num ? value.toDouble() : null;

  String? _textOrNull(Object? value) => value is String && value.isNotEmpty
      ? value
      : null;

  String _text(Object? value) => value?.toString() ?? '';

  /// Job progress is a 0..1 fraction (`services/jobs.py#Job.progress`);
  /// tolerate a legacy 0..100 payload by normalising anything > 1.
  double _fraction(Object? value) {
    if (value is! num) return 0.0;
    double progress = value.toDouble();
    if (progress > 1.0) progress /= 100.0;
    if (progress < 0.0) return 0.0;
    return progress > 1.0 ? 1.0 : progress;
  }
}
