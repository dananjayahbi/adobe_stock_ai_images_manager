import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/dashboard_repository_impl.dart';
import '../domain/dashboard_repository.dart';
import '../domain/dashboard_stats.dart';

/// Platform-scoped composed dashboard state (03 §3.5 — one family key per
/// platform id, so switching platforms rebuilds a fresh controller).
///
/// `build` fetches the four sections concurrently and captures each result
/// into its own [SectionState]: one endpoint failing lands as
/// [SectionError] inside the model instead of failing the whole provider —
/// the page shell and the healthy cards survive (05 §2.4).
final dashboardControllerProvider =
    AsyncNotifierProvider.family<DashboardController, DashboardStats, String>(
  DashboardController.new,
);

class DashboardController extends AsyncNotifier<DashboardStats> {
  DashboardController(this.platformId);

  /// Platform whose endpoints this instance composes (via `platformPath`).
  final String platformId;

  DashboardRepository get _repository => ref.read(dashboardRepositoryProvider);

  @override
  Future<DashboardStats> build() => _fetchAll();

  /// Reloads every section in one go (pull-to-refresh) — healthy cards keep
  /// showing their previous value until the swap lands.
  Future<void> refreshAll() async {
    state = AsyncData<DashboardStats>(await _fetchAll());
  }

  /// Retries a single failed section; the other three keep their state.
  Future<void> retrySection(DashboardSection section) async {
    final DashboardStats current =
        state.value ?? const DashboardStats.loading();
    state = AsyncData<DashboardStats>(
      current.withSection(section, _loadingFor(section)),
    );

    final SectionState<Object?> result = await _captureFor(section);
    final DashboardStats latest = state.value ?? current;
    state = AsyncData<DashboardStats>(latest.withSection(section, result));
  }

  /// Re-typed loading state per section — `withSection` downcasts, so the
  /// generic must match the section's model exactly.
  SectionState<Object?> _loadingFor(DashboardSection section) =>
      switch (section) {
        DashboardSection.stages =>
          const SectionState<StagesSummary>.loading(),
        DashboardSection.queues =>
          const SectionState<QueuesSummary>.loading(),
        DashboardSection.jobs =>
          const SectionState<List<JobSummary>>.loading(),
        DashboardSection.latest =>
          const SectionState<List<LatestImage>>.loading(),
      };

  Future<DashboardStats> _fetchAll() async {
    final List<SectionState<Object?>> results =
        await Future.wait<SectionState<Object?>>(
      <Future<SectionState<Object?>>>[
        _capture<StagesSummary>(
          () => _repository.fetchStagesSummary(platformId),
        ),
        _capture<QueuesSummary>(
          () => _repository.fetchQueuesSummary(platformId),
        ),
        _capture<List<JobSummary>>(() => _repository.fetchJobs(platformId)),
        _capture<List<LatestImage>>(() => _repository.fetchLatest(platformId)),
      ],
    );
    return DashboardStats(
      stages: results[0] as SectionState<StagesSummary>,
      queues: results[1] as SectionState<QueuesSummary>,
      jobs: results[2] as SectionState<List<JobSummary>>,
      latest: results[3] as SectionState<List<LatestImage>>,
    );
  }

  Future<SectionState<Object?>> _captureFor(DashboardSection section) =>
      switch (section) {
        DashboardSection.stages => _capture<StagesSummary>(
            () => _repository.fetchStagesSummary(platformId),
          ),
        DashboardSection.queues => _capture<QueuesSummary>(
            () => _repository.fetchQueuesSummary(platformId),
          ),
        DashboardSection.jobs =>
          _capture<List<JobSummary>>(() => _repository.fetchJobs(platformId)),
        DashboardSection.latest =>
          _capture<List<LatestImage>>(() => _repository.fetchLatest(platformId)),
      };

  /// Never throws: any failure becomes a per-section [SectionError] with its
  /// stack trace, so `build` always completes with a composed model.
  Future<SectionState<T>> _capture<T>(Future<T> Function() fetch) async {
    try {
      return SectionState<T>.data(await fetch());
    } catch (error, stackTrace) {
      return SectionState<T>.error(error, stackTrace);
    }
  }
}
