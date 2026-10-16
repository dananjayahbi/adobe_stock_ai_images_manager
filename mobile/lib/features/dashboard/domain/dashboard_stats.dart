/// Section load state for composed dashboards — a plain-Dart mirror of
/// Riverpod's `AsyncValue` so `domain/` stays framework-free (03 §"dependency
/// rule": nothing in `domain/` imports dio or Flutter widgets).
///
/// Each dashboard card owns one [SectionState]; one endpoint failing only
/// flips its own section to [SectionError] while the rest keep their data
/// (05 §2.4 "each card fails independently").
sealed class SectionState<T> {
  const SectionState();

  const factory SectionState.loading() = SectionLoading<T>;

  const factory SectionState.data(T value) = SectionData<T>;

  const factory SectionState.error(Object error, StackTrace stackTrace) =
      SectionError<T>;
}

/// The section has no value yet (first load or a retry in flight).
final class SectionLoading<T> extends SectionState<T> {
  const SectionLoading();
}

/// The section fetched successfully.
final class SectionData<T> extends SectionState<T> {
  const SectionData(this.value);

  /// Loaded value.
  final T value;
}

/// The section's endpoint failed; [error] is a mapped `AppException`
/// (or an unexpected failure captured with its [stackTrace]).
final class SectionError<T> extends SectionState<T> {
  const SectionError(this.error, this.stackTrace);

  /// Failure to surface through `ErrorView` + retry.
  final Object error;

  /// Stack trace captured at failure time.
  final StackTrace stackTrace;
}

/// The four dashboard reads (05 §2.4 endpoints), so retry/refresh logic can
/// target one section by name.
enum DashboardSection { stages, queues, jobs, latest }

/// `GET /api/stages/summary` — per-stage counts plus headline metrics
/// (`backend/routers/stages.py#stage_summary`).
class StagesSummary {
  const StagesSummary({
    required this.counts,
    required this.total,
    required this.ready,
    required this.rejected,
    required this.incompatible,
    this.averageScore,
  });

  /// One row per pipeline stage.
  final List<StageCount> counts;

  /// All records regardless of stage.
  final int total;

  /// Records at `PUBLISHED` (ready to upload).
  final int ready;

  /// Records at `OCR_REJECTED`.
  final int rejected;

  /// Records at `INCOMPATIBLE`.
  final int incompatible;

  /// Mean acceptance score, `null` when no record has one.
  final double? averageScore;
}

/// Stage-count row inside [StagesSummary.counts].
class StageCount {
  const StageCount({
    required this.stage,
    required this.number,
    required this.name,
    required this.count,
  });

  /// Stage key, e.g. `METADATA_READY`.
  final String stage;

  /// Pipeline step number (0-7).
  final int number;

  /// Human stage name, e.g. "Metadata & CSV".
  final String name;

  /// Records currently in this stage.
  final int count;
}

/// `GET /api/queues/summary` — pending depth per stage key
/// (`backend/routers/queues.py#queue_summary`).
class QueuesSummary {
  const QueuesSummary({required this.counts, required this.total});

  /// Stage key → pending record count (zero-filled server-side).
  final Map<String, int> counts;

  /// Sum of [counts] — the headline "queue depth".
  final int total;
}

/// `GET /api/jobs` row (`backend/schemas.py#JobResponse`).
class JobSummary {
  const JobSummary({
    required this.id,
    required this.stage,
    required this.kind,
    required this.status,
    required this.message,
    required this.progressLabel,
    required this.total,
    required this.processed,
    required this.succeeded,
    required this.failed,
    required this.skipped,
    required this.progress,
    this.finishedAt,
  });

  /// Job id (in-memory only — 404 after a server restart).
  final String id;

  /// Stage key the job runs, e.g. `metadata`.
  final String stage;

  /// Job kind, e.g. `metadata-run`.
  final String kind;

  /// `running | completed | failed | cancelled`.
  final String status;

  /// Free-form status line from the server.
  final String message;

  /// Short phase label (e.g. "Upscaling · pass 1/2").
  final String progressLabel;

  /// Records in the batch.
  final int total;

  /// Records that finished (succeeded + failed + skipped).
  final int processed;

  final int succeeded;
  final int failed;
  final int skipped;

