import 'dashboard_stats.dart';

/// Data ports for the Adobe Dashboard (05 §2.4 / 02 §5).
///
/// Four independent reads so the presentation layer can compose them into
/// per-card load/error states: one endpoint failing must not take the page
/// down. Implementations map raw JSON to these domain models and never leak
/// `DioException` (03 §4).
abstract interface class DashboardRepository {
  /// `GET {platformPath}/stages/summary` — counts + headline metrics.
  Future<StagesSummary> fetchStagesSummary(String platformId);

  /// `GET {platformPath}/queues/summary` — pending depth per stage key.
  Future<QueuesSummary> fetchQueuesSummary(String platformId);

  /// `GET {platformPath}/jobs?limit={limit}` — newest batch jobs first.
  Future<List<JobSummary>> fetchJobs(String platformId, {int limit = 10});

  /// `GET {platformPath}/records?limit={limit}` — newest-first feed for the
  /// Latest grid. The backend has no `sort` param yet (02 §16 gap 12), so
  /// ordering is the server default.
  Future<List<LatestImage>> fetchLatest(String platformId, {int limit = 8});
}