  /// Completion fraction 0..1 (`services/jobs.py` `Job.progress`).
  final double progress;

  /// Unix seconds the job finished; `null` while running.
  final double? finishedAt;

  bool get isRunning => status == 'running';

  /// Best display name: live phase label, then kind, then stage key.
  String get displayName {
    if (progressLabel.isNotEmpty) return progressLabel;
    if (kind.isNotEmpty) return kind;
    return stage;
  }
}

/// Row of `GET /api/records?limit=8` that the Latest grid tiles show — the
/// fields the dashboard reads off `RecordResponse` (02 §3).
class LatestImage {
  const LatestImage({
    required this.id,
    required this.filename,
    required this.stage,
    this.thumbnailPath,
    this.title,
  });

  /// Record id.
  final String id;

  /// Original file name.
  final String filename;

  /// Pipeline stage key.
  final String stage;

  /// Absolute thumbnail path from the DB; [Thumbnail] takes its basename.
  final String? thumbnailPath;

  /// Generated title, when metadata exists.
  final String? title;

  bool get hasThumbnail => thumbnailPath != null && thumbnailPath!.isNotEmpty;
}

/// Composed dashboard model: one [SectionState] per endpoint, plus helpers
/// the 2×2 stat grid reads directly (05 §2.4).
class DashboardStats {
  const DashboardStats({
    required this.stages,
    required this.queues,
    required this.jobs,
    required this.latest,
  });

  /// Every section still loading — the first-paint state.
  const DashboardStats.loading()
      : stages = const SectionLoading<StagesSummary>(),
        queues = const SectionLoading<QueuesSummary>(),
        jobs = const SectionLoading<List<JobSummary>>(),
        latest = const SectionLoading<List<LatestImage>>();

  /// `GET /api/stages/summary`.
  final SectionState<StagesSummary> stages;

  /// `GET /api/queues/summary`.
  final SectionState<QueuesSummary> queues;

  /// `GET /api/jobs?limit=10`.
  final SectionState<List<JobSummary>> jobs;

  /// `GET /api/records?limit=8`.
  final SectionState<List<LatestImage>> latest;

  /// Replaces one section, leaving the other three untouched (retry path).
  DashboardStats withSection(DashboardSection section, SectionState<Object?> next) =>
      switch (section) {
        DashboardSection.stages => DashboardStats(
            stages: next as SectionState<StagesSummary>,
            queues: queues,
            jobs: jobs,
            latest: latest,
          ),
        DashboardSection.queues => DashboardStats(
            stages: stages,
            queues: next as SectionState<QueuesSummary>,
            jobs: jobs,
            latest: latest,
          ),
        DashboardSection.jobs => DashboardStats(
            stages: stages,
            queues: queues,
            jobs: next as SectionState<List<JobSummary>>,
            latest: latest,
          ),
        DashboardSection.latest => DashboardStats(
            stages: stages,
            queues: queues,
            jobs: jobs,
            latest: next as SectionState<List<LatestImage>>,
          ),
      };

  StagesSummary? get stagesValue => _valueOf(stages);

  QueuesSummary? get queuesValue => _valueOf(queues);

  List<JobSummary> get jobsList => _valueOf(jobs) ?? const <JobSummary>[];

  List<LatestImage> get latestImages =>
      _valueOf(latest) ?? const <LatestImage>[];

  /// "Records total" tile.
  int get recordsTotal => stagesValue?.total ?? 0;

  /// "Ready to publish" tile.
  int get readyCount => stagesValue?.ready ?? 0;

  /// "Queue depth" tile.
  int get queueDepth => queuesValue?.total ?? 0;

  /// "Running jobs" tile.
  int get runningJobCount =>
      jobsList.where((JobSummary job) => job.isRunning).length;

  /// The active job driving the running-job card, if any.
  JobSummary? get activeJob {
    for (final JobSummary job in jobsList) {
      if (job.isRunning) return job;
    }
    return null;
  }

  /// True when the Latest grid has loaded and found nothing to show.
  bool get latestIsEmpty =>
      latest is SectionData<List<LatestImage>> && latestImages.isEmpty;

  static T? _valueOf<T>(SectionState<T> state) =>
      switch (state) { SectionData<T>(:final value) => value, _ => null };
}
